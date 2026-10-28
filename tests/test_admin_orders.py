import json
from asyncio import gather
from base64 import urlsafe_b64decode
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.orders.models import OrderStatus
from tests.builders import (
    add_orderable_item,
    change_order_status,
    move_order_to,
    order_body,
    place_order,
    place_pending_order,
    raw_cursor,
    signup_admin_and_login,
    signup_and_login,
)

pytestmark = pytest.mark.anyio

MAX_PAGES = 20

ORDERS_TO_PAGE = 5

INTERNAL_ID_KEYS = {'id', 'customer_id', 'actor_id', 'order_id'}

LEGAL_ADMIN_TRANSITIONS = [
    (OrderStatus.PENDING, OrderStatus.ACCEPTED),
    (OrderStatus.PENDING, OrderStatus.REJECTED),
    (OrderStatus.ACCEPTED, OrderStatus.OUT_FOR_DELIVERY),
    (OrderStatus.ACCEPTED, OrderStatus.CANCELLED),
    (OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED),
]

ILLEGAL_ADMIN_TRANSITIONS = [
    (OrderStatus.PENDING, OrderStatus.PENDING),
    (OrderStatus.PENDING, OrderStatus.OUT_FOR_DELIVERY),
    (OrderStatus.PENDING, OrderStatus.DELIVERED),
    # Only the customer cancels a pending order; staff reject it.
    (OrderStatus.PENDING, OrderStatus.CANCELLED),
    (OrderStatus.ACCEPTED, OrderStatus.ACCEPTED),
    (OrderStatus.ACCEPTED, OrderStatus.PENDING),
    (OrderStatus.ACCEPTED, OrderStatus.DELIVERED),
    (OrderStatus.OUT_FOR_DELIVERY, OrderStatus.CANCELLED),
    (OrderStatus.OUT_FOR_DELIVERY, OrderStatus.ACCEPTED),
    (OrderStatus.DELIVERED, OrderStatus.CANCELLED),
    (OrderStatus.REJECTED, OrderStatus.ACCEPTED),
    (OrderStatus.CANCELLED, OrderStatus.ACCEPTED),
]

ADMIN_ROUTES = [
    ('GET', '/api/v1/admin/orders', None),
    ('POST', '/api/v1/admin/orders/{public_id}/status', {'to': 'accepted'}),
    ('GET', '/api/v1/admin/orders/{public_id}/history', None),
]
ADMIN_ROUTE_IDS = ['list', 'status', 'history']


@pytest.mark.parametrize(
    ('from_status', 'to_status'),
    LEGAL_ADMIN_TRANSITIONS,
    ids=[f'{a}->{b}' for a, b in LEGAL_ADMIN_TRANSITIONS],
)
async def test_admin_can_make_every_allowed_status_change(
    client: AsyncClient,
    db_session: AsyncSession,
    customer: dict[str, str],
    admin: dict[str, str],
    from_status: OrderStatus,
    to_status: OrderStatus,
) -> None:
    public_id = await place_pending_order(client, db_session, customer)
    await move_order_to(client, admin, public_id, from_status)

    response = await change_order_status(client, admin, public_id, to_status)
    seen_by_customer = await client.get(f'/api/v1/orders/{public_id}', headers=customer)

    assert response.status_code == 200, response.text
    assert response.json()['status'] == to_status
    assert seen_by_customer.json()['status'] == to_status


@pytest.mark.parametrize(
    ('from_status', 'to_status'),
    ILLEGAL_ADMIN_TRANSITIONS,
    ids=[f'{a}->{b}' for a, b in ILLEGAL_ADMIN_TRANSITIONS],
)
async def test_disallowed_status_change_is_409_and_changes_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    customer: dict[str, str],
    admin: dict[str, str],
    from_status: OrderStatus,
    to_status: OrderStatus,
) -> None:
    public_id = await place_pending_order(client, db_session, customer)
    await move_order_to(client, admin, public_id, from_status)
    history_url = f'/api/v1/admin/orders/{public_id}/history'
    history_before = await client.get(history_url, headers=admin)

    response = await change_order_status(client, admin, public_id, to_status)
    seen_by_customer = await client.get(f'/api/v1/orders/{public_id}', headers=customer)
    history_after = await client.get(history_url, headers=admin)

    assert response.status_code == 409
    assert seen_by_customer.json()['status'] == from_status
    assert history_after.json() == history_before.json()


async def test_unknown_status_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str], admin: dict[str, str]
) -> None:
    public_id = await place_pending_order(client, db_session, customer)

    response = await client.post(
        f'/api/v1/admin/orders/{public_id}/status', json={'to': 'eaten'}, headers=admin
    )

    assert response.status_code == 422


async def test_status_change_returns_the_order_with_its_customer(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    customer = await signup_and_login(client, 'status-change@example.com')
    public_id = await place_pending_order(client, db_session, customer)

    response = await change_order_status(client, admin, public_id, OrderStatus.ACCEPTED)

    assert response.json()['public_id'] == public_id
    assert response.json()['customer']['email'] == 'status-change@example.com'
    assert response.json()['customer']['role'] == 'customer'


@pytest.mark.parametrize('path', ['status', 'history'])
async def test_missing_order_is_404(client: AsyncClient, admin: dict[str, str], path: str) -> None:
    url = f'/api/v1/admin/orders/{uuid4()}/{path}'
    if path == 'status':
        response = await client.post(url, json={'to': 'accepted'}, headers=admin)
    else:
        response = await client.get(url, headers=admin)

    assert response.status_code == 404


@pytest.mark.parametrize(('method', 'path', 'body'), ADMIN_ROUTES, ids=ADMIN_ROUTE_IDS)
async def test_customer_is_forbidden_on_admin_routes(
    client: AsyncClient,
    db_session: AsyncSession,
    customer: dict[str, str],
    method: str,
    path: str,
    body: dict | None,
) -> None:
    public_id = await place_pending_order(client, db_session, customer)

    response = await client.request(
        method, path.format(public_id=public_id), json=body, headers=customer
    )
    afterwards = await client.get(f'/api/v1/orders/{public_id}', headers=customer)

    assert response.status_code == 403
    assert afterwards.json()['status'] == 'pending'


@pytest.mark.parametrize(('method', 'path', 'body'), ADMIN_ROUTES, ids=ADMIN_ROUTE_IDS)
async def test_admin_routes_without_a_token_are_401(
    client: AsyncClient, method: str, path: str, body: dict | None
) -> None:
    response = await client.request(method, path.format(public_id=uuid4()), json=body)

    assert response.status_code == 401


async def test_history_records_creation_and_every_change_with_its_actor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    customer = await signup_and_login(client, 'history-customer@example.com')
    admin = await signup_admin_and_login(client, db_session, 'history-admin@example.com')
    public_id = await place_pending_order(client, db_session, customer)
    await move_order_to(client, admin, public_id, OrderStatus.DELIVERED)

    response = await client.get(f'/api/v1/admin/orders/{public_id}/history', headers=admin)

    assert response.status_code == 200
    assert [
        (event['from_status'], event['to_status'], event['actor']['email'])
        for event in response.json()
    ] == [
        (None, 'pending', 'history-customer@example.com'),
        ('pending', 'accepted', 'history-admin@example.com'),
        ('accepted', 'out_for_delivery', 'history-admin@example.com'),
        ('out_for_delivery', 'delivered', 'history-admin@example.com'),
    ]


async def test_history_records_a_customer_cancellation(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    customer = await signup_and_login(client, 'cancel-history@example.com')
    public_id = await place_pending_order(client, db_session, customer)
    await client.post(f'/api/v1/orders/{public_id}/cancel', headers=customer)

    response = await client.get(f'/api/v1/admin/orders/{public_id}/history', headers=admin)

    last_event = response.json()[-1]
    assert (last_event['from_status'], last_event['to_status']) == ('pending', 'cancelled')
    assert last_event['actor']['email'] == 'cancel-history@example.com'


async def test_admin_list_shows_every_customers_orders(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    first_customer = await signup_and_login(client, 'list-first@example.com')
    second_customer = await signup_and_login(client, 'list-second@example.com')
    await place_order(client, first_customer, body)
    await place_order(client, second_customer, body)

    response = await client.get(
        '/api/v1/admin/orders', params={'restaurant_id': item.restaurant_id}, headers=admin
    )

    assert response.status_code == 200
    assert sorted(order['customer']['email'] for order in response.json()['items']) == [
        'list-first@example.com',
        'list-second@example.com',
    ]


async def test_admin_list_filters_by_status(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str], admin: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    accepted_id = (await place_order(client, customer, body)).json()['public_id']
    await place_order(client, customer, body)
    await move_order_to(client, admin, accepted_id, OrderStatus.ACCEPTED)

    response = await client.get(
        '/api/v1/admin/orders',
        params={'restaurant_id': item.restaurant_id, 'status': 'accepted'},
        headers=admin,
    )

    assert [order['public_id'] for order in response.json()['items']] == [accepted_id]


async def test_admin_list_pages_newest_first_without_gaps_or_repeats(
    committed_client: AsyncClient, committed_session: AsyncSession
) -> None:
    admin = await signup_admin_and_login(committed_client, committed_session)
    customer = await signup_and_login(committed_client)
    item = await add_orderable_item(committed_session)
    await committed_session.commit()
    body = order_body(item.restaurant_id, [(item.id, 1)])
    placed_ids = []
    for _ in range(ORDERS_TO_PAGE):
        placed_ids.append(
            (await place_order(committed_client, customer, body)).json()['public_id']
        )

    pages = await walk_admin_order_pages(
        committed_client, admin, {'restaurant_id': item.restaurant_id, 'limit': 2}
    )

    assert [len(page['items']) for page in pages] == [2, 2, 1]
    assert [order['public_id'] for page in pages for order in page['items']] == list(
        reversed(placed_ids)
    )


@pytest.mark.parametrize(
    'params',
    [
        {'restaurant_id': 0},
        {'status': 'eaten'},
        {'cursor': 'not base64!'},
        {'cursor': raw_cursor([1, 2])},
    ],
    ids=[
        'restaurant-id-zero',
        'unknown-status',
        'bad-cursor',
        'int-cursor',
    ],
)
async def test_admin_list_with_bad_params_is_422(
    client: AsyncClient, admin: dict[str, str], params: dict
) -> None:
    response = await client.get('/api/v1/admin/orders', params=params, headers=admin)

    assert response.status_code == 422


async def test_admin_responses_hold_no_internal_ids(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str], admin: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    public_id = (await place_order(client, customer, body)).json()['public_id']
    await place_order(client, customer, body)

    status_change = await change_order_status(client, admin, public_id, OrderStatus.ACCEPTED)
    history = await client.get(f'/api/v1/admin/orders/{public_id}/history', headers=admin)
    listing = await client.get(
        '/api/v1/admin/orders',
        params={'restaurant_id': item.restaurant_id, 'limit': 1},
        headers=admin,
    )

    for response in (status_change, history, listing):
        assert not collect_keys(response.json()) & INTERNAL_ID_KEYS
    cursor_values = json.loads(urlsafe_b64decode(listing.json()['next_cursor']))
    assert all(isinstance(value, str) for value in cursor_values)
    assert str(UUID(cursor_values[-1])) == listing.json()['items'][0]['public_id']


async def test_two_admins_accepting_at_once_only_one_wins(
    committed_client: AsyncClient, committed_session: AsyncSession
) -> None:
    first_admin = await signup_admin_and_login(committed_client, committed_session)
    second_admin = await signup_admin_and_login(committed_client, committed_session)
    customer = await signup_and_login(committed_client)
    item = await add_orderable_item(committed_session)
    await committed_session.commit()
    placed = await place_order(
        committed_client, customer, order_body(item.restaurant_id, [(item.id, 1)])
    )
    public_id = placed.json()['public_id']

    responses = await gather(
        change_order_status(committed_client, first_admin, public_id, OrderStatus.ACCEPTED),
        change_order_status(committed_client, second_admin, public_id, OrderStatus.ACCEPTED),
    )
    history = await committed_client.get(
        f'/api/v1/admin/orders/{public_id}/history', headers=first_admin
    )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert [event['to_status'] for event in history.json()] == ['pending', 'accepted']


def collect_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in collect_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in collect_keys(child)}
    return set()


async def walk_admin_order_pages(
    client: AsyncClient, headers: dict[str, str], params: dict[str, str | int]
) -> list[dict]:
    pages = []
    seen_cursors = set()
    for _ in range(MAX_PAGES):
        response = await client.get('/api/v1/admin/orders', params=params, headers=headers)
        assert response.status_code == 200, response.text
        pages.append(response.json())
        if (cursor := response.json()['next_cursor']) is None:
            return pages
        assert cursor not in seen_cursors, 'The cursor repeated instead of moving forward.'
        seen_cursors.add(cursor)
        params = {**params, 'cursor': cursor}
    pytest.fail(f'No last page after {MAX_PAGES} pages.')
