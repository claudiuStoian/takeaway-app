from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.auth.schemas import UserSummaryResponse
from app.core.limits import (
    MAX_DELIVERY_ADDRESS_LENGTH,
    MAX_LINES_PER_ORDER,
    MAX_ORDER_NOTES_LENGTH,
    MAX_PHONE_LENGTH,
    MAX_QUANTITY_PER_ITEM,
    MIN_PHONE_LENGTH,
)
from app.orders.models import OrderStatus

PHONE_PATTERN = r'^[0-9 +()-]+$'

DeliveryAddress = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_DELIVERY_ADDRESS_LENGTH),
]
Phone = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=MIN_PHONE_LENGTH,
        max_length=MAX_PHONE_LENGTH,
        pattern=PHONE_PATTERN,
    ),
]
OrderNotes = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=MAX_ORDER_NOTES_LENGTH)
]


class OrderItemRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    menu_item_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=MAX_QUANTITY_PER_ITEM)


class OrderPlaceRequest(BaseModel):
    """Has no price or total fields: the server computes them from the current menu."""

    model_config = ConfigDict(extra='forbid')

    restaurant_id: int = Field(ge=1)
    items: list[OrderItemRequest] = Field(min_length=1, max_length=MAX_LINES_PER_ORDER)
    delivery_address: DeliveryAddress
    phone: Phone
    notes: OrderNotes | None = None

    @field_validator('items')
    @classmethod
    def reject_repeated_items(cls, items: list[OrderItemRequest]) -> list[OrderItemRequest]:
        menu_item_ids = [item.menu_item_id for item in items]
        if len(set(menu_item_ids)) != len(menu_item_ids):
            raise ValueError("Each menu item may appear only once; use quantity instead.")
        return items

    @field_validator('notes')
    @classmethod
    def store_blank_notes_as_none(cls, notes: str | None) -> str | None:
        # One value for "no notes", so a blank and an omitted field fingerprint the same.
        return notes or None


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    menu_item_id: int
    name: str
    unit_price_cents: int
    quantity: int


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    restaurant_id: int
    status: OrderStatus
    delivery_address: str
    phone: str
    notes: str | None
    subtotal_cents: int
    delivery_fee_cents: int
    total_cents: int
    items: list[OrderItemResponse]
    created_at: datetime
    updated_at: datetime


class OrderPageResponse(BaseModel):
    items: list[OrderResponse]
    next_cursor: str | None


class OrderStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    to: OrderStatus


class AdminOrderResponse(OrderResponse):
    customer: UserSummaryResponse


class AdminOrderPageResponse(BaseModel):
    items: list[AdminOrderResponse]
    next_cursor: str | None


class OrderStatusEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: OrderStatus | None
    to_status: OrderStatus
    actor: UserSummaryResponse
    created_at: datetime
