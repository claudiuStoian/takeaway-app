from asyncio import gather

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limits import (
    MAX_ITEM_PRICE_CENTS,
    MAX_MENU_DESCRIPTION_LENGTH,
    MAX_MENU_NAME_LENGTH,
    MAX_MENU_POSITION,
)
from tests.builders import (
    UNKNOWN_ID,
    add_restaurant,
    admin_menu_url,
    create_category,
    create_item,
    deactivate_restaurant,
    order_body,
    place_order,
    signup_admin_and_login,
    update_category,
    update_item,
)

pytestmark = pytest.mark.anyio

ADMIN_MENU_ROUTES = [
    ('GET', '/menu', None),
    ('POST', '/categories', {'name': 'Specials'}),
    ('PATCH', '/categories/{category_id}', {'is_archived': True}),
    ('POST', '/items', {'category_id': '{category_id}', 'name': 'Soup', 'price_cents': 500}),
    ('PATCH', '/items/{item_id}', {'is_archived': True}),
]
ADMIN_MENU_ROUTE_IDS = ['menu', 'create-category', 'update-category', 'create-item', 'update-item']

VALID_ITEM = {'name': 'Margherita', 'price_cents': 1400}

INVALID_ITEM_OVERRIDES = {
    'zero price': {'price_cents': 0},
    'price over the limit': {'price_cents': MAX_ITEM_PRICE_CENTS + 1},
    'blank name': {'name': '   '},
    'name too long': {'name': 'x' * (MAX_MENU_NAME_LENGTH + 1)},
    'description too long': {'description': 'x' * (MAX_MENU_DESCRIPTION_LENGTH + 1)},
    'client-sent restaurant': {'restaurant_id': 1},
}

INVALID_ITEM_UPDATES = {
    'null name': {'name': None},
    'null price': {'price_cents': None},
    'null category': {'category_id': None},
    'null archived flag': {'is_archived': None},
    'zero price': {'price_cents': 0},
    'client-sent id': {'id': 1},
}

INVALID_CATEGORY_UPDATES = {
    'null name': {'name': None},
    'null position': {'position': None},
    'negative position': {'position': -1},
    'position over the limit': {'position': MAX_MENU_POSITION + 1},
    'blank name': {'name': ''},
}


async def test_admin_menu_shows_archived_and_sold_out_rows_the_public_menu_hides(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    mains = await new_category(client, admin, restaurant.id, 'Mains')
    old_menu = await new_category(client, admin, restaurant.id, 'Old Menu')
    empty = await new_category(client, admin, restaurant.id, 'Empty')
    await new_item(client, admin, restaurant.id, mains, 'Pasta')
    sold_out = await new_item(client, admin, restaurant.id, mains, 'Risotto')
    retired = await new_item(client, admin, restaurant.id, mains, 'Truffle Pizza')
    await new_item(client, admin, restaurant.id, old_menu, 'Soup')
    await update_item(client, admin, restaurant.id, sold_out, {'is_available': False})
    await update_item(client, admin, restaurant.id, retired, {'is_archived': True})
    await update_category(client, admin, restaurant.id, old_menu, {'is_archived': True})

    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)
    public_view = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')

    assert admin_view.status_code == 200
    assert [
        (category['name'], category['is_archived'], category_items(category))
        for category in admin_view.json()['categories']
    ] == [
        (
            'Mains',
            False,
            [('Pasta', True, False), ('Risotto', False, False), ('Truffle Pizza', True, True)],
        ),
        ('Old Menu', True, [('Soup', True, False)]),
        ('Empty', False, []),
    ]
    assert empty not in {category['id'] for category in public_view.json()['categories']}
    assert visible_item_names(public_view.json()) == ['Pasta', 'Risotto']


async def test_admin_menu_of_an_inactive_restaurant_is_visible_and_editable(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    await deactivate_restaurant(db_session, restaurant.id)

    created = await create_category(client, admin, restaurant.id, 'Mains')
    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)
    public_view = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')

    assert created.status_code == 201
    assert admin_view.json()['is_active'] is False
    assert [category['name'] for category in admin_view.json()['categories']] == ['Mains']
    assert public_view.status_code == 404


@pytest.mark.parametrize(('method', 'path', 'body'), ADMIN_MENU_ROUTES, ids=ADMIN_MENU_ROUTE_IDS)
async def test_unknown_restaurant_is_404(
    client: AsyncClient, admin: dict[str, str], method: str, path: str, body: dict | None
) -> None:
    response = await client.request(
        method,
        admin_menu_url(UNKNOWN_ID, path.format(category_id=1, item_id=1)),
        json=fill_ids(body, category_id=1),
        headers=admin,
    )

    assert response.status_code == 404


@pytest.mark.parametrize(('method', 'path', 'body'), ADMIN_MENU_ROUTES, ids=ADMIN_MENU_ROUTE_IDS)
async def test_customer_is_forbidden_on_admin_menu_routes(
    client: AsyncClient,
    db_session: AsyncSession,
    admin: dict[str, str],
    customer: dict[str, str],
    method: str,
    path: str,
    body: dict | None,
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Mains')
    item_id = await new_item(client, admin, restaurant.id, category_id, 'Pasta')
    menu_before = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)

    response = await client.request(
        method,
        admin_menu_url(restaurant.id, path.format(category_id=category_id, item_id=item_id)),
        json=fill_ids(body, category_id=category_id),
        headers=customer,
    )
    menu_after = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)

    assert response.status_code == 403
    assert menu_after.json() == menu_before.json()


@pytest.mark.parametrize(('method', 'path', 'body'), ADMIN_MENU_ROUTES, ids=ADMIN_MENU_ROUTE_IDS)
async def test_admin_menu_routes_without_a_token_are_401(
    client: AsyncClient, method: str, path: str, body: dict | None
) -> None:
    response = await client.request(
        method,
        admin_menu_url(1, path.format(category_id=1, item_id=1)),
        json=fill_ids(body, category_id=1),
    )

    assert response.status_code == 401


async def test_new_categories_go_last_and_can_be_reordered(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    starters = await create_category(client, admin, restaurant.id, '  Starters  ')
    mains = await create_category(client, admin, restaurant.id, 'Mains')
    desserts_id = await new_category(client, admin, restaurant.id, 'Desserts')

    moved = await update_category(client, admin, restaurant.id, desserts_id, {'position': 0})
    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)

    assert starters.json()['name'] == 'Starters'
    assert (starters.json()['position'], mains.json()['position']) == (0, 1)
    assert moved.status_code == 200
    assert moved.json()['position'] == 0
    # Equal positions keep creation order.
    assert [category['name'] for category in admin_view.json()['categories']] == [
        'Starters',
        'Desserts',
        'Mains',
    ]


async def test_renamed_category_shows_its_new_name_publicly(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'mains')
    await new_item(client, admin, restaurant.id, category_id, 'Pasta')

    # A case-only rename must not collide with the category's own name.
    response = await update_category(client, admin, restaurant.id, category_id, {'name': 'Mains'})
    public_view = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')

    assert response.status_code == 200
    assert response.json()['name'] == 'Mains'
    assert [category['name'] for category in public_view.json()['categories']] == ['Mains']


async def test_archived_category_hides_and_blocks_its_items_until_unarchived(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str], customer: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Mains')
    pasta = await new_item(client, admin, restaurant.id, category_id, 'Pasta')
    retired = await new_item(client, admin, restaurant.id, category_id, 'Lasagne')
    await update_item(client, admin, restaurant.id, retired, {'is_archived': True})

    archived = await update_category(
        client, admin, restaurant.id, category_id, {'is_archived': True}
    )
    menu_while_archived = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')
    order_while_archived = await place_order(
        client, customer, order_body(restaurant.id, [(pasta, 1)])
    )
    await update_category(client, admin, restaurant.id, category_id, {'is_archived': False})
    menu_after = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')
    order_after = await place_order(client, customer, order_body(restaurant.id, [(pasta, 1)]))

    assert archived.json()['is_archived'] is True
    assert visible_item_names(menu_while_archived.json()) == []
    assert order_while_archived.status_code == 422
    # The item archived on its own stays archived.
    assert visible_item_names(menu_after.json()) == ['Pasta']
    assert order_after.status_code == 201


@pytest.mark.parametrize('existing_is_archived', [False, True], ids=['active', 'archived'])
async def test_duplicate_category_name_is_409_ignoring_case(
    client: AsyncClient,
    db_session: AsyncSession,
    admin: dict[str, str],
    existing_is_archived: bool,
) -> None:
    restaurant = await add_restaurant(db_session)
    pizza = await new_category(client, admin, restaurant.id, 'Pizza')
    pasta = await new_category(client, admin, restaurant.id, 'Pasta')
    await update_category(
        client, admin, restaurant.id, pizza, {'is_archived': existing_is_archived}
    )

    created = await create_category(client, admin, restaurant.id, 'pizza')
    renamed = await update_category(client, admin, restaurant.id, pasta, {'name': 'PIZZA'})
    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)

    assert created.status_code == 409
    assert renamed.status_code == 409
    assert [category['name'] for category in admin_view.json()['categories']] == ['Pizza', 'Pasta']


async def test_same_category_name_is_allowed_in_another_restaurant(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    first = await add_restaurant(db_session)
    second = await add_restaurant(db_session)
    await new_category(client, admin, first.id, 'Pizza')

    response = await create_category(client, admin, second.id, 'Pizza')

    assert response.status_code == 201


async def test_new_item_is_on_the_public_menu_and_orderable_at_its_price(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str], customer: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session, delivery_fee_cents=300)
    category_id = await new_category(client, admin, restaurant.id, 'Pizza')

    created = await create_item(
        client,
        admin,
        restaurant.id,
        {**VALID_ITEM, 'category_id': category_id, 'description': ' Tomato, mozzarella '},
    )
    public_view = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')
    order = await place_order(
        client, customer, order_body(restaurant.id, [(created.json()['id'], 2)])
    )

    assert created.status_code == 201
    assert created.json()['description'] == 'Tomato, mozzarella'
    assert (created.json()['is_available'], created.json()['is_archived']) == (True, False)
    assert public_view.json()['categories'][0]['items'] == [
        {
            'id': created.json()['id'],
            'name': 'Margherita',
            'description': 'Tomato, mozzarella',
            'price_cents': 1400,
            'is_available': True,
        }
    ]
    assert order.json()['total_cents'] == 2 * 1400 + 300


async def test_price_change_applies_to_new_orders_only(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str], customer: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Pizza')
    item_id = await new_item(client, admin, restaurant.id, category_id, 'Margherita', 1400)
    earlier = await place_order(client, customer, order_body(restaurant.id, [(item_id, 1)]))

    repriced = await update_item(client, admin, restaurant.id, item_id, {'price_cents': 1500})
    later = await place_order(client, customer, order_body(restaurant.id, [(item_id, 1)]))
    earlier_now = await client.get(
        f"/api/v1/orders/{earlier.json()['public_id']}", headers=customer
    )

    assert repriced.json()['price_cents'] == 1500
    assert later.json()['items'][0]['unit_price_cents'] == 1500
    assert earlier_now.json()['items'][0]['unit_price_cents'] == 1400


async def test_archived_item_is_hidden_and_unorderable_until_unarchived(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str], customer: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Pizza')
    item_id = await new_item(client, admin, restaurant.id, category_id, 'Truffle Bianca')

    archived = await update_item(client, admin, restaurant.id, item_id, {'is_archived': True})
    menu_while_archived = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')
    order_while_archived = await place_order(
        client, customer, order_body(restaurant.id, [(item_id, 1)])
    )
    await update_item(client, admin, restaurant.id, item_id, {'is_archived': False})
    menu_after = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')
    order_after = await place_order(client, customer, order_body(restaurant.id, [(item_id, 1)]))

    assert archived.json()['is_archived'] is True
    assert visible_item_names(menu_while_archived.json()) == []
    assert order_while_archived.status_code == 422
    assert visible_item_names(menu_after.json()) == ['Truffle Bianca']
    assert order_after.status_code == 201


async def test_sold_out_item_stays_listed_but_is_unorderable_until_available(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str], customer: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Pasta')
    item_id = await new_item(client, admin, restaurant.id, category_id, 'Lobster Ravioli')

    await update_item(client, admin, restaurant.id, item_id, {'is_available': False})
    menu_while_sold_out = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')
    order_while_sold_out = await place_order(
        client, customer, order_body(restaurant.id, [(item_id, 1)])
    )
    await update_item(client, admin, restaurant.id, item_id, {'is_available': True})
    order_after = await place_order(client, customer, order_body(restaurant.id, [(item_id, 1)]))

    assert menu_while_sold_out.json()['categories'][0]['items'][0]['is_available'] is False
    assert order_while_sold_out.status_code == 422
    assert order_after.status_code == 201


@pytest.mark.parametrize('existing_is_archived', [False, True], ids=['active', 'archived'])
async def test_duplicate_item_name_in_a_category_is_409_ignoring_case(
    client: AsyncClient,
    db_session: AsyncSession,
    admin: dict[str, str],
    existing_is_archived: bool,
) -> None:
    restaurant = await add_restaurant(db_session)
    pizza = await new_category(client, admin, restaurant.id, 'Pizza')
    pasta = await new_category(client, admin, restaurant.id, 'Pasta')
    margherita = await new_item(client, admin, restaurant.id, pizza, 'Margherita')
    diavola = await new_item(client, admin, restaurant.id, pizza, 'Diavola')
    pasta_margherita = await new_item(client, admin, restaurant.id, pasta, 'Margherita')
    await update_item(
        client, admin, restaurant.id, margherita, {'is_archived': existing_is_archived}
    )

    created = await create_item(
        client, admin, restaurant.id, {**VALID_ITEM, 'category_id': pizza, 'name': 'MARGHERITA'}
    )
    renamed = await update_item(client, admin, restaurant.id, diavola, {'name': 'margherita'})
    moved = await update_item(
        client, admin, restaurant.id, pasta_margherita, {'category_id': pizza}
    )
    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)

    assert (created.status_code, renamed.status_code, moved.status_code) == (409, 409, 409)
    assert [
        [item['name'] for item in category['items']]
        for category in admin_view.json()['categories']
    ] == [['Margherita', 'Diavola'], ['Margherita']]


async def test_item_moves_between_categories_and_hides_in_an_archived_one(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    specials = await new_category(client, admin, restaurant.id, 'Specials')
    pizza = await new_category(client, admin, restaurant.id, 'Pizza')
    old_menu = await new_category(client, admin, restaurant.id, 'Old Menu')
    await update_category(client, admin, restaurant.id, old_menu, {'is_archived': True})
    item_id = await new_item(client, admin, restaurant.id, specials, 'Margherita')

    to_pizza = await update_item(client, admin, restaurant.id, item_id, {'category_id': pizza})
    menu_in_pizza = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')
    to_old_menu = await update_item(
        client, admin, restaurant.id, item_id, {'category_id': old_menu}
    )
    menu_in_old_menu = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')

    assert (to_pizza.status_code, to_old_menu.status_code) == (200, 200)
    assert [
        (category['name'], [item['name'] for item in category['items']])
        for category in menu_in_pizza.json()['categories']
    ] == [('Pizza', ['Margherita'])]
    assert visible_item_names(menu_in_old_menu.json()) == []


async def test_category_of_another_restaurant_in_the_body_is_422(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    other = await add_restaurant(db_session)
    pizza = await new_category(client, admin, restaurant.id, 'Pizza')
    foreign_category = await new_category(client, admin, other.id, 'Pizza')
    item_id = await new_item(client, admin, restaurant.id, pizza, 'Margherita')

    created = await create_item(
        client,
        admin,
        restaurant.id,
        {**VALID_ITEM, 'name': 'Diavola', 'category_id': foreign_category},
    )
    moved = await update_item(
        client, admin, restaurant.id, item_id, {'category_id': foreign_category}
    )
    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)
    other_view = await client.get(admin_menu_url(other.id, '/menu'), headers=admin)

    assert (created.status_code, moved.status_code) == (422, 422)
    assert category_items(admin_view.json()['categories'][0]) == [('Margherita', True, False)]
    assert other_view.json()['categories'][0]['items'] == []


async def test_category_or_item_of_another_restaurant_in_the_path_is_404(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    other = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Pizza')
    item_id = await new_item(client, admin, restaurant.id, category_id, 'Margherita')

    category_response = await update_category(
        client, admin, other.id, category_id, {'is_archived': True}
    )
    item_response = await update_item(client, admin, other.id, item_id, {'is_archived': True})
    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)

    assert (category_response.status_code, item_response.status_code) == (404, 404)
    assert admin_view.json()['categories'][0]['is_archived'] is False
    assert category_items(admin_view.json()['categories'][0]) == [('Margherita', True, False)]


async def test_item_update_changes_only_the_fields_sent(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str]
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Pizza')
    created = await create_item(
        client,
        admin,
        restaurant.id,
        {**VALID_ITEM, 'category_id': category_id, 'description': 'Tomato, mozzarella'},
    )

    unchanged = await update_item(client, admin, restaurant.id, created.json()['id'], {})
    cleared = await update_item(
        client, admin, restaurant.id, created.json()['id'], {'description': None}
    )

    assert unchanged.status_code == 200
    assert unchanged.json()['description'] == 'Tomato, mozzarella'
    assert cleared.json()['description'] is None
    assert (cleared.json()['name'], cleared.json()['price_cents']) == ('Margherita', 1400)


@pytest.mark.parametrize('overrides', INVALID_ITEM_OVERRIDES.values(), ids=INVALID_ITEM_OVERRIDES)
async def test_invalid_new_item_is_422(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str], overrides: dict
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Pizza')

    response = await create_item(
        client, admin, restaurant.id, {**VALID_ITEM, 'category_id': category_id, **overrides}
    )
    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)

    assert response.status_code == 422
    assert admin_view.json()['categories'][0]['items'] == []


@pytest.mark.parametrize('body', INVALID_ITEM_UPDATES.values(), ids=INVALID_ITEM_UPDATES)
async def test_invalid_item_update_is_422(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str], body: dict
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Pizza')
    item_id = await new_item(client, admin, restaurant.id, category_id, 'Margherita', 1400)

    response = await update_item(client, admin, restaurant.id, item_id, body)
    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)

    assert response.status_code == 422
    item = admin_view.json()['categories'][0]['items'][0]
    assert (item['id'], item['name'], item['price_cents'], item['is_archived']) == (
        item_id,
        'Margherita',
        1400,
        False,
    )


@pytest.mark.parametrize('body', INVALID_CATEGORY_UPDATES.values(), ids=INVALID_CATEGORY_UPDATES)
async def test_invalid_category_update_is_422(
    client: AsyncClient, db_session: AsyncSession, admin: dict[str, str], body: dict
) -> None:
    restaurant = await add_restaurant(db_session)
    category_id = await new_category(client, admin, restaurant.id, 'Pizza')

    response = await update_category(client, admin, restaurant.id, category_id, body)
    admin_view = await client.get(admin_menu_url(restaurant.id, '/menu'), headers=admin)

    assert response.status_code == 422
    category = admin_view.json()['categories'][0]
    assert (category['name'], category['position']) == ('Pizza', 0)


async def test_zero_restaurant_id_in_the_path_is_422(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.get(admin_menu_url(0, '/menu'), headers=admin)

    assert response.status_code == 422


async def test_two_admins_creating_the_same_category_at_once_only_one_wins(
    committed_client: AsyncClient, committed_session: AsyncSession
) -> None:
    first_admin = await signup_admin_and_login(committed_client, committed_session)
    second_admin = await signup_admin_and_login(committed_client, committed_session)
    restaurant = await add_restaurant(committed_session)
    await committed_session.commit()

    responses = await gather(
        create_category(committed_client, first_admin, restaurant.id, 'Specials'),
        create_category(committed_client, second_admin, restaurant.id, 'specials'),
    )
    admin_view = await committed_client.get(
        admin_menu_url(restaurant.id, '/menu'), headers=first_admin
    )

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert len(admin_view.json()['categories']) == 1


async def new_category(
    client: AsyncClient, admin: dict[str, str], restaurant_id: int, name: str
) -> int:
    response = await create_category(client, admin, restaurant_id, name)
    assert response.status_code == 201, response.text
    return response.json()['id']


async def new_item(
    client: AsyncClient,
    admin: dict[str, str],
    restaurant_id: int,
    category_id: int,
    name: str,
    price_cents: int = 1000,
) -> int:
    response = await create_item(
        client,
        admin,
        restaurant_id,
        {'category_id': category_id, 'name': name, 'price_cents': price_cents},
    )
    assert response.status_code == 201, response.text
    return response.json()['id']


def fill_ids(body: dict | None, *, category_id: int) -> dict | None:
    """Replaces the '{category_id}' placeholder in a route's sample body."""
    if body is None:
        return None
    return {key: category_id if value == '{category_id}' else value for key, value in body.items()}


def category_items(category: dict) -> list[tuple[str, bool, bool]]:
    return [
        (item['name'], item['is_available'], item['is_archived']) for item in category['items']
    ]


def visible_item_names(menu: dict) -> list[str]:
    return [item['name'] for category in menu['categories'] for item in category['items']]
