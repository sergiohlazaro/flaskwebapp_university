"""Páginas de error en español (404, 403, 405, 413, 429, 500, CSRF...)."""
import pytest
from flask import abort

from tests.conftest import login, make_user
from website import create_app, db

HX = {"HX-Request": "true"}


def _app(tmp_path, **extra):
    app = create_app({"TESTING": True, "SECRET_KEY": "k", "UPLOAD_ROOT": str(tmp_path / "up"),
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", **extra})
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture
def err_app(tmp_path):
    app = _app(tmp_path, PROPAGATE_EXCEPTIONS=False)

    @app.route("/_t/abort/<int:code>", methods=["GET", "POST"])
    def _abort(code):
        abort(code)

    @app.route("/_t/boom")
    def _boom():
        raise RuntimeError("boom")

    return app


@pytest.mark.parametrize("code,text", [
    (400, "Petición no válida"),
    (403, "No tienes permiso"),
    (404, "no existe"),
    (405, "Método no permitido"),
    (413, "24 MB"),
    (429, "Demasiadas peticiones"),
])
def test_error_pages_are_spanish(err_app, code, text):
    client = err_app.test_client()
    r = client.get(f"/_t/abort/{code}")
    assert r.status_code == code
    html = r.get_data(as_text=True)
    assert text in html
    assert "<html lang=\"es\"" in html and "Volver al inicio" in html
    assert "Not Found" not in html and "Forbidden" not in html


def test_unknown_url_is_spanish_404(client):
    r = client.get("/no-existe")
    assert r.status_code == 404 and "no existe" in r.get_data(as_text=True)


def test_405_from_real_route(client):
    r = client.get("/logout")
    assert r.status_code == 405 and "Método no permitido" in r.get_data(as_text=True)


def test_500_page_is_spanish_and_rolls_back(err_app):
    r = err_app.test_client().get("/_t/boom")
    assert r.status_code == 500
    html = r.get_data(as_text=True)
    assert "Error del servidor" in html and "Internal Server Error" not in html


def test_413_real_request_too_large(tmp_path):
    app = _app(tmp_path, MAX_CONTENT_LENGTH=100)
    with app.app_context():
        make_user("u@example.com")
    client = app.test_client()
    login(client, "u@example.com")
    r = client.post("/material/nuevo", data={"title": "x" * 500})
    assert r.status_code == 413
    assert "El archivo supera el tamaño máximo de 24 MB." in r.get_data(as_text=True)


def test_csrf_error_message(tmp_path):
    app = _app(tmp_path, WTF_CSRF_ENABLED=True)
    r = app.test_client().post("/login", data={"email": "a@b.es", "password": "x"})
    assert r.status_code == 400
    assert "La sesión del formulario ha caducado. Vuelve a intentarlo." in r.get_data(as_text=True)


@pytest.mark.parametrize("code", [400, 403, 404, 405, 413, 429])
def test_htmx_errors_keep_status_with_short_spanish_body(err_app, code):
    r = err_app.test_client().get(f"/_t/abort/{code}", headers=HX)
    assert r.status_code == code
    body = r.get_data(as_text=True)
    assert "<html" not in body and len(body) < 200 and body.strip()


def test_htmx_500_keeps_status(err_app):
    r = err_app.test_client().get("/_t/boom", headers=HX)
    assert r.status_code == 500 and "<html" not in r.get_data(as_text=True)


def test_htmx_csrf_error_keeps_status(tmp_path):
    app = _app(tmp_path, WTF_CSRF_ENABLED=True)
    r = app.test_client().post("/login", data={}, headers=HX)
    assert r.status_code == 400 and "caducado" in r.get_data(as_text=True)
