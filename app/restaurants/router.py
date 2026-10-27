from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.core.db import SessionDep
from app.core.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.restaurants.schemas import CUISINE_PATTERN, MenuRead, RestaurantPage
from app.restaurants.service import RestaurantService

router = APIRouter(prefix='/restaurants', tags=['restaurants'])


@router.get('', response_model=RestaurantPage)
async def list_restaurants(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    cursor: str | None = None,
    cuisine: Annotated[str | None, Query(pattern=CUISINE_PATTERN)] = None,
) -> RestaurantPage:
    return await RestaurantService.list_page(session, limit=limit, cursor=cursor, cuisine=cuisine)


@router.get('/{restaurant_id}/menu', response_model=MenuRead)
async def get_menu(session: SessionDep, restaurant_id: Annotated[int, Path(ge=1)]) -> MenuRead:
    return await RestaurantService.get_menu(session, restaurant_id)
