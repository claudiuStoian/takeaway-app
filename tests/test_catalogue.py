import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.cli import RESTAURANTS_SEED_FILE
from app.restaurants.seed import CatalogueSeedService
from tests.builders import (
    UNKNOWN_ID,
    add_category,
    add_item,
    add_restaurant,
    add_restaurant_sync,
    count_restaurants_sync,
    random_cuisine,
    raw_cursor,
)

pytestmark = pytest.mark.anyio

MAX_PAGES = 20

RESTAURANT_KEYS = {'id', 'name', 'description', 'cuisine', 'address', 'delivery_fee_cents'}
CATEGORY_KEYS = {'id', 'name', 'items'}
MENU_ITEM_KEYS = {'id', 'name', 'description', 'price_cents', 'is_available'}


async def test_list_pages_by_name_then_id_without_gaps_or_repeats(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    cuisine = random_cuisine()
    first_b = await add_restaurant(db_session, name='B', cuisine=cuisine)
    a = await add_restaurant(db_session, name='A', cuisine=cuisine)
    c = await add_restaurant(db_session, name='C', cuisine=cuisine)
    second_b = await add_restaurant(db_session, name='B', cuisine=cuisine)
    third_b = await add_restaurant(db_session, name='B', cuisine=cuisine)
    await add_restaurant(db_session, name='A inactive', cuisine=cuisine, is_active=False)

    pages = await walk_restaurant_pages(client, cuisine, limit=2)

    assert [len(page['items']) for page in pages] == [2, 2, 1]
    assert pages[-1]['next_cursor'] is None
    seen_ids = [restaurant['id'] for page in pages for restaurant in page['items']]
    assert seen_ids == [a.id, first_b.id, second_b.id, third_b.id, c.id]


async def test_list_returns_only_public_restaurant_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    cuisine = random_cuisine()
    await add_restaurant(db_session, cuisine=cuisine)

    response = await client.get('/api/v1/restaurants', params={'cuisine': cuisine})

    assert response.status_code == 200
    assert [set(restaurant) for restaurant in response.json()['items']] == [RESTAURANT_KEYS]


@pytest.mark.parametrize(
    'params',
    [
        {'cursor': 'not base64!'},
        {'cursor': raw_cursor([1, 'A'])},
        {'cursor': raw_cursor(['A', True])},
        {'cursor': raw_cursor(['A'])},
        {'limit': 0},
        {'limit': 101},
        {'cuisine': 'Italian'},
    ],
    ids=[
        'malformed-cursor',
        'cursor-types-swapped',
        'cursor-bool-id',
        'cursor-too-short',
        'limit-zero',
        'limit-over-max',
        'cuisine-uppercase',
    ],
)
async def test_list_rejects_bad_query_params(client: AsyncClient, params: dict) -> None:
    response = await client.get('/api/v1/restaurants', params=params)

    assert response.status_code == 422


async def test_menu_shows_only_visible_categories_and_items_in_position_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    restaurant = await add_restaurant(db_session)
    drinks = await add_category(db_session, restaurant, name='Drinks', position=2)
    mains = await add_category(db_session, restaurant, name='Mains', position=1)
    archived = await add_category(db_session, restaurant, name='Old', position=0, is_archived=True)
    emptied = await add_category(db_session, restaurant, name='Emptied', position=3)
    await add_item(db_session, drinks, name='Lemonade', price_cents=300)
    await add_item(db_session, mains, name='Burger', price_cents=1250)
    await add_item(db_session, mains, name='Soup', price_cents=700, is_available=False)
    await add_item(db_session, mains, name='Retired', is_archived=True)
    await add_item(db_session, archived, name='Hidden by category')
    await add_item(db_session, emptied, name='Only archived', is_archived=True)

    response = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')

    assert response.status_code == 200
    menu = response.json()
    assert set(menu) == RESTAURANT_KEYS | {'categories'}
    assert [category['name'] for category in menu['categories']] == ['Mains', 'Drinks']
    assert all(set(category) == CATEGORY_KEYS for category in menu['categories'])
    mains_items = menu['categories'][0]['items']
    assert [(item['name'], item['price_cents'], item['is_available']) for item in mains_items] == [
        ('Burger', 1250, True),
        ('Soup', 700, False),
    ]
    assert all(set(item) == MENU_ITEM_KEYS for item in mains_items)


async def test_menu_of_an_inactive_restaurant_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    restaurant = await add_restaurant(db_session, is_active=False)

    response = await client.get(f'/api/v1/restaurants/{restaurant.id}/menu')

    assert response.status_code == 404


@pytest.mark.parametrize(
    ('restaurant_id', 'status_code'),
    [(UNKNOWN_ID, 404), (0, 422)],
    ids=['unknown', 'zero'],
)
async def test_menu_with_a_bad_restaurant_id(
    client: AsyncClient, restaurant_id: int, status_code: int
) -> None:
    response = await client.get(f'/api/v1/restaurants/{restaurant_id}/menu')

    assert response.status_code == status_code


def test_seed_adds_nothing_when_restaurants_exist(sync_db_session: Session) -> None:
    add_restaurant_sync(sync_db_session)
    count_before = count_restaurants_sync(sync_db_session)

    added = CatalogueSeedService.seed_if_empty(sync_db_session, RESTAURANTS_SEED_FILE)

    assert added == 0
    assert count_restaurants_sync(sync_db_session) == count_before


async def walk_restaurant_pages(client: AsyncClient, cuisine: str, limit: int) -> list[dict]:
    pages = []
    seen_cursors = set()
    params = {'cuisine': cuisine, 'limit': limit}
    for _ in range(MAX_PAGES):
        response = await client.get('/api/v1/restaurants', params=params)
        assert response.status_code == 200, response.text
        pages.append(response.json())
        if (cursor := response.json()['next_cursor']) is None:
            return pages
        assert cursor not in seen_cursors, 'The cursor repeated instead of moving forward.'
        seen_cursors.add(cursor)
        params['cursor'] = cursor
    pytest.fail(f'No last page after {MAX_PAGES} pages.')
