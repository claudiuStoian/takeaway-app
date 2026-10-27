from pydantic import BaseModel, ConfigDict, Field

from app.core.limits import MAX_DELIVERY_FEE_CENTS, MAX_ITEM_PRICE_CENTS

CUISINE_PATTERN = r'^[a-z]+(-[a-z]+)*$'


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


class MenuItemSeed(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1)
    description: str | None = None
    price_cents: int = Field(gt=0, le=MAX_ITEM_PRICE_CENTS)
    is_available: bool = True
    is_archived: bool = False


class MenuCategorySeed(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1)
    items: list[MenuItemSeed] = Field(min_length=1)


class RestaurantSeed(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    cuisine: str = Field(pattern=CUISINE_PATTERN)
    address: str = Field(min_length=1)
    delivery_fee_cents: int = Field(ge=0, le=MAX_DELIVERY_FEE_CENTS)
    categories: list[MenuCategorySeed] = Field(min_length=1)
