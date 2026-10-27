"""catalogue

Revision ID: 4c3a4377edb8
Revises:
Create Date: 2026-10-27 21:48:36.111281

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4c3a4377edb8'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'restaurants',
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
            'delivery_fee_cents >= 0', name=op.f('ck_restaurants_delivery_fee_cents_non_negative')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_restaurants')),
    )
    op.create_index(
        'ix_restaurants_cuisine_name_id', 'restaurants', ['cuisine', 'name', 'id'], unique=False
    )
    op.create_index('ix_restaurants_name_id', 'restaurants', ['name', 'id'], unique=False)
    op.create_table(
        'menu_categories',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('restaurant_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(
            ['restaurant_id'],
            ['restaurants.id'],
            name=op.f('fk_menu_categories_restaurant_id_restaurants'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_categories')),
        sa.UniqueConstraint(
            'restaurant_id', 'id', name=op.f('uq_menu_categories_restaurant_id_id')
        ),
    )
    op.create_index(
        'uq_menu_categories_restaurant_id_lower_name',
        'menu_categories',
        ['restaurant_id', sa.literal_column('lower(name)')],
        unique=True,
    )
    op.create_table(
        'menu_items',
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
        sa.CheckConstraint('price_cents > 0', name=op.f('ck_menu_items_price_cents_positive')),
        sa.ForeignKeyConstraint(
            ['restaurant_id', 'category_id'],
            ['menu_categories.restaurant_id', 'menu_categories.id'],
            name=op.f('fk_menu_items_restaurant_id_category_id_menu_categories'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_items')),
    )
    op.create_index(
        'uq_menu_items_category_id_lower_name',
        'menu_items',
        ['category_id', sa.literal_column('lower(name)')],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_menu_items_category_id_lower_name', table_name='menu_items')
    op.drop_table('menu_items')
    op.drop_index('uq_menu_categories_restaurant_id_lower_name', table_name='menu_categories')
    op.drop_table('menu_categories')
    op.drop_index('ix_restaurants_name_id', table_name='restaurants')
    op.drop_index('ix_restaurants_cuisine_name_id', table_name='restaurants')
    op.drop_table('restaurants')
