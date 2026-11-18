"""user email verification

Revision ID: a3f1c5d7e9b2
Revises: 6c8398ecd2fe
Create Date: 2026-11-18 10:20:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a3f1c5d7e9b2'
down_revision = '6c8398ecd2fe'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('pending_email', sa.String(length=100), nullable=True))

    # Las cuentas existentes cuentan como verificadas (SEC-09).
    op.execute('UPDATE "user" SET email_verified_at = created_at')


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('pending_email')
        batch_op.drop_column('email_verified_at')
