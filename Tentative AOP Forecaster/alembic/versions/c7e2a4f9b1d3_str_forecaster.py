"""planning_inputs.str_*: STR Forecaster uploads, fixture plan, sales plan and in-app edits

User, 2026-10-09: "I want to make a STR Forecaster, the components will be - Total Fixture Plan on Store Wise x Month
Wise, Minimum Density Qty, Sales Plan Month Wise. Add it in the additional APP section" -> storage "New DB tables".
  str_uploads        one row per uploaded file (kind fixture | sales_plan); the newest active one of a kind is used,
                     older ones stay so an upload can be rolled back
  str_fixture_rows   store x department x forecast month: fixtures and MDQ (= fixtures x qty per fixture), TABLE +
                     NON_TABLE rows summed; month = the forecast month (the file's month + its shift)
  str_plan_rows      store x department x forecast month: planned sales (Rs)
  str_edits          append-only edits; the latest per (month, store, department, field) wins.
                     field 'fixtures' = a store x dept x month fixture count; 'density' = qty per fixture for a
                     department (store / month NULL = every store / month)
New tables only - no existing data changes.

Revision ID: c7e2a4f9b1d3
Revises: b5d1e8f2a9c4
Create Date: 2026-10-09 00:00:00.000000

"""
from alembic import op

revision = "c7e2a4f9b1d3"
down_revision = "b5d1e8f2a9c4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS planning_inputs.str_uploads (
            id           bigserial   PRIMARY KEY,
            kind         varchar(12) NOT NULL CHECK (kind IN ('fixture', 'sales_plan')),
            file_name    text        NOT NULL,
            months       text        NOT NULL,
            month_shift  integer     NOT NULL DEFAULT 0,
            rows         integer     NOT NULL DEFAULT 0,
            uploaded_by  text,
            uploaded_at  timestamptz NOT NULL DEFAULT now(),
            active       boolean     NOT NULL DEFAULT true
        )""")
    op.execute("""
        CREATE TABLE IF NOT EXISTS planning_inputs.str_fixture_rows (
            upload_id  bigint NOT NULL REFERENCES planning_inputs.str_uploads(id) ON DELETE CASCADE,
            month      date   NOT NULL,
            store      text   NOT NULL,
            division   text   NOT NULL,
            department text   NOT NULL,
            fixtures   double precision NOT NULL DEFAULT 0,
            mdq        double precision NOT NULL DEFAULT 0,
            PRIMARY KEY (upload_id, month, store, department)
        )""")
    op.execute("""
        CREATE TABLE IF NOT EXISTS planning_inputs.str_plan_rows (
            upload_id  bigint NOT NULL REFERENCES planning_inputs.str_uploads(id) ON DELETE CASCADE,
            month      date   NOT NULL,
            store      text   NOT NULL,
            division   text   NOT NULL,
            department text   NOT NULL,
            plan_rs    double precision NOT NULL DEFAULT 0,
            PRIMARY KEY (upload_id, month, store, department)
        )""")
    op.execute("""
        CREATE TABLE IF NOT EXISTS planning_inputs.str_edits (
            id         bigserial   PRIMARY KEY,
            month      date,
            store      text,
            department text        NOT NULL,
            field      varchar(12) NOT NULL CHECK (field IN ('fixtures', 'density')),
            value      double precision NOT NULL,
            edited_by  text,
            edited_at  timestamptz NOT NULL DEFAULT now()
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_str_edits_key ON planning_inputs.str_edits (department, field, month, store)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS planning_inputs.str_edits")
    op.execute("DROP TABLE IF EXISTS planning_inputs.str_plan_rows")
    op.execute("DROP TABLE IF EXISTS planning_inputs.str_fixture_rows")
    op.execute("DROP TABLE IF EXISTS planning_inputs.str_uploads")
