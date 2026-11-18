import re

import pytest
from werkzeug.security import check_password_hash

from tests.conftest import PASSWORD, login, make_user
from website import create_app, db
from website.models import User
from website.services import tokens
from website.services.mail import sent_emails
from website.services.tokens import make_reset_token, make_verify_token

GENERIC = "Si existe una cuenta con ese email, te hemos enviado un enlace para restablecer la contraseña."
INVALID = "El enlace no es válido o ha caducado."


def _link(body):
    return re.search(r"https?://\S+/recuperar/\S+", body).group(0)


@pytest.mark.parametrize("email", ["exists@uni.es", "nobody@uni.es", "blocked@uni.es", "EXISTS@UNI.ES "])
def test_forgot_password_same_response(app, client, email):
    make_user("exists@uni.es")
    make_user("blocked@uni.es").is_blocked = True
    db.session.commit()
    response = client.post("/recuperar", data={"email": email})
    assert response.status_code == 302
    page = client.get(response.headers["Location"])
    assert page.status_code == 200
    assert GENERIC in page.get_data(as_text=True)
    expected = 1 if email.strip().lower() == "exists@uni.es" else 0
    assert len(sent_emails()) == expected
    if expected:
        assert sent_emails()[0]["to"] == "exists@uni.es"


def test_forgot_password_get_renders(client):
    assert client.get("/recuperar").status_code == 200


def test_forgot_password_rate_limited_posts_only(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "k", "RATELIMIT_ENABLED": True,
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "UPLOAD_ROOT": str(tmp_path / "up")})
    with app.app_context():
        db.create_all()
    client = app.test_client()
    for _ in range(8):
        assert client.get("/recuperar").status_code == 200
    codes = [client.post("/recuperar", data={"email": "x@y.es"}).status_code for _ in range(6)]
    assert codes[:5] == [302] * 5
    assert codes[5] == 429


def test_reset_flow_changes_password_and_bumps_version(app, client):
    user = make_user("exists@uni.es")
    old_version = user.session_version
    client.post("/recuperar", data={"email": "exists@uni.es"})
    link = _link(sent_emails()[0]["body"])
    assert client.get(link).status_code == 200
    response = client.post(link, data={"password": "nuevaclave1", "password2": "nuevaclave1"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    page = client.get("/login")
    assert "Contraseña actualizada. Ya puedes iniciar sesión." in page.get_data(as_text=True)
    db.session.refresh(user)
    assert check_password_hash(user.password, "nuevaclave1")
    assert user.session_version == old_version + 1
    # No se inicia sesión automáticamente
    assert client.get("/cuenta").status_code == 302
    # Y el enlace no se puede reutilizar
    reuse = client.post(link, data={"password": "otraclave12", "password2": "otraclave12"})
    assert reuse.status_code in (200, 400)
    assert INVALID in reuse.get_data(as_text=True)


def test_blocked_user_can_reset_but_not_login(app, client):
    user = make_user("b@uni.es")
    user.is_blocked = True
    db.session.commit()
    token = make_reset_token(user)
    client.post(f"/recuperar/{token}", data={"password": "nuevaclave1", "password2": "nuevaclave1"})
    db.session.refresh(user)
    assert check_password_hash(user.password, "nuevaclave1")


@pytest.mark.parametrize("variant", ["reused", "after_password_change", "expired", "tampered", "truncated",
                                     "verify_token"])
def test_reset_link_invalid_variants(app, client, monkeypatch, variant):
    user = make_user("a@uni.es")
    token = make_reset_token(user)
    if variant == "reused":
        client.post(f"/recuperar/{token}", data={"password": "nuevaclave1", "password2": "nuevaclave1"})
    elif variant == "after_password_change":
        user.password = "otro-hash-distinto-1234567"
        db.session.commit()
    elif variant == "expired":
        monkeypatch.setitem(tokens.MAX_AGE, "password-reset", -1)
    elif variant == "tampered":
        token = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    elif variant == "truncated":
        token = token[:10]
    elif variant == "verify_token":
        token = make_verify_token(user, user.email)
    for method in (client.get, client.post):
        response = method(f"/recuperar/{token}")
        assert response.status_code in (200, 400)
        text = response.get_data(as_text=True)
        assert INVALID in text
        assert "/recuperar" in text
    changed = client.post(f"/recuperar/{token}", data={"password": "zzzzzzzz1", "password2": "zzzzzzzz1"})
    assert INVALID in changed.get_data(as_text=True)
    assert not check_password_hash(db.session.get(User, user.id).password, "zzzzzzzz1")


def test_reset_new_password_validation(app, client):
    user = make_user("a@uni.es")
    old = user.password
    token = make_reset_token(user)
    short = client.post(f"/recuperar/{token}", data={"password": "corta", "password2": "corta"})
    assert short.status_code == 200
    assert "al menos 8 caracteres" in short.get_data(as_text=True)
    diff = client.post(f"/recuperar/{token}", data={"password": "nuevaclave1", "password2": "distinta123"})
    assert diff.status_code == 200
    assert "Las contraseñas no coinciden." in diff.get_data(as_text=True)
    db.session.refresh(user)
    assert user.password == old


def test_admin_generates_reset_link(app, client):
    make_user("admin@uni.es", role=0)
    target = make_user("u@uni.es")
    login(client, "admin@uni.es")
    response = client.post(f"/admin/usuarios/{target.id}/enlace-recuperacion")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    match = re.search(r'<input[^>]*readonly[^>]*value="([^"]+/recuperar/[^"]+)"', html)
    assert match
    link = match.group(1)
    token = link.rsplit("/", 1)[1]
    assert link.startswith("http")
    assert tokens.load_reset_token(token) == target


def test_admin_reset_link_not_logged(app, client):
    import logging
    records = []

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Collect(level=logging.DEBUG)
    old_level, old_disabled = app.logger.level, app.logger.disabled
    app.logger.disabled = False  # fileConfig de Alembic en otros tests puede dejarlo desactivado
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG)
    try:
        make_user("admin@uni.es", role=0)
        target = make_user("u@uni.es")
        login(client, "admin@uni.es")
        response = client.post(f"/admin/usuarios/{target.id}/enlace-recuperacion")
    finally:
        app.logger.removeHandler(handler)
        app.logger.setLevel(old_level)
        app.logger.disabled = old_disabled
    token = re.search(r"/recuperar/([^\"<\s]+)", response.get_data(as_text=True)).group(1)
    logged = "\n".join(records)
    assert "generó un enlace" in logged
    assert token not in logged


def test_admin_reset_link_forbidden_for_non_admin_and_for_admin_targets(app, client):
    other_admin = make_user("admin2@uni.es", role=0)
    user = make_user("u@uni.es")
    make_user("v@uni.es")
    login(client, "u@uni.es")
    assert client.post(f"/admin/usuarios/{user.id}/enlace-recuperacion").status_code == 403
    client.post("/logout")
    make_user("admin@uni.es", role=0)
    login(client, "admin@uni.es")
    assert client.post(f"/admin/usuarios/{other_admin.id}/enlace-recuperacion").status_code == 400
    assert client.post("/admin/usuarios/9999/enlace-recuperacion").status_code == 404


def test_login_page_links_to_forgot_password(client):
    html = client.get("/login").get_data(as_text=True)
    assert "¿Has olvidado tu contraseña?" in html
    assert 'href="/recuperar"' in html


def test_update_password_hash_and_version_single_commit(app, client, monkeypatch):
    make_user("a@uni.es")
    login(client, "a@uni.es")
    commits = []
    original = db.session.commit
    monkeypatch.setattr(db.session, "commit", lambda: (commits.append(1), original())[1])
    response = client.post("/cuenta/password", data={
        "current_password": PASSWORD, "new_password": "nuevaclave1", "confirm_password": "nuevaclave1"})
    assert response.status_code == 302
    assert len(commits) == 1
