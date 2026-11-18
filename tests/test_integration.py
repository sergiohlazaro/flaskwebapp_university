import io

import pytest
from werkzeug.security import generate_password_hash

from website import create_app, db
from website.models import User
from website.services.search import ensure_search_index


@pytest.fixture
def app():
    # La configuración se pasa a create_app para que se aplique ANTES de
    # inicializar la BD (si no, los tests usarían y borrarían la BD real).
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False
    })

    with app.app_context():
        db.create_all()
        ensure_search_index()
        yield app

        db.session.remove()
        db.drop_all()

@pytest.fixture
def user(app):
    user = User(
        name="Integration",
        surname="User",
        email="integration@example.com",
        password=generate_password_hash("integrationpass")
    )
    db.session.add(user)
    db.session.commit()
    return user

@pytest.fixture
def client(app):
    return app.test_client()

def register_user(client, name, surname, email, password):
    # Función auxiliar para registrar usuarios y hacer logout para evitar sesiones abiertas
    client.post("/registro", data={
        "name": name,
        "surname": surname,
        "email": email,
        "password": password,
        "password2": password
    }, follow_redirects=True)
    client.post("/logout", follow_redirects=True)

# --------- INTEGRACIÓN: Registro + Login + Material ---------
# Casos de prueba: TC-001, TC-004 (la publicación TC-019 se sustituye por subir material)

def test_register_login_create_material(client, app):
    from website.models import Subject
    register_user(client, "Integration", "Tester", "integration@example.com", "password123")

    response = client.post("/login", data={
        "email": "integration@example.com",
        "password": "password123"
    }, follow_redirects=True)
    assert "Sesión iniciada correctamente".encode() in response.data

    with app.app_context():
        subject = Subject(name="Cálculo")
        db.session.add(subject)
        db.session.commit()
        subject_id = subject.id

    response = client.post("/material/nuevo", data={
        "title": "Apuntes de integración",
        "description": "Resumen del tema 1",
        "subject_id": subject_id,
        "course": "",
        "kind": "",
        "files": [(io.BytesIO(b"contenido"), "apuntes.txt")],
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"Material publicado." in response.data

    response = client.get("/explorar")
    assert "Apuntes de integración".encode() in response.data


# --------- INTEGRACIÓN: Admin bloquea y desbloquea usuario ---------
# Casos de prueba: TC-007, TC-028, TC-029

def test_admin_block_unblock_user_flow(client, app):
    # Crear admin y usuario normal
    register_user(client, "Admin", "User", "admin@example.com", "adminpass")
    register_user(client, "User", "Normal", "user@example.com", "userpass")

    # Convertir usuario admin a rol administrador
    with app.app_context():
        admin_user = User.query.filter_by(email="admin@example.com").first()
        admin_user.role = 0
        db.session.commit()

        user = User.query.filter_by(email="user@example.com").first()
        user_id = user.id  # ID necesario para bloquear/desbloquear

    # Login como admin
    client.post("/login", data={"email": "admin@example.com", "password": "adminpass"}, follow_redirects=True)

    # TC-028: Bloquear usuario desde panel admin
    response = client.post(f"/admin/usuarios/{user_id}/bloquear", follow_redirects=True)
    assert b"Usuario bloqueado." in response.data

    # Logout admin
    client.post("/logout", follow_redirects=True)

    # TC-007: Intento de login por parte de usuario bloqueado
    response = client.post("/login", data={"email": "user@example.com", "password": "userpass"}, follow_redirects=True)
    assert "Email o contraseña incorrectos.".encode() in response.data
    assert client.get("/explorar").status_code == 302  # la cuenta bloqueada no obtiene sesión

    # Login como admin de nuevo
    client.post("/login", data={"email": "admin@example.com", "password": "adminpass"}, follow_redirects=True)

    # TC-029: Desbloquear usuario desde panel admin
    response = client.post(f"/admin/usuarios/{user_id}/desbloquear", follow_redirects=True)
    assert b"Usuario desbloqueado." in response.data

    # Logout admin
    client.post("/logout", follow_redirects=True)

    # Verificación de login exitoso después del desbloqueo
    response = client.post("/login", data={"email": "user@example.com", "password": "userpass"}, follow_redirects=True)
    assert "Sesión iniciada correctamente".encode() in response.data
