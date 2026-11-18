"""Migraciones, ausencia de rutas antiguas y token CSRF real."""
import re

from conftest import PASSWORD, make_user
from sqlalchemy import inspect

from website import create_app, db

EXPECTED_TABLES = {
    "user", "login_record", "subject", "material", "material_file", "rating", "comment",
    "favorite", "report", "message", "alembic_version",
}


def _tmp_app(tmp_path, **extra):
    return create_app({"TESTING": True, "SECRET_KEY": "k", "UPLOAD_ROOT": str(tmp_path / "up"),
                       "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}", **extra})


def test_migrations_upgrade_creates_schema(tmp_path):
    from flask_migrate import upgrade
    app = _tmp_app(tmp_path)
    with app.app_context():
        upgrade()
        tables = set(inspect(db.engine).get_table_names())
    assert EXPECTED_TABLES <= tables
    assert "publication" not in tables


def test_no_legacy_routes_registered(app):
    assert [r.endpoint for r in app.url_map.iter_rules() if r.endpoint.startswith("views.")] == []


def test_app_starts_without_create_all(tmp_path):
    app = _tmp_app(tmp_path)
    with app.app_context():
        assert inspect(db.engine).get_table_names() == []


def test_csrf_enforced_on_admin_and_material_posts(tmp_path):
    app = _tmp_app(tmp_path, WTF_CSRF_ENABLED=True)
    # Contexto solo para preparar datos: Flask-WTF cachea el token en `g`, y un
    # contexto compartido entre clientes mezclaría los tokens de ambas sesiones.
    with app.app_context():
        db.create_all()
        make_user("admin@example.com", role=0)
        make_user("user@example.com")
    admin = app.test_client()
    user = app.test_client()

    def token_from(client, url):
        page = client.get(url).get_data(as_text=True)
        return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)

    for client, email in ((admin, "admin@example.com"), (user, "user@example.com")):
        client.post("/login", data={"email": email, "password": PASSWORD,
                                    "csrf_token": token_from(client, "/login")})

    assert admin.post("/admin/asignaturas", data={"name": "Redes"}).status_code == 400
    assert user.post("/material/nuevo", data={"title": "Apuntes"}).status_code == 400

    token = token_from(admin, "/admin/asignaturas")
    assert admin.post("/admin/asignaturas", data={"name": "Redes", "csrf_token": token}).status_code != 400
    token = token_from(user, "/material/nuevo")
    assert user.post("/material/nuevo", data={"csrf_token": token}).status_code != 400
