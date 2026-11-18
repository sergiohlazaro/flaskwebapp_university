"""Retención de datos (SEC-13): borra lo caducado según las constantes `*_RETENTION_DAYS`."""
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import delete

from ..extensions import db
from ..models import AuthThrottle, LoginRecord, Notification


def purge_expired(now=None) -> dict[str, int]:
    """Borra registros de acceso, avisos leídos y filas de throttle caducados y cuenta cuántos."""
    now = now or datetime.now(UTC)
    config = current_app.config

    def cutoff(name):
        return now - timedelta(days=config[name])

    results = {
        "login_records": db.session.execute(
            delete(LoginRecord).where(LoginRecord.login_time < cutoff("LOGIN_RECORD_RETENTION_DAYS"))).rowcount,
        # Los avisos no leídos no caducan.
        "notifications": db.session.execute(
            delete(Notification).where(Notification.read_at.is_not(None),
                                       Notification.read_at < cutoff("NOTIFICATION_READ_RETENTION_DAYS"))).rowcount,
        # Un bloqueo todavía vigente nunca se purga.
        "throttle": db.session.execute(
            delete(AuthThrottle).where(AuthThrottle.updated_at < cutoff("THROTTLE_RETENTION_DAYS"),
                                       (AuthThrottle.locked_until.is_(None)) | (AuthThrottle.locked_until <= now))
        ).rowcount,
    }
    db.session.commit()
    return results
