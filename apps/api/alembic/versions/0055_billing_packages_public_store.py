"""Billing packages decide whether the public store works; per-tenant override.

Revision ID: 0055
Revises: 0054

  * subscription_tiers.public_store_included - does this package include the public store? NOT NULL, defaults TRUE, so
    every existing package (and so every existing tenant) keeps its public store exactly as before.
  * tenant_catalog_settings.public_store_enabled - a superadmin's per-tenant override. NULL = follow the package
    (the default), TRUE = force the store on, FALSE = force it off. Nullable: nothing existing changes.
Downgrade drops both columns.

If you did not add migration 0054 (farm_profiles.hero_layout), change down_revision below to "0053".
"""
import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscription_tiers",
        sa.Column("public_store_included", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("tenant_catalog_settings", sa.Column("public_store_enabled", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenant_catalog_settings", "public_store_enabled")
    op.drop_column("subscription_tiers", "public_store_included")
