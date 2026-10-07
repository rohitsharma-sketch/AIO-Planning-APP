"""forecast_results: index on (run_id, metric_key)

Every per-run total (recent-runs for Plan Cycles, runs/{id}/division-totals for
BIS's AOP Review, division-aop-summary for Sales Plan) filtered 10.8 M rows by
run_id with only the primary key to go on - a full scan each, ~10.7 s for
recent-runs (user, 2026-10-07: "check loading times in the other core apps").
Built CONCURRENTLY so the table stays readable/writable meanwhile. No data change.

Revision ID: a7c4e9b2d1f3
Revises: d9f3b2a7c1e5
Create Date: 2026-10-07 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c4e9b2d1f3"
down_revision = "d9f3b2a7c1e5"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index("ix_forecast_results_run_metric", "forecast_results", ["run_id", "metric_key"],
                        schema="engine", postgresql_concurrently=True, if_not_exists=True)


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index("ix_forecast_results_run_metric", table_name="forecast_results", schema="engine",
                      postgresql_concurrently=True, if_exists=True)
