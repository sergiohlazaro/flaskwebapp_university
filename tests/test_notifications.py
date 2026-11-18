"""Notificaciones en la aplicación (spec §5.8)."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from tests.conftest import login, make_user
from tests.test_comments_reports import _comment, _material
from website import db
from website.models import Notification, Report, ReportReason, ReportTarget, User
from website.services.notifications import unread_count

CUSTOM_MSG = "Este contenido ya no está disponible"


def _notes(user=None):
    query = select(Notification).order_by(Notification.id)
    if user is not None:
        query = query.where(Notification.user_id == user.id)
    return db.session.scalars(query).all()


def _kinds(user):
    return sorted(n.kind for n in _notes(user))


def _add_note(user, kind="comment_on_material", actor=None, material=None, comment=None, minutes=0, read=False):
    note = Notification(user_id=user.id, kind=kind, actor_id=actor.id if actor else None,
                        material_id=material.id if material else None,
                        comment_id=comment.id if comment else None,
                        created_at=datetime.now(UTC) + timedelta(minutes=minutes),
                        read_at=datetime.now(UTC) if read else None)
    db.session.add(note)
    db.session.commit()
    return note


def _comment_via_post(client, email, material):
    login(client, email)
    assert client.post(f"/material/{material.id}/comentarios", data={"body": "un comentario"}).status_code in (200, 302)


def test_comment_notifies_author_not_self(app, client):
    author = make_user("autor@uni.es")
    other = make_user("otro@uni.es")
    material = _material(author)
    _comment_via_post(client, "autor@uni.es", material)
    assert _notes() == []
    client.post("/logout")
    _comment_via_post(client, "otro@uni.es", material)
    (note,) = _notes(author)
    assert (note.kind, note.actor_id, note.material_id) == ("comment_on_material", other.id, material.id)
    assert note.comment_id is not None
    assert note.read_at is None


def test_reply_notifies_previous_commenters_once_each(app, client):
    author = make_user("autor@uni.es")
    a = make_user("a@uni.es")
    b = make_user("b@uni.es")
    c = make_user("c@uni.es")
    material = _material(author)
    _comment(material, a)
    _comment(material, a, body="otra")
    _comment(material, b)
    _comment_via_post(client, "c@uni.es", material)
    assert _kinds(a) == ["reply_in_thread"]
    assert _kinds(b) == ["reply_in_thread"]
    assert _kinds(author) == ["comment_on_material"]
    assert _kinds(c) == []


def test_previous_commenter_who_is_author_gets_only_one(app, client):
    author = make_user("autor@uni.es")
    other = make_user("otro@uni.es")
    material = _material(author)
    _comment(material, author)
    _comment_via_post(client, "otro@uni.es", material)
    assert _kinds(author) == ["comment_on_material"]
    assert other.id not in {n.user_id for n in _notes()}


def _admin_hide(client, kind, item):
    return client.post(f"/admin/oculto/{kind}/{item.id}/ocultar")


def test_hide_notifies_author_except_self_and_already_hidden(app, client):
    admin = make_user("admin@uni.es", role=0)
    author = make_user("autor@uni.es")
    material = _material(author)
    own = _material(admin)
    comment = _comment(material, author)
    login(client, "admin@uni.es")
    _admin_hide(client, "material", own)
    assert _notes() == []  # el admin oculta lo suyo
    _admin_hide(client, "material", material)
    (note,) = _notes(author)
    assert (note.kind, note.actor_id, note.material_id, note.comment_id) == (
        "content_hidden", admin.id, material.id, None)
    _admin_hide(client, "material", material)  # ya estaba oculto
    assert len(_notes(author)) == 1
    _admin_hide(client, "comment", comment)
    assert [(n.comment_id) for n in _notes(author)] == [None, comment.id]


def test_rehide_after_restore_notifies_again(app, client):
    make_user("admin@uni.es", role=0)
    author = make_user("autor@uni.es")
    material = _material(author)
    login(client, "admin@uni.es")
    _admin_hide(client, "material", material)
    client.post(f"/admin/oculto/material/{material.id}/restaurar")
    assert len(_notes(author)) == 1  # restaurar no avisa
    _admin_hide(client, "material", material)
    assert len(_notes(author)) == 2


def test_resolve_report_notifies_author(app, client):
    make_user("admin@uni.es", role=0)
    author = make_user("autor@uni.es")
    reporter = make_user("rep@uni.es")
    material = _material(author)
    report = Report(reporter_id=reporter.id, target_type=ReportTarget.MATERIAL, target_id=material.id,
                    reason=ReportReason.OTHER)
    db.session.add(report)
    db.session.commit()
    login(client, "admin@uni.es")
    client.post(f"/admin/reportes/{report.id}/ocultar")
    assert _kinds(author) == ["content_hidden"]


def test_new_report_notifies_admins_except_reporter(app, client):
    a1 = make_user("a1@uni.es", role=0)
    a2 = make_user("a2@uni.es", role=0)
    author = make_user("autor@uni.es")
    user = make_user("user@uni.es")
    material = _material(author)
    login(client, "user@uni.es")
    resp = client.post("/reportar", data={"target_type": "material", "target_id": material.id, "reason": "Otro"})
    assert resp.status_code == 302
    assert [n.user_id for n in _notes()] == [a1.id, a2.id]
    assert {n.kind for n in _notes()} == {"new_report"}
    assert {n.actor_id for n in _notes()} == {user.id}
    assert {n.material_id for n in _notes()} == {material.id}
    assert _notes(author) == [] and _notes(user) == []


def test_admin_reporter_not_notified(app, client):
    a1 = make_user("a1@uni.es", role=0)
    a2 = make_user("a2@uni.es", role=0)
    material = _material(make_user("autor@uni.es"))
    login(client, "a1@uni.es")
    client.post("/reportar", data={"target_type": "material", "target_id": material.id, "reason": "Otro"})
    assert [n.user_id for n in _notes()] == [a2.id]
    assert a1.id not in {n.user_id for n in _notes()}


def test_duplicate_report_no_new_notification(app, client):
    make_user("a1@uni.es", role=0)
    make_user("user@uni.es")
    material = _material(make_user("autor@uni.es"))
    login(client, "user@uni.es")
    data = {"target_type": "material", "target_id": material.id, "reason": "Otro"}
    client.post("/reportar", data=data)
    client.post("/reportar", data=data)
    assert len(_notes()) == 1


def test_comment_report_notification_targets_comment(app, client):
    make_user("a1@uni.es", role=0)
    make_user("user@uni.es")
    material = _material(make_user("autor@uni.es"))
    comment = _comment(material, make_user("otro@uni.es"))
    login(client, "user@uni.es")
    client.post("/reportar", data={"target_type": "comment", "target_id": comment.id, "reason": "Otro"})
    (note,) = _notes()
    assert (note.material_id, note.comment_id) == (material.id, comment.id)


def test_bell_count_caps_at_9_plus(app, client):
    user = make_user("u@uni.es")
    material = _material(make_user("autor@uni.es"))
    login(client, "u@uni.es")
    assert "Notificaciones (0 sin leer)" in client.get("/explorar").get_data(as_text=True)
    assert "9+" not in client.get("/explorar").get_data(as_text=True)
    for _ in range(9):
        _add_note(user, material=material)
    html = client.get("/explorar").get_data(as_text=True)
    assert "Notificaciones (9 sin leer)" in html and "9+" not in html
    _add_note(user, material=material)
    html = client.get("/explorar").get_data(as_text=True)
    assert "Notificaciones (10 sin leer)" in html and "9+" in html
    assert unread_count(user) == 10


def test_bell_absent_for_anonymous(app, client):
    assert "Notificaciones" not in client.get("/").get_data(as_text=True)


def test_list_paginates_20_newest_first(app, client):
    user = make_user("u@uni.es")
    actor = make_user("ana@uni.es", name="Ana", surname="G.")
    material = _material(actor)
    for i in range(25):
        _add_note(user, actor=actor, material=material, minutes=i)
    login(client, "u@uni.es")
    page1 = client.get("/notificaciones").get_data(as_text=True)
    assert page1.count("/abrir") == 20
    page2 = client.get("/notificaciones?pagina=2").get_data(as_text=True)
    assert page2.count("/abrir") == 5
    ids = [n.id for n in _notes(user)]
    assert page1.index(f"/notificaciones/{ids[-1]}/abrir") < page1.index(f"/notificaciones/{ids[-2]}/abrir")
    assert f"/notificaciones/{ids[0]}/abrir" in page2
    assert "Ana G. comentó en" in page1


def test_list_texts(app, client):
    user = make_user("u@uni.es", role=0)
    actor = make_user("ana@uni.es", name="Ana", surname="G.")
    material = _material(actor)
    _add_note(user, "reply_in_thread", actor, material)
    _add_note(user, "content_hidden", actor, material)
    _add_note(user, "new_report", actor, material)
    login(client, "u@uni.es")
    html = client.get("/notificaciones").get_data(as_text=True)
    assert "Ana G. respondió en «Apuntes de redes»" in html
    assert "Tu material «Apuntes de redes» fue ocultado por moderación" in html
    assert "Nuevo reporte: «Apuntes de redes»" in html


def test_empty_list(app, client):
    make_user("u@uni.es")
    login(client, "u@uni.es")
    assert "No tienes notificaciones" in client.get("/notificaciones").get_data(as_text=True)


def test_open_marks_read_and_redirects_to_target(app, client):
    user = make_user("u@uni.es")
    admin = make_user("admin@uni.es", role=0)
    actor = make_user("ana@uni.es")
    material = _material(actor)
    comment = _comment(material, actor)
    on_material = _add_note(user, material=material, actor=actor)
    on_comment = _add_note(user, "reply_in_thread", actor, material, comment)
    login(client, "u@uni.es")
    resp = client.get(f"/notificaciones/{on_material.id}/abrir")
    assert resp.status_code == 302 and resp.headers["Location"] == f"/material/{material.id}"
    resp = client.get(f"/notificaciones/{on_comment.id}/abrir")
    assert resp.headers["Location"] == f"/material/{material.id}#comment-{comment.id}"
    db.session.expire_all()
    assert on_material.read_at is not None and on_comment.read_at is not None
    client.post("/logout")
    report_note = _add_note(admin, "new_report", actor, material)
    login(client, "admin@uni.es")
    resp = client.get(f"/notificaciones/{report_note.id}/abrir")
    assert resp.status_code == 302 and resp.headers["Location"] == "/admin/reportes"


def test_open_requires_login(app, client):
    user = make_user("u@uni.es")
    note = _add_note(user)
    assert client.get(f"/notificaciones/{note.id}/abrir").status_code == 302


def test_open_other_users_notification_404(app, client):
    owner = make_user("u@uni.es")
    make_user("x@uni.es")
    note = _add_note(owner, material=_material(owner))
    login(client, "x@uni.es")
    assert client.get(f"/notificaciones/{note.id}/abrir").status_code == 404
    assert client.get("/notificaciones/99999/abrir").status_code == 404
    db.session.expire_all()
    assert note.read_at is None


def test_hidden_target_for_non_author_shows_unavailable(app, client):
    user = make_user("u@uni.es")
    actor = make_user("ana@uni.es")
    material = _material(actor, hidden=True)
    note = _add_note(user, "reply_in_thread", actor, material)
    login(client, "u@uni.es")
    html = client.get("/notificaciones").get_data(as_text=True)
    assert CUSTOM_MSG in html
    assert f"/notificaciones/{note.id}/abrir" not in html
    assert material.title not in html
    resp = client.get(f"/notificaciones/{note.id}/abrir", follow_redirects=True)
    assert resp.status_code == 200 and CUSTOM_MSG in resp.get_data(as_text=True)
    assert f"/material/{material.id}" not in resp.get_data(as_text=True)


def test_hidden_target_for_author_still_linked(app, client):
    author = make_user("autor@uni.es")
    material = _material(author, hidden=True)
    note = _add_note(author, "content_hidden", None, material)
    login(client, "autor@uni.es")
    html = client.get("/notificaciones").get_data(as_text=True)
    assert f"/notificaciones/{note.id}/abrir" in html and CUSTOM_MSG not in html
    resp = client.get(f"/notificaciones/{note.id}/abrir")
    assert resp.headers["Location"] == f"/material/{material.id}"


def test_hidden_comment_unavailable_for_non_author(app, client):
    user = make_user("u@uni.es")
    actor = make_user("ana@uni.es")
    material = _material(make_user("autor@uni.es"))
    comment = _comment(material, actor, hidden=True)
    _add_note(user, "reply_in_thread", actor, material, comment)
    login(client, "u@uni.es")
    assert CUSTOM_MSG in client.get("/notificaciones").get_data(as_text=True)


def test_deleted_actor_shows_usuario_eliminado(app, client):
    user = make_user("u@uni.es")
    actor = make_user("ana@uni.es", name="Ana", surname="Gómez")
    material = _material(make_user("autor@uni.es"))
    _add_note(user, "comment_on_material", actor, material)
    db.session.delete(db.session.get(User, actor.id))
    db.session.commit()
    login(client, "u@uni.es")
    html = client.get("/notificaciones").get_data(as_text=True)
    assert "Usuario eliminado comentó en" in html


def test_deleting_comment_or_material_removes_notifications(app, client):
    author = make_user("autor@uni.es")
    other = make_user("otro@uni.es")
    m1, m2 = _material(author), _material(author)
    c1 = _comment(m1, other)
    _add_note(author, material=m1, comment=c1, actor=other)
    _add_note(author, material=m2, actor=other)
    _add_note(other, "new_report", author, m2)
    login(client, "otro@uni.es")
    client.post(f"/comentarios/{c1.id}/borrar")
    assert [n.material_id for n in _notes()] == [m2.id, m2.id]
    client.post("/logout")
    login(client, "autor@uni.es")
    client.post(f"/material/{m2.id}/borrar")
    assert _notes() == []


def test_mark_all_read(app, client):
    user = make_user("u@uni.es")
    other = make_user("x@uni.es")
    material = _material(other)
    _add_note(user, material=material)
    _add_note(user, material=material)
    theirs = _add_note(other, material=material)
    login(client, "u@uni.es")
    assert client.get("/notificaciones/leer-todas").status_code == 405
    resp = client.post("/notificaciones/leer-todas")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/notificaciones")
    assert unread_count(user) == 0
    db.session.expire_all()
    assert theirs.read_at is None


def test_mark_all_read_requires_csrf(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    make_user("u@uni.es")
    login(client, "u@uni.es")
    assert client.post("/notificaciones/leer-todas").status_code == 400
