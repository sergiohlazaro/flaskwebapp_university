"""Tests de regresión para los hallazgos de docs/audit/AUDIT.md."""
import io
import os

from conftest import login, make_user, png_bytes
from website import db
from website.models import User

# ---------------------------------------------------------------------------
# QA-01: la subida de foto de perfil debe funcionar sin el módulo imghdr
# ---------------------------------------------------------------------------

def test_qa01_profile_pic_valid_png_is_accepted(app, client):
    user = make_user("pic@example.com")
    login(client, "pic@example.com")

    response = client.post(
        "/profile",
        data={"profile_pic": (png_bytes(), "avatar.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Profile updated successfully." in response.data
    stored = db.session.get(User, user.id).profile_pic
    assert stored != "default.jpg"
    path = os.path.join(app.root_path, "static", "profile_pics", stored)
    assert os.path.exists(path)
    os.remove(path)


def test_qa01_profile_pic_fake_image_is_rejected(app, client):
    user = make_user("fake@example.com")
    login(client, "fake@example.com")

    response = client.post(
        "/profile",
        data={"profile_pic": (io.BytesIO(b"<script>alert(1)</script>"), "evil.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert b"Invalid image file type." in response.data
    assert db.session.get(User, user.id).profile_pic == "default.jpg"
