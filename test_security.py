"""Tests de regresión para los hallazgos de docs/audit/AUDIT.md."""
import io
import os

from conftest import login, make_user, png_bytes
from website import db
from website.models import User

# ---------------------------------------------------------------------------
# QA-01: la subida de foto de perfil debe funcionar sin el módulo imghdr
# ---------------------------------------------------------------------------

def test_qa01_profile_pic_valid_png_is_accepted(app, client):
    user = make_user("pic@example.com")
    login(client, "pic@example.com")

    response = client.post(
        "/profile",
        data={"profile_pic": (png_bytes(), "avatar.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Profile updated successfully." in response.data
    stored = db.session.get(User, user.id).profile_pic
    assert stored != "default.jpg"
    path = os.path.join(app.root_path, "static", "profile_pics", stored)
    assert os.path.exists(path)
    os.remove(path)


def test_qa01_profile_pic_fake_image_is_rejected(app, client):
    user = make_user("fake@example.com")
    login(client, "fake@example.com")

    response = client.post(
        "/profile",
        data={"profile_pic": (io.BytesIO(b"<script>alert(1)</script>"), "evil.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert b"Invalid image file type." in response.data
    assert db.session.get(User, user.id).profile_pic == "default.jpg"


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
# ---------------------------------------------------------------------------

def test_sec01_normal_user_cannot_block_admin(client):
    admin = make_user("admin@example.com", role=0)
    make_user("attacker@example.com")
    login(client, "attacker@example.com")

    response = client.post(f"/block_user/{admin.id}")

    assert response.status_code == 403
    assert db.session.get(User, admin.id).is_blocked is False


def test_sec01_normal_user_cannot_unblock_user(client):
    victim = make_user("blocked@example.com")
    victim.is_blocked = True
    db.session.commit()
    make_user("attacker@example.com")
    login(client, "attacker@example.com")

    response = client.post(f"/unblock_user/{victim.id}")

    assert response.status_code == 403
    assert db.session.get(User, victim.id).is_blocked is True


def test_sec01_admin_can_still_block_user(client):
    make_user("admin@example.com", role=0)
    target = make_user("target@example.com")
    login(client, "admin@example.com")

    response = client.post(f"/block_user/{target.id}", follow_redirects=True)

    assert b"User blocked" in response.data
    assert db.session.get(User, target.id).is_blocked is True


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
