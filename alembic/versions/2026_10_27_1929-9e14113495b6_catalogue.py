"""catalogue

Revision ID: 9e14113495b6
Revises:
Create Date: 2026-10-27 19:29:40.447705

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9e14113495b6'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'restaurant',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('cuisine', sa.Text(), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('delivery_fee_cents', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            'delivery_fee_cents >= 0', name=op.f('ck_restaurant_delivery_fee_cents_non_negative')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_restaurant')),
    )
    op.create_index(
        'ix_restaurant_cuisine_name_id', 'restaurant', ['cuisine', 'name', 'id'], unique=False
    )
    op.create_index('ix_restaurant_name_id', 'restaurant', ['name', 'id'], unique=False)
    op.create_table(
        'menu_category',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('restaurant_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(
            ['restaurant_id'],
            ['restaurant.id'],
            name=op.f('fk_menu_category_restaurant_id_restaurant'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_category')),
        sa.UniqueConstraint('restaurant_id', 'id', name=op.f('uq_menu_category_restaurant_id_id')),
    )
    op.create_index(
        'uq_menu_category_restaurant_id_lower_name',
        'menu_category',
        ['restaurant_id', sa.literal_column('lower(name)')],
        unique=True,
    )
    op.create_table(
        'menu_item',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('restaurant_id', sa.BigInteger(), nullable=False),
        sa.Column('category_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price_cents', sa.Integer(), nullable=False),
        sa.Column('is_available', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint('price_cents > 0', name=op.f('ck_menu_item_price_cents_positive')),
        sa.ForeignKeyConstraint(
            ['restaurant_id', 'category_id'],
            ['menu_category.restaurant_id', 'menu_category.id'],
            name=op.f('fk_menu_item_restaurant_id_category_id_menu_category'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_item')),
    )
    op.create_index(
        'uq_menu_item_category_id_lower_name',
        'menu_item',
        ['category_id', sa.literal_column('lower(name)')],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_menu_item_category_id_lower_name', table_name='menu_item')
    op.drop_table('menu_item')
    op.drop_index('uq_menu_category_restaurant_id_lower_name', table_name='menu_category')
    op.drop_table('menu_category')
    op.drop_index('ix_restaurant_name_id', table_name='restaurant')
    op.drop_index('ix_restaurant_cuisine_name_id', table_name='restaurant')
    op.drop_table('restaurant')
