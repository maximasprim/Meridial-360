"""Follow-up of daily-gain alerts: which alerts a person has reviewed.

Revision ID: 0053
Revises: 0052

One new table, nothing existing is altered. An alert (daily gain above +2 or below -2 kg/day between an animal's last two
weighings) stays on the dashboard until it is marked reviewed here, or until a newer weighing replaces it (a new weighing
is a new alert date, so it is judged afresh). Downgrade drops the table: every alert is open again.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weight_alert_reviews",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("alert_date", sa.Date, nullable=False),                 # the date of the later weighing of the pair
        sa.Column("adg", sa.Numeric(8, 3), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("reviewed_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("animal_id", "alert_date", name="uq_weight_alert_reviews_animal_date"),
    )
    op.create_index("ix_weight_alert_reviews_organization_id", "weight_alert_reviews", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_weight_alert_reviews_organization_id", table_name="weight_alert_reviews")
    op.drop_table("weight_alert_reviews")
