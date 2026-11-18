import io

import pytest
from flask.testing import FlaskClient
from PIL import Image
from werkzeug.security import generate_password_hash

from website import create_app, db
from website.models import User

PASSWORD = "password123"


class BufferedClient(FlaskClient):
    """Lee y cierra cada respuesta: send_file deja abierto el fichero si no."""

    def open(self, *args, **kwargs):
        kwargs.setdefault("buffered", True)
        return super().open(*args, **kwargs)


@pytest.fixture(autouse=True)
def _dispose_engines(monkeypatch):
    """Cierra las conexiones SQLite de cada app creada en el test (incluidas las ad hoc)."""
    apps = []
    original = db.init_app

    def init_app(app):
        apps.append(app)
        return original(app)

    monkeypatch.setattr(db, "init_app", init_app)
    yield
    for created in apps:
        with created.app_context():
            for engine in db.engines.values():
                engine.dispose()


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "UPLOAD_ROOT": str(tmp_path / "uploads"),
    })
    app.test_client_class = BufferedClient
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(email, role=1, name="Test", surname="User", is_teacher=False):
    user = User(
        name=name,
        surname=surname,
        email=email,
        password=generate_password_hash(PASSWORD),
        role=role,
        is_teacher=is_teacher,
    )
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email, password=PASSWORD):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


def png_bytes(size=(10, 10), color="red"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    buf.seek(0)
    return buf
