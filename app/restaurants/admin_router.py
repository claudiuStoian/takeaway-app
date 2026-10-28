from typing import Annotated

from fastapi import APIRouter, Path, status

from app.auth.dependencies import AdminDep
from app.core.db import SessionDep
from app.restaurants.admin_service import AdminMenuService
from app.restaurants.schemas import (
    AdminMenuCategoryResponse,
    AdminMenuItemResponse,
    AdminMenuResponse,
    MenuCategoryCreateRequest,
    MenuCategoryUpdateRequest,
    MenuItemCreateRequest,
    MenuItemUpdateRequest,
)

router = APIRouter(prefix='/admin/restaurants/{restaurant_id}', tags=['admin menus'])

DbId = Annotated[int, Path(ge=1)]


@router.get('/menu', response_model=AdminMenuResponse)
async def get_admin_menu(
    session: SessionDep, _: AdminDep, restaurant_id: DbId
) -> AdminMenuResponse:
    return await AdminMenuService.get_menu(session, restaurant_id)


@router.post(
    '/categories', response_model=AdminMenuCategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    session: SessionDep, _: AdminDep, restaurant_id: DbId, request: MenuCategoryCreateRequest
) -> AdminMenuCategoryResponse:
    return await AdminMenuService.create_category(session, restaurant_id, request)


@router.patch('/categories/{category_id}', response_model=AdminMenuCategoryResponse)
async def update_category(
    session: SessionDep,
    _: AdminDep,
    restaurant_id: DbId,
    category_id: DbId,
    request: MenuCategoryUpdateRequest,
) -> AdminMenuCategoryResponse:
    return await AdminMenuService.update_category(session, restaurant_id, category_id, request)


@router.post('/items', response_model=AdminMenuItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    session: SessionDep, _: AdminDep, restaurant_id: DbId, request: MenuItemCreateRequest
) -> AdminMenuItemResponse:
    return await AdminMenuService.create_item(session, restaurant_id, request)


@router.patch('/items/{item_id}', response_model=AdminMenuItemResponse)
async def update_item(
    session: SessionDep,
    _: AdminDep,
    restaurant_id: DbId,
    item_id: DbId,
    request: MenuItemUpdateRequest,
) -> AdminMenuItemResponse:
    return await AdminMenuService.update_item(session, restaurant_id, item_id, request)
