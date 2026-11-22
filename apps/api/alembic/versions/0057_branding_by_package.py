"""Own branding becomes a package benefit (like the public store), with a per-farm override.

Revision ID: 0057
Revises: 0056

  * subscription_tiers.staff_branding_included / shop_branding_included - does this package include own branding for the
    staff app (installed app + sign-in page) / the public shop? NOT NULL, default FALSE, so nothing is included anywhere
    until a superadmin ticks it.
  * tenant_catalog_settings.staff_branding_tenant / shop_branding_tenant become a three-way override: NULL = follow the
    package (the new default), TRUE = force on, FALSE = force off. Existing rows that were merely FALSE ("off, never
    chosen") become NULL; they follow the package, which includes nothing yet, so they behave exactly as before. Rows that
    were TRUE (a superadmin switched it on for that farm) stay forced on.
Downgrade restores the two-way switch: NULL becomes FALSE again, and the package columns are dropped.
"""
import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscription_tiers", sa.Column("staff_branding_included", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("subscription_tiers", sa.Column("shop_branding_included", sa.Boolean(), nullable=False, server_default=sa.false()))
    for column in ("staff_branding_tenant", "shop_branding_tenant"):
        op.alter_column("tenant_catalog_settings", column, existing_type=sa.Boolean(), nullable=True, server_default=None)
        op.execute(f"UPDATE tenant_catalog_settings SET {column} = NULL WHERE {column} = FALSE")


def downgrade() -> None:
    for column in ("shop_branding_tenant", "staff_branding_tenant"):
        op.execute(f"UPDATE tenant_catalog_settings SET {column} = FALSE WHERE {column} IS NULL")
        op.alter_column("tenant_catalog_settings", column, existing_type=sa.Boolean(), nullable=False, server_default=sa.false())
    op.drop_column("subscription_tiers", "shop_branding_included")
    op.drop_column("subscription_tiers", "staff_branding_included")
