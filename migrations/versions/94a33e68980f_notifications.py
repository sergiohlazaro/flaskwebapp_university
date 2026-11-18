"""notifications

Revision ID: 94a33e68980f
Revises: 51b2aaacdf0e
Create Date: 2026-11-18 10:39:36.155864

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '94a33e68980f'
down_revision = '51b2aaacdf0e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('notification',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('material_id', sa.Integer(), nullable=True),
    sa.Column('comment_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['actor_id'], ['user.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['comment_id'], ['comment.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['material_id'], ['material.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.create_index('ix_notification_user_created', ['user_id', 'created_at'], unique=False)



def downgrade():
    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.drop_index('ix_notification_user_created')

    op.drop_table('notification')
