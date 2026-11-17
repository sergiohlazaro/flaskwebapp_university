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


def register_filters(app) -> None:
    app.jinja_env.filters["localtime"] = localtime
    app.jinja_env.filters["timeago"] = timeago
