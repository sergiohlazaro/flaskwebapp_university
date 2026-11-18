"""Mensajería privada entre personas, por id de usuario (spec §5.8)."""
from datetime import UTC, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func, or_, select, update

from ..extensions import db, limiter
from ..models import Message, User
from ..services.query import escape_like
from ..services.uploads import (
    ALLOWED_MATERIAL_EXTENSIONS,
    UploadError,
    delete_upload,
    save_upload,
    validate_upload,
)

messages = Blueprint("messages", __name__)

NEUTRAL_ERROR = "No se puede enviar el mensaje a este usuario."
MAX_CONTENT = 5000
PICKER_LIMIT = 20
EXCERPT = 80


def _is_htmx():
    return request.headers.get("HX-Request") == "true"


def _between(other_id):
    me = current_user.id
    return or_(
        (Message.sender_id == me) & (Message.receiver_id == other_id),
        (Message.sender_id == other_id) & (Message.receiver_id == me),
    )


def _with_deleted():
    """Mensajes cuya otra parte ya no existe (el id pasó a NULL)."""
    me = current_user.id
    return or_(
        (Message.sender_id == me) & Message.receiver_id.is_(None),
        (Message.receiver_id == me) & Message.sender_id.is_(None),
    )


def _mark_read(condition):
    db.session.execute(
        update(Message).where(condition, Message.receiver_id == current_user.id, Message.read_at.is_(None))
        .values(read_at=datetime.now(UTC)))
    db.session.commit()


def _conversations():
    """Una fila por interlocutor, la más reciente primero (consultas constantes)."""
    me = current_user.id
    other = case((Message.sender_id == me, Message.receiver_id), else_=Message.sender_id)
    mine = or_(Message.sender_id == me, Message.receiver_id == me)
    unread = func.sum(case(((Message.receiver_id == me) & Message.read_at.is_(None), 1), else_=0))
    groups = db.session.execute(
        select(other.label("other_id"), func.max(Message.id).label("last_id"), unread.label("unread"))
        .where(mine).group_by(other)).all()
    last = {m.id: m for m in db.session.scalars(
        select(Message).where(Message.id.in_([g.last_id for g in groups])))} if groups else {}
    ids = [g.other_id for g in groups if g.other_id is not None]
    people = {u.id: u for u in db.session.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    rows = [{"user": people.get(g.other_id), "deleted": g.other_id is None, "last": last[g.last_id],
             "unread": int(g.unread or 0)} for g in groups if g.other_id is None or g.other_id in people]
    rows.sort(key=lambda r: (r["last"].created_at, r["last"].id), reverse=True)
    return rows


def _render(template, *, other=None, deleted=False, thread=None, error=None, draft="", **extra):
    ctx = dict(conversations=_conversations(), other=other, deleted=deleted, error=error, draft=draft,
               active_id=other.id if other else None, excerpt=EXCERPT, **extra)
    if thread is None and (other is not None or deleted):
        condition = _with_deleted() if deleted else _between(other.id)
        thread = db.session.scalars(select(Message).where(condition).order_by(Message.created_at, Message.id)).all()
    ctx["thread"] = thread or []
    return render_template(template, **ctx)


@messages.route("/mensajes")
@login_required
def inbox():
    return _render("messages/inbox.html")


@messages.route("/mensajes/nuevo")
@login_required
def pick_user():
    text = (request.args.get("q") or "").strip()[:100]
    results = []
    if text:
        pattern = f"%{escape_like(text)}%"
        full_name = User.name + " " + User.surname
        results = db.session.scalars(
            select(User).where(
                User.is_blocked.is_(False), User.id != current_user.id,
                or_(User.name.ilike(pattern, escape="\\"), User.surname.ilike(pattern, escape="\\"),
                    full_name.ilike(pattern, escape="\\")))
            .order_by(func.lower(User.name), func.lower(User.surname), User.id).limit(PICKER_LIMIT)).all()
    if _is_htmx():
        return render_template("partials/user_picker.html", results=results, q=text)
    return render_template("messages/inbox.html", picker=True, results=results, q=text,
                           conversations=_conversations(), other=None, deleted=False, thread=[],
                           active_id=None, excerpt=EXCERPT, error=None, draft="")


@messages.route("/mensajes/eliminados")
@login_required
def deleted_conversation():
    _mark_read(_with_deleted())
    return _render("messages/conversation.html", deleted=True)


@messages.route("/mensajes/<int:user_id>")
@login_required
def conversation(user_id):
    other = db.session.get(User, user_id)
    if other is None or other.id == current_user.id:
        abort(404)
    _mark_read(Message.sender_id == other.id)
    return _render("messages/conversation.html", other=other)


def _fail(other, text, draft, status_redirect):
    """Error al enviar: fragmento con htmx; sin JS, aviso y redirección."""
    if _is_htmx():
        if other is None:
            return render_template("partials/message_thread.html", other=None, deleted=False, thread=[],
                                   error=text, draft="")
        return _render("partials/message_thread.html", other=other, error=text, draft=draft)
    flash(text, "error")
    return redirect(status_redirect)


@messages.route("/mensajes/<int:user_id>", methods=["POST"])
@login_required
@limiter.limit("15 per hour")
def send(user_id):
    other = db.session.get(User, user_id)
    if other is None or other.is_blocked or other.id == current_user.id:
        return _fail(None, NEUTRAL_ERROR, "", url_for("messages.inbox"))
    back = url_for("messages.conversation", user_id=other.id)
    content = (request.form.get("content") or "").strip()
    if not content:
        return _fail(other, "El mensaje no puede estar vacío.", content, back)
    if len(content) > MAX_CONTENT:
        return _fail(other, f"El mensaje no puede superar los {MAX_CONTENT} caracteres.", content, back)

    upload = request.files.get("file")
    saved = None
    if upload is not None and upload.filename:
        try:
            validate_upload(upload, ALLOWED_MATERIAL_EXTENSIONS)
            saved = save_upload(upload, "messages", ALLOWED_MATERIAL_EXTENSIONS)
        except UploadError as exc:
            return _fail(other, str(exc), content, back)

    db.session.add(Message(
        sender_id=current_user.id, receiver_id=other.id, content=content,
        file_stored_name=saved.stored_name if saved else None,
        file_original_name=saved.original_name if saved else None))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        if saved:
            delete_upload("messages", saved.stored_name)
        raise
    if _is_htmx():
        return _render("partials/message_thread.html", other=other)
    return redirect(back)
