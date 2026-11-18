"""Migraciones, ausencia de rutas antiguas y token CSRF real."""
import re

from conftest import PASSWORD, make_user
from sqlalchemy import inspect

from website import create_app, db
from website.services.search import ensure_search_index

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
        ensure_search_index()
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


def test_autoincrement_migration_keeps_data_and_stops_id_reuse(tmp_path):
    from flask_migrate import upgrade
    from sqlalchemy import text
    app = _tmp_app(tmp_path)
    with app.app_context():
        upgrade(revision="9377f229440c")
        with db.engine.begin() as conn:
            conn.execute(text("INSERT INTO user (id, name, surname, email, password, role, is_teacher, is_blocked, "
                              "created_at) VALUES (1, 'a', 'b', 'a@b.es', 'x', 1, 0, 0, '2026-01-01')"))
            conn.execute(text("INSERT INTO subject (id, name, name_key, is_archived) VALUES (1, 'R', 'r', 0)"))
            conn.execute(text("INSERT INTO material (id, title, description, subject_id, author_id, created_at, "
                              "updated_at, is_hidden) VALUES (1, 't', '', 1, 1, '2026-01-01', '2026-01-01', 0)"))
            conn.execute(text("INSERT INTO material_file (material_id, stored_name, original_name, mime, size) "
                              "VALUES (1, 's.pdf', 's.pdf', 'application/pdf', 1)"))
            conn.execute(text("INSERT INTO comment (id, material_id, author_id, body, created_at, is_hidden) "
                              "VALUES (1, 1, 1, 'c', '2026-01-01', 0)"))
        upgrade()
        with db.engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM material_file")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM comment")).scalar() == 1
            sql = " ".join(conn.execute(text("SELECT sql FROM sqlite_master WHERE name IN ('material','comment')"))
                           .scalars())
            assert sql.upper().count("AUTOINCREMENT") == 2
            conn.execute(text("DELETE FROM comment"))
            conn.execute(text("INSERT INTO comment (material_id, author_id, body, created_at, is_hidden) "
                              "VALUES (1, 1, 'n', '2026-01-01', 0)"))
            assert conn.execute(text("SELECT id FROM comment")).scalar() == 2


def test_fts_migration_backfills_and_downgrades(tmp_path):
    from flask_migrate import downgrade, upgrade
    from sqlalchemy import text
    app = _tmp_app(tmp_path)
    with app.app_context():
        upgrade(revision="94a33e68980f")
        for sql in (
            ("INSERT INTO user (name, surname, email, password, role, is_teacher, is_blocked, session_version, "
             "created_at) VALUES ('Ana', 'García', 'a@uni.es', 'x', 1, 0, 0, 0, '2026-01-01')"),
            "INSERT INTO subject (name, name_key, is_archived) VALUES ('Redes', 'redes', 0)",
            ("INSERT INTO material (title, description, subject_id, author_id, created_at, updated_at, is_hidden) "
             "VALUES ('Apuntes', 'sobre grafos', 1, 1, '2026-01-01', '2026-01-01', 0)"),
        ):
            db.session.execute(text(sql))
        db.session.commit()
        upgrade()
        row = db.session.execute(text("SELECT rowid, title, description, subject_name, author_name "
                                      "FROM material_fts")).one()
        assert tuple(row) == (1, "Apuntes", "sobre grafos", "Redes", "Ana García")
        downgrade(revision="94a33e68980f")
        left = db.session.execute(text("SELECT name FROM sqlite_master WHERE name LIKE 'material_fts%'")).all()
        db.session.remove()
    assert left == []
