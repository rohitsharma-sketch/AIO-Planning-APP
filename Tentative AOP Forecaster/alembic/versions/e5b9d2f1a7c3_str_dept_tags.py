"""planning_inputs.str_dept_tags: STR Forecaster department tags (Core / Seasonal) and attribute

User, 2026-10-09: "Add a tab to add Core or Seasonal Tag to the department and Add Attribute to them. I will give the
master so that you can tag each department with it". One row per department (from the tag master upload or an in-app
edit); attribute empty = the suite's attribute master (masterdata.attribute_master.attribute1) is shown instead.
New table only - no existing data changes.

Revision ID: e5b9d2f1a7c3
Revises: d4a8c1e7f2b9
Create Date: 2026-10-09 00:00:00.000000

"""
from alembic import op

revision = "e5b9d2f1a7c3"
down_revision = "d4a8c1e7f2b9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS planning_inputs.str_dept_tags (
            department  text        PRIMARY KEY,
            tag         varchar(10) CHECK (tag IN ('CORE', 'SEASONAL')),
            attribute   text,
            source      text,
            updated_by  text,
            updated_at  timestamptz NOT NULL DEFAULT now()
        )""")


def downgrade():
    op.execute("DROP TABLE IF EXISTS planning_inputs.str_dept_tags")
