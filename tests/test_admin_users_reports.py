from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import login, make_user
from website import db
from website.models import (
    Comment,
    LoginRecord,
    Material,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
    Subject,
    User,
)

ROUTES = [
    ("get", "/admin"),
    ("get", "/admin/usuarios"),
    ("post", "/admin/usuarios/1/bloquear"),
    ("post", "/admin/usuarios/1/desbloquear"),
    ("post", "/admin/usuarios/1/profesor"),
    ("get", "/admin/usuarios/1/accesos"),
    ("get", "/admin/reportes"),
    ("post", "/admin/reportes/1/ocultar"),
    ("post", "/admin/reportes/1/descartar"),
    ("get", "/admin/oculto"),
    ("post", "/admin/oculto/material/1/restaurar"),
    ("post", "/admin/oculto/comment/1/restaurar"),
    ("get", "/admin/asignaturas"),
    ("post", "/admin/asignaturas"),
    ("post", "/admin/asignaturas/1/renombrar"),
    ("post", "/admin/asignaturas/1/archivar"),
]


def _admin(client, email="admin@example.com"):
    admin = make_user(email, role=0, name="Admin")
    login(client, email)
    return admin


def _material(author, title="Apuntes de redes", hidden=False):
    subject = Subject.query.first() or Subject(name="Redes")
    db.session.add(subject)
    db.session.commit()
    material = Material(title=title, description="d", subject_id=subject.id, author_id=author.id,
                        is_hidden=hidden)
    db.session.add(material)
    db.session.commit()
    return material


def _comment(material, author, body="hola", hidden=False):
    comment = Comment(material_id=material.id, author_id=author.id, body=body, is_hidden=hidden)
    db.session.add(comment)
    db.session.commit()
    return comment


def _report(reporter, kind, target_id, minutes=0, status=ReportStatus.PENDING):
    report = Report(reporter_id=reporter.id, target_type=kind, target_id=target_id,
                    reason=ReportReason.OTHER,
                    details="detalle", status=status,
                    created_at=datetime.now(UTC) + timedelta(minutes=minutes))
    db.session.add(report)
    db.session.commit()
    return report


@pytest.mark.parametrize("method,url", ROUTES)
def test_non_admin_forbidden_on_every_admin_route(client, method, url):
    make_user("u@example.com")
    login(client, "u@example.com")
    assert getattr(client, method)(url, data={"name": "X"}).status_code == 403


@pytest.mark.parametrize("method,url", ROUTES)
def test_anonymous_redirected_on_every_admin_route(client, method, url):
    assert getattr(client, method)(url, data={"name": "X"}).status_code == 302


def test_admin_root_redirects_to_users(client):
    _admin(client)
    r = client.get("/admin")
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/usuarios")


def test_legacy_routes_gone(client):
    _admin(client)
    target = make_user("t@example.com")
    assert client.post(f"/block_user/{target.id}").status_code == 404
    assert client.post(f"/unblock_user/{target.id}").status_code == 404


def test_block_unblock_and_toggle_teacher(client):
    _admin(client)
    target = make_user("t@example.com")
    r = client.post(f"/admin/usuarios/{target.id}/bloquear", follow_redirects=True)
    assert "Usuario bloqueado." in r.get_data(as_text=True)
    assert db.session.get(User, target.id).is_blocked is True
    r = client.post(f"/admin/usuarios/{target.id}/desbloquear", follow_redirects=True)
    assert "Usuario desbloqueado." in r.get_data(as_text=True)
    assert db.session.get(User, target.id).is_blocked is False
    client.post(f"/admin/usuarios/{target.id}/profesor")
    assert db.session.get(User, target.id).is_teacher is True
    client.post(f"/admin/usuarios/{target.id}/profesor")
    assert db.session.get(User, target.id).is_teacher is False
    assert client.post("/admin/usuarios/99999/bloquear").status_code == 404


def test_non_admin_cannot_block_and_state_unchanged(client):
    admin = make_user("admin@example.com", role=0)
    make_user("attacker@example.com")
    login(client, "attacker@example.com")
    assert client.post(f"/admin/usuarios/{admin.id}/bloquear").status_code == 403
    assert db.session.get(User, admin.id).is_blocked is False


def test_non_admin_cannot_unblock_and_state_unchanged(client):
    victim = make_user("blocked@example.com")
    victim.is_blocked = True
    db.session.commit()
    make_user("attacker@example.com")
    login(client, "attacker@example.com")
    assert client.post(f"/admin/usuarios/{victim.id}/desbloquear").status_code == 403
    assert db.session.get(User, victim.id).is_blocked is True


def test_non_admin_cannot_toggle_teacher(client):
    victim = make_user("v@example.com")
    make_user("attacker@example.com")
    login(client, "attacker@example.com")
    assert client.post(f"/admin/usuarios/{victim.id}/profesor").status_code == 403
    assert db.session.get(User, victim.id).is_teacher is False


def test_admin_cannot_block_self(client):
    admin = _admin(client)
    r = client.post(f"/admin/usuarios/{admin.id}/bloquear", follow_redirects=True)
    assert r.status_code == 400
    assert "No puedes bloquear tu propia cuenta." in r.get_data(as_text=True)
    assert db.session.get(User, admin.id).is_blocked is False


def test_admin_can_block_another_admin_while_one_stays_active(client):
    _admin(client)
    other = make_user("other@example.com", role=0)
    assert client.post(f"/admin/usuarios/{other.id}/bloquear").status_code == 302
    assert db.session.get(User, other.id).is_blocked is True


def test_users_search_by_name_or_email(client):
    _admin(client)
    make_user("ana@uni.es", name="Ana", surname="Pérez")
    make_user("luis@uni.es", name="Luis", surname="Gómez")
    make_user("100%@uni.es", name="Cien", surname="Porciento")
    html = client.get("/admin/usuarios?q=ANA").get_data(as_text=True)
    assert "ana@uni.es" in html and "luis@uni.es" not in html
    html = client.get("/admin/usuarios?q=gómez").get_data(as_text=True)
    assert "luis@uni.es" in html and "ana@uni.es" not in html
    html = client.get("/admin/usuarios?q=luis@").get_data(as_text=True)
    assert "luis@uni.es" in html
    html = client.get("/admin/usuarios?q=%25").get_data(as_text=True)
    assert "100%@uni.es" in html and "ana@uni.es" not in html


def test_users_list_columns_and_pagination(client):
    _admin(client)
    for i in range(24):
        make_user(f"u{i:02d}@uni.es")
    user = User.query.filter_by(email="u00@uni.es").first()
    db.session.add(LoginRecord(user_id=user.id, ip_address="1.2.3.4"))
    db.session.commit()
    page1 = client.get("/admin/usuarios").get_data(as_text=True)
    page2 = client.get("/admin/usuarios?pagina=2").get_data(as_text=True)
    assert "Activo" in page1 and "Admin" in page1 and "—" in page1
    assert page1.count("@uni.es") + page2.count("@uni.es") >= 24
    assert client.get("/admin/usuarios?pagina=abc").status_code == 200
    assert client.get("/admin/usuarios?pagina=99999999999999999999").status_code == 200


def test_user_logins(client):
    _admin(client)
    user = make_user("t@example.com")
    now = datetime.now(UTC)
    db.session.add(LoginRecord(user_id=user.id, ip_address="10.0.0.1", login_time=now - timedelta(days=1)))
    db.session.add(LoginRecord(user_id=user.id, ip_address="10.0.0.2", login_time=now))
    db.session.commit()
    html = client.get(f"/admin/usuarios/{user.id}/accesos").get_data(as_text=True)
    assert html.index("10.0.0.2") < html.index("10.0.0.1")
    assert client.get("/admin/usuarios/99999/accesos").status_code == 404


def test_reports_queue_filters_and_links(client):
    admin = _admin(client)
    author = make_user("autor@uni.es")
    reporter = make_user("rep@uni.es", name="Rita", surname="Reporter")
    material = _material(author)
    comment = _comment(material, author, body="c" * 200)
    _report(reporter, ReportTarget.MATERIAL, material.id, minutes=-10)
    _report(reporter, ReportTarget.COMMENT, comment.id, minutes=-5)
    _report(reporter, ReportTarget.MATERIAL, 99999, minutes=-1)
    done = _report(reporter, ReportTarget.MATERIAL, material.id, status=ReportStatus.RESOLVED)
    done.resolved_by_id = admin.id
    db.session.commit()
    html = client.get("/admin/reportes").get_data(as_text=True)
    assert "Rita Reporter" in html and "detalle" in html
    assert f"/material/{material.id}#comment-{comment.id}" in html
    assert "c" * 120 in html and "c" * 121 not in html
    assert "Contenido eliminado" in html
    assert html.index("Apuntes de redes") < html.index("c" * 120)  # el más antiguo primero
    assert client.get("/admin/reportes?estado=resuelto").status_code == 200
    assert client.get("/admin/reportes?estado=descartado").status_code == 200
    assert client.get("/admin/reportes?estado=hack").get_data(as_text=True).count("detalle") == 3


def test_resolving_report_hides_target_and_resolves_all_pending_on_it(client):
    admin = _admin(client)
    author = make_user("autor@uni.es")
    r1, r2 = make_user("r1@uni.es"), make_user("r2@uni.es")
    material = _material(author)
    other = _material(author, title="Otro")
    a = _report(r1, ReportTarget.MATERIAL, material.id)
    b = _report(r2, ReportTarget.MATERIAL, material.id)
    c = _report(r1, ReportTarget.MATERIAL, other.id)
    resp = client.post(f"/admin/reportes/{a.id}/ocultar")
    assert resp.status_code == 302
    assert db.session.get(Material, material.id).is_hidden is True
    assert db.session.get(Material, other.id).is_hidden is False
    for report in (a, b):
        report = db.session.get(Report, report.id)
        assert report.status is ReportStatus.RESOLVED
        assert report.resolved_by_id == admin.id and report.resolved_at is not None
    assert db.session.get(Report, c.id).status is ReportStatus.PENDING
    assert client.post(f"/admin/reportes/{a.id}/ocultar").status_code == 400
    assert client.post(f"/admin/reportes/{a.id}/descartar").status_code == 400
    assert client.post("/admin/reportes/99999/ocultar").status_code == 404


def test_resolving_comment_report_hides_comment(client):
    _admin(client)
    author, reporter = make_user("autor@uni.es"), make_user("r@uni.es")
    comment = _comment(_material(author), author)
    report = _report(reporter, ReportTarget.COMMENT, comment.id)
    client.post(f"/admin/reportes/{report.id}/ocultar")
    assert db.session.get(Comment, comment.id).is_hidden is True


def test_resolving_report_of_deleted_target_is_refused(client):
    _admin(client)
    report = _report(make_user("r@uni.es"), ReportTarget.MATERIAL, 99999)
    assert client.post(f"/admin/reportes/{report.id}/ocultar").status_code == 400
    assert db.session.get(Report, report.id).status is ReportStatus.PENDING
    assert client.post(f"/admin/reportes/{report.id}/descartar").status_code == 302


def test_dismiss_report(client):
    admin = _admin(client)
    author, reporter = make_user("autor@uni.es"), make_user("r@uni.es")
    material = _material(author)
    a = _report(reporter, ReportTarget.MATERIAL, material.id)
    b = _report(make_user("r2@uni.es"), ReportTarget.MATERIAL, material.id)
    assert client.post(f"/admin/reportes/{a.id}/descartar").status_code == 302
    a = db.session.get(Report, a.id)
    assert a.status is ReportStatus.DISMISSED
    assert a.resolved_by_id == admin.id and a.resolved_at is not None
    assert db.session.get(Report, b.id).status is ReportStatus.PENDING
    assert db.session.get(Material, material.id).is_hidden is False
    assert client.post(f"/admin/reportes/{a.id}/descartar").status_code == 400
    assert client.post("/admin/reportes/99999/descartar").status_code == 404


def test_restore_hidden_material_and_comment(client):
    _admin(client)
    author = make_user("autor@uni.es")
    material = _material(author, title="Material oculto", hidden=True)
    comment = _comment(_material(author, title="Visible"), author, body="comentario oculto", hidden=True)
    html = client.get("/admin/oculto").get_data(as_text=True)
    assert "Material oculto" in html and "comentario oculto" in html
    assert client.post(f"/admin/oculto/material/{material.id}/restaurar").status_code == 302
    assert client.post(f"/admin/oculto/comment/{comment.id}/restaurar").status_code == 302
    assert db.session.get(Material, material.id).is_hidden is False
    assert db.session.get(Comment, comment.id).is_hidden is False
    assert client.post(f"/admin/oculto/foo/{material.id}/restaurar").status_code == 404
    assert client.post("/admin/oculto/material/99999/restaurar").status_code == 404


def test_pending_count_in_tabs(client):
    _admin(client)
    author, reporter = make_user("autor@uni.es"), make_user("r@uni.es")
    material = _material(author)
    _report(reporter, ReportTarget.MATERIAL, material.id)
    _report(make_user("r2@uni.es"), ReportTarget.MATERIAL, material.id)
    _report(reporter, ReportTarget.MATERIAL, material.id, status=ReportStatus.DISMISSED)
    html = client.get("/admin/asignaturas").get_data(as_text=True)
    assert 'href="/admin/reportes"' in html and 'href="/admin/oculto"' in html
    assert '<span class="badge text-bg-danger">2</span>' in html


def test_teacher_badge_follows_current_flag(client):
    admin = _admin(client)
    teacher = make_user("prof@uni.es", is_teacher=True, name="Prof")
    _material(teacher, title="Tema profe")
    assert "Profesor/a" in client.get("/explorar").get_data(as_text=True)
    client.post(f"/admin/usuarios/{teacher.id}/profesor")
    assert admin.is_admin
    assert "Profesor/a" not in client.get("/explorar").get_data(as_text=True)
