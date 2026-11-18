"""Utilidades compartidas por los blueprints para leer parámetros y construir consultas."""
from urllib.parse import urlsplit

from flask import request
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Favorite, Material

MAX_INT = 2**63 - 1  # rango de INTEGER en SQLite
MAX_PAGE = 1_000_000


def feed_loader_options():
    """Opciones de carga anticipada para las tarjetas de material (evita N+1 en feeds y perfiles)."""
    return [selectinload(Material.subject), selectinload(Material.author),
            selectinload(Material.files), selectinload(Material.ratings)]


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


def internal_path(url):
    """Ruta (con consulta) de una URL de este mismo sitio, o None si es externa o dudosa."""
    if not url or "\\" in url:
        return None
    parts = urlsplit(url)
    if (parts.scheme or parts.netloc) and (parts.scheme not in ("http", "https") or parts.netloc != request.host):
        return None
    if not parts.path.startswith("/") or parts.path.startswith("//"):
        return None
    return parts.path + (f"?{parts.query}" if parts.query else "")


def login_next_target():
    """Destino al que volver tras iniciar sesión: solo URLs que se puedan abrir con GET.

    GET: la propia URL. htmx: la página actual (HX-Current-URL), no el fragmento pedido.
    Otros métodos (POST...): el referrer interno, o nada (la URL es solo-POST).
    """
    if request.headers.get("HX-Request"):
        current = internal_path(request.headers.get("HX-Current-URL"))
        if current:
            return current
    elif request.method not in ("GET", "HEAD"):
        return internal_path(request.referrer)
    if request.method in ("GET", "HEAD"):
        return request.full_path.rstrip("?")
    return None
