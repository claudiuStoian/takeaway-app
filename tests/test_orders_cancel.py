from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.orders.models import OrderStatus
from tests.builders import (
    add_orderable_item,
    move_order_to,
    order_body,
    place_order,
    place_pending_order,
    signup_and_login,
)

pytestmark = pytest.mark.anyio


async def test_customer_can_cancel_a_pending_order(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    public_id = await place_pending_order(client, db_session, customer)

    cancelled = await client.post(f'/api/v1/orders/{public_id}/cancel', headers=customer)
    afterwards = await client.get(f'/api/v1/orders/{public_id}', headers=customer)

    assert cancelled.status_code == 200
    assert cancelled.json()['status'] == 'cancelled'
    assert afterwards.json()['status'] == 'cancelled'


async def test_cancellation_is_saved(
    committed_client: AsyncClient, committed_session: AsyncSession
) -> None:
    customer = await signup_and_login(committed_client)
    item = await add_orderable_item(committed_session)
    await committed_session.commit()
    placed = await place_order(
        committed_client, customer, order_body(item.restaurant_id, [(item.id, 1)])
    )
    public_id = placed.json()['public_id']

    await committed_client.post(f'/api/v1/orders/{public_id}/cancel', headers=customer)
    afterwards = await committed_client.get(f'/api/v1/orders/{public_id}', headers=customer)

    assert afterwards.json()['status'] == 'cancelled'


async def test_cancelling_twice_is_409(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    public_id = await place_pending_order(client, db_session, customer)
    await client.post(f'/api/v1/orders/{public_id}/cancel', headers=customer)

    response = await client.post(f'/api/v1/orders/{public_id}/cancel', headers=customer)

    assert response.status_code == 409


@pytest.mark.parametrize(
    'status',
    [
        OrderStatus.ACCEPTED,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED,
        OrderStatus.REJECTED,
    ],
)
async def test_customer_cannot_cancel_once_the_order_left_pending(
    client: AsyncClient,
    db_session: AsyncSession,
    customer: dict[str, str],
    admin: dict[str, str],
    status: OrderStatus,
) -> None:
    public_id = await place_pending_order(client, db_session, customer)
    await move_order_to(client, admin, public_id, status)

    response = await client.post(f'/api/v1/orders/{public_id}/cancel', headers=customer)
    afterwards = await client.get(f'/api/v1/orders/{public_id}', headers=customer)

    assert response.status_code == 409
    assert afterwards.json()['status'] == status


async def test_cancelling_another_customers_order_is_404_and_changes_nothing(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    public_id = await place_pending_order(client, db_session, customer)
    other_customer = await signup_and_login(client)

    response = await client.post(f'/api/v1/orders/{public_id}/cancel', headers=other_customer)
    afterwards = await client.get(f'/api/v1/orders/{public_id}', headers=customer)

    assert response.status_code == 404
    assert afterwards.json()['status'] == 'pending'


async def test_cancelling_a_missing_order_is_404(
    client: AsyncClient, customer: dict[str, str]
) -> None:
    response = await client.post(f'/api/v1/orders/{uuid4()}/cancel', headers=customer)

    assert response.status_code == 404
