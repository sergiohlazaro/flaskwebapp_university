"""initial schema

Revision ID: 9377f229440c
Revises: 
Create Date: 2026-11-18 01:53:13.825380

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '9377f229440c'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('subject',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('name_key', sa.String(length=120), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name_key')
    )
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('surname', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=100), nullable=False),
    sa.Column('password', sa.String(length=255), nullable=False),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('role', sa.Integer(), nullable=False),
    sa.Column('is_teacher', sa.Boolean(), nullable=False),
    sa.Column('is_blocked', sa.Boolean(), nullable=False),
    sa.Column('avatar', sa.String(length=150), nullable=True),
    sa.Column('twitter', sa.String(length=255), nullable=True),
    sa.Column('linkedin', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('login_record',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('ip_address', sa.String(length=50), nullable=False),
    sa.Column('login_time', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('material',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('course', sa.Enum('1º', '2º', '3º', '4º', 'Máster', name='course', native_enum=False, length=20), nullable=True),
    sa.Column('kind', sa.Enum('Apuntes', 'Ejercicios', 'Examen', 'Resumen', 'Otro', name='materialkind', native_enum=False, length=20), nullable=True),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_hidden', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['subject_id'], ['subject.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sender_id', sa.Integer(), nullable=True),
    sa.Column('receiver_id', sa.Integer(), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('file_stored_name', sa.String(length=255), nullable=True),
    sa.Column('file_original_name', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['receiver_id'], ['user.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sender_id'], ['user.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('report',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('reporter_id', sa.Integer(), nullable=False),
    sa.Column('target_type', sa.Enum('material', 'comment', name='reporttarget', native_enum=False, length=20), nullable=False),
    sa.Column('target_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Enum('Inapropiado', 'Erróneo', 'Copyright', 'Otro', name='reportreason', native_enum=False, length=20), nullable=False),
    sa.Column('details', sa.String(length=500), nullable=False),
    sa.Column('status', sa.Enum('pending', 'resolved', 'dismissed', name='reportstatus', native_enum=False, length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_by_id', sa.Integer(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['reporter_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['resolved_by_id'], ['user.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('comment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_hidden', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['material_id'], ['material.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('favorite',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['material_id'], ['material.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'material_id')
    )
    op.create_table('material_file',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('stored_name', sa.String(length=255), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('mime', sa.String(length=100), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['material_id'], ['material.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('rating',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('stars', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('stars BETWEEN 1 AND 5', name='ck_rating_stars'),
    sa.ForeignKeyConstraint(['material_id'], ['material.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'material_id')
    )
    # ### end Alembic commands ###


def downgrade():
    op.drop_table('rating')
    op.drop_table('material_file')
    op.drop_table('favorite')
    op.drop_table('comment')
    op.drop_table('report')
    op.drop_table('message')
    op.drop_table('material')
    op.drop_table('login_record')
    op.drop_table('user')
    op.drop_table('subject')
    # ### end Alembic commands ###
