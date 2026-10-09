"""planning_inputs.str_plan_rows.plan_qty: the sales plan's own quantity

User, 2026-10-09: the store-level sales plan ("MAMJ'26 - Sales Plan.xlsx") carries value AND quantity per store x
department x month, so STR uses the planned qty directly (LY selling price only where a row has no qty).
Adds one nullable column to an STR table created the same day (c7e2a4f9b1d3) - no other data changes.

Revision ID: d4a8c1e7f2b9
Revises: c7e2a4f9b1d3
Create Date: 2026-10-09 00:00:00.000000

"""
from alembic import op

revision = "d4a8c1e7f2b9"
down_revision = "c7e2a4f9b1d3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE planning_inputs.str_plan_rows ADD COLUMN IF NOT EXISTS plan_qty double precision")


def downgrade():
    op.execute("ALTER TABLE planning_inputs.str_plan_rows DROP COLUMN IF EXISTS plan_qty")
