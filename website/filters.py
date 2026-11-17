"""Filtros Jinja para mostrar fechas (guardadas en UTC) en hora de Madrid."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")


def _aware(dt: datetime) -> datetime:
    # SQLite devuelve fechas sin zona: se interpretan como UTC.
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def localtime(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return _aware(dt).astimezone(MADRID).strftime("%d/%m/%Y %H:%M")


def timeago(dt: datetime | None, now: datetime | None = None) -> str:
    if dt is None:
        return ""
    now = _aware(now) if now else datetime.now(UTC)
    dt = _aware(dt)
    delta = now - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return "hace un momento"
    if seconds < 3600:
        return f"hace {int(seconds // 60)} min"
    if seconds < 86400:
        return f"hace {int(seconds // 3600)} h"
    days = delta.days
    if days < 2:
        return "ayer"
    if days < 7:
        return f"hace {days} días"
    return dt.astimezone(MADRID).strftime("%d/%m/%Y")


def filesize(size: int | None) -> str:
    """Tamaño legible con coma decimal: 2048 -> '2,0 KB'."""
    value = float(size or 0)
    if value < 1024:
        return f"{int(value)} B"
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024 or unit == "GB":
            return f"{value:.1f}".replace(".", ",") + f" {unit}"
    return ""


def register_filters(app) -> None:
    app.jinja_env.filters["filesize"] = filesize
    app.jinja_env.filters["localtime"] = localtime
    app.jinja_env.filters["timeago"] = timeago
