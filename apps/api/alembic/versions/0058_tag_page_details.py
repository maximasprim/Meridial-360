"""What a scanned animal tag may show: photo, current weight, date of birth - each switchable per farm.

Revision ID: 0058
Revises: 0057

  * farm_profiles.tag_show_photo / tag_show_weight / tag_show_birth_date - NOT NULL, default TRUE. A farm chooses in Site
    content -> Profile whether its public animal tag page shows each of these. They default to shown, matching what the shop
    already publishes for animals that are listed for sale.
Downgrade drops the three columns.
"""
import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("tag_show_photo", "tag_show_weight", "tag_show_birth_date"):
        op.add_column("farm_profiles", sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    for column in ("tag_show_birth_date", "tag_show_weight", "tag_show_photo"):
        op.drop_column("farm_profiles", column)
