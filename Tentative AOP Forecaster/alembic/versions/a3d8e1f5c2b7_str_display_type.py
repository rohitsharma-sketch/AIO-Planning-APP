"""planning_inputs.str_fixture_rows / str_plan_rows.display: TABLE / NON_TABLE display type

User, 2026-10-09: "Break it further into table and non-tbale" ... "display type" - the fixture plan (UDF-06) and the
sales plan (UDF06) both carry the display type per row; they were summed per store x department. Kept apart now
('' = a file without a display type).

Revision ID: a3d8e1f5c2b7
Revises: f7a2c9e4b1d6
Create Date: 2026-10-09 00:00:00.000000

"""
from alembic import op

revision = "a3d8e1f5c2b7"
down_revision = "f7a2c9e4b1d6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE planning_inputs.str_fixture_rows ADD COLUMN IF NOT EXISTS display text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE planning_inputs.str_fixture_rows DROP CONSTRAINT IF EXISTS str_fixture_rows_pkey")
    op.execute("ALTER TABLE planning_inputs.str_fixture_rows ADD PRIMARY KEY (upload_id, month, store, department, display)")
    op.execute("ALTER TABLE planning_inputs.str_plan_rows ADD COLUMN IF NOT EXISTS display text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE planning_inputs.str_plan_rows DROP CONSTRAINT IF EXISTS str_plan_rows_pkey")
    op.execute("ALTER TABLE planning_inputs.str_plan_rows ADD PRIMARY KEY (upload_id, month, store, department, article, display)")


def downgrade():
    for t, k in (("str_fixture_rows", "upload_id, month, store, department"),
                 ("str_plan_rows", "upload_id, month, store, department, article")):
        op.execute(f"ALTER TABLE planning_inputs.{t} DROP CONSTRAINT IF EXISTS {t}_pkey")
        op.execute(f"DELETE FROM planning_inputs.{t} WHERE display <> ''")
        op.execute(f"ALTER TABLE planning_inputs.{t} ADD PRIMARY KEY ({k})")
        op.execute(f"ALTER TABLE planning_inputs.{t} DROP COLUMN IF EXISTS display")
