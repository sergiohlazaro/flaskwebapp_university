import io
import re

from conftest import login, make_user, png_bytes
from werkzeug.datastructures import FileStorage

from website import db
from website.models import Material, MaterialFile, Message, Subject
from website.services.uploads import ALLOWED_MATERIAL_EXTENSIONS, save_upload


def _material(author, hidden=False, original="Tema 3 – Normalización (versión final).pdf"):
    subject = Subject.query.filter_by(name_key="bases de datos").first() or Subject(name="Bases de datos")
    db.session.add(subject)
    db.session.flush()
    saved = save_upload(
        FileStorage(stream=io.BytesIO(b"%PDF-1.4 contenido"), filename=original),
        "materials",
        ALLOWED_MATERIAL_EXTENSIONS,
    )
    material = Material(title="Apuntes", subject_id=subject.id, author_id=author.id, is_hidden=hidden)
    material.files.append(MaterialFile(
        stored_name=saved.stored_name, original_name=saved.original_name,
        mime=saved.mime, size=saved.size,
    ))
    db.session.add(material)
    db.session.commit()
    return material.files[0].id


def test_unicode_long_name_roundtrip(app, client):
    author = make_user("a@x.com")
    fid = _material(author)
    long_id = _material(author, original="n" * 200 + ".pdf")
    login(client, "a@x.com")
    r = client.get(f"/archivos/material/{fid}")
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF-")
    cd = r.headers["Content-Disposition"]
    assert "attachment" in cd
    assert "filename*=UTF-8''Tema%203%20%E2%80%93%20Normalizaci%C3%B3n" in cd
    r = client.get(f"/archivos/material/{long_id}")
    assert r.status_code == 200
    assert "filename*=" in r.headers["Content-Disposition"] or "n" * 200 in r.headers["Content-Disposition"]


def test_download_name_is_sanitized(app, client):
    author = make_user("a@x.com")
    fid = _material(author)
    db.session.get(MaterialFile, fid).original_name = 'x/../a\r\nb"c.pdf'
    db.session.commit()
    login(client, "a@x.com")
    r = client.get(f"/archivos/material/{fid}")
    assert r.status_code == 200
    cd = r.headers["Content-Disposition"]
    assert "\r" not in cd and "\n" not in cd and "/" not in cd


def test_material_file_requires_login(client):
    r = client.get("/archivos/material/1")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_material_file_404(app, client):
    make_user("a@x.com")
    login(client, "a@x.com")
    assert client.get("/archivos/material/999").status_code == 404


def test_hidden_material_file_forbidden_for_others(app, client):
    author = make_user("a@x.com")
    make_user("o@x.com")
    make_user("admin@x.com", role=0)
    fid = _material(author, hidden=True)
    login(client, "o@x.com")
    assert client.get(f"/archivos/material/{fid}").status_code == 403
    client.post("/logout")
    login(client, "a@x.com")
    assert client.get(f"/archivos/material/{fid}").status_code == 200
    client.post("/logout")
    login(client, "admin@x.com")
    assert client.get(f"/archivos/material/{fid}").status_code == 200


def test_visible_material_file_open_to_any_user(app, client):
    author = make_user("a@x.com")
    make_user("o@x.com")
    fid = _material(author)
    login(client, "o@x.com")
    assert client.get(f"/archivos/material/{fid}").status_code == 200


def test_image_material_is_inline(app, client):
    author = make_user("a@x.com")
    subject = Subject(name="Redes")
    db.session.add(subject)
    db.session.flush()
    saved = save_upload(
        FileStorage(stream=png_bytes(), filename="foto.png"), "materials", ALLOWED_MATERIAL_EXTENSIONS
    )
    m = Material(title="Foto", subject_id=subject.id, author_id=author.id)
    m.files.append(MaterialFile(stored_name=saved.stored_name, original_name="foto.png",
                                mime=saved.mime, size=saved.size))
    db.session.add(m)
    db.session.commit()
    login(client, "a@x.com")
    r = client.get(f"/archivos/material/{m.files[0].id}")
    assert r.status_code == 200
    assert r.headers["Content-Disposition"].startswith("inline")
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def _message(sender, receiver, with_file=True):
    kwargs = {}
    if with_file:
        saved = save_upload(
            FileStorage(stream=io.BytesIO(b"%PDF-1 msg"), filename="adjunto.pdf"),
            "messages", ALLOWED_MATERIAL_EXTENSIONS,
        )
        kwargs = {"file_stored_name": saved.stored_name, "file_original_name": "adjunto.pdf"}
    m = Message(sender_id=sender.id, receiver_id=receiver.id, content="hola", **kwargs)
    db.session.add(m)
    db.session.commit()
    return m.id


def test_message_file_only_sender_or_receiver(app, client):
    s = make_user("s@x.com")
    r = make_user("r@x.com")
    make_user("t@x.com")
    mid = _message(s, r)
    assert client.get(f"/archivos/mensaje/{mid}").status_code == 302
    login(client, "t@x.com")
    assert client.get(f"/archivos/mensaje/{mid}").status_code == 403
    client.post("/logout")
    login(client, "s@x.com")
    assert client.get(f"/archivos/mensaje/{mid}").status_code == 200
    client.post("/logout")
    login(client, "r@x.com")
    resp = client.get(f"/archivos/mensaje/{mid}")
    assert resp.status_code == 200 and b"%PDF-1 msg" in resp.data


def test_message_file_404_without_attachment_or_message(app, client):
    s = make_user("s@x.com")
    r = make_user("r@x.com")
    mid = _message(s, r, with_file=False)
    login(client, "s@x.com")
    assert client.get(f"/archivos/mensaje/{mid}").status_code == 404
    assert client.get("/archivos/mensaje/999").status_code == 404


def test_avatar_requires_login_and_redirects_default(app, client):
    u = make_user("a@x.com")
    r = client.get(f"/avatar/{u.id}")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    login(client, "a@x.com")
    r = client.get(f"/avatar/{u.id}")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("img/default-avatar.jpg")
    assert client.get("/avatar/999").status_code == 404


def test_avatar_served_when_set(app, client):
    from website.services.uploads import save_avatar
    u = make_user("a@x.com")
    saved = save_avatar(FileStorage(stream=png_bytes(), filename="a.png"))
    u.avatar = saved.stored_name
    db.session.commit()
    login(client, "a@x.com")
    r = client.get(f"/avatar/{u.id}")
    assert r.status_code == 200 and r.mimetype.startswith("image/")


def test_permission_helpers(app):
    from website.services.permissions import (
        can_download_message_file,
        can_view_material,
    )
    a = make_user("a@x.com")
    o = make_user("o@x.com")
    adm = make_user("adm@x.com", role=0)
    m = Material(title="T", subject_id=1, author_id=a.id, is_hidden=True)
    assert can_view_material(a, m) and can_view_material(adm, m) and not can_view_material(o, m)
    m.is_hidden = False
    assert can_view_material(o, m)
    msg = Message(sender_id=a.id, receiver_id=o.id, content="x")
    assert can_download_message_file(a, msg) and can_download_message_file(o, msg)
    assert not can_download_message_file(adm, msg)
    assert re.match(r"^$", "")
