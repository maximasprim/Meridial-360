"""Storefront hero layout chosen per tenant.

Revision ID: 0054
Revises: 0053

  * farm_profiles.hero_layout - 'classic' or 'focus'. Nullable: NULL means "the tenant has not chosen", and the shop
    then uses the platform default (the NEXT_PUBLIC_SHOP_HERO setting), so nothing existing changes.
Downgrade drops the column.
"""
import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("farm_profiles", sa.Column("hero_layout", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("farm_profiles", "hero_layout")