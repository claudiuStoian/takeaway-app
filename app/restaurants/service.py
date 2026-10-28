from sqlalchemy import Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.restaurants.models import MenuCategory, MenuItem, Restaurant
from app.restaurants.schemas import MenuResponse, RestaurantPageResponse, RestaurantResponse


class RestaurantNotFound(NotFoundError):
    detail = 'Restaurant not found.'


class RestaurantService:
    @classmethod
    async def list_page(
        cls, session: AsyncSession, *, limit: int, cursor: str | None, cuisine: str | None
    ) -> RestaurantPageResponse:
        query = cls._build_list_query(limit, cursor, cuisine)
        rows = list(await session.scalars(query))

        return RestaurantPageResponse(
            items=[RestaurantResponse.model_validate(restaurant) for restaurant in rows[:limit]],
            next_cursor=cls._next_cursor(rows, limit),
        )

    @classmethod
    async def get_menu(cls, session: AsyncSession, restaurant_id: int) -> MenuResponse:
        restaurant = await session.scalar(cls._build_menu_query(restaurant_id))
        if restaurant is None:
            raise RestaurantNotFound

        menu = MenuResponse.model_validate(restaurant)
        menu.categories = [category for category in menu.categories if category.items]
        return menu

    @staticmethod
    def _build_list_query(limit: int, cursor: str | None, cuisine: str | None) -> Select:
        query = (
            select(Restaurant)
            .where(Restaurant.is_active)
            .order_by(Restaurant.name, Restaurant.id)
            # One extra row tells us whether there is a next page.
            .limit(limit + 1)
        )
        if cuisine is not None:
            query = query.where(Restaurant.cuisine == cuisine)
        if cursor is not None:
            name, restaurant_id = decode_cursor(cursor, expected_types=(str, int))
            query = query.where(tuple_(Restaurant.name, Restaurant.id) > (name, restaurant_id))
        return query

    @staticmethod
    def _next_cursor(rows: list[Restaurant], limit: int) -> str | None:
        if len(rows) <= limit:
            return None

        last_shown = rows[limit - 1]
        return encode_cursor([last_shown.name, last_shown.id])

    @staticmethod
    def _build_menu_query(restaurant_id: int) -> Select:
        visible_categories = Restaurant.categories.and_(MenuCategory.is_archived.is_(False))
        visible_items = MenuCategory.items.and_(MenuItem.is_archived.is_(False))
        return (
            select(Restaurant)
            .where(Restaurant.id == restaurant_id, Restaurant.is_active)
            .options(selectinload(visible_categories).selectinload(visible_items))
            # Re-filter collections the session may already hold unfiltered.
            .execution_options(populate_existing=True)
        )
