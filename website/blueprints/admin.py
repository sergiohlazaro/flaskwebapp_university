"""Panel de administración: usuarios, asignaturas, reportes y contenido oculto (spec §5.2, §5.6, §5.9)."""

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..forms import SubjectForm
from ..models import (
    Comment,
    LoginRecord,
    Material,
    Report,
    ReportStatus,
    ReportTarget,
    Subject,
    User,
    utcnow,
)
from ..services.notifications import notify_hidden
from ..services.permissions import admin_required
from ..services.query import escape_like, page_param
from ..services.reports import resolve_pending_reports
from ..services.tokens import make_reset_token

admin = Blueprint("admin", __name__, url_prefix="/admin")

DUPLICATE_MSG = "Ya existe una asignatura con ese nombre."
USERS_PER_PAGE = 20
EXCERPT_LEN = 120
STATUS_BY_SLUG = {
    "pendiente": ReportStatus.PENDING,
    "resuelto": ReportStatus.RESOLVED,
    "descartado": ReportStatus.DISMISSED,
}


@admin.context_processor
def _tabs_context():
    count = db.session.scalar(
        select(func.count(Report.id)).where(Report.status == ReportStatus.PENDING)
    )
    return {"pending_reports_count": count or 0}


@admin.route("")
@login_required
@admin_required
def index():
    return redirect(url_for("admin.users"))


# --- Usuarios -------------------------------------------------------------

@admin.route("/usuarios")
@login_required
@admin_required
def users():
    q = request.args.get("q", "").strip()[:100]
    query = select(User).order_by(User.name, User.surname, User.id)
    if q:
        pattern = f"%{escape_like(q)}%"
        full_name = User.name + " " + User.surname
        query = query.where(
            User.name.ilike(pattern, escape="\\") | User.surname.ilike(pattern, escape="\\")
            | User.email.ilike(pattern, escape="\\") | full_name.ilike(pattern, escape="\\")
        )
    page = page_param(request.args.get("pagina"))
    pagination = db.paginate(query, page=page, per_page=USERS_PER_PAGE, error_out=False)

    def page_url(number):
        return url_for("admin.users", q=q or None, pagina=number if number > 1 else None)

    ids = [u.id for u in pagination.items]
    last_login = dict(db.session.execute(
        select(LoginRecord.user_id, func.max(LoginRecord.login_time))
        .where(LoginRecord.user_id.in_(ids)).group_by(LoginRecord.user_id)
    ).all()) if ids else {}
    rows = [(u, last_login.get(u.id)) for u in pagination.items]

    return render_template("admin/users.html", rows=rows, q=q, active_tab="users",
                           page=pagination.page, pages=pagination.pages, page_url=page_url)


def _user_or_404(user_id):
    return db.session.get(User, user_id) or abort(404)


@admin.route("/usuarios/<int:user_id>/bloquear", methods=["POST"])
@login_required
@admin_required
def block(user_id):
    user = _user_or_404(user_id)
    if user.id == current_user.id:
        flash("No puedes bloquear tu propia cuenta.", "error")
        return users(), 400
    # No hace falta proteger al "último administrador activo": quien bloquea es siempre un
    # administrador activo distinto del bloqueado (el autobloqueo se rechaza arriba).
    user.is_blocked = True
    db.session.commit()
    flash("Usuario bloqueado.", "success")
    return redirect(url_for("admin.users"))


@admin.route("/usuarios/<int:user_id>/desbloquear", methods=["POST"])
@login_required
@admin_required
def unblock(user_id):
    user = _user_or_404(user_id)
    user.is_blocked = False
    db.session.commit()
    flash("Usuario desbloqueado.", "success")
    return redirect(url_for("admin.users"))


@admin.route("/usuarios/<int:user_id>/verificar", methods=["POST"])
@login_required
@admin_required
def mark_verified(user_id):
    user = _user_or_404(user_id)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        db.session.commit()
    flash("Usuario marcado como verificado.", "success")
    return redirect(url_for("admin.users"))


@admin.route("/usuarios/<int:user_id>/profesor", methods=["POST"])
@login_required
@admin_required
def toggle_teacher(user_id):
    user = _user_or_404(user_id)
    user.is_teacher = not user.is_teacher
    db.session.commit()
    flash("Marcado como profesor/a." if user.is_teacher else "Ya no figura como profesor/a.", "success")
    return redirect(url_for("admin.users"))


@admin.route("/usuarios/<int:user_id>/enlace-recuperacion", methods=["POST"])
@login_required
@admin_required
def reset_link(user_id):
    user = _user_or_404(user_id)
    if user.is_admin:
        flash("No se puede generar un enlace de recuperación para otro administrador.", "error")
        return users(), 400
    link = url_for("auth.reset_password", token=make_reset_token(user), _external=True)
    # Sin el token en el log general.
    current_app.logger.info(f"admin {current_user.id} generó un enlace de recuperación para el usuario {user.id}")
    return render_template("admin/reset_link.html", target=user, link=link, active_tab="users")


@admin.route("/usuarios/<int:user_id>/accesos")
@login_required
@admin_required
def user_logins(user_id):
    user = _user_or_404(user_id)
    records = db.session.scalars(
        select(LoginRecord).where(LoginRecord.user_id == user.id)
        .order_by(LoginRecord.login_time.desc(), LoginRecord.id.desc()).limit(200)
    ).all()
    return render_template("admin/user_logins.html", target=user, records=records, active_tab="users")


# --- Reportes -------------------------------------------------------------

def _excerpt(text):
    return text if len(text) <= EXCERPT_LEN else text[:EXCERPT_LEN]


@admin.route("/reportes")
@login_required
@admin_required
def reports():
    slug = request.args.get("estado", "pendiente")
    if slug not in STATUS_BY_SLUG:
        slug = "pendiente"
    status = STATUS_BY_SLUG[slug]
    order = (Report.created_at.asc(), Report.id.asc()) if status is ReportStatus.PENDING else (
        Report.resolved_at.desc(), Report.id.desc())
    rows = db.session.scalars(
        select(Report).options(joinedload(Report.reporter)).where(Report.status == status).order_by(*order)
    ).all()
    material_ids = {r.target_id for r in rows if r.target_type is ReportTarget.MATERIAL}
    comment_ids = {r.target_id for r in rows if r.target_type is ReportTarget.COMMENT}
    comments = {c.id: c for c in db.session.scalars(select(Comment).where(Comment.id.in_(comment_ids)))} \
        if comment_ids else {}
    material_ids |= {c.material_id for c in comments.values()}
    materials = {m.id: m for m in db.session.scalars(select(Material).where(Material.id.in_(material_ids)))} \
        if material_ids else {}
    items = []
    for report in rows:
        link = excerpt = None
        if report.target_type is ReportTarget.MATERIAL:
            material = materials.get(report.target_id)
            if material:
                link = url_for("materials.detail", material_id=material.id)
                excerpt = material.title
        else:
            comment = comments.get(report.target_id)
            if comment and comment.material_id in materials:
                link = url_for("materials.detail", material_id=comment.material_id) + f"#comment-{comment.id}"
                excerpt = _excerpt(comment.body)
        items.append({"report": report, "link": link, "excerpt": excerpt})
    return render_template("admin/reports.html", items=items, estado=slug, active_tab="reports")


def _pending_report_or_error(report_id):
    report = db.session.get(Report, report_id) or abort(404)
    if report.status is not ReportStatus.PENDING:
        abort(400)
    return report


def _target(report):
    model = Material if report.target_type is ReportTarget.MATERIAL else Comment
    return db.session.get(model, report.target_id)


@admin.route("/reportes/<int:report_id>/ocultar", methods=["POST"])
@login_required
@admin_required
def resolve_report(report_id):
    report = _pending_report_or_error(report_id)
    target = _target(report)
    if target is None:
        abort(400)
    notify_hidden(report.target_type, target, current_user)
    target.is_hidden = True
    resolve_pending_reports(report.target_type, report.target_id, current_user.id)
    db.session.commit()
    flash("Contenido ocultado y reportes resueltos.", "success")
    return redirect(url_for("admin.reports"))


@admin.route("/reportes/<int:report_id>/descartar", methods=["POST"])
@login_required
@admin_required
def dismiss_report(report_id):
    report = _pending_report_or_error(report_id)
    report.status = ReportStatus.DISMISSED
    report.resolved_by_id = current_user.id
    report.resolved_at = utcnow()
    db.session.commit()
    flash("Reporte descartado.", "success")
    return redirect(url_for("admin.reports"))


# --- Contenido oculto -----------------------------------------------------

@admin.route("/oculto")
@login_required
@admin_required
def hidden():
    materials = db.session.scalars(
        select(Material).options(joinedload(Material.author)).where(Material.is_hidden.is_(True))
        .order_by(Material.updated_at.desc(), Material.id.desc())
    ).all()
    comments = db.session.scalars(
        select(Comment).options(joinedload(Comment.author), joinedload(Comment.material))
        .where(Comment.is_hidden.is_(True)).order_by(Comment.created_at.desc(), Comment.id.desc())
    ).all()
    return render_template("admin/hidden.html", materials=materials, comments=comments, active_tab="hidden")


@admin.route("/oculto/<target_type>/<int:target_id>/ocultar", methods=["POST"])
@login_required
@admin_required
def hide(target_type, target_id):
    """Ocultar contenido sin reporte previo (spec §5.1); resuelve los reportes pendientes."""
    kind = {"material": ReportTarget.MATERIAL, "comment": ReportTarget.COMMENT}.get(target_type) or abort(404)
    model = Material if kind is ReportTarget.MATERIAL else Comment
    item = db.session.get(model, target_id) or abort(404)
    notify_hidden(kind, item, current_user)
    item.is_hidden = True
    resolve_pending_reports(kind, item.id, current_user.id)
    db.session.commit()
    flash("Contenido ocultado.", "success")
    if kind is ReportTarget.MATERIAL:
        return redirect(url_for("materials.detail", material_id=item.id))
    return redirect(url_for("materials.detail", material_id=item.material_id) + f"#comment-{item.id}")


@admin.route("/oculto/<target_type>/<int:target_id>/restaurar", methods=["POST"])
@login_required
@admin_required
def restore(target_type, target_id):
    model = {"material": Material, "comment": Comment}.get(target_type) or abort(404)
    item = db.session.get(model, target_id) or abort(404)
    item.is_hidden = False
    db.session.commit()
    flash("Contenido restaurado.", "success")
    return redirect(url_for("admin.hidden"))


def _name_taken(name, exclude_id=None):
    key = Subject(name=name).name_key
    query = Subject.query.filter(Subject.name_key == key)
    if exclude_id is not None:
        query = query.filter(Subject.id != exclude_id)
    return db.session.query(query.exists()).scalar()


def _render(form):
    subjects = Subject.query.order_by(Subject.name_key).all()
    return render_template("admin/subjects.html", form=form, subjects=subjects, active_tab="subjects")


def _save(subject, name):
    """Guarda el nombre; devuelve un mensaje de error o None."""
    try:
        if _name_taken(name, subject.id):
            return DUPLICATE_MSG
        subject.name = name
        db.session.add(subject)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return DUPLICATE_MSG
    except ValueError as exc:
        db.session.rollback()
        return str(exc)
    return None


@admin.route("/asignaturas", methods=["GET", "POST"])
@login_required
@admin_required
def subjects():
    form = SubjectForm()
    if form.validate_on_submit():
        error = _save(Subject(name="x"), form.name.data)
        if error is None:
            flash("Asignatura creada.", "success")
            return redirect(url_for("admin.subjects"))
        form.name.errors.append(error)
    return _render(form)


@admin.route("/asignaturas/<int:subject_id>/renombrar", methods=["POST"])
@login_required
@admin_required
def rename_subject(subject_id):
    subject = db.session.get(Subject, subject_id) or abort(404)
    form = SubjectForm()
    if form.validate_on_submit():
        error = _save(subject, form.name.data)
        if error is None:
            flash("Asignatura renombrada.", "success")
        else:
            flash(error, "error")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")
    return redirect(url_for("admin.subjects"))


@admin.route("/asignaturas/<int:subject_id>/archivar", methods=["POST"])
@login_required
@admin_required
def toggle_archive_subject(subject_id):
    subject = db.session.get(Subject, subject_id) or abort(404)
    subject.is_archived = not subject.is_archived
    db.session.commit()
    flash("Asignatura archivada." if subject.is_archived else "Asignatura restaurada.", "success")
    return redirect(url_for("admin.subjects"))
