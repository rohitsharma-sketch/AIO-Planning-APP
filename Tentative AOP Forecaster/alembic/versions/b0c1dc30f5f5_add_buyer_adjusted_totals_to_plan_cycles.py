"""add buyer_adjusted_totals to plan_cycles

Revision ID: b0c1dc30f5f5
Revises: 1968caf074da
Create Date: 2026-08-25 09:56:41.950302

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b0c1dc30f5f5'
down_revision = '1968caf074da'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('plan_cycles', sa.Column('buyer_adjusted_totals', sa.JSON(), nullable=True), schema='workflow')


def downgrade():
    op.drop_column('plan_cycles', 'buyer_adjusted_totals', schema='workflow')
