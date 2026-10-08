"""calendar.sales_fact + calendar.sales_fact_load: multi-year calendar sales (Phase 0)

User, 2026-10-08: "flow all sales for actual and reindexed in all other apps from calendarised app" -> "go ahead with
phase 0". The one-row-per-kind calendar.sales_snapshots can hold one year only, so apps re-read the data lake. This
table holds every closed month as plain rows:
  kind 'actual'    - Jan 2019 onwards on its own month (calendar_id 0, ref_month = month)
  kind 'reindexed' - per saved calendar, each closed reference month spread over its TY months (calendar_id, ref_month
                     -> month) by the Calendar's own proportional split
at store x raw division x department x ATTRIBUTE1, SL_V and SL_Q, plus the planning division (rs_common.divisions).
sales_fact_load = one row per (kind, calendar, reference month) loaded: totals, source file, frozen flag.
Filled by sync/calendar_sales_fact_sync.py; checked by sync/calendar_check_sync.py (check 8). No existing data changes.

Revision ID: b5d1e8f2a9c4
Revises: a7c4e9b2d1f3
Create Date: 2026-10-08 00:00:00.000000

"""
from alembic import op

revision = "b5d1e8f2a9c4"
down_revision = "a7c4e9b2d1f3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS calendar.sales_fact (
            kind          varchar(10) NOT NULL CHECK (kind IN ('actual', 'reindexed')),
            calendar_id   bigint      NOT NULL DEFAULT 0,
            ref_month     date        NOT NULL,
            month         date        NOT NULL,
            store         text        NOT NULL,
            division      text        NOT NULL,
            plan_division text,
            department    text        NOT NULL,
            attribute1    text        NOT NULL,
            sl_v          double precision NOT NULL DEFAULT 0,
            sl_q          double precision NOT NULL DEFAULT 0,
            PRIMARY KEY (kind, calendar_id, ref_month, month, store, division, department, attribute1)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_fact_month ON calendar.sales_fact (kind, calendar_id, month)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_fact_store ON calendar.sales_fact (store, month)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS calendar.sales_fact_load (
            kind         varchar(10) NOT NULL,
            calendar_id  bigint      NOT NULL DEFAULT 0,
            ref_month    date        NOT NULL,
            rows         integer     NOT NULL,
            sl_v         double precision NOT NULL,
            sl_q         double precision NOT NULL,
            source_file  text,
            frozen       boolean     NOT NULL DEFAULT true,
            loaded_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (kind, calendar_id, ref_month)
        )""")


def downgrade():
    op.execute("DROP TABLE IF EXISTS calendar.sales_fact_load")
    op.execute("DROP TABLE IF EXISTS calendar.sales_fact")
