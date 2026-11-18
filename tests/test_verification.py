import re

import pytest
from sqlalchemy import inspect, text

from tests.conftest import PASSWORD, BufferedClient, login, make_user
from website import create_app, db
from website.models import User
from website.services import tokens
from website.services.mail import sent_emails
from website.services.search import ensure_search_index
from website.services.tokens import make_verify_token

SIGNUP_MSG = "Si el email no estaba registrado, te hemos enviado un enlace para activar la cuenta. Revísalo para empezar."
UNACTIVATED = "Tu cuenta aún no está activada. Revisa tu email o pide un nuevo enlace."
INVALID = "El enlace no es válido o ha caducado."
RESEND_MSG = "Si existe una cuenta pendiente de activar con ese email, te hemos enviado un nuevo enlace."
GENERIC_LOGIN = "Email o contraseña incorrectos."


@pytest.fixture
def app_verify(tmp_path):
    app = create_app({
        "TESTING": True, "SECRET_KEY": "test-secret-key", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False, "UPLOAD_ROOT": str(tmp_path / "uploads"),
        "MAIL_BACKEND": "memory", "REQUIRE_EMAIL_VERIFICATION": True,
    })
    app.test_client_class = BufferedClient
    with app.app_context():
        db.create_all()
        ensure_search_index()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def vclient(app_verify):
    return app_verify.test_client()


def _signup(client, email="new@uni.es"):
    return client.post("/registro", data={"name": "Ana", "surname": "Pérez", "email": email,
                                          "password": PASSWORD, "password2": PASSWORD})


def _verify_link(body):
    return re.search(r"https?://\S+/verificar/\S+", body).group(0)


def test_verification_off_keeps_current_behaviour(app, client):
    make_user("taken@uni.es")
    response = _signup(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/explorar")
    assert client.get("/cuenta").status_code == 200  # sesión iniciada
    assert User.query.filter_by(email="new@uni.es").one().email_verified_at is not None
    assert sent_emails() == []
    client.post("/logout")
    dup = _signup(client, "taken@uni.es")
    assert dup.status_code == 200
    assert "Ya existe una cuenta con ese email." in dup.get_data(as_text=True)


def test_signup_existing_unverified_resends_verification(app_verify, vclient):
    make_user("pend@uni.es", verified=False)
    response = _signup(vclient, "pend@uni.es")
    assert response.status_code == 302 and response.headers["Location"].endswith("/login")
    assert SIGNUP_MSG in vclient.get(response.headers["Location"]).get_data(as_text=True)
    [mail] = sent_emails()
    assert mail["to"] == "pend@uni.es"
    assert "/verificar/" in mail["body"] and "Alguien ha intentado registrarse" not in mail["body"]


@pytest.mark.parametrize("email", ["new@uni.es", "taken@uni.es"])
def test_signup_with_verification_same_response(app_verify, vclient, email):
    make_user("taken@uni.es")
    response = _signup(vclient, email)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert SIGNUP_MSG in vclient.get(response.headers["Location"]).get_data(as_text=True)
    assert vclient.get("/cuenta").status_code == 302  # sin sesión
    [mail] = sent_emails()
    assert mail["to"] == email
    if email == "new@uni.es":
        assert "/verificar/" in mail["body"]
        assert User.query.filter_by(email=email).one().email_verified_at is None
    else:
        assert "Alguien ha intentado registrarse" in mail["body"]
        assert User.query.filter_by(email=email).count() == 1


def test_unverified_login_correct_password_shows_activation_message(app_verify, vclient):
    make_user("u@uni.es", verified=False)
    response = vclient.post("/login", data={"email": "u@uni.es", "password": PASSWORD})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert UNACTIVATED in html
    assert "/verificar/reenviar" in html
    assert vclient.get("/cuenta").status_code == 302


def test_unverified_login_wrong_password_generic_message(app_verify, vclient):
    make_user("u@uni.es", verified=False)
    html = vclient.post("/login", data={"email": "u@uni.es", "password": "mala-mala-1"}).get_data(as_text=True)
    assert GENERIC_LOGIN in html
    assert UNACTIVATED not in html


def test_verified_user_logs_in_with_verification_on(app_verify, vclient):
    make_user("u@uni.es")
    login(vclient, "u@uni.es")
    assert vclient.get("/cuenta").status_code == 200


def test_verify_link_activates_and_invalid_link_page(app_verify, vclient):
    _signup(vclient)
    link = _verify_link(sent_emails()[0]["body"])
    response = vclient.get(link)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert User.query.filter_by(email="new@uni.es").one().email_verified_at is not None
    login(vclient, "new@uni.es")
    assert vclient.get("/cuenta").status_code == 200
    for bad in (link[:-3] + "xyz", "garbage", make_verify_token(User.query.one(), "other@uni.es")):
        page = vclient.get(f"/verificar/{bad.rsplit('/', 1)[-1]}")
        assert page.status_code in (200, 400)
        assert INVALID in page.get_data(as_text=True)


def test_reset_token_is_not_a_verify_token(app_verify, vclient):
    user = make_user("u@uni.es", verified=False)
    page = vclient.get(f"/verificar/{tokens.make_reset_token(user)}")
    assert INVALID in page.get_data(as_text=True)
    assert db.session.get(User, user.id).email_verified_at is None


@pytest.mark.parametrize("email", ["unver@uni.es", "ver@uni.es", "nobody@uni.es", "blocked@uni.es"])
def test_resend_verification_same_response(app_verify, vclient, email):
    make_user("unver@uni.es", verified=False)
    make_user("ver@uni.es")
    make_user("blocked@uni.es", verified=False).is_blocked = True
    db.session.commit()
    assert vclient.get("/verificar/reenviar").status_code == 200
    response = vclient.post("/verificar/reenviar", data={"email": email})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert RESEND_MSG in vclient.get(response.headers["Location"]).get_data(as_text=True)
    if email == "unver@uni.es":
        [mail] = sent_emails()
        assert mail["to"] == email and "/verificar/" in mail["body"]
    else:
        assert sent_emails() == []


def test_resend_rate_limited_posts_only(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "k", "RATELIMIT_ENABLED": True,
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "UPLOAD_ROOT": str(tmp_path / "up"),
                      "REQUIRE_EMAIL_VERIFICATION": True})
    with app.app_context():
        db.create_all()
        ensure_search_index()
    client = app.test_client()
    for _ in range(8):
        assert client.get("/verificar/reenviar").status_code == 200
    codes = [client.post("/verificar/reenviar", data={"email": "x@y.es"}).status_code for _ in range(6)]
    assert codes[:5] == [302] * 5
    assert codes[5] == 429


def _change_email(client, new):
    return client.post("/cuenta/email", data={"new_email": new, "current_password": PASSWORD})


def test_email_change_goes_to_pending_until_verified(app_verify, vclient):
    user = make_user("old@uni.es")
    login(vclient, "old@uni.es")
    response = _change_email(vclient, "new@uni.es")
    assert response.status_code == 302
    db.session.refresh(user)
    assert user.email == "old@uni.es" and user.pending_email == "new@uni.es"
    [mail] = sent_emails()
    assert mail["to"] == "new@uni.es"
    assert "Pendiente de verificar: <strong>new@uni.es</strong>" in vclient.get("/cuenta").get_data(as_text=True)
    vclient.post("/logout")
    # El login sigue usando el email actual, nunca el pendiente
    assert GENERIC_LOGIN in vclient.post("/login", data={"email": "new@uni.es", "password": PASSWORD}
                                         ).get_data(as_text=True)
    assert vclient.get(_verify_link(mail["body"])).status_code == 302
    db.session.refresh(user)
    assert user.email == "new@uni.es" and user.pending_email is None and user.email_verified_at is not None
    login(vclient, "new@uni.es")
    assert vclient.get("/cuenta").status_code == 200


@pytest.mark.parametrize("new", ["free@uni.es", "taken@uni.es"])
def test_email_change_with_verification_same_response(app_verify, vclient, new):
    user = make_user("old@uni.es")
    make_user("taken@uni.es", name="Owner")
    login(vclient, "old@uni.es")
    response = _change_email(vclient, new)
    assert response.status_code == 302
    html = vclient.get(response.headers["Location"]).get_data(as_text=True)
    assert f"Te hemos enviado un enlace a {new} para confirmarlo. Tu email no cambia hasta entonces." in html
    assert "Ya existe una cuenta con ese email." not in html
    db.session.refresh(user)
    assert user.email == "old@uni.es"
    [mail] = sent_emails()
    assert mail["to"] == new
    if new == "free@uni.es":
        assert user.pending_email == new and "/verificar/" in mail["body"]
    else:
        assert user.pending_email is None
        assert "/verificar/" not in mail["body"] and "Owner" in mail["body"]


def test_stale_verify_token_does_not_apply(app_verify, vclient):
    user = make_user("old@uni.es")
    login(vclient, "old@uni.es")
    _change_email(vclient, "first@uni.es")
    _change_email(vclient, "second@uni.es")
    first_link, second_link = (_verify_link(m["body"]) for m in sent_emails())
    assert INVALID in vclient.get(first_link).get_data(as_text=True)
    db.session.refresh(user)
    assert user.email == "old@uni.es" and user.pending_email == "second@uni.es"
    vclient.get(second_link)
    db.session.refresh(user)
    assert user.email == "second@uni.es"
    # Ya aplicado: el enlace viejo sigue sin valer
    assert INVALID in vclient.get(first_link).get_data(as_text=True)
    assert db.session.get(User, user.id).email == "second@uni.es"


def test_verify_email_change_rechecks_taken(app_verify, vclient):
    user = make_user("old@uni.es")
    login(vclient, "old@uni.es")
    _change_email(vclient, "new@uni.es")
    link = _verify_link(sent_emails()[0]["body"])
    make_user("new@uni.es")  # otra cuenta se queda el email mientras tanto
    response = vclient.get(link, follow_redirects=True)
    assert response.status_code == 200
    assert "Ya existe una cuenta con ese email." in response.get_data(as_text=True)
    db.session.refresh(user)
    assert user.email == "old@uni.es"


def test_email_change_immediate_when_verification_off(app, client):
    user = make_user("old@uni.es")
    login(client, "old@uni.es")
    assert _change_email(client, "new@uni.es").status_code == 302
    db.session.refresh(user)
    assert user.email == "new@uni.es" and user.pending_email is None
    assert sent_emails() == []


def test_admin_mark_verified(app_verify, vclient):
    make_user("admin@uni.es", role=0)
    target = make_user("u@uni.es", verified=False)
    login(vclient, "admin@uni.es")
    html = vclient.get("/admin/usuarios").get_data(as_text=True)
    assert "Verificado" in html and "Marcar como verificado" in html
    response = vclient.post(f"/admin/usuarios/{target.id}/verificar")
    assert response.status_code == 302
    db.session.refresh(target)
    assert target.email_verified_at is not None
    assert vclient.post("/admin/usuarios/9999/verificar").status_code == 404


def test_admin_mark_verified_forbidden_for_non_admin(app_verify, vclient):
    make_user("u@uni.es")
    target = make_user("v@uni.es", verified=False)
    login(vclient, "u@uni.es")
    assert vclient.post(f"/admin/usuarios/{target.id}/verificar").status_code == 403
    assert db.session.get(User, target.id).email_verified_at is None


def test_create_admin_creates_verified_account(app):
    result = app.test_cli_runner().invoke(args=["create-admin", "--email", "boss@uni.es"],
                                          input="S3cure-pass!\nS3cure-pass!\n")
    assert result.exit_code == 0, result.output
    assert User.query.filter_by(email="boss@uni.es").one().email_verified_at is not None


def test_migration_marks_existing_users_verified(tmp_path):
    from flask_migrate import upgrade
    app = create_app({"TESTING": True, "SECRET_KEY": "k", "UPLOAD_ROOT": str(tmp_path / "up"),
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}"})
    with app.app_context():
        upgrade(revision="6c8398ecd2fe")
        db.session.execute(text(
            "INSERT INTO user (name, surname, email, password, role, is_teacher, is_blocked, created_at) "
            "VALUES ('A', 'B', 'a@uni.es', 'x', 1, 0, 0, '2026-01-02 03:04:05.000000')"))
        db.session.commit()
        upgrade()
        row = db.session.execute(text("SELECT email_verified_at, created_at, pending_email FROM user")).one()
        columns = {c["name"] for c in inspect(db.engine).get_columns("user")}
        db.session.remove()
    assert {"email_verified_at", "pending_email"} <= columns
    assert row.email_verified_at is not None and row.email_verified_at == row.created_at
    assert row.pending_email is None
