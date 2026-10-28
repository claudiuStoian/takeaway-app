from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limits import (
    MAX_DELIVERY_ADDRESS_LENGTH,
    MAX_DELIVERY_FEE_CENTS,
    MAX_ITEM_PRICE_CENTS,
    MAX_LINES_PER_ORDER,
    MAX_QUANTITY_PER_ITEM,
)
from tests.builders import (
    UNKNOWN_ID,
    add_category,
    add_item,
    add_orderable_item,
    add_restaurant,
    archive_category,
    change_item,
    deactivate_restaurant,
    order_body,
    place_order,
)

pytestmark = pytest.mark.anyio

ORDER_KEYS = {
    'public_id',
    'restaurant_id',
    'status',
    'delivery_address',
    'phone',
    'notes',
    'subtotal_cents',
    'delivery_fee_cents',
    'total_cents',
    'items',
    'created_at',
    'updated_at',
}
ORDER_ITEM_KEYS = {'menu_item_id', 'name', 'unit_price_cents', 'quantity'}


async def test_order_totals_are_computed_from_menu_prices_and_delivery_fee(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session, delivery_fee_cents=300)
    category = await add_category(db_session, restaurant)
    burger = await add_item(db_session, category, name='Burger', price_cents=1250)
    fries = await add_item(db_session, category, name='Fries', price_cents=400)

    response = await place_order(
        client, customer, order_body(restaurant.id, [(burger.id, 2), (fries.id, 1)])
    )

    assert response.status_code == 201, response.text
    order = response.json()
    assert set(order) == ORDER_KEYS
    assert order['status'] == 'pending'
    assert order['restaurant_id'] == restaurant.id
    assert order['subtotal_cents'] == 2900
    assert order['delivery_fee_cents'] == 300
    assert order['total_cents'] == 3200
    assert all(set(item) == ORDER_ITEM_KEYS for item in order['items'])
    assert sorted(
        (item['name'], item['unit_price_cents'], item['quantity']) for item in order['items']
    ) == [('Burger', 1250, 2), ('Fries', 400, 1)]


async def test_order_keeps_the_name_and_price_it_was_placed_with(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session, price_cents=1250)
    placed = await place_order(client, customer, order_body(item.restaurant_id, [(item.id, 1)]))

    await change_item(db_session, item.id, name='Renamed', price_cents=9999)
    response = await client.get(f"/api/v1/orders/{placed.json()['public_id']}", headers=customer)

    assert response.status_code == 200
    [line] = response.json()['items']
    assert (line['name'], line['unit_price_cents']) == ('Dish', 1250)
    assert response.json()['total_cents'] == 1550


async def test_order_with_the_largest_allowed_total_is_accepted(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session, delivery_fee_cents=MAX_DELIVERY_FEE_CENTS)
    category = await add_category(db_session, restaurant)
    lines = []
    for number in range(MAX_LINES_PER_ORDER):
        item = await add_item(
            db_session, category, name=f'Item {number}', price_cents=MAX_ITEM_PRICE_CENTS
        )
        lines.append((item.id, MAX_QUANTITY_PER_ITEM))

    response = await place_order(client, customer, order_body(restaurant.id, lines))

    assert response.status_code == 201, response.text
    assert response.json()['total_cents'] == 495_010_000


async def test_blank_notes_are_stored_as_no_notes(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)]) | {'notes': '   '}

    response = await place_order(client, customer, body)

    assert response.status_code == 201
    assert response.json()['notes'] is None


@pytest.mark.parametrize(
    'overrides',
    [
        {'total_cents': 1},
        {'items': []},
        {'phone': 'call me'},
        {'phone': '12345'},
        {'delivery_address': 'x' * (MAX_DELIVERY_ADDRESS_LENGTH + 1)},
        {'delivery_address': '  '},
    ],
    ids=[
        'client-total',
        'no-items',
        'phone-letters',
        'phone-too-short',
        'address-too-long',
        'address-blank',
    ],
)
async def test_invalid_order_field_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str], overrides: dict
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)]) | overrides

    response = await place_order(client, customer, body)

    assert response.status_code == 422


@pytest.mark.parametrize(
    'line_overrides',
    [
        {'unit_price_cents': 1},
        {'quantity': 0},
        {'quantity': MAX_QUANTITY_PER_ITEM + 1},
    ],
    ids=['client-unit-price', 'zero-quantity', 'quantity-over-max'],
)
async def test_invalid_order_line_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str], line_overrides: dict
) -> None:
    item = await add_orderable_item(db_session)
    body = order_body(item.restaurant_id, [(item.id, 1)])
    body['items'][0] |= line_overrides

    response = await place_order(client, customer, body)

    assert response.status_code == 422


async def test_same_item_on_two_lines_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)

    response = await place_order(
        client, customer, order_body(item.restaurant_id, [(item.id, 1), (item.id, 2)])
    )

    assert response.status_code == 422


async def test_too_many_lines_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    category = await add_category(db_session, restaurant)
    lines = []
    for number in range(MAX_LINES_PER_ORDER + 1):
        item = await add_item(db_session, category, name=f'Item {number}')
        lines.append((item.id, 1))

    response = await place_order(client, customer, order_body(restaurant.id, lines))

    assert response.status_code == 422


async def test_unknown_item_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)

    response = await place_order(
        client, customer, order_body(item.restaurant_id, [(item.id, 1), (UNKNOWN_ID, 1)])
    )

    assert response.status_code == 422


async def test_item_from_another_restaurant_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    other_restaurant_item = await add_orderable_item(db_session)

    response = await place_order(
        client, customer, order_body(item.restaurant_id, [(other_restaurant_item.id, 1)])
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    'change',
    [{'is_archived': True}, {'is_available': False}],
    ids=['archived', 'sold-out'],
)
async def test_unorderable_item_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str], change: dict
) -> None:
    item = await add_orderable_item(db_session)
    await change_item(db_session, item.id, **change)

    response = await place_order(client, customer, order_body(item.restaurant_id, [(item.id, 1)]))

    assert response.status_code == 422


async def test_item_in_an_archived_category_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    await archive_category(db_session, item.category_id)

    response = await place_order(client, customer, order_body(item.restaurant_id, [(item.id, 1)]))

    assert response.status_code == 422


async def test_inactive_restaurant_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)
    await deactivate_restaurant(db_session, item.restaurant_id)

    response = await place_order(client, customer, order_body(item.restaurant_id, [(item.id, 1)]))

    assert response.status_code == 422


async def test_unknown_restaurant_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str]
) -> None:
    item = await add_orderable_item(db_session)

    response = await place_order(client, customer, order_body(UNKNOWN_ID, [(item.id, 1)]))

    assert response.status_code == 422


@pytest.mark.parametrize('key', [None, 'not-a-uuid'], ids=['missing', 'not-a-uuid'])
async def test_order_without_a_valid_idempotency_key_is_422(
    client: AsyncClient, db_session: AsyncSession, customer: dict[str, str], key: str | None
) -> None:
    item = await add_orderable_item(db_session)
    headers = customer if key is None else {**customer, 'Idempotency-Key': key}

    response = await client.post(
        '/api/v1/orders', json=order_body(item.restaurant_id, [(item.id, 1)]), headers=headers
    )

    assert response.status_code == 422


async def test_order_without_a_token_is_401(client: AsyncClient, db_session: AsyncSession) -> None:
    item = await add_orderable_item(db_session)

    response = await client.post(
        '/api/v1/orders',
        json=order_body(item.restaurant_id, [(item.id, 1)]),
        headers={'Idempotency-Key': str(uuid4())},
    )

    assert response.status_code == 401
