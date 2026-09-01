"""add reindex month cache

Revision ID: a3f7d9c1e4b2
Revises: b7f1c9e4d2a3
Create Date: 2026-09-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a3f7d9c1e4b2'
down_revision = 'b7f1c9e4d2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('reindex_month_cache',
    sa.Column('source_type', sa.String(), nullable=False),
    sa.Column('ref_month', sa.String(), nullable=False),
    sa.Column('calendar_fingerprint', sa.String(), nullable=False),
    sa.Column('fields_key', sa.String(), nullable=False),
    sa.Column('result_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("source_type IN ('mw', 'dw')", name='ck_reindex_month_cache_source_type'),
    sa.PrimaryKeyConstraint('source_type', 'ref_month', 'calendar_fingerprint', 'fields_key'),
    schema='calendar'
    )


def downgrade():
    op.drop_table('reindex_month_cache', schema='calendar')
