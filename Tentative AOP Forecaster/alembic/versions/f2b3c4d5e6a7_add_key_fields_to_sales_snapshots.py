"""add key_fields to sales_snapshots

Revision ID: f2b3c4d5e6a7
Revises: e1a2b3c4d5f6
Create Date: 2026-08-26 07:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f2b3c4d5e6a7'
down_revision = 'e1a2b3c4d5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'sales_snapshots',
        sa.Column('key_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                   server_default='["store"]'),
        schema='calendar',
    )
    op.alter_column('sales_snapshots', 'key_fields', server_default=None, schema='calendar')


def downgrade():
    op.drop_column('sales_snapshots', 'key_fields', schema='calendar')
