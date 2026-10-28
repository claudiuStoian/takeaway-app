from asyncio import gather
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.builders import (
    add_category,
    add_item,
    add_orderable_item,
    add_restaurant,
    change_item,
    order_body,
    place_order,
    signup_and_login,
)

pytestmark = pytest.mark.anyio

CONCURRENT_REQUESTS = 10


async def test_retry_with_the_same_key_and_body_returns_the_original_order(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    key = uuid4()

    first = await place_order(client, customer, body, key)
    retry = await place_order(client, customer, body, key)
    my_orders = await client.get('/api/v1/orders', headers=customer)

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert [order['public_id'] for order in my_orders.json()['items']] == [
        first.json()['public_id']
    ]


async def test_line_order_does_not_make_a_different_request(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    category = await add_category(db_session, restaurant)
    burger = await add_item(db_session, category, name='Burger')
    fries = await add_item(db_session, category, name='Fries')
    key = uuid4()

    first = await place_order(
        client, customer, order_body(restaurant.id, [(burger.id, 1), (fries.id, 2)]), key
    )
    reordered = await place_order(
        client, customer, order_body(restaurant.id, [(fries.id, 2), (burger.id, 1)]), key
    )

    assert first.status_code == 201
    assert reordered.status_code == 200
    assert reordered.json()['public_id'] == first.json()['public_id']


async def test_same_key_with_a_different_quantity_or_restaurant_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    other_restaurant = await add_restaurant(db_session)
    key = uuid4()
    await place_order(client, customer, order_body(item.restaurant_id, [(item.id, 1)]), key)
    # A different quantity is otherwise orderable, so its 422 can only be the key conflict.
    key_conflict = await place_order(
        client, customer, order_body(item.restaurant_id, [(item.id, 2)]), key
    )

    response = await place_order(
        client, customer, order_body(other_restaurant.id, [(item.id, 1)]), key
    )

    assert key_conflict.status_code == 422
    assert response.status_code == 422
    assert response.json() == key_conflict.json()


@pytest.mark.parametrize(
    'change',
    [{'is_archived': True}, {'is_available': False}, {'price_cents': 9999}],
    ids=['archived', 'sold-out', 'repriced'],
)
async def test_retry_after_the_menu_changed_still_returns_the_original_order(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str], change: dict
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    key = uuid4()
    first = await place_order(client, customer, body, key)

    await change_item(db_session, item.id, **change)
    retry = await place_order(client, customer, body, key)

    assert retry.status_code == 200
    assert retry.json() == first.json()


async def test_two_customers_may_use_the_same_key(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    other_customer = await signup_and_login(client)
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    key = uuid4()

    mine = await place_order(client, customer, body, key)
    theirs = await place_order(client, other_customer, body, key)

    assert mine.status_code == 201
    assert theirs.status_code == 201
    assert mine.json()['public_id'] != theirs.json()['public_id']


async def test_concurrent_requests_with_one_key_create_one_order(
    committed_client: AsyncClient, committed_session: AsyncSession
) -> None:
    customer = await signup_and_login(committed_client)
    item = await add_orderable_item(committed_session)
    await committed_session.commit()
    body = order_body(item.restaurant_id, [(item.id, 1)])
    key = uuid4()

    responses = await gather(
        *(place_order(committed_client, customer, body, key) for _ in range(CONCURRENT_REQUESTS))
    )

    assert sorted(response.status_code for response in responses) == [200] * (
        CONCURRENT_REQUESTS - 1
    ) + [201]
    assert len({response.json()['public_id'] for response in responses}) == 1


async def test_concurrent_retries_after_the_item_was_archived_all_get_the_order(
    committed_client: AsyncClient, committed_session: AsyncSession
) -> None:
    customer = await signup_and_login(committed_client)
    item = await add_orderable_item(committed_session)
    await committed_session.commit()
    body = order_body(item.restaurant_id, [(item.id, 1)])
    key = uuid4()
    first = await place_order(committed_client, customer, body, key)

    await change_item(committed_session, item.id, is_archived=True)
    await committed_session.commit()
    retries = await gather(
        *(place_order(committed_client, customer, body, key) for _ in range(CONCURRENT_REQUESTS))
    )

    assert first.status_code == 201
    assert [response.status_code for response in retries] == [200] * CONCURRENT_REQUESTS
    assert {response.json()['public_id'] for response in retries} == {first.json()['public_id']}
