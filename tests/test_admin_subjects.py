import pytest

from tests.conftest import login, make_user
from website import db
from website.models import Subject

DUP = "Ya existe una asignatura con ese nombre."
ROUTES = [
    ("get", "/admin/asignaturas"),
    ("post", "/admin/asignaturas"),
    ("post", "/admin/asignaturas/1/renombrar"),
    ("post", "/admin/asignaturas/1/archivar"),
]


@pytest.fixture
def admin(client):
    make_user("admin@example.com", role=0)
    login(client, "admin@example.com")


def add_subject(name):
    s = Subject(name=name)
    db.session.add(s)
    db.session.commit()
    return s


@pytest.mark.parametrize("method,url", ROUTES)
def test_non_admin_forbidden(client, method, url):
    make_user("u@example.com")
    login(client, "u@example.com")
    assert getattr(client, method)(url, data={"name": "X"}).status_code == 403


@pytest.mark.parametrize("method,url", ROUTES)
def test_anonymous_redirected(client, method, url):
    assert getattr(client, method)(url, data={"name": "X"}).status_code == 302


def test_list_page_and_tabs(client, admin):
    add_subject("Cálculo")
    r = client.get("/admin/asignaturas")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for text in ("Usuarios", "Asignaturas", "Reportes", "Contenido oculto", "Cálculo"):
        assert text in html


def test_create(client, admin):
    r = client.post("/admin/asignaturas", data={"name": "Bases de Datos"})
    assert r.status_code == 302
    assert Subject.query.filter_by(name="Bases de Datos").count() == 1


def test_create_duplicate_case_insensitive(client, admin):
    add_subject("Bases de Datos")
    r = client.post("/admin/asignaturas", data={"name": "bases de datos"})
    assert r.status_code == 200
    assert DUP in r.get_data(as_text=True)
    assert Subject.query.count() == 1


def test_create_duplicate_unicode_decomposed(client, admin):
    add_subject("Álgebra")
    r = client.post("/admin/asignaturas", data={"name": "Álgebra"})
    assert r.status_code == 200
    assert DUP in r.get_data(as_text=True)
    assert Subject.query.count() == 1


def test_create_integrity_error_race(client, admin, monkeypatch):
    add_subject("Redes")
    import website.blueprints.admin as mod
    monkeypatch.setattr(mod, "_name_taken", lambda *a, **k: False)
    r = client.post("/admin/asignaturas", data={"name": "REDES"})
    assert r.status_code == 200
    assert DUP in r.get_data(as_text=True)
    assert Subject.query.count() == 1


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_create_invalid_length(client, admin, name):
    r = client.post("/admin/asignaturas", data={"name": name})
    assert r.status_code == 200
    assert "asignatura" in r.get_data(as_text=True).lower()
    assert Subject.query.count() == 0


def test_create_max_length_ok(client, admin):
    client.post("/admin/asignaturas", data={"name": "x" * 100})
    assert Subject.query.count() == 1


def test_rename(client, admin):
    s = add_subject("Fisica")
    r = client.post(f"/admin/asignaturas/{s.id}/renombrar", data={"name": "Física"})
    assert r.status_code == 302
    assert db.session.get(Subject, s.id).name == "Física"
    assert db.session.get(Subject, s.id).name_key == "física"


def test_rename_same_name_other_case_allowed(client, admin):
    s = add_subject("fisica")
    client.post(f"/admin/asignaturas/{s.id}/renombrar", data={"name": "Fisica"})
    assert db.session.get(Subject, s.id).name == "Fisica"


def test_rename_duplicate(client, admin):
    add_subject("Redes")
    s = add_subject("Fisica")
    r = client.post(f"/admin/asignaturas/{s.id}/renombrar", data={"name": "redes"}, follow_redirects=True)
    assert r.status_code == 200
    assert DUP in r.get_data(as_text=True)
    assert db.session.get(Subject, s.id).name == "Fisica"


def test_rename_race_integrity(client, admin, monkeypatch):
    add_subject("Redes")
    s = add_subject("Fisica")
    import website.blueprints.admin as mod
    monkeypatch.setattr(mod, "_name_taken", lambda *a, **k: False)
    r = client.post(f"/admin/asignaturas/{s.id}/renombrar", data={"name": "Redes"}, follow_redirects=True)
    assert r.status_code == 200
    assert DUP in r.get_data(as_text=True)
    assert db.session.get(Subject, s.id).name == "Fisica"


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_rename_invalid(client, admin, name):
    s = add_subject("Fisica")
    r = client.post(f"/admin/asignaturas/{s.id}/renombrar", data={"name": name}, follow_redirects=True)
    assert r.status_code == 200
    assert db.session.get(Subject, s.id).name == "Fisica"


def test_archive_toggle(client, admin):
    s = add_subject("Fisica")
    client.post(f"/admin/asignaturas/{s.id}/archivar")
    assert db.session.get(Subject, s.id).is_archived is True
    client.post(f"/admin/asignaturas/{s.id}/archivar")
    assert db.session.get(Subject, s.id).is_archived is False


def test_unknown_subject_404(client, admin):
    assert client.post("/admin/asignaturas/999/renombrar", data={"name": "X"}).status_code == 404
    assert client.post("/admin/asignaturas/999/archivar").status_code == 404


def test_model_nfc_and_none(app):
    s = Subject(name="Álgebra ")
    assert s.name == "Álgebra"
    assert s.name_key == "álgebra"
    with pytest.raises(ValueError):
        Subject(name=None)
