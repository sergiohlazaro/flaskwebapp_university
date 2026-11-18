from datetime import UTC, datetime, timedelta

from tests.conftest import PASSWORD, make_user
from website import create_app, db
from website.models import AuthThrottle
from website.services import throttle

LOCK = "Demasiados intentos. Inténtalo de nuevo en unos minutos."
GENERIC = "Email o contraseña incorrectos."


def _post(client, email, password, ip="10.0.0.1"):
    return client.post("/login", data={"email": email, "password": password},
                       environ_base={"REMOTE_ADDR": ip})


def _text(response):
    return response.get_data(as_text=True)


def test_login_keys_normalise_email():
    assert throttle.login_keys("1.2.3.4", "  Ana@Uni.ES ") == ["ip:1.2.3.4", "acct:ana@uni.es"]


def test_ip_locks_after_5_failures_in_10_minutes(app, client):
    make_user("a@uni.es")
    for i in range(5):
        assert GENERIC in _text(_post(client, f"x{i}@uni.es", "mala-mala-1"))
    # Otra cuenta distinta, misma IP, contraseña correcta: bloqueada por IP.
    assert LOCK in _text(_post(client, "a@uni.es", PASSWORD))
    # Otra IP sí puede entrar.
    assert client.post("/login", data={"email": "a@uni.es", "password": PASSWORD},
                       environ_base={"REMOTE_ADDR": "10.0.0.2"}).status_code == 302


def test_ip_failures_outside_window_do_not_accumulate(app):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    keys = ["ip:9.9.9.9"]
    for i in range(4):
        throttle.register_failure(keys, now=t0 + timedelta(seconds=i))
    throttle.register_failure(keys, now=t0 + timedelta(seconds=700))
    assert not throttle.is_locked(keys, now=t0 + timedelta(seconds=701))
    assert db.session.get(AuthThrottle, "ip:9.9.9.9").failures == 1


def test_ip_lock_lasts_600s_and_account_lock_900s(app):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    for _ in range(5):
        throttle.register_failure(["ip:1.1.1.1", "acct:a@uni.es"], now=t0)
    assert throttle.is_locked(["ip:1.1.1.1"], now=t0 + timedelta(seconds=599))
    assert not throttle.is_locked(["ip:1.1.1.1"], now=t0 + timedelta(seconds=601))
    assert throttle.is_locked(["acct:a@uni.es"], now=t0 + timedelta(seconds=899))
    assert not throttle.is_locked(["acct:a@uni.es"], now=t0 + timedelta(seconds=901))


def test_account_locks_after_5_failures_from_different_ips(app, client):
    make_user("a@uni.es")
    for i in range(5):
        assert GENERIC in _text(_post(client, "a@uni.es", "mala-mala-1", ip=f"10.0.1.{i}"))
    response = _post(client, "a@uni.es", PASSWORD, ip="10.0.1.99")
    assert response.status_code == 200 and LOCK in _text(response)


def test_nonexistent_email_accumulates_like_existing(app, client):
    make_user("real@uni.es")
    for i in range(5):
        _post(client, "nadie@uni.es", "mala-mala-1", ip=f"10.0.2.{i}")
    for i in range(5):
        _post(client, "real@uni.es", "mala-mala-1", ip=f"10.0.3.{i}")
    assert db.session.get(AuthThrottle, "acct:nadie@uni.es").failures == 5
    assert db.session.get(AuthThrottle, "acct:real@uni.es").failures == 5
    assert LOCK in _text(_post(client, "nadie@uni.es", PASSWORD, ip="10.0.4.1"))
    assert LOCK in _text(_post(client, "real@uni.es", PASSWORD, ip="10.0.4.2"))


def test_lock_message_is_generic(app, client):
    make_user("real@uni.es")
    for i in range(5):
        _post(client, "real@uni.es", "mala-mala-1", ip=f"10.0.5.{i}")
        _post(client, "nadie@uni.es", "mala-mala-1", ip=f"10.0.6.{i}")
    existing = _text(_post(client, "real@uni.es", PASSWORD, ip="10.0.7.1"))
    missing = _text(_post(client, "nadie@uni.es", PASSWORD, ip="10.0.7.2"))
    assert LOCK in existing and LOCK in missing
    assert GENERIC not in existing and GENERIC not in missing


def test_expired_lock_allows_login_and_resets(app, client):
    make_user("a@uni.es")
    past = datetime.now(UTC) - timedelta(seconds=1000)
    for key in ("ip:10.0.8.1", "acct:a@uni.es"):
        db.session.add(AuthThrottle(key=key, failures=5, first_failure_at=past,
                                    locked_until=past + timedelta(seconds=900), updated_at=past))
    db.session.commit()
    response = _post(client, "a@uni.es", PASSWORD, ip="10.0.8.1")
    assert response.status_code == 302
    assert AuthThrottle.query.filter(AuthThrottle.failures > 0).count() == 0


def test_success_resets_both_keys(app, client):
    make_user("a@uni.es")
    for _ in range(3):
        _post(client, "a@uni.es", "mala-mala-1")
    assert db.session.get(AuthThrottle, "acct:a@uni.es").failures == 3
    assert _post(client, "a@uni.es", PASSWORD).status_code == 302
    assert db.session.get(AuthThrottle, "acct:a@uni.es") is None
    assert db.session.get(AuthThrottle, "ip:10.0.0.1") is None


def test_blocked_user_counts_but_unverified_correct_password_does_not(app, client):
    user = make_user("b@uni.es")
    user.is_blocked = True
    db.session.commit()
    _post(client, "b@uni.es", PASSWORD)
    assert db.session.get(AuthThrottle, "acct:b@uni.es").failures == 1

    app.config["REQUIRE_EMAIL_VERIFICATION"] = True
    make_user("u@uni.es", verified=False)
    assert "no está activada" in _text(_post(client, "u@uni.es", PASSWORD, ip="10.0.9.1"))
    assert db.session.get(AuthThrottle, "acct:u@uni.es") is None


def test_register_failure_survives_concurrent_insert(app, monkeypatch):
    """Si otra petición inserta la clave entre la lectura y la escritura, no hay IntegrityError."""
    real_get = db.session.get
    calls = {"n": 0}

    def racing_get(model, key, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1 and model is AuthThrottle:
            db.session.execute(AuthThrottle.__table__.insert().values(
                key=key, failures=1, first_failure_at=throttle._now(), updated_at=throttle._now()))
            return None
        return real_get(model, key, *a, **kw)

    monkeypatch.setattr(db.session, "get", racing_get)
    throttle.register_failure(["acct:race@uni.es"])
    assert db.session.get(AuthThrottle, "acct:race@uni.es").failures == 2


def test_throttle_survives_app_restart(tmp_path):
    uri = f"sqlite:///{tmp_path / 'shared.db'}"
    cfg = {"TESTING": True, "SECRET_KEY": "k", "SQLALCHEMY_DATABASE_URI": uri,
           "UPLOAD_ROOT": str(tmp_path / "up")}
    first = create_app(cfg)
    with first.app_context():
        db.create_all()
        for _ in range(5):
            throttle.register_failure(["ip:7.7.7.7"])
        db.session.remove()
    second = create_app(cfg)
    with second.app_context():
        assert throttle.is_locked(["ip:7.7.7.7"])
        assert not throttle.is_locked(["ip:7.7.7.8"])
        db.session.remove()


def test_ratelimit_storage_uri_from_env(monkeypatch):
    import importlib

    from website import config
    monkeypatch.setenv("RATELIMIT_STORAGE_URI", "redis://localhost:6379/1")
    importlib.reload(config)
    try:
        assert config.BaseConfig.RATELIMIT_STORAGE_URI == "redis://localhost:6379/1"
    finally:
        monkeypatch.delenv("RATELIMIT_STORAGE_URI")
        importlib.reload(config)
    assert config.BaseConfig.RATELIMIT_STORAGE_URI == "memory://"
