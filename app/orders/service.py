import json
from datetime import datetime
from hashlib import sha256
from operator import itemgetter
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User
from app.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from app.core.limits import MAX_ORDER_TOTAL_CENTS
from app.core.pagination import InvalidCursor, decode_cursor, encode_cursor
from app.orders.models import Order, OrderItem, OrderStatus, OrderStatusEvent
from app.orders.schemas import OrderCreate, OrderPage, OrderRead
from app.restaurants.models import MenuCategory, MenuItem, Restaurant

# The single source of allowed status moves, per actor. Anything not listed is a 409.
CUSTOMER_TRANSITIONS = {OrderStatus.PENDING: {OrderStatus.CANCELLED}}
ADMIN_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.ACCEPTED, OrderStatus.REJECTED},
    OrderStatus.ACCEPTED: {OrderStatus.OUT_FOR_DELIVERY, OrderStatus.CANCELLED},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
}


class OrderNotFound(NotFoundError):
    detail = 'Order not found.'


class IdempotencyKeyReused(InvalidInputError):
    detail = 'This Idempotency-Key was already used with a different request body.'


class RestaurantUnavailable(InvalidInputError):
    detail = 'Restaurant not found or not accepting orders.'


class MenuItemsUnavailable(InvalidInputError):
    detail = 'Some menu items are not available.'


class OrderTotalTooLarge(InvalidInputError):
    detail = 'Order total is too large.'


class InvalidStatusTransition(ConflictError):
    detail = 'This status change is not allowed.'


class OrderService:
    @classmethod
    async def place(
        cls, session: AsyncSession, customer: User, idempotency_key: UUID, request: OrderCreate
    ) -> tuple[OrderRead, bool]:
        """Places an order once per idempotency key; returns the order and whether it is new.

        A repeat with the same body returns the original order without re-checking the menu,
        so a retry still succeeds after items were archived or repriced.
        """
        # Same-key requests run one at a time; released at commit or rollback.
        lock_id = func.hashtextextended(f'{customer.id}:{idempotency_key}', 0)
        await session.execute(select(func.pg_advisory_xact_lock(lock_id)))

        fingerprint = cls._fingerprint(request)
        if existing := await cls._find_by_idempotency_key(session, customer.id, idempotency_key):
            if existing.idempotency_fingerprint != fingerprint:
                raise IdempotencyKeyReused
            return OrderRead.model_validate(existing), False

        restaurant = await cls._load_active_restaurant(session, request.restaurant_id)
        menu_items = await cls._load_orderable_items(session, request)
        items = [
            OrderItem(
                menu_item_id=line.menu_item_id,
                name=menu_items[line.menu_item_id].name,
                unit_price_cents=menu_items[line.menu_item_id].price_cents,
                quantity=line.quantity,
            )
            for line in request.items
        ]
        subtotal_cents = sum(item.unit_price_cents * item.quantity for item in items)
        total_cents = subtotal_cents + restaurant.delivery_fee_cents
        if total_cents > MAX_ORDER_TOTAL_CENTS:
            raise OrderTotalTooLarge

        order = Order(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status=OrderStatus.PENDING,
            delivery_address=request.delivery_address,
            phone=request.phone,
            notes=request.notes,
            subtotal_cents=subtotal_cents,
            delivery_fee_cents=restaurant.delivery_fee_cents,
            total_cents=total_cents,
            idempotency_key=idempotency_key,
            idempotency_fingerprint=fingerprint,
            items=items,
            status_events=[
                OrderStatusEvent(
                    from_status=None, to_status=OrderStatus.PENDING, actor_id=customer.id
                )
            ],
        )
        session.add(order)
        await session.commit()
        return OrderRead.model_validate(order), True

    @classmethod
    async def list_page(
        cls, session: AsyncSession, customer: User, *, limit: int, cursor: str | None
    ) -> OrderPage:
        query = build_order_list_query([Order.customer_id == customer.id], limit, cursor)
        rows = list(await session.scalars(query))

        return OrderPage(
            items=[OrderRead.model_validate(order) for order in rows[:limit]],
            next_cursor=next_order_cursor(rows, limit),
        )

    @classmethod
    async def get(cls, session: AsyncSession, customer: User, public_id: UUID) -> OrderRead:
        order = await session.scalar(cls._build_own_order_query(customer.id, public_id))
        if order is None:
            raise OrderNotFound
        return OrderRead.model_validate(order)

    @classmethod
    async def cancel(cls, session: AsyncSession, customer: User, public_id: UUID) -> OrderRead:
        query = cls._build_own_order_query(customer.id, public_id).with_for_update(of=Order)
        if (order := await session.scalar(query)) is None:
            raise OrderNotFound

        session.add(transition_order(order, OrderStatus.CANCELLED, customer, CUSTOMER_TRANSITIONS))
        await session.commit()
        return OrderRead.model_validate(order)

    @staticmethod
    def _fingerprint(request: OrderCreate) -> str:
        body = request.model_dump(mode='json')
        # Line order alone doesn't make a different order.
        body['items'] = sorted(body['items'], key=itemgetter('menu_item_id'))
        return sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    @staticmethod
    async def _find_by_idempotency_key(
        session: AsyncSession, customer_id: int, idempotency_key: UUID
    ) -> Order | None:
        return await session.scalar(
            build_order_query(
                Order.customer_id == customer_id, Order.idempotency_key == idempotency_key
            )
        )

    @staticmethod
    async def _load_active_restaurant(session: AsyncSession, restaurant_id: int) -> Restaurant:
        restaurant = await session.scalar(
            select(Restaurant).where(Restaurant.id == restaurant_id, Restaurant.is_active)
        )
        if restaurant is None:
            raise RestaurantUnavailable
        return restaurant

    @staticmethod
    async def _load_orderable_items(
        session: AsyncSession, request: OrderCreate
    ) -> dict[int, MenuItem]:
        requested_ids = [item.menu_item_id for item in request.items]
        menu_items = await session.scalars(
            select(MenuItem)
            .join(MenuCategory, MenuItem.category_id == MenuCategory.id)
            .where(
                MenuItem.id.in_(requested_ids),
                MenuItem.restaurant_id == request.restaurant_id,
                MenuItem.is_available,
                MenuItem.is_archived.is_(False),
                MenuCategory.is_archived.is_(False),
            )
        )
        orderable = {menu_item.id: menu_item for menu_item in menu_items}

        if missing_ids := [item_id for item_id in requested_ids if item_id not in orderable]:
            raise MenuItemsUnavailable(
                f"Menu items not available: {', '.join(map(str, missing_ids))}."
            )
        return orderable

    @staticmethod
    def _build_own_order_query(customer_id: int, public_id: UUID) -> Select:
        # Filtering by owner makes another customer's order indistinguishable from a missing one.
        return build_order_query(Order.customer_id == customer_id, Order.public_id == public_id)


def build_order_query(*conditions: ColumnElement[bool]) -> Select:
    return (
        select(Order)
        .where(*conditions)
        .options(selectinload(Order.items))
        # Re-read rows the session may already hold, e.g. a status changed under a lock.
        .execution_options(populate_existing=True)
    )


def build_order_list_query(
    conditions: list[ColumnElement[bool]], limit: int, cursor: str | None
) -> Select:
    """Newest orders first, keyset-paginated on (created_at, public_id)."""
    query = (
        build_order_query(*conditions)
        .order_by(Order.created_at.desc(), Order.public_id.desc())
        # One extra row tells us whether there is a next page.
        .limit(limit + 1)
    )
    if cursor is not None:
        created_at, public_id = decode_order_cursor(cursor)
        query = query.where(tuple_(Order.created_at, Order.public_id) < (created_at, public_id))
    return query


def decode_order_cursor(cursor: str) -> tuple[datetime, UUID]:
    created_at, public_id = decode_cursor(cursor, expected_types=(str, str))
    try:
        return datetime.fromisoformat(created_at), UUID(public_id)
    except ValueError as exc:
        raise InvalidCursor from exc


def next_order_cursor(rows: list[Order], limit: int) -> str | None:
    if len(rows) <= limit:
        return None

    last_shown = rows[limit - 1]
    return encode_cursor([last_shown.created_at.isoformat(), str(last_shown.public_id)])


def transition_order(
    order: Order,
    to_status: OrderStatus,
    actor: User,
    allowed_transitions: dict[OrderStatus, set[OrderStatus]],
) -> OrderStatusEvent:
    """Moves the order to `to_status`; returns the history event for the caller to add."""
    if to_status not in allowed_transitions.get(order.status, set()):
        raise InvalidStatusTransition(
            f"Cannot change an order from {order.status} to {to_status}."
        )

    event = OrderStatusEvent(
        order_id=order.id, from_status=order.status, to_status=to_status, actor_id=actor.id
    )
    order.status = to_status
    return event
