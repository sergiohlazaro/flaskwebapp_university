"""Perfil público, «Mi cuenta» y directorio de usuarios (spec §5.7)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import delete, func, or_, select, update
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, limiter
from ..forms import (
    WRONG_PASSWORD,
    AvatarForm,
    DeleteAccountForm,
    EmailForm,
    PasswordForm,
    ProfileForm,
)
from ..models import (
    Comment,
    Favorite,
    LoginRecord,
    Material,
    Message,
    Rating,
    Report,
    ReportTarget,
    User,
)
from ..services.uploads import UploadError, delete_upload, save_avatar
from .materials import MAX_PAGE, _escape_like, _favorite_ids, _int_param

users = Blueprint("users", __name__)

PROFILE_PER_PAGE = 12
DIRECTORY_PER_PAGE = 24
LAST_ADMIN_MSG = "No puedes borrar tu cuenta: eres el último administrador activo."


def _page():
    return min(_int_param(request.args.get("pagina")) or 1, MAX_PAGE)


def _page_url_factory(endpoint, **fixed):
    def page_url(number):
        args = {k: v for k, v in fixed.items() if v not in ("", None)}
        if number > 1:
            args["pagina"] = number
        return url_for(endpoint, **args)
    return page_url


# --- Perfil público ---------------------------------------------------------

@users.route("/u/<int:user_id>")
@login_required
def profile(user_id):
    user = db.session.get(User, user_id)
    if user is None or (user.is_blocked and not current_user.is_admin):
        abort(404)
    query = select(Material).where(Material.author_id == user.id)
    if not (current_user.id == user.id or current_user.is_admin):
        query = query.where(Material.is_hidden.is_(False))
    query = query.order_by(Material.created_at.desc(), Material.id.desc())
    pagination = db.paginate(query, page=_page(), per_page=PROFILE_PER_PAGE, error_out=False)
    return render_template(
        "users/profile.html", profile_user=user, pagination=pagination, page=pagination.page,
        pages=pagination.pages, page_url=_page_url_factory("users.profile", user_id=user.id),
        favorite_ids=_favorite_ids(pagination.items),
    )


# --- Directorio -------------------------------------------------------------

@users.route("/usuarios")
@login_required
def directory():
    text = (request.args.get("q") or "").strip()
    query = select(User).where(User.is_blocked.is_(False))
    if text:
        pattern = f"%{_escape_like(text)}%"
        full_name = User.name + " " + User.surname
        query = query.where(or_(User.name.ilike(pattern, escape="\\"), User.surname.ilike(pattern, escape="\\"),
                                full_name.ilike(pattern, escape="\\")))
    query = query.order_by(func.lower(User.name), func.lower(User.surname), User.id)
    pagination = db.paginate(query, page=_page(), per_page=DIRECTORY_PER_PAGE, error_out=False)
    return render_template("users/directory.html", pagination=pagination, q=text, page=pagination.page,
                           pages=pagination.pages, page_url=_page_url_factory("users.directory", q=text))


# --- Mi cuenta --------------------------------------------------------------

def _render_account(status=200, **forms):
    forms.setdefault("profile_form", ProfileForm(formdata=None, obj=current_user))
    forms.setdefault("avatar_form", AvatarForm(formdata=None))
    forms.setdefault("email_form", EmailForm(formdata=None))
    forms.setdefault("password_form", PasswordForm(formdata=None))
    forms.setdefault("delete_form", DeleteAccountForm(formdata=None))
    return render_template("users/account.html", **forms), status


@users.route("/cuenta")
@login_required
def account():
    return _render_account()


@users.route("/cuenta/perfil", methods=["POST"])
@login_required
def update_profile():
    form = ProfileForm()
    if not form.validate_on_submit():
        return _render_account(profile_form=form)
    current_user.name = form.name.data
    current_user.surname = form.surname.data
    current_user.bio = form.bio.data or ""
    current_user.twitter = form.twitter.data or None
    current_user.linkedin = form.linkedin.data or None
    db.session.commit()
    flash("Perfil actualizado.", "success")
    return redirect(url_for("users.account"))


@users.route("/cuenta/avatar", methods=["POST"])
@login_required
def update_avatar():
    form = AvatarForm()
    if not form.validate_on_submit():
        return _render_account(avatar_form=form)
    try:
        saved = save_avatar(form.avatar.data)
    except UploadError as exc:
        form.avatar.errors = [str(exc)]
        return _render_account(avatar_form=form)
    previous = current_user.avatar
    current_user.avatar = saved.stored_name
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        delete_upload("avatars", saved.stored_name)
        raise
    if previous:
        delete_upload("avatars", previous)
    flash("Foto de perfil actualizada.", "success")
    return redirect(url_for("users.account"))


@users.route("/cuenta/email", methods=["POST"])
@limiter.limit("10 per minute")
@login_required
def update_email():
    form = EmailForm()
    if form.validate_on_submit():
        if not check_password_hash(current_user.password, form.current_password.data):
            form.current_password.errors = [WRONG_PASSWORD]
        elif form.new_email.data == current_user.email:
            form.new_email.errors = ["Ese ya es tu email."]
        elif db.session.scalar(select(User.id).where(User.email == form.new_email.data)):
            form.new_email.errors = ["Ya existe una cuenta con ese email."]
        else:
            current_user.email = form.new_email.data
            db.session.commit()
            flash("Email actualizado.", "success")
            return redirect(url_for("users.account"))
    return _render_account(email_form=form)


@users.route("/cuenta/password", methods=["POST"])
@limiter.limit("10 per minute")
@login_required
def update_password():
    form = PasswordForm()
    if form.validate_on_submit():
        if not check_password_hash(current_user.password, form.current_password.data):
            form.current_password.errors = [WRONG_PASSWORD]
        else:
            current_user.password = generate_password_hash(form.new_password.data)
            db.session.commit()
            flash("Contraseña actualizada.", "success")
            return redirect(url_for("users.account"))
    return _render_account(password_form=form)


def _delete_user_data(user):
    """Borra al usuario y sus datos; devuelve los ficheros a eliminar del disco tras el commit.

    Los mensajes se conservan para la otra parte (sender/receiver pasan a NULL);
    las conversaciones que se quedan sin participantes se borran con sus adjuntos.
    """
    uid = user.id
    materials = db.session.scalars(select(Material).where(Material.author_id == uid)).all()
    material_ids = [m.id for m in materials]
    material_files = [f.stored_name for m in materials for f in m.files]
    own_comment_ids = list(db.session.scalars(select(Comment.id).where(Comment.author_id == uid)))
    on_my_materials = list(db.session.scalars(
        select(Comment.id).where(Comment.material_id.in_(material_ids)))) if material_ids else []
    avatar = user.avatar

    # Reportes: los que presentó y los que apuntan a lo que se va a borrar.
    db.session.execute(delete(Report).where(Report.reporter_id == uid))
    if material_ids:
        db.session.execute(delete(Report).where(Report.target_type == ReportTarget.MATERIAL,
                                                Report.target_id.in_(material_ids)))
    comment_ids = own_comment_ids + on_my_materials
    if comment_ids:
        db.session.execute(delete(Report).where(Report.target_type == ReportTarget.COMMENT,
                                                Report.target_id.in_(comment_ids)))
    db.session.execute(delete(Favorite).where(Favorite.user_id == uid))
    db.session.execute(delete(Rating).where(Rating.user_id == uid))
    db.session.execute(delete(Comment).where(Comment.author_id == uid))
    db.session.expire_all()
    for material in db.session.scalars(select(Material).where(Material.author_id == uid)).all():
        db.session.delete(material)  # cascada: ficheros, valoraciones, favoritos y comentarios
    db.session.flush()
    db.session.execute(delete(LoginRecord).where(LoginRecord.user_id == uid))

    db.session.execute(update(Message).where(Message.sender_id == uid).values(sender_id=None))
    db.session.execute(update(Message).where(Message.receiver_id == uid).values(receiver_id=None))
    orphan = (Message.sender_id.is_(None), Message.receiver_id.is_(None))
    attachments = [name for name in db.session.scalars(
        select(Message.file_stored_name).where(*orphan, Message.file_stored_name.is_not(None)))]
    db.session.execute(delete(Message).where(*orphan))

    db.session.expire_all()
    db.session.delete(db.session.get(User, uid))
    return material_files, avatar, attachments


@users.route("/cuenta/borrar", methods=["POST"])
@limiter.limit("10 per minute")
@login_required
def delete_account():
    form = DeleteAccountForm()
    if form.validate_on_submit():
        if not check_password_hash(current_user.password, form.current_password.data):
            form.current_password.errors = [WRONG_PASSWORD]
        elif current_user.is_admin and not db.session.scalar(
                select(func.count(User.id)).where(User.role == 0, User.is_blocked.is_(False),
                                                  User.id != current_user.id)):
            flash(LAST_ADMIN_MSG, "error")  # SEC-18
            return _render_account(status=400, delete_form=form)
        else:
            user = db.session.get(User, current_user.id)
            try:
                material_files, avatar, attachments = _delete_user_data(user)
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            for name in material_files:
                delete_upload("materials", name)
            if avatar:
                delete_upload("avatars", avatar)
            for name in attachments:
                delete_upload("messages", name)
            logout_user()
            flash("Tu cuenta se ha eliminado.", "success")
            return redirect(url_for("auth.login"))
    return _render_account(delete_form=form)
