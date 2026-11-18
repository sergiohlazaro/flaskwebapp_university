"""Límite de intentos de login persistente (SEC-10), en la tabla `auth_throttle`.

Reglas por prefijo de clave:
- `ip:<addr>`: 5 fallos dentro de 600 s bloquean la IP 600 s.
- `acct:<email>`: 5 fallos seguidos (sin ventana) bloquean la cuenta 900 s.
Un bloqueo vencido se descarta al registrar el siguiente fallo; un login correcto borra las claves.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.sqlite import insert

from ..extensions import db
from ..models import AuthThrottle

MAX_FAILURES = 5
# prefijo -> (ventana de fallos en s, o None si son seguidos; duración del bloqueo en s)
RULES = {"ip": (600, 600), "acct": (None, 900)}


def _now():
    return datetime.now(UTC)


def _aware(value):
    # SQLite devuelve fechas sin zona: se interpretan como UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def login_keys(ip: str, email: str) -> list[str]:
    return [f"ip:{ip}", f"acct:{email.strip().lower()}"]


def is_locked(keys: list[str], now=None) -> bool:
    now = now or _now()
    for row in db.session.query(AuthThrottle).filter(AuthThrottle.key.in_(keys)):
        locked_until = _aware(row.locked_until)
        if locked_until is not None and locked_until > now:
            return True
    return False


def _get_or_create(key, now):
    row = db.session.get(AuthThrottle, key)
    if row is None:
        # Si otra petición inserta la misma clave a la vez, el INSERT se ignora y se relee.
        db.session.execute(insert(AuthThrottle).values(
            key=key, failures=0, first_failure_at=now, updated_at=now).on_conflict_do_nothing())
        row = db.session.get(AuthThrottle, key)
    return row


def register_failure(keys: list[str], now=None) -> None:
    now = now or _now()
    for key in keys:
        window, lock_seconds = RULES[key.split(":", 1)[0]]
        row = _get_or_create(key, now)
        locked_until = _aware(row.locked_until)
        expired_lock = locked_until is not None and locked_until <= now
        expired_window = window is not None and now - _aware(row.first_failure_at) > timedelta(seconds=window)
        if expired_lock or expired_window:
            row.failures, row.first_failure_at, row.locked_until = 0, now, None
        row.failures += 1
        row.updated_at = now
        if row.failures >= MAX_FAILURES:
            row.locked_until = now + timedelta(seconds=lock_seconds)
    db.session.commit()


def reset(keys: list[str]) -> None:
    db.session.query(AuthThrottle).filter(AuthThrottle.key.in_(keys)).delete(synchronize_session=False)
    db.session.commit()
