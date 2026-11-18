"""Utilidades compartidas por los blueprints para leer parámetros y construir consultas."""
from flask_login import current_user
from sqlalchemy import select

from ..extensions import db
from ..models import Favorite

MAX_INT = 2**63 - 1  # rango de INTEGER en SQLite
MAX_PAGE = 1_000_000


def escape_like(text):
    """Escapa %, _ y \\ para usar `text` literalmente en un LIKE con escape="\\"."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def int_param(value, minimum=1):
    """Entero acotado a [minimum, MAX_INT]; None si no es un número válido."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= MAX_INT else None


def page_param(value):
    """Número de página saneado: por defecto 1 y como máximo MAX_PAGE."""
    return min(int_param(value) or 1, MAX_PAGE)


def favorite_ids(items):
    """Ids de los materiales de la página que el usuario actual tiene guardados (una sola consulta)."""
    ids = [m.id for m in items]
    if not ids:
        return set()
    rows = db.session.scalars(select(Favorite.material_id).where(
        Favorite.user_id == current_user.id, Favorite.material_id.in_(ids)))
    return set(rows)
