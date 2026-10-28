from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.auth.dependencies import AdminDep
from app.core.db import SessionDep
from app.core.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.orders.admin_service import AdminOrderService
from app.orders.models import OrderStatus
from app.orders.schemas import (
    AdminOrderPageResponse,
    AdminOrderResponse,
    OrderStatusEventResponse,
    OrderStatusUpdateRequest,
)

router = APIRouter(prefix='/admin/orders', tags=['admin orders'])


@router.get('', response_model=AdminOrderPageResponse)
async def list_orders(
    session: SessionDep,
    _: AdminDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    cursor: str | None = None,
    status: OrderStatus | None = None,
    restaurant_id: Annotated[int | None, Query(ge=1)] = None,
) -> AdminOrderPageResponse:
    return await AdminOrderService.list_page(
        session, limit=limit, cursor=cursor, status=status, restaurant_id=restaurant_id
    )


@router.get('/{public_id}', response_model=AdminOrderResponse)
async def get_order(session: SessionDep, _: AdminDep, public_id: UUID) -> AdminOrderResponse:
    return await AdminOrderService.get(session, public_id)


@router.post('/{public_id}/status', response_model=AdminOrderResponse)
async def change_order_status(
    session: SessionDep, admin: AdminDep, public_id: UUID, request: OrderStatusUpdateRequest
) -> AdminOrderResponse:
    return await AdminOrderService.change_status(session, admin, public_id, request.to)


@router.get('/{public_id}/history', response_model=list[OrderStatusEventResponse])
async def list_order_history(
    session: SessionDep, _: AdminDep, public_id: UUID
) -> list[OrderStatusEventResponse]:
    return await AdminOrderService.list_history(session, public_id)
