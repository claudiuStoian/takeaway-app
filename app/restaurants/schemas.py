from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.limits import (
    MAX_DB_ID,
    MAX_DELIVERY_FEE_CENTS,
    MAX_ITEM_PRICE_CENTS,
    MAX_MENU_DESCRIPTION_LENGTH,
    MAX_MENU_NAME_LENGTH,
    MAX_MENU_POSITION,
)

CUISINE_PATTERN = r'^[a-z]+(-[a-z]+)*$'

MenuName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MENU_NAME_LENGTH)
]
MenuDescription = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MENU_DESCRIPTION_LENGTH),
]


class RestaurantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    cuisine: str
    address: str
    delivery_fee_cents: int


class RestaurantPage(BaseModel):
    items: list[RestaurantRead]
    next_cursor: str | None


class MenuItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    price_cents: int
    is_available: bool


class MenuCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    items: list[MenuItemRead]


class MenuRead(RestaurantRead):
    categories: list[MenuCategoryRead]


class AdminMenuItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    name: str
    description: str | None
    price_cents: int
    is_available: bool
    is_archived: bool
    updated_at: datetime


class AdminCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    position: int
    is_archived: bool


class AdminMenuCategoryRead(AdminCategoryRead):
    items: list[AdminMenuItemRead]


class AdminMenuRead(RestaurantRead):
    """Every category and item, archived ones included, with their flags."""

    is_active: bool
    categories: list[AdminMenuCategoryRead]


class MenuCategoryCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: MenuName


class MenuCategoryUpdate(BaseModel):
    """Only the fields sent are changed."""

    model_config = ConfigDict(extra='forbid')

    name: MenuName | None = None
    position: int | None = Field(default=None, ge=0, le=MAX_MENU_POSITION)
    is_archived: bool | None = None

    @field_validator('name', 'position', 'is_archived')
    @classmethod
    def reject_null(cls, value: object) -> object:
        return reject_null(value)


class MenuItemCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    category_id: int = Field(ge=1, le=MAX_DB_ID)
    name: MenuName
    description: MenuDescription | None = None
    price_cents: int = Field(gt=0, le=MAX_ITEM_PRICE_CENTS)
    is_available: bool = True


class MenuItemUpdate(BaseModel):
    """Only the fields sent are changed; `description` may be set to null to clear it."""

    model_config = ConfigDict(extra='forbid')

    category_id: int | None = Field(default=None, ge=1, le=MAX_DB_ID)
    name: MenuName | None = None
    description: MenuDescription | None = None
    price_cents: int | None = Field(default=None, gt=0, le=MAX_ITEM_PRICE_CENTS)
    is_available: bool | None = None
    is_archived: bool | None = None

    @field_validator('category_id', 'name', 'price_cents', 'is_available', 'is_archived')
    @classmethod
    def reject_null(cls, value: object) -> object:
        return reject_null(value)


class MenuItemSeed(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: MenuName
    description: MenuDescription | None = None
    price_cents: int = Field(gt=0, le=MAX_ITEM_PRICE_CENTS)
    is_available: bool = True
    is_archived: bool = False


class MenuCategorySeed(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: MenuName
    items: list[MenuItemSeed] = Field(min_length=1)


class RestaurantSeed(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    cuisine: str = Field(pattern=CUISINE_PATTERN)
    address: str = Field(min_length=1)
    delivery_fee_cents: int = Field(ge=0, le=MAX_DELIVERY_FEE_CENTS)
    categories: list[MenuCategorySeed] = Field(min_length=1)


def reject_null(value: object) -> object:
    """A field left out of a partial update keeps its value; an explicit null is an error."""
    if value is None:
        raise ValueError('may be left out, but not set to null')
    return value
