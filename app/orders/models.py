from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Identity,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.core.db import Base


class OrderStatus(StrEnum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    OUT_FOR_DELIVERY = 'out_for_delivery'
    DELIVERED = 'delivered'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'


def status_type(constraint_name: str) -> Enum:
    # Text + CHECK, not a Postgres enum: a new status swaps the CHECK (and widens the
    # column if longer than the current longest value) instead of ALTER TYPE.
    return Enum(
        OrderStatus,
        name=constraint_name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda statuses: [status.value for status in statuses],
    )


class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (
        CheckConstraint('subtotal_cents > 0', name='subtotal_cents_positive'),
        CheckConstraint('delivery_fee_cents >= 0', name='delivery_fee_cents_non_negative'),
        CheckConstraint(
            'total_cents = subtotal_cents + delivery_fee_cents', name='total_cents_sum'
        ),
        UniqueConstraint('customer_id', 'idempotency_key'),
        Index(
            'ix_orders_customer_id_created_at_public_id', 'customer_id', 'created_at', 'public_id'
        ),
        Index('ix_orders_created_at_public_id', 'created_at', 'public_id'),
        Index('ix_orders_status_created_at_public_id', 'status', 'created_at', 'public_id'),
        Index(
            'ix_orders_restaurant_id_created_at_public_id',
            'restaurant_id',
            'created_at',
            'public_id',
        ),
    )
    # Fetches updated_at back on UPDATE, so it never has to be lazy-loaded after a commit.
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(default=uuid4, unique=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    restaurant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('restaurants.id'))
    status: Mapped[OrderStatus] = mapped_column(status_type('status'))
    delivery_address: Mapped[str]
    phone: Mapped[str]
    notes: Mapped[str | None]
    subtotal_cents: Mapped[int]
    delivery_fee_cents: Mapped[int]
    total_cents: Mapped[int]
    idempotency_key: Mapped[UUID]
    idempotency_fingerprint: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    customer: Mapped[User] = relationship(lazy='raise')
    items: Mapped[list[OrderItem]] = relationship(lazy='raise', order_by='OrderItem.id')
    status_events: Mapped[list[OrderStatusEvent]] = relationship(
        lazy='raise', order_by='OrderStatusEvent.id'
    )


class OrderItem(Base):
    """A line of an order; name and price are snapshots taken when the order was placed."""

    __tablename__ = 'order_items'
    __table_args__ = (
        CheckConstraint('unit_price_cents > 0', name='unit_price_cents_positive'),
        CheckConstraint('quantity > 0', name='quantity_positive'),
        UniqueConstraint('order_id', 'menu_item_id'),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('orders.id'))
    menu_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('menu_items.id'))
    name: Mapped[str]
    unit_price_cents: Mapped[int]
    quantity: Mapped[int]


class OrderStatusEvent(Base):
    __tablename__ = 'order_status_events'
    __table_args__ = (
        Index('ix_order_status_events_order_id_created_at', 'order_id', 'created_at'),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('orders.id'))
    # None on the event that records the order's creation.
    from_status: Mapped[OrderStatus | None] = mapped_column(status_type('from_status'))
    to_status: Mapped[OrderStatus] = mapped_column(status_type('to_status'))
    actor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    actor: Mapped[User] = relationship(lazy='raise')
