from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from app.restaurants.models import MenuCategory, MenuItem, Restaurant
from app.restaurants.schemas import (
    AdminCategoryRead,
    AdminMenuItemRead,
    AdminMenuRead,
    MenuCategoryCreate,
    MenuCategoryUpdate,
    MenuItemCreate,
    MenuItemUpdate,
)
from app.restaurants.service import RestaurantNotFound


class MenuCategoryNotFound(NotFoundError):
    detail = 'Menu category not found.'


class MenuItemNotFound(NotFoundError):
    detail = 'Menu item not found.'


class CategoryNotInRestaurant(InvalidInputError):
    detail = 'The category does not belong to this restaurant.'


class DuplicateCategoryName(ConflictError):
    detail = 'This restaurant already has a category with this name; un-archive it to reuse it.'


class DuplicateItemName(ConflictError):
    detail = 'This category already has an item with this name; un-archive it to reuse it.'


class AdminMenuService:
    """Menu management for staff; only admin routes may call these.

    Every write locks the restaurant row first, so menu writes for one restaurant run one at a
    time and the duplicate-name checks are exact.
    """

    @classmethod
    async def get_menu(cls, session: AsyncSession, restaurant_id: int) -> AdminMenuRead:
        query = (
            select(Restaurant)
            .where(Restaurant.id == restaurant_id)
            .options(selectinload(Restaurant.categories).selectinload(MenuCategory.items))
            # Replace collections the session may already hold filtered by the public menu.
            .execution_options(populate_existing=True)
        )
        if (restaurant := await session.scalar(query)) is None:
            raise RestaurantNotFound
        return AdminMenuRead.model_validate(restaurant)

    @classmethod
    async def create_category(
        cls, session: AsyncSession, restaurant_id: int, request: MenuCategoryCreate
    ) -> AdminCategoryRead:
        await cls._lock_restaurant(session, restaurant_id)
        await cls._ensure_category_name_is_free(session, restaurant_id, request.name)

        last_position = await session.scalar(
            select(func.max(MenuCategory.position)).where(
                MenuCategory.restaurant_id == restaurant_id
            )
        )
        category = MenuCategory(
            restaurant_id=restaurant_id,
            name=request.name,
            position=0 if last_position is None else last_position + 1,
        )
        session.add(category)
        await session.commit()
        return AdminCategoryRead.model_validate(category)

    @classmethod
    async def update_category(
        cls,
        session: AsyncSession,
        restaurant_id: int,
        category_id: int,
        request: MenuCategoryUpdate,
    ) -> AdminCategoryRead:
        await cls._lock_restaurant(session, restaurant_id)
        category = await session.scalar(
            select(MenuCategory).where(
                MenuCategory.id == category_id, MenuCategory.restaurant_id == restaurant_id
            )
        )
        if category is None:
            raise MenuCategoryNotFound

        changes = request.model_dump(exclude_unset=True)
        if 'name' in changes:
            await cls._ensure_category_name_is_free(
                session, restaurant_id, changes['name'], category.id
            )
        for field, value in changes.items():
            setattr(category, field, value)
        await session.commit()
        return AdminCategoryRead.model_validate(category)

    @classmethod
    async def create_item(
        cls, session: AsyncSession, restaurant_id: int, request: MenuItemCreate
    ) -> AdminMenuItemRead:
        await cls._lock_restaurant(session, restaurant_id)
        await cls._ensure_category_is_in_restaurant(session, restaurant_id, request.category_id)
        await cls._ensure_item_name_is_free(session, request.category_id, request.name)

        item = MenuItem(restaurant_id=restaurant_id, **request.model_dump())
        session.add(item)
        await session.commit()
        return AdminMenuItemRead.model_validate(item)

    @classmethod
    async def update_item(
        cls, session: AsyncSession, restaurant_id: int, item_id: int, request: MenuItemUpdate
    ) -> AdminMenuItemRead:
        await cls._lock_restaurant(session, restaurant_id)
        item = await session.scalar(
            select(MenuItem).where(MenuItem.id == item_id, MenuItem.restaurant_id == restaurant_id)
        )
        if item is None:
            raise MenuItemNotFound

        changes = request.model_dump(exclude_unset=True)
        if 'category_id' in changes:
            await cls._ensure_category_is_in_restaurant(
                session, restaurant_id, changes['category_id']
            )
        if 'name' in changes or 'category_id' in changes:
            await cls._ensure_item_name_is_free(
                session,
                changes.get('category_id', item.category_id),
                changes.get('name', item.name),
                item.id,
            )
        for field, value in changes.items():
            setattr(item, field, value)
        await session.commit()
        return AdminMenuItemRead.model_validate(item)

    @staticmethod
    async def _lock_restaurant(session: AsyncSession, restaurant_id: int) -> None:
        # NO KEY UPDATE doesn't block the FK check of an order being placed at this restaurant.
        locked_id = await session.scalar(
            select(Restaurant.id)
            .where(Restaurant.id == restaurant_id)
            .with_for_update(key_share=True)
        )
        if locked_id is None:
            raise RestaurantNotFound

    @staticmethod
    async def _ensure_category_name_is_free(
        session: AsyncSession, restaurant_id: int, name: str, category_id: int | None = None
    ) -> None:
        query = select(MenuCategory.id).where(
            MenuCategory.restaurant_id == restaurant_id,
            func.lower(MenuCategory.name) == func.lower(name),
        )
        if category_id is not None:
            query = query.where(MenuCategory.id != category_id)
        if await session.scalar(query) is not None:
            raise DuplicateCategoryName

    @staticmethod
    async def _ensure_category_is_in_restaurant(
        session: AsyncSession, restaurant_id: int, category_id: int
    ) -> None:
        found_id = await session.scalar(
            select(MenuCategory.id).where(
                MenuCategory.id == category_id, MenuCategory.restaurant_id == restaurant_id
            )
        )
        if found_id is None:
            raise CategoryNotInRestaurant

    @staticmethod
    async def _ensure_item_name_is_free(
        session: AsyncSession, category_id: int, name: str, item_id: int | None = None
    ) -> None:
        query = select(MenuItem.id).where(
            MenuItem.category_id == category_id,
            func.lower(MenuItem.name) == func.lower(name),
        )
        if item_id is not None:
            query = query.where(MenuItem.id != item_id)
        if await session.scalar(query) is not None:
            raise DuplicateItemName
