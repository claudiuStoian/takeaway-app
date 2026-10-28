from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Restaurant(Base):
    __tablename__ = 'restaurants'
    __table_args__ = (
        CheckConstraint('delivery_fee_cents >= 0', name='delivery_fee_cents_non_negative'),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str]
    description: Mapped[str]
    cuisine: Mapped[str]
    address: Mapped[str]
    delivery_fee_cents: Mapped[int]
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    categories: Mapped[list[MenuCategory]] = relationship(
        lazy='raise', order_by='[MenuCategory.position, MenuCategory.id]'
    )


class MenuCategory(Base):
    __tablename__ = 'menu_categories'
    # Target of menu_items' composite FK, which keeps an item's category in its restaurant.
    __table_args__ = (UniqueConstraint('restaurant_id', 'id'),)
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('restaurants.id'))
    name: Mapped[str]
    position: Mapped[int]
    is_archived: Mapped[bool] = mapped_column(server_default=false())

    items: Mapped[list[MenuItem]] = relationship(lazy='raise', order_by='MenuItem.id')


class MenuItem(Base):
    __tablename__ = 'menu_items'
    __table_args__ = (
        ForeignKeyConstraint(
            ['restaurant_id', 'category_id'],
            ['menu_categories.restaurant_id', 'menu_categories.id'],
        ),
        CheckConstraint('price_cents > 0', name='price_cents_positive'),
    )
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger)
    category_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str]
    description: Mapped[str | None]
    price_cents: Mapped[int]
    is_available: Mapped[bool] = mapped_column(server_default=true())
    is_archived: Mapped[bool] = mapped_column(server_default=false())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


# Case-insensitive unique names, archived rows included: re-adding a name means un-archiving.
Index(
    'uq_menu_categories_restaurant_id_lower_name',
    MenuCategory.restaurant_id,
    func.lower(MenuCategory.name),
    unique=True,
)
Index(
    'uq_menu_items_category_id_lower_name',
    MenuItem.category_id,
    func.lower(MenuItem.name),
    unique=True,
)
