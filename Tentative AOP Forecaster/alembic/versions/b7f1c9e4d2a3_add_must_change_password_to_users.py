"""add must_change_password to users

Revision ID: b7f1c9e4d2a3
Revises: a9b6a4b4d35f
Create Date: 2026-08-31 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7f1c9e4d2a3'
down_revision = 'a9b6a4b4d35f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False,
                                      server_default=sa.false()), schema='auth')


def downgrade():
    op.drop_column('users', 'must_change_password', schema='auth')
