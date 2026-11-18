"""material_fts

Revision ID: d5e8a2b7c901
Revises: 94a33e68980f
Create Date: 2026-11-18 12:00:00.000000

"""
from alembic import op

from website.services.search import ensure_search_index, reindex_all

# revision identifiers, used by Alembic.
revision = 'd5e8a2b7c901'
down_revision = '94a33e68980f'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    ensure_search_index(connection)
    reindex_all(connection)


def downgrade():
    op.execute("DROP TABLE IF EXISTS material_fts")
