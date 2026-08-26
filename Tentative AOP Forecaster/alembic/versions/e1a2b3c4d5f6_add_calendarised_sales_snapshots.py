"""add sales snapshots (actual + trend shifted)

Revision ID: e1a2b3c4d5f6
Revises: b0c1dc30f5f5
Create Date: 2026-08-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e1a2b3c4d5f6'
down_revision = 'b0c1dc30f5f5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sales_snapshots',
    sa.Column('source_type', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('grain', sa.String(), nullable=False),
    sa.Column('metric', sa.String(), nullable=False),
    sa.Column('columns', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rows', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rows_read', sa.Integer(), nullable=False),
    sa.Column('rows_mapped', sa.Integer(), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("source_type IN ('mw', 'dw')", name='ck_sales_snapshots_source_type'),
    sa.CheckConstraint("kind IN ('actual', 'trend_shifted')", name='ck_sales_snapshots_kind'),
    sa.PrimaryKeyConstraint('source_type', 'kind'),
    schema='calendar'
    )


def downgrade():
    op.drop_table('sales_snapshots', schema='calendar')
