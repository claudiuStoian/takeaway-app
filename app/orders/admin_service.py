from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User
from app.orders.models import Order, OrderStatus, OrderStatusEvent
from app.orders.schemas import AdminOrderPageResponse, AdminOrderResponse, OrderStatusEventResponse
from app.orders.service import (
    ADMIN_TRANSITIONS,
    OrderNotFound,
    build_order_list_query,
    build_order_query,
    next_order_cursor,
    transition_order,
)


class AdminOrderService:
    """Order operations across all customers; only admin routes may call these."""

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        *,
        limit: int,
        cursor: str | None,
        status: OrderStatus | None,
        restaurant_id: int | None,
    ) -> AdminOrderPageResponse:
        query = build_order_list_query(
            cls._build_filters(status, restaurant_id), limit, cursor
        ).options(selectinload(Order.customer))
        rows = list(await session.scalars(query))

        return AdminOrderPageResponse(
            items=[AdminOrderResponse.model_validate(order) for order in rows[:limit]],
            next_cursor=next_order_cursor(rows, limit),
        )

    @classmethod
    async def change_status(
        cls, session: AsyncSession, admin: User, public_id: UUID, to_status: OrderStatus
    ) -> AdminOrderResponse:
        query = (
            build_order_query(Order.public_id == public_id)
            .options(selectinload(Order.customer))
            .with_for_update(of=Order)
        )
        if (order := await session.scalar(query)) is None:
            raise OrderNotFound

        session.add(transition_order(order, to_status, admin, ADMIN_TRANSITIONS))
        await session.commit()
        return AdminOrderResponse.model_validate(order)

    @classmethod
    async def list_history(
        cls, session: AsyncSession, public_id: UUID
    ) -> list[OrderStatusEventResponse]:
        order_id = await session.scalar(select(Order.id).where(Order.public_id == public_id))
        if order_id is None:
            raise OrderNotFound

        events = await session.scalars(
            select(OrderStatusEvent)
            .where(OrderStatusEvent.order_id == order_id)
            .options(selectinload(OrderStatusEvent.actor))
            .order_by(OrderStatusEvent.id)
        )
        return [OrderStatusEventResponse.model_validate(event) for event in events]

    @staticmethod
    def _build_filters(
        status: OrderStatus | None, restaurant_id: int | None
    ) -> list[ColumnElement[bool]]:
        filters = []
        if status is not None:
            filters.append(Order.status == status)
        if restaurant_id is not None:
            filters.append(Order.restaurant_id == restaurant_id)
        return filters
