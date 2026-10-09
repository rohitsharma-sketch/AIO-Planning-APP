"""planning_inputs.str_plan_rows.article: the sales plan's article name

User, 2026-10-09: "replace the sales plan sheet with this one it has article names in it" - the store-level sales plan
now carries ARTICLE NAME per row (e.g. "02-ECO [KB02]"), and the fixture plan is split to articles by their cont % of
the plan. Adds one nullable column; existing rows stay (article NULL = the department as a whole).

Revision ID: f7a2c9e4b1d6
Revises: e5b9d2f1a7c3
Create Date: 2026-10-09 00:00:00.000000

"""
from alembic import op

revision = "f7a2c9e4b1d6"
down_revision = "e5b9d2f1a7c3"
branch_labels = None
depends_on = None


def upgrade():
    # one row per article now, so the article joins the key ('' = a plan without articles)
    op.execute("ALTER TABLE planning_inputs.str_plan_rows ADD COLUMN IF NOT EXISTS article text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE planning_inputs.str_plan_rows DROP CONSTRAINT IF EXISTS str_plan_rows_pkey")
    op.execute("ALTER TABLE planning_inputs.str_plan_rows ADD PRIMARY KEY (upload_id, month, store, department, article)")


def downgrade():
    op.execute("ALTER TABLE planning_inputs.str_plan_rows DROP CONSTRAINT IF EXISTS str_plan_rows_pkey")
    op.execute("DELETE FROM planning_inputs.str_plan_rows WHERE article <> ''")
    op.execute("ALTER TABLE planning_inputs.str_plan_rows ADD PRIMARY KEY (upload_id, month, store, department)")
    op.execute("ALTER TABLE planning_inputs.str_plan_rows DROP COLUMN IF EXISTS article")
