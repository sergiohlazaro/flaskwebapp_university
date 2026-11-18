"""auth_throttle

Revision ID: 51b2aaacdf0e
Revises: a3f1c5d7e9b2
Create Date: 2026-11-18 10:31:08.369159

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '51b2aaacdf0e'
down_revision = 'a3f1c5d7e9b2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('auth_throttle',
    sa.Column('key', sa.String(length=320), nullable=False),
    sa.Column('failures', sa.Integer(), nullable=False),
    sa.Column('first_failure_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )


def downgrade():
    op.drop_table('auth_throttle')
