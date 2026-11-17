import pytest
from flask import g

from tests.conftest import PASSWORD, login, make_user
from website import db
from website.models import LoginRecord, User

GENERIC = "Email o contraseña incorrectos."


@pytest.fixture(autouse=True)
def reset_failed_logins():
    from website.blueprints import auth as auth_module
    auth_module.FAILED_LOGINS.clear()
    yield
    auth_module.FAILED_LOGINS.clear()


def _signup(client, **overrides):
    data = {"name": "Ana", "surname": "Pérez", "email": "ana@uni.es",
            "password": PASSWORD, "password2": PASSWORD}
    data.update(overrides)
    return client.post("/registro", data=data)


def test_login_error_message_is_generic(app, client):
    make_user("real@uni.es")
    unknown = client.post("/login", data={"email": "nadie@uni.es", "password": PASSWORD})
    wrong = client.post("/login", data={"email": "real@uni.es", "password": "mala-mala-1"})
    assert unknown.status_code == 200 and wrong.status_code == 200
    assert GENERIC in unknown.get_data(as_text=True)
    assert GENERIC in wrong.get_data(as_text=True)


def test_blocked_user_gets_generic_message_and_counts_attempt(app, client):
    from website.blueprints import auth as auth_module
    user = make_user("blocked@uni.es")
    user.is_blocked = True
    db.session.commit()

    response = client.post("/login", data={"email": "blocked@uni.es", "password": PASSWORD})

    assert GENERIC in response.get_data(as_text=True)
    assert auth_module.FAILED_LOGINS["127.0.0.1"][0] == 1
    assert client.get("/home").status_code == 302  # sin sesión


def test_blocked_user_session_is_invalidated(app, client):
    user = make_user("victim@uni.es")
    login(client, "victim@uni.es")
    assert client.get("/home").status_code == 200

    user.is_blocked = True
    db.session.commit()
    # El fixture mantiene un app context abierto que cachea el usuario en g;
    # en producción cada petición tiene su propio contexto.
    g.pop("_login_user", None)

    response = client.get("/home")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_signup_normalizes_email_and_validates(app, client):
    response = _signup(client, email="  Ana@Uni.ES ")
    assert response.status_code == 302
    assert User.query.filter_by(email="ana@uni.es").one().name == "Ana"
    assert LoginRecord.query.count() == 1

    client.post("/logout")
    bad_email = _signup(client, email="no-es-un-email")
    assert bad_email.status_code == 200
    assert User.query.count() == 1

    short = _signup(client, email="otra@uni.es", password="corta", password2="corta")
    assert short.status_code == 200
    assert "al menos 8 caracteres" in short.get_data(as_text=True)
    assert User.query.filter_by(email="otra@uni.es").first() is None

    mismatch = _signup(client, email="otra@uni.es", password2="distinta-123")
    assert "no coinciden" in mismatch.get_data(as_text=True)

    dup = _signup(client, email="ANA@uni.es")
    assert "Ya existe una cuenta con ese email." in dup.get_data(as_text=True)
    assert User.query.count() == 1


def test_signup_missing_fields_no_500(client):
    response = client.post("/registro", data={})
    assert response.status_code == 200
    assert "obligatorio" in response.get_data(as_text=True)


def test_signup_redirects_after_success(client):
    response = _signup(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_old_signup_url_redirects_308(client):
    response = client.post("/signup", data={})
    assert response.status_code == 308
    assert response.headers["Location"].endswith("/registro")


def test_login_next_param_follows_internal_path(app, client):
    make_user("n@uni.es")
    response = client.post("/login?next=/perfil-x",
                           data={"email": "n@uni.es", "password": PASSWORD})
    assert response.headers["Location"].endswith("/perfil-x")


@pytest.mark.parametrize("target", ["https://evil.com", "//evil.com", "javascript:alert(1)", "/\\evil.com"])
def test_login_next_param_rejects_external(app, client, target):
    make_user("n@uni.es")
    response = client.post("/login", query_string={"next": target},
                           data={"email": "n@uni.es", "password": PASSWORD})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_signup_cannot_set_teacher_or_admin(client):
    _signup(client, is_teacher="1", role="0")
    user = User.query.filter_by(email="ana@uni.es").one()
    assert user.role == 1
    assert user.is_teacher is False


def test_logout_requires_post(client):
    make_user("o@uni.es")
    login(client, "o@uni.es")
    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 302
    assert client.get("/home").status_code == 302


def test_ip_lockout_after_five_failed_attempts(app, client):
    make_user("lock@uni.es")
    for _ in range(5):
        client.post("/login", data={"email": "lock@uni.es", "password": "mala-mala-1"})

    response = client.post("/login", data={"email": "lock@uni.es", "password": PASSWORD})

    assert "Demasiados intentos fallidos" in response.get_data(as_text=True)
    assert client.get("/home").status_code == 302  # ni con la contraseña correcta


def test_legacy_default_credentials_rejected_with_own_message(app, client):
    make_user("user1@user.com")  # la contraseña real no importa: se rechaza el par público
    from werkzeug.security import generate_password_hash
    User.query.filter_by(email="user1@user.com").one().password = generate_password_hash("password1")
    db.session.commit()

    response = client.post("/login", data={"email": "user1@user.com", "password": "password1"})

    assert "Las credenciales por defecto están desactivadas" in response.get_data(as_text=True)
    assert client.get("/home").status_code == 302
