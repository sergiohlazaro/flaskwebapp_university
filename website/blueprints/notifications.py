"""Lista de avisos y apertura de cada uno (spec §5.8)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Notification, utcnow
from ..services.notifications import CONTENT_HIDDEN, NEW_REPORT, REPLY_IN_THREAD
from ..services.permissions import can_view_material
from ..services.query import page_param

notifications = Blueprint("notifications", __name__)

PER_PAGE = 20
UNAVAILABLE_MSG = "Este contenido ya no está disponible"
DELETED_ACTOR = "Usuario eliminado"


def _available(note, user) -> bool:
    """Un destino oculto solo se muestra a su autor y a los administradores."""
    if note.kind == NEW_REPORT:
        return user.is_admin
    if note.material is None or not can_view_material(user, note.material):
        return False
    comment = note.comment
    return comment is None or not comment.is_hidden or user.is_admin or comment.author_id == user.id


def _text(note) -> str:
    actor = note.actor.display_name if note.actor else DELETED_ACTOR
    title = note.material.title if note.material else ""
    if note.kind == REPLY_IN_THREAD:
        return f"{actor} respondió en «{title}»"
    if note.kind == CONTENT_HIDDEN:
        if note.comment_id:
            return f"Tu comentario en «{title}» fue ocultado por moderación"
        return f"Tu material «{title}» fue ocultado por moderación"
    if note.kind == NEW_REPORT:
        return f"Nuevo reporte: «{title}»"
    return f"{actor} comentó en «{title}»"


def _target_url(note) -> str:
    if note.kind == NEW_REPORT:
        return url_for("admin.reports")
    url = url_for("materials.detail", material_id=note.material_id)
    return f"{url}#comment-{note.comment_id}" if note.comment_id else url


@notifications.route("/notificaciones")
@login_required
def index():
    query = (select(Notification).where(Notification.user_id == current_user.id)
             .options(selectinload(Notification.actor), selectinload(Notification.material),
                      selectinload(Notification.comment))
             .order_by(Notification.created_at.desc(), Notification.id.desc()))
    pagination = db.paginate(query, page=page_param(request.args.get("pagina")), per_page=PER_PAGE,
                             error_out=False)

    def page_url(number):
        return url_for("notifications.index", pagina=number) if number > 1 else url_for("notifications.index")

    items = [{"note": n, "text": _text(n), "available": _available(n, current_user)} for n in pagination.items]
    return render_template("notifications/list.html", items=items, unavailable_msg=UNAVAILABLE_MSG,
                           page=pagination.page, pages=pagination.pages, page_url=page_url)


@notifications.route("/notificaciones/<int:notification_id>/abrir")
@login_required
def open(notification_id):
    note = db.session.get(Notification, notification_id)
    if note is None or note.user_id != current_user.id:
        abort(404)
    if note.read_at is None:
        note.read_at = utcnow()
        db.session.commit()
    if not _available(note, current_user):
        flash(UNAVAILABLE_MSG + ".", "info")
        return redirect(url_for("notifications.index"))
    return redirect(_target_url(note))


@notifications.route("/notificaciones/leer-todas", methods=["POST"])
@login_required
def read_all():
    db.session.execute(update(Notification).where(Notification.user_id == current_user.id,
                                                  Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.session.commit()
    return redirect(url_for("notifications.index"))
