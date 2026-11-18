"""Subject.name_key to String(200)

casefold() can expand a 100-character name (e.g. "ß" -> "ss"), so the key needs more room.

Revision ID: c7d2e9a1f4b3
Revises: b41c7a9e2d10
Create Date: 2026-11-18 13:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c7d2e9a1f4b3'
down_revision = 'b41c7a9e2d10'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.alter_column('name_key',
                              existing_type=sa.String(length=120),
                              type_=sa.String(length=200),
                              existing_nullable=False)


def downgrade():
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.alter_column('name_key',
                              existing_type=sa.String(length=200),
                              type_=sa.String(length=120),
                              existing_nullable=False)
