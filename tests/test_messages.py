import io
import os
from datetime import UTC, datetime, timedelta

from conftest import login, make_user, png_bytes
from sqlalchemy import event

from website import db
from website.models import Message, User
from website.services.uploads import upload_path

NEUTRAL = "No se puede enviar el mensaje a este usuario."


def _msg(sender, receiver, content="hola", minutes=0, read=False):
    when = datetime.now(UTC) - timedelta(minutes=minutes)
    m = Message(sender_id=sender.id if sender else None, receiver_id=receiver.id if receiver else None,
                content=content, created_at=when, read_at=when if read else None)
    db.session.add(m)
    db.session.commit()
    return m


def _send(client, user_id, content="hola", file=None, htmx=False):
    data = {"content": content}
    if file is not None:
        data["file"] = file
    headers = {"HX-Request": "true"} if htmx else {}
    return client.post(f"/mensajes/{user_id}", data=data, content_type="multipart/form-data",
                       headers=headers)


def test_inbox_lists_conversations_latest_first(client):
    me = make_user("me@example.com")
    a = make_user("a@example.com", name="Ana")
    b = make_user("b@example.com", name="Berta")
    _msg(a, me, "viejo de Ana", minutes=30)
    _msg(me, b, "nuevo para Berta", minutes=5)
    _msg(a, me, "otro de Ana", minutes=20)
    login(client, "me@example.com")
    html = client.get("/mensajes").get_data(as_text=True)
    assert html.index("Berta") < html.index("Ana")
    assert html.count("nuevo para Berta") == 1 and "otro de Ana" in html
    assert "viejo de Ana" not in html
    assert f'href="/mensajes/{a.id}"' in html


def test_send_message_by_user_id_with_attachment(app, client):
    me = make_user("me@example.com")
    other = make_user("o@example.com")
    login(client, "me@example.com")
    r = _send(client, other.id, "mira", (png_bytes(), "foto.png", "image/png"))
    assert r.status_code == 302
    m = Message.query.one()
    assert m.sender_id == me.id and m.receiver_id == other.id and m.file_original_name == "foto.png"
    assert os.path.isfile(upload_path("messages", m.file_stored_name))
    assert client.get(f"/archivos/mensaje/{m.id}").status_code == 200
    client.post("/logout")
    make_user("x@example.com")
    login(client, "x@example.com")
    assert client.get(f"/archivos/mensaje/{m.id}").status_code == 403
    client.post("/logout")
    login(client, "o@example.com")
    assert client.get(f"/archivos/mensaje/{m.id}").status_code == 200
    assert "foto.png" in client.get(f"/mensajes/{me.id}").get_data(as_text=True)


def test_same_attachment_name_twice_keeps_both(client):
    make_user("me@example.com")
    other = make_user("o@example.com")
    login(client, "me@example.com")
    _send(client, other.id, "uno", (io.BytesIO(b"one"), "cv.txt", "text/plain"))
    _send(client, other.id, "dos", (io.BytesIO(b"two"), "cv.txt", "text/plain"))
    names = [m.file_stored_name for m in Message.query.order_by(Message.id)]
    assert len(set(names)) == 2
    for name, body in zip(names, (b"one", b"two")):
        with open(upload_path("messages", name), "rb") as fh:
            assert fh.read() == body


def test_cannot_message_self_blocked_or_missing_user(client):
    me = make_user("me@example.com")
    blocked = make_user("b@example.com")
    blocked.is_blocked = True
    db.session.commit()
    login(client, "me@example.com")
    for uid in (me.id, blocked.id, 99999):
        r = _send(client, uid, htmx=True)
        assert r.status_code == 200 and NEUTRAL in r.get_data(as_text=True)
        r = _send(client, uid)
        assert r.status_code == 302 and r.headers["Location"].endswith("/mensajes")
        assert NEUTRAL in client.get("/mensajes").get_data(as_text=True)
    assert Message.query.count() == 0


def test_conversation_marks_received_as_read_and_updates_count(client):
    me = make_user("me@example.com")
    other = make_user("o@example.com")
    _msg(other, me, "uno")
    _msg(other, me, "dos")
    _msg(me, other, "mio")
    login(client, "me@example.com")
    nav = client.get("/mensajes").get_data(as_text=True)
    assert "unread-dot" in nav
    r = client.get(f"/mensajes/{other.id}")
    assert r.status_code == 200
    assert Message.query.filter(Message.receiver_id == me.id, Message.read_at.is_(None)).count() == 0
    assert "unread-dot" not in r.get_data(as_text=True)
    assert Message.query.filter(Message.receiver_id == other.id, Message.read_at.is_(None)).count() == 1


def test_deleted_user_shows_placeholder_and_no_reply_form(client):
    me = make_user("me@example.com")
    gone = make_user("g@example.com")
    _msg(gone, me, "adios")
    _msg(me, gone, "chao", minutes=1)
    for m in Message.query.all():
        if m.sender_id == gone.id:
            m.sender_id = None
        if m.receiver_id == gone.id:
            m.receiver_id = None
    db.session.commit()
    login(client, "me@example.com")
    inbox = client.get("/mensajes").get_data(as_text=True)
    assert "Usuario eliminado" in inbox and 'href="/mensajes/eliminados"' in inbox
    page = client.get("/mensajes/eliminados").get_data(as_text=True)
    assert "adios" in page and "chao" in page
    assert "<textarea" not in page


def test_blocked_conversation_readable_without_reply_form(client):
    me = make_user("me@example.com")
    other = make_user("o@example.com")
    _msg(other, me, "antes del bloqueo")
    other.is_blocked = True
    db.session.commit()
    login(client, "me@example.com")
    page = client.get(f"/mensajes/{other.id}").get_data(as_text=True)
    assert "antes del bloqueo" in page and "No puedes responder a este usuario." in page
    assert "<textarea" not in page
    assert client.get("/mensajes/99999").status_code == 404


def test_user_picker_by_name_lists_homonyms_with_avatar(client):
    make_user("me@example.com", name="Yo")
    h1 = make_user("h1@example.com", name="Laura", surname="Gil", is_teacher=True)
    h2 = make_user("h2@example.com", name="Laura", surname="Gil")
    blocked = make_user("h3@example.com", name="Laura", surname="Gil")
    blocked.is_blocked = True
    db.session.commit()
    login(client, "me@example.com")
    r = client.get("/mensajes/nuevo?q=laura", headers={"HX-Request": "true"})
    html = r.get_data(as_text=True)
    assert "<html" not in html
    assert html.count('class="avatar-md"') == 2
    assert f"/mensajes/{h1.id}" in html and f"/mensajes/{h2.id}" in html
    assert f"/mensajes/{blocked.id}" not in html and "Profesor/a" in html
    full = client.get("/mensajes/nuevo?q=laura").get_data(as_text=True)
    assert "<html" in full


def test_message_content_required_and_max_5000(client):
    make_user("me@example.com")
    other = make_user("o@example.com")
    login(client, "me@example.com")
    r = _send(client, other.id, "   ", htmx=True)
    assert "El mensaje no puede estar vacío." in r.get_data(as_text=True)
    r = _send(client, other.id, "x" * 5001, htmx=True)
    assert "no puede superar los 5000 caracteres" in r.get_data(as_text=True)
    assert Message.query.count() == 0
    r = _send(client, other.id, "x" * 5000, htmx=True)
    assert r.status_code == 200 and Message.query.count() == 1


def test_invalid_attachment_is_error_not_500(client):
    make_user("me@example.com")
    other = make_user("o@example.com")
    login(client, "me@example.com")
    r = _send(client, other.id, "hola", (io.BytesIO(b"MZ"), "virus.exe", "application/octet-stream"), htmx=True)
    assert r.status_code == 200 and "Tipo de archivo no permitido." in r.get_data(as_text=True)
    assert Message.query.count() == 0


def test_legacy_messages_redirect(client):
    r = client.get("/messages")
    assert r.status_code == 301 and r.headers["Location"].endswith("/mensajes")
    assert client.post("/send_message").status_code == 404


def _count_queries(client, url):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        assert client.get(url).status_code == 200
    finally:
        event.remove(db.engine, "before_cursor_execute", record)
    return len(statements)


def test_inbox_query_count_constant(app, client):
    me = make_user("me@example.com")
    login(client, "me@example.com")
    for i in range(2):
        _msg(make_user(f"a{i}@example.com", name=f"Peer{i}"), me, f"hola {i}")
    few = _count_queries(client, "/mensajes")
    for i in range(2, 8):
        _msg(make_user(f"a{i}@example.com", name=f"Peer{i}"), me, f"hola {i}")
    many = _count_queries(client, "/mensajes")
    assert "Peer7" in client.get("/mensajes").get_data(as_text=True)
    assert many == few


def test_message_content_is_escaped(client):
    me = make_user("me@example.com")
    other = make_user("o@example.com")
    _msg(other, me, "<script>alert(1)</script>")
    login(client, "me@example.com")
    for url in (f"/mensajes/{other.id}", "/mensajes"):
        html = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_deleted_messages_page_only_shows_own(client):
    me = make_user("me@example.com")
    x = make_user("x@example.com")
    y = make_user("y@example.com")
    _msg(None, me, "huérfano mío")
    _msg(me, None, "mío hacia eliminado")
    _msg(None, x, "huérfano de otro")
    _msg(y, None, "de otro hacia eliminado")
    _msg(x, y, "entre otros dos")
    login(client, "me@example.com")
    html = client.get("/mensajes/eliminados").get_data(as_text=True)
    assert "huérfano mío" in html and "mío hacia eliminado" in html
    for text in ("huérfano de otro", "de otro hacia eliminado", "entre otros dos"):
        assert text not in html


def test_kept_message_attachment_survives_account_deletion(app, client):
    sender = make_user("s@example.com")
    receiver = make_user("r@example.com")
    login(client, "s@example.com")
    assert _send(client, receiver.id, "con adjunto", (png_bytes(), "foto.png", "image/png")).status_code == 302
    message_id = Message.query.one().id
    stored = Message.query.one().file_stored_name
    path = upload_path("messages", stored)
    assert os.path.isfile(path)

    r = client.post("/cuenta/borrar", data={"current_password": "password123", "confirm": "y"})
    assert r.status_code == 302
    db.session.expire_all()
    assert db.session.get(User, sender.id) is None
    kept = db.session.get(Message, message_id)
    assert kept is not None and kept.sender_id is None and kept.receiver_id == receiver.id
    assert os.path.isfile(path)

    client.post("/logout")
    login(client, "r@example.com")
    assert "con adjunto" in client.get("/mensajes/eliminados").get_data(as_text=True)
    assert client.get(f"/archivos/mensaje/{message_id}").status_code == 200
