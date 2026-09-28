"""sales_snapshots: allow the department-level kinds actual_dept / trend_shifted_dept

Sales Plan's store x department actual and reindexed sales now come from the
Calendar output (user, 2026-09-28) instead of a manual Excel import. The main
month-wise snapshot is collapsed to store x division (x ATTRIBUTE1) to stay
small, so the nightly calendar_reindex_sync runs a second month-wise reindex
with DEPARTMENT and saves it under its own kinds. No column changes.

Revision ID: d9f3b2a7c1e5
Revises: c8e2a5f1b6d4
Create Date: 2026-09-28 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "d9f3b2a7c1e5"
down_revision = "c8e2a5f1b6d4"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_sales_snapshots_kind", "sales_snapshots", schema="calendar", type_="check")
    op.create_check_constraint(
        "ck_sales_snapshots_kind", "sales_snapshots",
        "kind IN ('actual', 'trend_shifted', 'actual_dept', 'trend_shifted_dept')", schema="calendar")


def downgrade():
    op.execute("DELETE FROM calendar.sales_snapshots WHERE kind IN ('actual_dept', 'trend_shifted_dept')")
    op.drop_constraint("ck_sales_snapshots_kind", "sales_snapshots", schema="calendar", type_="check")
    op.create_check_constraint(
        "ck_sales_snapshots_kind", "sales_snapshots", "kind IN ('actual', 'trend_shifted')", schema="calendar")
