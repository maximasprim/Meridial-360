"""Installed-app / login branding chosen per tenant by a superadmin.

Revision ID: 0056
Revises: 0055

  * tenant_catalog_settings.staff_branding_tenant - the STAFF app (installed app name + icon, and the sign-in page)
    shows the farm's own name and logo instead of the platform's. NOT NULL, default FALSE: every existing tenant keeps
    the platform branding exactly as before.
  * tenant_catalog_settings.shop_branding_tenant  - the same for the PUBLIC SHOP when a customer installs it.
Downgrade drops both columns.
"""
import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenant_catalog_settings", sa.Column("staff_branding_tenant", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tenant_catalog_settings", sa.Column("shop_branding_tenant", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("tenant_catalog_settings", "shop_branding_tenant")
    op.drop_column("tenant_catalog_settings", "staff_branding_tenant")
