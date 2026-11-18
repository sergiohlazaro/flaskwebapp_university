"""AUTOINCREMENT for material and comment

SQLite reuses the highest deleted rowid; with AUTOINCREMENT ids are never reused, so a
new material/comment can no longer inherit reports that pointed at a deleted one.

Revision ID: b41c7a9e2d10
Revises: 9377f229440c
Create Date: 2026-11-18 12:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b41c7a9e2d10'
down_revision = '9377f229440c'
branch_labels = None
depends_on = None


def _set_autoincrement(enabled):
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    # Recrear la tabla con claves foráneas activas borraría en cascada sus hijos
    # (material_file, comment, rating, favorite): se desactivan durante el cambio.
    op.execute("PRAGMA foreign_keys=OFF")
    try:
        for table in ("material", "comment"):
            with op.batch_alter_table(table, recreate="always",
                                      table_kwargs={"sqlite_autoincrement": enabled}):
                pass
    finally:
        op.execute("PRAGMA foreign_keys=ON")


def upgrade():
    _set_autoincrement(True)


def downgrade():
    _set_autoincrement(False)
