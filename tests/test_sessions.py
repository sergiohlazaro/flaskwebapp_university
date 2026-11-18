"""SEC-11: «Recordarme» opcional y versión de sesión."""
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from conftest import PASSWORD, login, make_user
from flask import g

from website import db
from website.models import User
from website.services.tokens import (
    bump_session_version,
    load_reset_token,
    make_reset_token,
)

CHANGED = "Contraseña cambiada. Se ha cerrado la sesión en tus otros dispositivos."


def _set_cookies(response):
    return [h for h in response.headers.getlist("Set-Cookie") if h.startswith("remember_token=")]


def _post_password(client, new="nueva-clave-123"):
    return client.post("/cuenta/password", data={
        "current_password": PASSWORD, "new_password": new, "confirm_password": new},
        follow_redirects=True)


def test_login_without_remember_sets_no_remember_cookie(app, client):
    make_user("a@example.com")
    r = client.post("/login", data={"email": "a@example.com", "password": PASSWORD})
    assert r.status_code == 302
    assert _set_cookies(r) == []


def test_login_with_remember_sets_30_day_cookie(app, client):
    make_user("a@example.com")
    r = client.post("/login", data={"email": "a@example.com", "password": PASSWORD, "remember": "y"})
    cookies = _set_cookies(r)
    assert len(cookies) == 1
    expires = parsedate_to_datetime(cookies[0].split("Expires=")[1].split(";")[0])
    days = (expires - datetime.now(UTC)).total_seconds() / 86400
    assert 29.9 < days < 30.1


def test_login_form_has_unchecked_remember_checkbox(client):
    html = client.get("/login").get_data(as_text=True)
    assert 'name="remember"' in html
    assert "Recordarme" in html
    assert "checked" not in html.split('name="remember"')[1].split(">")[0]


def test_get_id_includes_session_version(app):
    user = make_user("a@example.com")
    assert user.get_id() == f"{user.id}:0"
    bump_session_version(user)
    assert user.get_id() == f"{user.id}:1"


def test_old_format_id_rejected(app, client):
    user = make_user("a@example.com")
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    r = client.get("/explorar")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_wrong_version_or_malformed_id_rejected(app, client):
    user = make_user("a@example.com")
    for bad in (f"{user.id}:5", f"{user.id}:x", f"{user.id}:0:0", "x:0", ":0", f"{user.id}:-0"):
        with client.session_transaction() as sess:
            sess["_user_id"] = bad
        g.pop("_login_user", None)
        assert client.get("/explorar").status_code == 302, bad


def test_password_change_logs_out_other_sessions_keeps_current(app):
    make_user("a@example.com")
    a, b = app.test_client(), app.test_client()
    login(a, "a@example.com")
    login(b, "a@example.com")
    assert b.get("/explorar").status_code == 200
    r = _post_password(a)
    assert CHANGED in r.get_data(as_text=True)
    g.pop("_login_user", None)  # el fixture mantiene un app context que cachea el usuario
    assert a.get("/explorar").status_code == 200
    g.pop("_login_user", None)
    rb = b.get("/explorar")
    assert rb.status_code == 302 and "/login" in rb.headers["Location"]


def test_password_change_invalidates_other_remember_cookie(app):
    make_user("a@example.com")
    a, b = app.test_client(), app.test_client()
    login(a, "a@example.com")
    login(b, "a@example.com", remember=True)
    _post_password(a)
    g.pop("_login_user", None)
    with b.session_transaction() as sess:
        sess.clear()  # solo queda la cookie remember, con el id antiguo
    rb = b.get("/explorar")
    assert rb.status_code == 302 and "/login" in rb.headers["Location"]


def test_password_change_keeps_remember_choice_of_current_client(app):
    make_user("a@example.com")
    plain, remembered = app.test_client(), app.test_client()
    login(plain, "a@example.com")
    login(remembered, "a@example.com", remember=True)
    assert _set_cookies(_post_password_raw(plain)) == []
    r = _post_password_raw(remembered, "otra-clave-456", current="nueva-clave-123")
    assert len(_set_cookies(r)) == 1
    with remembered.session_transaction() as sess:
        sess.clear()
    g.pop("_login_user", None)
    assert remembered.get("/explorar").status_code == 200  # la cookie nueva basta


def _post_password_raw(client, new="nueva-clave-123", current=PASSWORD):
    return client.post("/cuenta/password", data={
        "current_password": current, "new_password": new, "confirm_password": new})


def test_signup_logs_in_without_remember(app, client):
    r = client.post("/registro", data={
        "name": "Ana", "surname": "Pérez", "email": "ana@example.com",
        "password": PASSWORD, "password2": PASSWORD})
    assert r.status_code == 302
    assert _set_cookies(r) == []
    assert client.get("/explorar").status_code == 200


def test_reset_token_invalid_after_bump_session_version(app):
    user = make_user("a@example.com")
    token = make_reset_token(user)
    assert load_reset_token(token) == user
    bump_session_version(user)
    assert load_reset_token(token) is None
    assert db.session.get(User, user.id).session_version == 1
