"""Retención de datos (SEC-13) y limpieza al borrar la cuenta."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.conftest import PASSWORD, login, make_user
from tests.test_comments_reports import _material
from website import db
from website.models import AuthThrottle, LoginRecord, Notification, User
from website.services.retention import purge_expired
from website.services.search import index_material
from website.services.throttle import register_failure

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def _days(n):
    return NOW - timedelta(days=n)


def _seed(user, actor=None):
    db.session.add_all([
        LoginRecord(user_id=user.id, ip_address="1.1.1.1", login_time=_days(91)),
        LoginRecord(user_id=user.id, ip_address="1.1.1.2", login_time=_days(89)),
        Notification(user_id=user.id, kind="content_hidden", created_at=_days(100), read_at=_days(61)),
        Notification(user_id=user.id, kind="content_hidden", created_at=_days(100), read_at=_days(59)),
        Notification(user_id=user.id, kind="content_hidden", created_at=_days(200), read_at=None),
        AuthThrottle(key="ip:9.9.9.9", failures=1, first_failure_at=_days(3), updated_at=_days(2)),
        AuthThrottle(key="ip:8.8.8.8", failures=1, first_failure_at=_days(1), updated_at=NOW - timedelta(hours=2)),
        AuthThrottle(key="acct:locked@x.es", failures=5, first_failure_at=_days(3), updated_at=_days(2),
                     locked_until=NOW + timedelta(minutes=5)),
    ])
    db.session.commit()


def test_purge_removes_only_expired(app):
    user = make_user("u@uni.es")
    _seed(user)
    assert purge_expired(NOW) == {"login_records": 1, "notifications": 1, "throttle": 1}
    assert sorted(r.ip_address for r in LoginRecord.query) == ["1.1.1.2"]
    assert Notification.query.count() == 2
    assert Notification.query.filter(Notification.read_at.is_(None)).count() == 1
    assert sorted(t.key for t in AuthThrottle.query) == ["acct:locked@x.es", "ip:8.8.8.8"]


def test_purge_command_reports_counts(app):
    user = make_user("u@uni.es")
    now = datetime.now(UTC)
    db.session.add_all([
        LoginRecord(user_id=user.id, ip_address="1.1.1.1", login_time=now - timedelta(days=91)),
        Notification(user_id=user.id, kind="content_hidden", read_at=now - timedelta(days=61)),
        AuthThrottle(key="ip:9.9.9.9", failures=1, first_failure_at=now - timedelta(days=3),
                     updated_at=now - timedelta(days=2)),
    ])
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["purge-data"])
    assert result.exit_code == 0
    assert "Registros de acceso: 1 · Notificaciones: 1 · Intentos: 1" in result.output


def test_privacy_page_lists_retention_periods(client):
    html = client.get("/privacidad").get_data(as_text=True)
    for period in ("90 días", "60 días", "30 días", "1 día"):
        assert period in html


def test_account_deletion_cleans_index_notifications_throttle(app, client):
    victim = make_user("victim@example.com")
    other = make_user("other@example.com")
    mine = _material(victim)
    theirs = _material(other)
    index_material(mine)
    index_material(theirs)
    db.session.add_all([
        Notification(user_id=victim.id, kind="content_hidden", material_id=theirs.id),
        Notification(user_id=other.id, kind="comment_on_material", actor_id=victim.id, material_id=theirs.id),
    ])
    db.session.commit()
    register_failure(["ip:1.2.3.4", "acct:victim@example.com"])
    victim_id, other_id, mine_id, theirs_id = victim.id, other.id, mine.id, theirs.id
    login(client, "victim@example.com")
    r = client.post("/cuenta/borrar", data={"current_password": PASSWORD, "confirm": "y"})
    assert r.status_code == 302
    db.session.expire_all()
    assert db.session.get(User, victim_id) is None
    ids = [row[0] for row in db.session.execute(text("SELECT rowid FROM material_fts"))]
    assert mine_id not in ids and theirs_id in ids
    assert Notification.query.filter_by(user_id=victim_id).count() == 0
    kept = Notification.query.filter_by(user_id=other_id).one()
    assert kept.actor_id is None
    assert db.session.get(AuthThrottle, "acct:victim@example.com") is None
    assert db.session.get(AuthThrottle, "ip:1.2.3.4") is not None
    login(client, "other@example.com")
    assert "Usuario eliminado" in client.get("/notificaciones").get_data(as_text=True)
