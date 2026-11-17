from datetime import UTC, datetime, timedelta

from tests.conftest import login, make_user
from website import db
from website.models import (
    Comment,
    Material,
    MaterialFile,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
    Subject,
)

HX = {"HX-Request": "true"}


def _material(author, hidden=False):
    subject = Subject.query.first() or Subject(name="Redes")
    db.session.add(subject)
    db.session.commit()
    material = Material(title="Apuntes de redes", description="d", subject_id=subject.id,
                        author_id=author.id, is_hidden=hidden)
    material.files.append(MaterialFile(stored_name="s.pdf", original_name="t.pdf", mime="application/pdf", size=10))
    db.session.add(material)
    db.session.commit()
    return material


def _comment(material, author, body="hola", hidden=False, minutes=0):
    comment = Comment(material_id=material.id, author_id=author.id, body=body, is_hidden=hidden,
                      created_at=datetime.now(UTC) + timedelta(minutes=minutes))
    db.session.add(comment)
    db.session.commit()
    return comment


def _setup(client):
    author = make_user("autor@uni.es", name="Autor")
    viewer = make_user("lector@uni.es", name="Lector")
    material = _material(author)
    login(client, "lector@uni.es")
    return author, viewer, material


def _post_comment(client, material, body, **kw):
    return client.post(f"/material/{material.id}/comentarios", data={"body": body}, **kw)


def test_add_comment_plain_text_and_order(app, client):
    author, viewer, material = _setup(client)
    _comment(material, author, "primero", minutes=-10)
    _comment(material, author, "tercero", minutes=10)
    resp = _post_comment(client, material, "  <b>x</b>  ")
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/material/{material.id}#comments")
    assert Comment.query.filter_by(author_id=viewer.id).one().body == "<b>x</b>"
    body = client.get(f"/material/{material.id}").get_data(as_text=True)
    assert "&lt;b&gt;x&lt;/b&gt;" in body and "<b>x</b>" not in body
    assert body.index("primero") < body.index("&lt;b&gt;x") < body.index("tercero")
    resp = _post_comment(client, material, "otro", headers=HX)
    assert resp.status_code == 200 and 'id="comment-list"' in resp.get_data(as_text=True)


def test_comment_length_limits(app, client):
    _, _, material = _setup(client)
    for bad in ("", "   ", "a" * 2001):
        resp = _post_comment(client, material, bad)
        assert resp.status_code == 302
    assert Comment.query.count() == 0
    resp = _post_comment(client, material, "", headers=HX)
    assert resp.status_code == 200 and "Escribe un comentario" in resp.get_data(as_text=True)
    resp = _post_comment(client, material, "a" * 2001, headers=HX)
    assert "2000" in resp.get_data(as_text=True) and Comment.query.count() == 0
    assert _post_comment(client, material, "a" * 2000).status_code == 302
    assert Comment.query.count() == 1


def test_delete_comment_author_or_admin_only(app, client):
    author, viewer, material = _setup(client)
    make_user("adm@uni.es", role=0)
    comment = _comment(material, author)
    assert client.post(f"/comentarios/{comment.id}/borrar").status_code == 403
    assert db.session.get(Comment, comment.id) is not None
    assert client.post("/comentarios/9999/borrar").status_code == 404
    login(client, "autor@uni.es")
    resp = client.post(f"/comentarios/{comment.id}/borrar")
    assert resp.status_code == 302 and db.session.get(Comment, comment.id) is None
    other = _comment(material, viewer)
    login(client, "adm@uni.es")
    assert client.post(f"/comentarios/{other.id}/borrar", headers=HX).status_code == 200
    assert db.session.get(Comment, other.id) is None


def test_delete_and_report_buttons_in_detail(app, client):
    author, viewer, material = _setup(client)
    mine = _comment(material, viewer, "mio")
    theirs = _comment(material, author, "suyo")
    body = client.get(f"/material/{material.id}").get_data(as_text=True)
    assert f"/comentarios/{mine.id}/borrar" in body and f"/comentarios/{theirs.id}/borrar" not in body
    assert f"target_type=comment&amp;target_id={theirs.id}" in body
    assert f"target_type=comment&amp;target_id={mine.id}" not in body
    assert "report-modal" in body


def test_hidden_comment_placeholder(app, client):
    author, _, material = _setup(client)
    make_user("adm@uni.es", role=0)
    _comment(material, author, "texto secreto", hidden=True)
    body = client.get(f"/material/{material.id}").get_data(as_text=True)
    assert "Comentario ocultado por moderación." in body and "texto secreto" not in body
    login(client, "adm@uni.es")
    body = client.get(f"/material/{material.id}").get_data(as_text=True)
    assert "texto secreto" in body and "Oculto" in body


def test_cannot_comment_on_hidden_material(app, client):
    author = make_user("autor@uni.es")
    make_user("lector@uni.es")
    material = _material(author, hidden=True)
    login(client, "lector@uni.es")
    assert _post_comment(client, material, "hola").status_code == 404
    assert Comment.query.count() == 0


def _report(client, target_type, target_id, reason="Inapropiado", details="", **kw):
    return client.post("/reportar", data={"target_type": target_type, "target_id": target_id,
                                          "reason": reason, "details": details}, **kw)


def test_report_material_and_comment(app, client):
    author, viewer, material = _setup(client)
    comment = _comment(material, author)
    resp = _report(client, "material", material.id, "Copyright", "es mío")
    assert resp.status_code == 302
    resp = _report(client, "comment", comment.id, headers=HX)
    assert resp.status_code == 200 and "Gracias, un administrador lo revisará." in resp.get_data(as_text=True)
    rows = Report.query.order_by(Report.id).all()
    assert [(r.target_type, r.reason, r.status, r.reporter_id) for r in rows] == [
        (ReportTarget.MATERIAL, ReportReason.COPYRIGHT, ReportStatus.PENDING, viewer.id),
        (ReportTarget.COMMENT, ReportReason.INAPPROPRIATE, ReportStatus.PENDING, viewer.id)]
    assert rows[0].details == "es mío"
    page = client.get(f"/reportar?target_type=material&target_id={material.id}")
    assert page.status_code == 200 and "Inapropiado" in page.get_data(as_text=True)


def test_report_requires_login(app, client):
    assert client.post("/reportar", data={}).status_code in (302, 401)
    assert Report.query.count() == 0


def test_cannot_report_own_content(app, client):
    _author, viewer, material = _setup(client)
    mine = _comment(material, viewer)
    resp = _report(client, "comment", mine.id)
    assert resp.status_code == 400 and "No puedes reportar tu propio contenido." in resp.get_data(as_text=True)
    login(client, "autor@uni.es")
    resp = _report(client, "material", material.id, headers=HX)
    assert resp.status_code == 200 and "alert-danger" in resp.get_data(as_text=True)
    assert "No puedes reportar tu propio contenido." in resp.get_data(as_text=True)
    assert Report.query.count() == 0


def test_duplicate_pending_report_is_idempotent(app, client):
    _, _, material = _setup(client)
    _report(client, "material", material.id)
    resp = _report(client, "material", material.id, headers=HX)
    assert resp.status_code == 200 and "Ya lo has reportado." in resp.get_data(as_text=True)
    resp = _report(client, "material", material.id, follow_redirects=True)
    assert "Ya lo has reportado." in resp.get_data(as_text=True)
    assert Report.query.count() == 1
    Report.query.update({"status": ReportStatus.RESOLVED})
    db.session.commit()
    _report(client, "material", material.id)
    assert Report.query.count() == 2


def test_report_reason_must_be_valid_and_details_max_500(app, client):
    _, _, material = _setup(client)
    assert _report(client, "material", material.id, reason="Spam").status_code == 400
    assert _report(client, "material", material.id, reason="").status_code == 400
    assert _report(client, "material", material.id, details="x" * 501).status_code == 400
    assert _report(client, "foo", material.id).status_code == 400
    assert Report.query.count() == 0
    assert _report(client, "material", material.id, details="x" * 500).status_code == 302
    assert Report.query.count() == 1


def test_report_unknown_or_hidden_target_404(app, client):
    author, _, _ = _setup(client)
    hidden = _material(author, hidden=True)
    comment = _comment(hidden, author)
    assert _report(client, "material", 99999).status_code == 404
    assert _report(client, "comment", 99999).status_code == 404
    assert _report(client, "material", 2**70).status_code == 404
    assert _report(client, "material", hidden.id).status_code == 404
    assert _report(client, "comment", comment.id).status_code == 404
    assert client.get("/reportar?target_type=material&target_id=99999").status_code == 404
    assert Report.query.count() == 0


def test_no_js_report_redirects_to_material_detail(app, client):
    author, _, material = _setup(client)
    comment = _comment(material, author)
    resp = client.post("/reportar", data={"target_type": "material", "target_id": material.id, "reason": "Otro"},
                       headers={"Referer": f"http://localhost/reportar?target_type=material&target_id={material.id}"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/material/{material.id}#comments")
    resp = client.post("/reportar", data={"target_type": "comment", "target_id": comment.id, "reason": "Otro"},
                       headers={"Referer": "http://localhost/reportar?x=1"})
    assert resp.headers["Location"].endswith(f"/material/{material.id}#comment-{comment.id}")
    resp = client.post("/reportar", data={"target_type": "comment", "target_id": comment.id, "reason": "Otro"})
    assert resp.headers["Location"].endswith(f"/material/{material.id}#comment-{comment.id}")


def test_htmx_report_invalid_or_unavailable_returns_danger_alert(app, client):
    _author, _, material = _setup(client)
    resp = _report(client, "material", material.id, reason="Spam", headers=HX)
    assert resp.status_code == 200 and "alert-danger" in resp.get_data(as_text=True)
    material.is_hidden = True
    db.session.commit()
    resp = _report(client, "material", material.id, headers=HX)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "alert-danger" in html and "ya no está disponible" in html
    resp = _report(client, "comment", 99999, headers=HX)
    assert resp.status_code == 200 and "ya no está disponible" in resp.get_data(as_text=True)
    assert Report.query.count() == 0
