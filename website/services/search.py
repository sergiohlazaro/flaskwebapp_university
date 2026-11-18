"""Búsqueda de texto completo con SQLite FTS5 (spec §5.9).

La tabla virtual `material_fts` (rowid = material.id) se crea con `ensure_search_index()`, que
usan la migración y los tests, y se mantiene con eventos de SQLAlchemy en el mismo flush (y por
tanto en la misma transacción) que el cambio de datos: un rollback deshace también el índice.
"""
import re
import sqlite3

from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session

from ..extensions import db
from ..models import Material, Subject, User

MAX_TERMS = 10
FTS5_MISSING_MSG = "Esta instalación de SQLite no incluye FTS5"
_STOP_WORDS = {"and", "or", "not", "near"}
_SPECIAL = str.maketrans("", "", '"*^:()-+')
_TOKEN = re.compile(r'"([^"]*)"|(\S+)')

_CREATE_SQL = ("CREATE VIRTUAL TABLE IF NOT EXISTS material_fts USING fts5("
               "title, description, subject_name, author_name, "
               "tokenize='unicode61 remove_diacritics 2')")
_INSERT_SQL = ('INSERT INTO material_fts(rowid, title, description, subject_name, author_name) '
               'SELECT m.id, m.title, m.description, s.name, u.name || \' \' || u.surname '
               'FROM material m JOIN subject s ON s.id = m.subject_id JOIN "user" u ON u.id = m.author_id')


def check_fts5_available() -> None:
    """Falla con un mensaje claro si esta SQLite no incluye FTS5."""
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE fts5_probe USING fts5(x)")
    except sqlite3.Error:
        raise RuntimeError(FTS5_MISSING_MSG) from None
    finally:
        connection.close()


def ensure_search_index(connection=None) -> None:
    """Crea `material_fts` si no existe. Con `connection` (migraciones) usa esa conexión."""
    if connection is not None:
        connection.execute(text(_CREATE_SQL))
        return
    with db.engine.begin() as conn:
        conn.execute(text(_CREATE_SQL))


def _reindex(executor, where="", params=None, ids=None):
    """Borra y reinserta las filas indicadas (todas si no hay condición) a partir de las tablas."""
    params = params or {}
    if where:
        executor.execute(text(f"DELETE FROM material_fts WHERE rowid IN (SELECT m.id FROM material m WHERE {where})"),
                         params)
    else:
        executor.execute(text("DELETE FROM material_fts"))
    executor.execute(text(_INSERT_SQL + (f" WHERE {where}" if where else "")), params)


def index_material(material, executor=None) -> None:
    """(Re)indexa un material con su estado actual en la base de datos."""
    executor = executor or db.session
    _reindex(executor, "m.id = :id", {"id": material.id})


def remove_material(material_id: int, executor=None) -> None:
    (executor or db.session).execute(text("DELETE FROM material_fts WHERE rowid = :id"), {"id": material_id})


def reindex_all(executor=None) -> int:
    """Reconstruye todo el índice y devuelve cuántos materiales contiene."""
    executor = executor or db.session
    _reindex(executor)
    return executor.execute(text("SELECT COUNT(*) FROM material_fts")).scalar_one()


def build_match(q: str) -> str | None:
    """Expresión MATCH segura a partir del texto del usuario; None si no queda ningún término."""
    terms = []
    for phrase, word in _TOKEN.findall(q or ""):
        is_phrase = bool(phrase)
        raw = phrase if is_phrase else word
        raw = "".join(" " if ch.isspace() or not ch.isprintable() else ch for ch in raw)  # NUL y controles
        cleaned = " ".join(raw.translate(_SPECIAL).split())
        if not any(ch.isalnum() for ch in cleaned) or (not is_phrase and cleaned.lower() in _STOP_WORDS):
            continue
        terms.append(f'"{cleaned}"' if is_phrase else f'"{cleaned}"*')
        if len(terms) == MAX_TERMS:
            break
    return " ".join(terms) or None


@event.listens_for(Session, "after_flush")
def _maintain_index(session, _flush_context):
    for obj in session.deleted:
        if isinstance(obj, Material):
            remove_material(obj.id, session)
    ids = {obj.id for obj in session.new if isinstance(obj, Material)}
    for obj in session.dirty:
        if isinstance(obj, Material):
            ids.add(obj.id)
        elif isinstance(obj, Subject) and inspect(obj).attrs.name.history.has_changes():
            _reindex(session, "m.subject_id = :v", {"v": obj.id})
        elif isinstance(obj, User) and (inspect(obj).attrs.name.history.has_changes()
                                        or inspect(obj).attrs.surname.history.has_changes()):
            _reindex(session, "m.author_id = :v", {"v": obj.id})
    for material_id in ids:
        _reindex(session, "m.id = :id", {"id": material_id})
