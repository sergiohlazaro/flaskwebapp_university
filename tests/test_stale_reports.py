"""Borrar material o comentarios elimina sus reportes (y los ids no se reutilizan)."""
from sqlalchemy import select

from tests.conftest import login, make_user
from tests.test_comments_reports import _comment, _material
from website import db
from website.models import Report, ReportReason, ReportStatus, ReportTarget


def _report(reporter, kind, target_id):
    report = Report(reporter_id=reporter.id, target_type=kind, target_id=target_id, reason=ReportReason.OTHER)
    db.session.add(report)
    db.session.commit()
    return report


def _all_reports():
    return db.session.scalars(select(Report)).all()


def test_delete_material_removes_its_and_its_comments_reports(client):
    author = make_user("autor@uni.es")
    other = make_user("otro@uni.es")
    material = _material(author)
    comment = _comment(material, other)
    keep_material = _material(author)
    _report(other, ReportTarget.MATERIAL, material.id)
    _report(other, ReportTarget.COMMENT, comment.id)
    _report(other, ReportTarget.MATERIAL, keep_material.id)
    login(client, "autor@uni.es")
    assert client.post(f"/material/{material.id}/borrar").status_code == 302
    remaining = _all_reports()
    assert [(r.target_type, r.target_id) for r in remaining] == [(ReportTarget.MATERIAL, keep_material.id)]


def test_delete_comment_removes_its_reports(client):
    author = make_user("autor@uni.es")
    other = make_user("otro@uni.es")
    material = _material(author)
    comment = _comment(material, other)
    keep = _comment(material, other, body="otro")
    _report(author, ReportTarget.COMMENT, comment.id)
    _report(author, ReportTarget.COMMENT, keep.id)
    login(client, "otro@uni.es")
    client.post(f"/comentarios/{comment.id}/borrar")
    assert [r.target_id for r in _all_reports()] == [keep.id]


def test_new_material_never_inherits_reports_of_deleted_one(client):
    author = make_user("autor@uni.es")
    other = make_user("otro@uni.es")
    material = _material(author)
    old_id = material.id
    _report(other, ReportTarget.MATERIAL, old_id)
    login(client, "autor@uni.es")
    client.post(f"/material/{old_id}/borrar")
    fresh = _material(author)
    assert fresh.id != old_id
    assert db.session.scalars(select(Report)).all() == []


def test_new_comment_id_is_not_reused_after_delete(client):
    author = make_user("autor@uni.es")
    material = _material(author)
    comment = _comment(material, author)
    old_id = comment.id
    login(client, "autor@uni.es")
    client.post(f"/comentarios/{old_id}/borrar")
    assert _comment(material, author, body="nuevo").id != old_id


def test_resolved_reports_are_deleted_too(client):
    author = make_user("autor@uni.es")
    other = make_user("otro@uni.es")
    material = _material(author)
    report = _report(other, ReportTarget.MATERIAL, material.id)
    report.status = ReportStatus.RESOLVED
    db.session.commit()
    login(client, "autor@uni.es")
    client.post(f"/material/{material.id}/borrar")
    assert _all_reports() == []
