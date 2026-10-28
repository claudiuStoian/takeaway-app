from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Response, status

from app.auth.dependencies import CurrentUserDep
from app.core.db import SessionDep
from app.core.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.orders.schemas import OrderPageResponse, OrderPlaceRequest, OrderResponse
from app.orders.service import OrderService

router = APIRouter(prefix='/orders', tags=['orders'])


@router.post('', response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    session: SessionDep,
    customer: CurrentUserDep,
    request: OrderPlaceRequest,
    idempotency_key: Annotated[UUID, Header()],
    response: Response,
) -> OrderResponse:
    order, is_new = await OrderService.place(session, customer, idempotency_key, request)
    if not is_new:
        response.status_code = status.HTTP_200_OK
    return order


@router.get('', response_model=OrderPageResponse)
async def list_my_orders(
    session: SessionDep,
    customer: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    cursor: str | None = None,
) -> OrderPageResponse:
    return await OrderService.list_page(session, customer, limit=limit, cursor=cursor)


@router.get('/{public_id}', response_model=OrderResponse)
async def get_my_order(
    session: SessionDep, customer: CurrentUserDep, public_id: UUID
) -> OrderResponse:
    return await OrderService.get(session, customer, public_id)


@router.post('/{public_id}/cancel', response_model=OrderResponse)
async def cancel_my_order(
    session: SessionDep, customer: CurrentUserDep, public_id: UUID
) -> OrderResponse:
    return await OrderService.cancel(session, customer, public_id)
