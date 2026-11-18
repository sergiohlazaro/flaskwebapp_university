"""Avisos en la aplicación (spec §5.8). Nada aquí hace commit: el aviso viaja con el evento."""
from sqlalchemy import func, select

from ..extensions import db
from ..models import Comment, Material, Notification, ReportTarget, User

COMMENT_ON_MATERIAL = "comment_on_material"
REPLY_IN_THREAD = "reply_in_thread"
CONTENT_HIDDEN = "content_hidden"
NEW_REPORT = "new_report"


def _add(user_id, kind, actor_id, material_id, comment_id=None):
    db.session.add(Notification(user_id=user_id, kind=kind, actor_id=actor_id,
                                material_id=material_id, comment_id=comment_id))


def notify_comment(comment) -> None:
    """Avisa al autor del material y a quienes ya comentaron (una vez cada uno, nunca a quien comenta)."""
    material = db.session.get(Material, comment.material_id)
    actor_id = comment.author_id
    recipients = set()
    if material.author_id != actor_id:
        recipients.add(material.author_id)
        _add(material.author_id, COMMENT_ON_MATERIAL, actor_id, material.id, comment.id)
    previous = db.session.scalars(
        select(Comment.author_id).where(Comment.material_id == material.id, Comment.id != comment.id).distinct()
    ).all()
    for user_id in sorted(set(previous) - recipients - {actor_id}):
        _add(user_id, REPLY_IN_THREAD, actor_id, material.id, comment.id)


def notify_hidden(target_type, item, admin) -> None:
    """Avisa al autor de que se ha ocultado su contenido.

    Llamar ANTES de poner `is_hidden = True`: si ya estaba oculto o lo oculta su propio autor, no avisa.
    """
    if item.is_hidden or item.author_id == admin.id:
        return
    if target_type is ReportTarget.MATERIAL:
        _add(item.author_id, CONTENT_HIDDEN, admin.id, item.id)
    else:
        _add(item.author_id, CONTENT_HIDDEN, admin.id, item.material_id, item.id)


def notify_new_report(report) -> None:
    """Un aviso por administrador, salvo quien reporta."""
    if report.target_type is ReportTarget.MATERIAL:
        material_id, comment_id = report.target_id, None
    else:
        comment = db.session.get(Comment, report.target_id)
        material_id, comment_id = comment.material_id, comment.id
    admin_ids = db.session.scalars(
        select(User.id).where(User.role == 0, User.id != report.reporter_id).order_by(User.id))
    for admin_id in admin_ids:
        _add(admin_id, NEW_REPORT, report.reporter_id, material_id, comment_id)


def unread_count(user) -> int:
    return db.session.scalar(
        select(func.count(Notification.id)).where(Notification.user_id == user.id,
                                                  Notification.read_at.is_(None))) or 0
