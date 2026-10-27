"""auth

Revision ID: 6bb4d5802196
Revises: 4c3a4377edb8
Create Date: 2026-10-27 21:48:37.150313

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '6bb4d5802196'
down_revision: str | None = '4c3a4377edb8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('public_id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('hashed_password', sa.Text(), nullable=False),
        sa.Column('full_name', sa.Text(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('customer', 'admin', name='role', native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
        sa.UniqueConstraint('email', name=op.f('uq_users_email')),
        sa.UniqueConstraint('public_id', name=op.f('uq_users_public_id')),
    )


def downgrade() -> None:
    op.drop_table('users')
