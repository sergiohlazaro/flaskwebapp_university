"""Operaciones sobre reportes compartidas por varios blueprints."""
from sqlalchemy import delete, select

from ..extensions import db
from ..models import Comment, Report, ReportStatus, ReportTarget, utcnow


def delete_reports_for(material_ids=(), comment_ids=()):
    """Borra los reportes (en cualquier estado) que apuntan a esos materiales o comentarios.

    También los de los comentarios de cada material. No hace commit.
    """
    material_ids = list(material_ids)
    comment_ids = list(comment_ids)
    if material_ids:
        comment_ids += db.session.scalars(select(Comment.id).where(Comment.material_id.in_(material_ids)))
        db.session.execute(delete(Report).where(Report.target_type == ReportTarget.MATERIAL,
                                                Report.target_id.in_(material_ids)))
    if comment_ids:
        db.session.execute(delete(Report).where(Report.target_type == ReportTarget.COMMENT,
                                                Report.target_id.in_(comment_ids)))


def resolve_pending_reports(target_type, target_id, admin_id):
    """Marca como resueltos los reportes pendientes de un contenido. No hace commit."""
    now = utcnow()
    pending = db.session.scalars(
        select(Report).where(Report.target_type == target_type, Report.target_id == target_id,
                             Report.status == ReportStatus.PENDING)
    ).all()
    for item in pending:
        item.status = ReportStatus.RESOLVED
        item.resolved_by_id = admin_id
        item.resolved_at = now
