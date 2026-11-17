import io

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from website import create_app, db
from website.models import User

PASSWORD = "password123"


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(email, role=1, name="Test", surname="User"):
    user = User(
        name=name,
        surname=surname,
        email=email,
        password=generate_password_hash(PASSWORD),
        role=role,
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
