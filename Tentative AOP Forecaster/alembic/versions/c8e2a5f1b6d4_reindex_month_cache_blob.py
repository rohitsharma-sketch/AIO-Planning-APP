"""reindex_month_cache: JSONB -> BYTEA (fixes ProgramLimitExceeded on large months)

A day-wise month with several extra output fields (DIVISION/DEPARTMENT/
ATTRIBUTE1 etc.) serializes to well over Postgres's hard per-JSONB-value
limit of 268,435,455 bytes (~256MB) - a real 2026-04 day-wise cache write
hit this exactly ("total size of jsonb object elements exceeds the
maximum"). JSONB's on-disk representation caps any single value at that
size; there is no configuration knob to raise it. BYTEA (backed by TOAST,
like any large text/binary column) supports up to 1GB per value - no
practical ceiling for this table's actual payloads - so the column is
retyped rather than trying to shrink what gets cached (shrinking would mean
dropping fields the user explicitly asked to break the output out by,
silently corrupting cached results' grain).

Existing rows (JSONB) are converted in place to their UTF-8 text bytes via
convert_to(result_json::text, 'UTF8') - a lossless representation, not a
compression. Future writes from scans.py write json.dumps(...).encode()
directly; reads json.loads() the bytes back. See _save_month_cache /
_load_month_cache in calendar_engine/scans.py.

Revision ID: c8e2a5f1b6d4
Revises: a3f7d9c1e4b2
Create Date: 2026-09-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c8e2a5f1b6d4'
down_revision = 'a3f7d9c1e4b2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reindex_month_cache', sa.Column('result_blob', sa.LargeBinary(), nullable=True), schema='calendar')
    op.execute(
        "UPDATE calendar.reindex_month_cache "
        "SET result_blob = convert_to(result_json::text, 'UTF8')"
    )
    op.alter_column('reindex_month_cache', 'result_blob', nullable=False, schema='calendar')
    op.drop_column('reindex_month_cache', 'result_json', schema='calendar')


def downgrade():
    op.add_column('reindex_month_cache', sa.Column('result_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='calendar')
    op.execute(
        "UPDATE calendar.reindex_month_cache "
        "SET result_json = convert_from(result_blob, 'UTF8')::jsonb"
    )
    op.alter_column('reindex_month_cache', 'result_json', nullable=False, schema='calendar')
    op.drop_column('reindex_month_cache', 'result_blob', schema='calendar')
