"""Tests de regresión para los hallazgos de docs/audit/AUDIT.md."""
import os

from conftest import make_user

from website import db
from website.models import User

# ---------------------------------------------------------------------------
# QA-02: los tests no deben tocar la base de datos real
# ---------------------------------------------------------------------------

def test_qa02_create_app_uses_config_passed_before_init(tmp_path):
    from website import create_app
    db_file = tmp_path / "isolated.db"

    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}"})

    with app.app_context():
        assert db.engine.url.database == str(db_file)
        assert User.query.count() == 0  # sin usuarios sembrados en modo test


def test_qa02_fixture_uses_in_memory_database(app):
    assert db.engine.url.database in (None, "", ":memory:")


# ---------------------------------------------------------------------------
# SEC-01: solo un administrador puede bloquear o desbloquear usuarios
# (portado a las rutas /admin/usuarios/... en tests/test_admin_users_reports.py)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# SEC-02: la SECRET_KEY no puede ser la clave filtrada en el repositorio
# ---------------------------------------------------------------------------

LEAKED_KEY = "mysecretkeymysecretkey"
TEST_DB = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "WTF_CSRF_ENABLED": False}


def _forge_session_cookie(app, user_id, key):
    from flask.sessions import SecureCookieSessionInterface
    forger = app.__class__(__name__)
    forger.config["SECRET_KEY"] = key
    serializer = SecureCookieSessionInterface().get_signing_serializer(forger)
    return serializer.dumps({"_user_id": str(user_id), "_fresh": True})


def test_sec02_session_forged_with_leaked_key_is_rejected(monkeypatch):
    from website import create_app
    monkeypatch.delenv("SECRET_KEY", raising=False)
    app = create_app(TEST_DB)
    with app.app_context():
        db.create_all()
        admin = make_user("admin@example.com", role=0)
        client = app.test_client()
        client.set_cookie("session", _forge_session_cookie(app, admin.id, LEAKED_KEY))

        response = client.get("/admin")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_sec02_secret_key_is_read_from_environment(monkeypatch):
    from website import create_app
    monkeypatch.setenv("SECRET_KEY", "from-env-0123456789abcdef0123456789")

    app = create_app(TEST_DB)

    assert app.config["SECRET_KEY"] == "from-env-0123456789abcdef0123456789"


# ---------------------------------------------------------------------------
# SEC-03: no se crean cuentas con credenciales por defecto
# ---------------------------------------------------------------------------

def test_sec03_app_start_does_not_seed_default_accounts(tmp_path):
    from website import create_app
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'prod.db'}"})

    with app.app_context():
        assert User.query.count() == 0


def test_sec03_legacy_default_admin_credentials_cannot_log_in(app, client):
    from werkzeug.security import generate_password_hash
    # Simula una BD existente creada por la versión anterior (seed admin/admin)
    db.session.add(User(name="admin", surname="admin", email="admin@admin.com",
                        password=generate_password_hash("admin"), role=0))
    db.session.commit()

    response = client.post("/login", data={"email": "admin@admin.com", "password": "admin"})

    assert "Las credenciales por defecto están desactivadas" in response.get_data(as_text=True)
    assert client.get("/admin").status_code == 302  # no hay sesión: redirige a login


def test_sec03_create_admin_command_creates_admin_with_given_password(app):
    from werkzeug.security import check_password_hash
    runner = app.test_cli_runner()

    result = runner.invoke(
        args=["create-admin", "--email", "boss@uni.es", "--name", "Ada", "--surname", "Lovelace"],
        input="S3cure-pass!\nS3cure-pass!\n",
    )

    assert result.exit_code == 0, result.output
    admin = User.query.filter_by(email="boss@uni.es").one()
    assert admin.role == 0
    assert check_password_hash(admin.password, "S3cure-pass!")


def test_sec03_create_admin_command_rejects_short_password(app):
    runner = app.test_cli_runner()

    result = runner.invoke(args=["create-admin", "--email", "boss@uni.es"], input="short\nshort\n")

    assert result.exit_code != 0
    assert "at least 8 characters" in result.output
    assert User.query.filter_by(email="boss@uni.es").first() is None


# ---------------------------------------------------------------------------
# SEC-05: una subida nunca sobrescribe el fichero de otro usuario
# ---------------------------------------------------------------------------

def _static(app, *parts):
    return os.path.join(app.root_path, "static", *parts)


def _logout(client):
    client.post("/logout")


def test_qa03_each_login_record_gets_its_own_timestamp(app):
    import time

    from website.models import LoginRecord
    user = make_user("clock@example.com")

    first = LoginRecord(user_id=user.id, ip_address="1.1.1.1")
    db.session.add(first)
    db.session.commit()
    time.sleep(1.1)
    second = LoginRecord(user_id=user.id, ip_address="1.1.1.1")
    db.session.add(second)
    db.session.commit()

    assert second.login_time > first.login_time
