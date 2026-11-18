"""Worksheet version history + voided weights.

Revision ID: 0052
Revises: 0051

Two new tables, nothing existing is altered:

  worksheet_versions  every workbook that was imported (upload, Google Sheet sync) or restored, with the file itself,
                      its SHA-256, who/when, and a summary of what it changed. Lets the farm download, compare and
                      restore any earlier version of the worksheet.
  weight_voids        a weight record that a worksheet correction has set aside. weight_records stays append-only
                      (its trigger is untouched); a wrong imported weight is voided here and the right one appended.
                      Deleting a void row brings the record back (that is what "restore an older version" does).

Downgrade drops both tables: every voided weight becomes live again and the stored workbooks are lost.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worksheet_versions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("production_cycle_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),            # upload | sync | restore | unpost
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content", sa.LargeBinary, nullable=True),           # the .xlsx (NULL for an 'unpost' entry)
        sa.Column("summary", pg.JSONB, nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("restored_from_version_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "version_no", name="uq_worksheet_versions_org_no"),
    )
    op.create_index("ix_worksheet_versions_organization_id", "worksheet_versions", ["organization_id"])

    op.create_table(
        "weight_voids",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("weight_record_id", pg.UUID(as_uuid=True), sa.ForeignKey("weight_records.id"), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("version_id", pg.UUID(as_uuid=True), sa.ForeignKey("worksheet_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("voided_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("weight_record_id", name="uq_weight_voids_record"),
    )
    op.create_index("ix_weight_voids_organization_id", "weight_voids", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_weight_voids_organization_id", table_name="weight_voids")
    op.drop_table("weight_voids")
    op.drop_index("ix_worksheet_versions_organization_id", table_name="worksheet_versions")
    op.drop_table("worksheet_versions")
