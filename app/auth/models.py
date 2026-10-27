from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Enum, Identity, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UserRole(StrEnum):
    CUSTOMER = 'customer'
    ADMIN = 'admin'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(default=uuid4, unique=True)
    email: Mapped[str] = mapped_column(unique=True)
    hashed_password: Mapped[str]
    full_name: Mapped[str]
    # Text + CHECK rather than a Postgres enum type: adding a role needs no ALTER TYPE.
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name='role',
            native_enum=False,
            create_constraint=True,
            values_callable=lambda roles: [role.value for role in roles],
        )
    )
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
