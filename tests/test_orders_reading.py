import json
from base64 import urlsafe_b64decode
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.builders import (
    add_orderable_item,
    order_body,
    place_order,
    raw_cursor,
    signup_and_login,
)

pytestmark = pytest.mark.anyio

MAX_PAGES = 20

ORDERS_TO_PAGE = 5


async def test_customer_can_read_their_own_order(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    placed = await place_order(client, customer, order_body(item.restaurant_id, [(item.id, 1)]))

    response = await client.get(f"/api/v1/orders/{placed.json()['public_id']}", headers=customer)

    assert response.status_code == 200
    assert response.json() == placed.json()


async def test_another_customers_order_looks_the_same_as_a_missing_one(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    placed = await place_order(client, customer, order_body(item.restaurant_id, [(item.id, 1)]))
    other_customer = await signup_and_login(client)

    not_mine = await client.get(
        f"/api/v1/orders/{placed.json()['public_id']}", headers=other_customer
    )
    missing = await client.get(f'/api/v1/orders/{uuid4()}', headers=other_customer)

    assert not_mine.status_code == 404
    assert missing.status_code == 404
    assert not_mine.json() == missing.json()


async def test_list_shows_only_my_orders(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    other_customer = await signup_and_login(client)
    mine = [(await place_order(client, customer, body)).json()['public_id'] for _ in range(2)]
    await place_order(client, other_customer, body)

    response = await client.get('/api/v1/orders', headers=customer)

    assert response.status_code == 200
    assert sorted(order['public_id'] for order in response.json()['items']) == sorted(mine)


async def test_list_pages_newest_first_without_gaps_or_repeats(
    committed_client: AsyncClient, committed_session: AsyncSession
) -> None:
    customer = await signup_and_login(committed_client)
    item = await add_orderable_item(committed_session)
    await committed_session.commit()
    body = order_body(item.restaurant_id, [(item.id, 1)])
    placed_ids = []
    for _ in range(ORDERS_TO_PAGE):
        placed_ids.append(
            (await place_order(committed_client, customer, body)).json()['public_id']
        )

    pages = await walk_order_pages(committed_client, customer, limit=2)

    assert [len(page['items']) for page in pages] == [2, 2, 1]
    assert pages[-1]['next_cursor'] is None
    assert [order['public_id'] for page in pages for order in page['items']] == list(
        reversed(placed_ids)
    )


async def test_list_pages_through_orders_with_the_same_timestamp(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    placed = [(await place_order(client, customer, body)).json() for _ in range(ORDERS_TO_PAGE)]
    assert len({order['created_at'] for order in placed}) == 1

    pages = await walk_order_pages(client, customer, limit=2)

    seen_ids = [order['public_id'] for page in pages for order in page['items']]
    assert sorted(seen_ids) == sorted(order['public_id'] for order in placed)
    assert len(seen_ids) == len(set(seen_ids))


async def test_cursor_holds_no_internal_ids(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    for _ in range(2):
        await place_order(client, customer, body)

    response = await client.get('/api/v1/orders', params={'limit': 1}, headers=customer)

    cursor_values = json.loads(urlsafe_b64decode(response.json()['next_cursor']))
    assert all(isinstance(value, str) for value in cursor_values)
    assert str(UUID(cursor_values[-1])) == response.json()['items'][0]['public_id']


@pytest.mark.parametrize(
    'cursor', ['not base64!', raw_cursor([1, 2])], ids=['malformed', 'int-values']
)
async def test_list_with_a_bad_cursor_is_422(
    client: AsyncClient, customer: dict[str, str], cursor: str
) -> None:
    response = await client.get('/api/v1/orders', params={'cursor': cursor}, headers=customer)

    assert response.status_code == 422


async def test_reading_orders_without_a_token_is_401(client: AsyncClient) -> None:
    listing = await client.get('/api/v1/orders')
    single = await client.get(f'/api/v1/orders/{uuid4()}')

    assert listing.status_code == 401
    assert single.status_code == 401


async def walk_order_pages(client: AsyncClient, headers: dict[str, str], limit: int) -> list[dict]:
    pages = []
    seen_cursors = set()
    params: dict[str, str | int] = {'limit': limit}
    for _ in range(MAX_PAGES):
        response = await client.get('/api/v1/orders', params=params, headers=headers)
        assert response.status_code == 200, response.text
        pages.append(response.json())
        if (cursor := response.json()['next_cursor']) is None:
            return pages
        assert cursor not in seen_cursors, 'The cursor repeated instead of moving forward.'
        seen_cursors.add(cursor)
        params['cursor'] = cursor
    pytest.fail(f'No last page after {MAX_PAGES} pages.')
