"""Test data builders.

Users are created over HTTP; admins are signed up, then promoted through the ORM. Restaurants
have no API, so catalogue rows are built through the ORM here; this is the only test module that
knows the table layout. Admin menu changes under test go through the HTTP helpers.
"""

import json
from base64 import urlsafe_b64encode
from random import choices
from string import ascii_lowercase
from uuid import UUID, uuid4

from httpx import AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.orders.models import OrderStatus
from app.restaurants.models import MenuCategory, MenuItem, Restaurant

TEST_PASSWORD = 'correct-horse-battery'

ADMIN_PATHS_FROM_PENDING = {
    OrderStatus.PENDING: [],
    OrderStatus.ACCEPTED: [OrderStatus.ACCEPTED],
    OrderStatus.OUT_FOR_DELIVERY: [OrderStatus.ACCEPTED, OrderStatus.OUT_FOR_DELIVERY],
    OrderStatus.DELIVERED: [
        OrderStatus.ACCEPTED,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED,
    ],
    OrderStatus.REJECTED: [OrderStatus.REJECTED],
    OrderStatus.CANCELLED: [OrderStatus.ACCEPTED, OrderStatus.CANCELLED],
}


async def signup_and_login(client: AsyncClient, email: str | None = None) -> dict[str, str]:
    email = email or f'{uuid4()}@example.com'
    signup = await client.post(
        '/api/v1/auth/signup',
        json={'email': email, 'password': TEST_PASSWORD, 'full_name': 'Test Customer'},
    )
    assert signup.status_code == 201, signup.text
    login = await client.post(
        '/api/v1/auth/login', json={'email': email, 'password': TEST_PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


async def signup_admin_and_login(
    client: AsyncClient, session: AsyncSession, email: str | None = None
) -> dict[str, str]:
    """There is no admin signup: sign up a customer, then promote them. Commit when committing."""
    email = email or f'{uuid4()}@example.com'
    headers = await signup_and_login(client, email)
    await session.execute(update(User).where(User.email == email).values(role=UserRole.ADMIN))
    return headers


def order_body(restaurant_id: int, lines: list[tuple[int, int]]) -> dict:
    """An order request; `lines` is a list of (menu_item_id, quantity)."""
    return {
        'restaurant_id': restaurant_id,
        'items': [
            {'menu_item_id': menu_item_id, 'quantity': quantity}
            for menu_item_id, quantity in lines
        ],
        'delivery_address': '1 Main St',
        'phone': '+1 555 0100',
    }


async def place_order(
    client: AsyncClient,
    headers: dict[str, str],
    body: dict,
    idempotency_key: UUID | None = None,
) -> Response:
    key = idempotency_key or uuid4()
    return await client.post(
        '/api/v1/orders', json=body, headers={**headers, 'Idempotency-Key': str(key)}
    )


async def place_pending_order(
    client: AsyncClient, session: AsyncSession, customer: dict[str, str]
) -> str:
    """Places an order at a fresh restaurant; returns its public id."""
    item = await add_orderable_item(session)
    response = await place_order(client, customer, order_body(item.restaurant_id, [(item.id, 1)]))
    assert response.status_code == 201, response.text
    return response.json()['public_id']


async def change_order_status(
    client: AsyncClient, admin: dict[str, str], public_id: str, status: OrderStatus
) -> Response:
    return await client.post(
        f'/api/v1/admin/orders/{public_id}/status', json={'to': status}, headers=admin
    )


async def move_order_to(
    client: AsyncClient, admin: dict[str, str], public_id: str, status: OrderStatus
) -> None:
    """Walks a pending order to `status` along the admin flow."""
    for step in ADMIN_PATHS_FROM_PENDING[status]:
        response = await change_order_status(client, admin, public_id, step)
        assert response.status_code == 200, response.text


def admin_menu_url(restaurant_id: int, path: str = '') -> str:
    return f'/api/v1/admin/restaurants/{restaurant_id}{path}'


async def create_category(
    client: AsyncClient, admin: dict[str, str], restaurant_id: int, name: str
) -> Response:
    return await client.post(
        admin_menu_url(restaurant_id, '/categories'), json={'name': name}, headers=admin
    )


async def update_category(
    client: AsyncClient, admin: dict[str, str], restaurant_id: int, category_id: int, body: dict
) -> Response:
    return await client.patch(
        admin_menu_url(restaurant_id, f'/categories/{category_id}'), json=body, headers=admin
    )


async def create_item(
    client: AsyncClient, admin: dict[str, str], restaurant_id: int, body: dict
) -> Response:
    return await client.post(admin_menu_url(restaurant_id, '/items'), json=body, headers=admin)


async def update_item(
    client: AsyncClient, admin: dict[str, str], restaurant_id: int, item_id: int, body: dict
) -> Response:
    return await client.patch(
        admin_menu_url(restaurant_id, f'/items/{item_id}'), json=body, headers=admin
    )


def raw_cursor(values: list) -> str:
    """A pagination cursor with arbitrary contents, for probing cursor validation."""
    return urlsafe_b64encode(json.dumps(values).encode()).decode()


def random_cuisine() -> str:
    """A cuisine no other test uses, so list assertions only see this test's restaurants."""
    return ''.join(choices(ascii_lowercase, k=16))


async def add_restaurant(
    session: AsyncSession,
    *,
    name: str = 'Test Kitchen',
    cuisine: str = 'test',
    delivery_fee_cents: int = 300,
    is_active: bool = True,
) -> Restaurant:
    restaurant = Restaurant(
        name=name,
        description='A test restaurant',
        cuisine=cuisine,
        address='1 Test Road',
        delivery_fee_cents=delivery_fee_cents,
        is_active=is_active,
    )
    session.add(restaurant)
    await session.flush()
    return restaurant


async def add_category(
    session: AsyncSession,
    restaurant: Restaurant,
    *,
    name: str = 'Mains',
    position: int = 0,
    is_archived: bool = False,
) -> MenuCategory:
    category = MenuCategory(
        restaurant_id=restaurant.id, name=name, position=position, is_archived=is_archived
    )
    session.add(category)
    await session.flush()
    return category


async def add_item(
    session: AsyncSession,
    category: MenuCategory,
    *,
    name: str = 'Dish',
    price_cents: int = 1250,
    is_available: bool = True,
    is_archived: bool = False,
) -> MenuItem:
    item = MenuItem(
        restaurant_id=category.restaurant_id,
        category_id=category.id,
        name=name,
        price_cents=price_cents,
        is_available=is_available,
        is_archived=is_archived,
    )
    session.add(item)
    await session.flush()
    return item


async def add_orderable_item(
    session: AsyncSession, *, price_cents: int = 1250, delivery_fee_cents: int = 300
) -> MenuItem:
    """One item in its own category in its own active restaurant."""
    restaurant = await add_restaurant(session, delivery_fee_cents=delivery_fee_cents)
    category = await add_category(session, restaurant)
    return await add_item(session, category, price_cents=price_cents)


async def change_item(session: AsyncSession, item_id: int, **values: object) -> None:
    await session.execute(update(MenuItem).where(MenuItem.id == item_id).values(**values))


async def archive_category(session: AsyncSession, category_id: int) -> None:
    await session.execute(
        update(MenuCategory).where(MenuCategory.id == category_id).values(is_archived=True)
    )


async def deactivate_restaurant(session: AsyncSession, restaurant_id: int) -> None:
    await session.execute(
        update(Restaurant).where(Restaurant.id == restaurant_id).values(is_active=False)
    )


async def deactivate_user(session: AsyncSession, email: str) -> None:
    await session.execute(update(User).where(User.email == email).values(is_active=False))


def add_restaurant_sync(session: Session) -> None:
    session.add(
        Restaurant(
            name='Test Kitchen',
            description='A test restaurant',
            cuisine='test',
            address='1 Test Road',
            delivery_fee_cents=300,
        )
    )
    session.flush()


def count_restaurants_sync(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Restaurant))
