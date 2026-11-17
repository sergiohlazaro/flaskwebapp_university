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


def test_qa01_profile_pic_phone_jpeg_mpo_is_accepted(app, client):
    from PIL import Image
    mpo = io.BytesIO()
    Image.new("RGB", (10, 10)).save(mpo, format="MPO", save_all=True,
                                    append_images=[Image.new("RGB", (10, 10))])
    mpo.seek(0)
    user = make_user("phone@example.com")
    login(client, "phone@example.com")

    response = client.post(
        "/profile",
        data={"profile_pic": (mpo, "IMG_0001.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert b"Profile updated successfully." in response.data
    stored = db.session.get(User, user.id).profile_pic
    assert stored != "default.jpg"
    os.remove(os.path.join(app.root_path, "static", "profile_pics", stored))


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

    client.post("/login", data={"email": "admin@admin.com", "password": "admin"})

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
    client.get("/logout")


def test_sec05_profile_pic_named_default_does_not_overwrite_shared_default(app, client):
    default_path = _static(app, "profile_pics", "default.jpg")
    with open(default_path, "rb") as fh:
        original = fh.read()
    user = make_user("evil@example.com")
    login(client, "evil@example.com")

    client.post(
        "/profile",
        data={"profile_pic": (png_bytes(color="blue"), "default.jpg")},
        content_type="multipart/form-data",
    )

    try:
        with open(default_path, "rb") as fh:
            assert fh.read() == original
    finally:
        with open(default_path, "wb") as fh:  # restaurar si el test falla
            fh.write(original)
        stored = db.session.get(User, user.id).profile_pic
        if stored != "default.jpg" and os.path.exists(_static(app, "profile_pics", stored)):
            os.remove(_static(app, "profile_pics", stored))


def _upload_publication(client, email, content):
    make_user(email)
    login(client, email)
    client.post(
        "/publications",
        data={"publication": "hi", "publication_file": (io.BytesIO(content), "notes.txt", "text/plain")},
        content_type="multipart/form-data",
    )
    _logout(client)


def test_sec05_same_attachment_name_from_two_users_keeps_both_files(app, client):
    from website.models import Publication
    _upload_publication(client, "a@example.com", b"secret of A")
    _upload_publication(client, "b@example.com", b"content of B")

    paths = [p.file_path for p in Publication.query.order_by(Publication.id).all()]
    try:
        assert len(set(paths)) == 2
        with open(_static(app, "uploads", "publications", paths[0]), "rb") as fh:
            assert fh.read() == b"secret of A"
    finally:
        for p in set(paths):
            full = _static(app, "uploads", "publications", p)
            if os.path.exists(full):
                os.remove(full)


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


def test_sec05_message_attachments_with_same_name_are_stored_separately(app, client):
    from website.models import Message
    make_user("dest@example.com")
    for sender, body in (("s1@example.com", b"one"), ("s2@example.com", b"two")):
        make_user(sender)
        login(client, sender)
        client.post(
            "/send_message",
            data={"receiver_email": "dest@example.com", "content": "hello",
                  "message_file": (io.BytesIO(body), "cv.txt", "text/plain")},
            content_type="multipart/form-data",
        )
        _logout(client)

    paths = [m.file_path for m in Message.query.order_by(Message.id).all()]
    try:
        assert len(set(paths)) == 2
        with open(_static(app, "uploads", "messages", paths[0]), "rb") as fh:
            assert fh.read() == b"one"
    finally:
        for p in set(paths):
            full = _static(app, "uploads", "messages", p)
            if os.path.exists(full):
                os.remove(full)
