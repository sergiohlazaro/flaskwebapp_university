"""Crear, editar y borrar material didáctico (spec §5.1, §5.2)."""
from collections.abc import Mapping
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import Select, column, func, literal_column, select, table
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest, NotFound

from ..extensions import db
from ..forms import CommentForm, MaterialForm, ReportForm
from ..models import (
    Comment,
    Course,
    Favorite,
    Material,
    MaterialFile,
    MaterialKind,
    Rating,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
    Subject,
    User,
)
from ..services.notifications import notify_comment, notify_new_report
from ..services.permissions import can_view_material
from ..services.query import (
    favorite_ids,
    feed_loader_options,
    int_param,
    page_param,
)
from ..services.reports import delete_reports_for
from ..services.search import build_match
from ..services.uploads import (
    ALLOWED_MATERIAL_EXTENSIONS,
    UploadError,
    delete_upload,
    save_upload,
    validate_upload,
)

materials = Blueprint("materials", __name__)

FTS = table("material_fts", column("rowid"), column("material_fts"))
MAX_FILES = 5
PER_PAGE = 12
NO_FILES_MSG = "Sube al menos un fichero."
TOO_MANY_MSG = "Máximo 5 ficheros."


def _get_or_404(material_id):
    material = db.session.get(Material, material_id)
    if material is None:
        abort(404)
    return material


def _set_choices(form, current_subject=None):
    query = Subject.query.filter(Subject.is_archived.is_(False))
    subjects = query.order_by(Subject.name_key).all()
    if current_subject is not None and current_subject.is_archived:
        subjects.append(current_subject)
    form.subject_id.choices = [(0, "Selecciona una asignatura")] + [(s.id, s.name) for s in subjects]
    form.course.choices = [("", "—")] + [(c.value, c.value) for c in Course]
    form.kind.choices = [("", "—")] + [(k.value, k.value) for k in MaterialKind]


def _uploads(form):
    return [f for f in (form.files.data or []) if f and f.filename]


def _render(form, material=None):
    return render_template("materials/form.html", form=form, material=material)


def _store(form, material, new_files, existing):
    """Valida y guarda los ficheros nuevos y confirma. Devuelve True si todo fue bien."""
    if existing + len(new_files) == 0:
        form.files.errors = [NO_FILES_MSG]
        return False
    if existing + len(new_files) > MAX_FILES:
        form.files.errors = [TOO_MANY_MSG]
        return False
    saved = []
    try:
        for upload in new_files:
            validate_upload(upload, ALLOWED_MATERIAL_EXTENSIONS)
        for upload in new_files:
            saved.append(save_upload(upload, "materials", ALLOWED_MATERIAL_EXTENSIONS))
        material.title = form.title.data
        material.description = form.description.data or ""
        material.subject_id = form.subject_id.data
        material.course = Course(form.course.data) if form.course.data else None
        material.kind = MaterialKind(form.kind.data) if form.kind.data else None
        for item in saved:
            material.files.append(MaterialFile(stored_name=item.stored_name, original_name=item.original_name,
                                               mime=item.mime, size=item.size))
        db.session.add(material)
        db.session.commit()
    except UploadError as exc:
        db.session.rollback()
        _cleanup(saved)
        form.files.errors = [str(exc)]
        return False
    except Exception:
        db.session.rollback()
        _cleanup(saved)
        raise
    return True


def _cleanup(saved):
    for item in saved:
        delete_upload("materials", item.stored_name)


@materials.route("/material/nuevo", methods=["GET", "POST"])
@login_required
def new():
    form = MaterialForm()
    _set_choices(form)
    if form.validate_on_submit():
        material = Material(author_id=current_user.id)
        if _store(form, material, _uploads(form), 0):
            flash("Material publicado.", "success")
            return redirect(url_for("materials.detail", material_id=material.id))
    return _render(form)


def _visible_or_404(material_id):
    material = _get_or_404(material_id)
    if not can_view_material(current_user, material):
        abort(404)
    return material


def _rating_context(material):
    mine = db.session.get(Rating, (current_user.id, material.id))
    return {"material": material, "my_stars": mine.stars if mine else 0,
            "can_rate": material.author_id != current_user.id}


def _is_saved(material):
    return db.session.get(Favorite, (current_user.id, material.id)) is not None


def _internal_referrer():
    referrer = request.referrer
    if not referrer or "\\" in referrer:
        return None
    parts = urlsplit(referrer)
    if parts.scheme or parts.netloc:
        if parts.scheme not in ("http", "https") or parts.netloc != request.host:
            return None
    elif not referrer.startswith("/") or referrer.startswith("//"):
        return None
    return referrer


def _back(material):
    return redirect(_internal_referrer() or url_for("materials.detail", material_id=material.id))


def _comment_context(material, form=None):
    comments = db.session.scalars(select(Comment).where(Comment.material_id == material.id)
                                  .order_by(Comment.created_at, Comment.id)).all()
    return {"comments": comments, "comment_form": form or CommentForm(formdata=None),
            "report_form": ReportForm(formdata=None)}


def _comments_response(material, form=None):
    """Lista de comentarios para htmx; sin htmx, vuelve al detalle."""
    if request.headers.get("HX-Request"):
        return render_template("partials/comment_list.html", material=material, **_comment_context(material, form))
    return redirect(url_for("materials.detail", material_id=material.id) + "#comments")


@materials.route("/material/<int:material_id>")
@login_required
def detail(material_id):
    material = _visible_or_404(material_id)
    return render_template("materials/detail.html", saved=_is_saved(material),
                           **_comment_context(material), **_rating_context(material))


@materials.route("/material/<int:material_id>/valorar", methods=["POST"])
@login_required
def rate(material_id):
    material = _visible_or_404(material_id)
    if material.author_id == current_user.id:
        abort(403)
    stars = int_param(request.form.get("stars"), minimum=0)
    if stars is None or stars > 5:
        abort(400)
    for attempt in range(2):
        rating = db.session.get(Rating, (current_user.id, material.id))
        if stars == 0:
            if rating is not None:
                db.session.delete(rating)
        elif rating is None:
            db.session.add(Rating(user_id=current_user.id, material_id=material.id, stars=stars))
        else:
            rating.stars = stars
        try:
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()  # carrera: otro envío creó o borró la fila; se relee y se repite
            if attempt:
                raise
    db.session.refresh(material)
    if request.headers.get("HX-Request"):
        return render_template("partials/rating.html", **_rating_context(material))
    return _back(material)


@materials.route("/material/<int:material_id>/guardar", methods=["POST"])
@login_required
def toggle_favorite(material_id):
    material = _visible_or_404(material_id)
    favorite = db.session.get(Favorite, (current_user.id, material.id))
    try:
        if favorite is None:
            db.session.add(Favorite(user_id=current_user.id, material_id=material.id))
        else:
            db.session.delete(favorite)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()  # doble envío: ya estaba guardado
    if request.headers.get("HX-Request"):
        return render_template("partials/favorite_button.html", material=material, saved=_is_saved(material))
    return _back(material)


@materials.route("/material/<int:material_id>/comentarios", methods=["POST"])
@login_required
def add_comment(material_id):
    material = _get_or_404(material_id)
    if material.is_hidden and not current_user.is_admin:
        abort(404)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(material_id=material.id, author_id=current_user.id, body=form.body.data)
        db.session.add(comment)
        db.session.flush()
        notify_comment(comment)
        db.session.commit()
        return _comments_response(material)
    if request.headers.get("HX-Request"):
        return _comments_response(material, form)
    flash(" ".join(form.body.errors) or "No se pudo publicar el comentario.", "error")
    return _comments_response(material)


@materials.route("/comentarios/<int:comment_id>/borrar", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = db.session.get(Comment, comment_id)
    if comment is None:
        abort(404)
    if comment.author_id != current_user.id and not current_user.is_admin:
        abort(403)
    material = _visible_or_404(comment.material_id)
    delete_reports_for(comment_ids=[comment.id])
    db.session.delete(comment)
    db.session.commit()
    return _comments_response(material)


OWN_CONTENT_MSG = "No puedes reportar tu propio contenido."
REPORTED_MSG = "Ya lo has reportado."
THANKS_MSG = "Gracias, un administrador lo revisará."
INVALID_REPORT_MSG = "Revisa el motivo y los detalles del reporte."


def _report_target(target_type, target_id):
    """Devuelve (tipo, id, autor_id, material_id) del contenido reportable; 404 si no existe o no es visible."""
    if target_type not in {t.value for t in ReportTarget}:
        abort(400)
    number = int_param(target_id)
    if number is None:
        abort(404)
    if target_type == ReportTarget.MATERIAL.value:
        material = _visible_or_404(number)
        return ReportTarget.MATERIAL, number, material.author_id, material.id
    comment = db.session.get(Comment, number)
    if comment is None:
        abort(404)
    _visible_or_404(comment.material_id)
    if comment.is_hidden and not current_user.is_admin:
        abort(404)
    return ReportTarget.COMMENT, number, comment.author_id, comment.material_id


UNAVAILABLE_MSG = "Este contenido ya no está disponible."


def _report_reply(message, category, status, form=None, target=None, anchor=None):
    if request.headers.get("HX-Request"):
        # htmx no sustituye respuestas 4xx: el aviso viaja siempre en un 200.
        return render_template("partials/report_result.html", message=message, category=category)
    if status == 200:
        flash(message, "success" if category == "success" else "info")
        return redirect(url_for("materials.detail", material_id=anchor[0]) + anchor[1])
    form = form or ReportForm(formdata=None)
    return render_template("materials/report.html", form=form, message=message,
                           target_type=target[0] if target else "", target_id=target[1] if target else "",
                           back_url=_internal_referrer() or url_for("materials.explore")), status


@materials.route("/reportar", methods=["GET", "POST"])
@login_required
def report():
    source = request.form if request.method == "POST" else request.args
    try:
        kind, target_id, author_id, material_id = _report_target(source.get("target_type"), source.get("target_id"))
    except (NotFound, BadRequest):
        if request.method == "POST" and request.headers.get("HX-Request"):
            return _report_reply(UNAVAILABLE_MSG, "danger", 404)
        raise
    target = (kind.value, target_id)
    anchor = (material_id, "#comments" if kind is ReportTarget.MATERIAL else f"#comment-{target_id}")
    if request.method == "GET":
        return render_template("materials/report.html", form=ReportForm(formdata=None), message=None,
                               target_type=target[0], target_id=target[1],
                               back_url=_internal_referrer() or url_for("materials.explore"))
    form = ReportForm()
    if author_id == current_user.id:
        return _report_reply(OWN_CONTENT_MSG, "danger", 400, form, target)
    if not form.validate_on_submit():
        return _report_reply(INVALID_REPORT_MSG, "danger", 400, form, target)
    pending = Report.query.filter_by(reporter_id=current_user.id, target_type=kind, target_id=target_id,
                                     status=ReportStatus.PENDING).first()
    if pending is not None:
        return _report_reply(REPORTED_MSG, "info", 200, anchor=anchor)
    new_report = Report(reporter_id=current_user.id, target_type=kind, target_id=target_id,
                        reason=ReportReason(form.reason.data), details=form.details.data or "")
    db.session.add(new_report)
    notify_new_report(new_report)
    db.session.commit()
    return _report_reply(THANKS_MSG, "success", 200, anchor=anchor)


@materials.route("/guardados")
@login_required
def saved():
    page = page_param(request.args.get("pagina"))
    query = (select(Material).join(Favorite, Favorite.material_id == Material.id)
             .where(Favorite.user_id == current_user.id, Material.is_hidden.is_(False))
             .order_by(Favorite.created_at.desc(), Material.id.desc())
             .options(*feed_loader_options()))
    pagination = db.paginate(query, page=page, per_page=PER_PAGE, error_out=False)

    def page_url(number):
        return url_for("materials.saved", pagina=number) if number > 1 else url_for("materials.saved")

    return render_template("materials/saved.html", pagination=pagination, page=pagination.page,
                           pages=pagination.pages, page_url=page_url,
                           favorite_ids=favorite_ids(pagination.items))


@materials.route("/material/<int:material_id>/editar", methods=["GET", "POST"])
@login_required
def edit(material_id):
    material = _get_or_404(material_id)
    if material.author_id != current_user.id:
        abort(403)
    is_post = request.method == "POST"
    form = MaterialForm() if is_post else MaterialForm(obj=material)
    _set_choices(form, material.subject)
    if not is_post:
        form.course.data = material.course.value if material.course else ""
        form.kind.data = material.kind.value if material.kind else ""
    if form.validate_on_submit() and _store(form, material, _uploads(form), len(material.files)):
        flash("Material actualizado.", "success")
        return redirect(url_for("materials.detail", material_id=material.id))
    return _render(form, material)


@materials.route("/material/<int:material_id>/borrar", methods=["POST"])
@login_required
def delete(material_id):
    material = _get_or_404(material_id)
    if material.author_id != current_user.id and not current_user.is_admin:
        abort(403)
    stored = [f.stored_name for f in material.files]
    delete_reports_for(material_ids=[material.id])
    db.session.delete(material)
    db.session.commit()
    for name in stored:
        delete_upload("materials", name)
    flash("Material eliminado.", "success")
    return redirect(url_for("materials.explore"))


@materials.route("/material/<int:material_id>/ficheros/<int:file_id>/quitar", methods=["POST"])
@login_required
def remove_file(material_id, file_id):
    material = _get_or_404(material_id)
    if material.author_id != current_user.id:
        abort(403)
    target = next((f for f in material.files if f.id == file_id), None)
    if target is None:
        abort(404)
    if len(material.files) <= 1:
        flash("El material debe conservar al menos un fichero.", "error")
        return redirect(url_for("materials.edit", material_id=material.id))
    stored = target.stored_name
    material.files.remove(target)
    db.session.commit()
    delete_upload("materials", stored)
    flash("Fichero eliminado.", "success")
    return redirect(url_for("materials.edit", material_id=material.id))


def build_feed_query(params: Mapping[str, str], viewer: User) -> Select:
    """Consulta del feed (sin paginar). Los valores inválidos se ignoran.

    El material oculto no aparece en el feed para nadie, ni para su autor.
    """
    _ = viewer  # reservado: los perfiles reutilizan esta función con reglas por espectador
    query = select(Material).where(Material.is_hidden.is_(False))

    text = (params.get("q") or "").strip()
    match = None
    if text:
        match = build_match(text)
        if match is not None:
            query = query.join(FTS, FTS.c.rowid == Material.id).where(FTS.c.material_fts.op("MATCH")(match))

    subject_id = int_param(params.get("asignatura"))
    if subject_id is not None and db.session.get(Subject, subject_id) is not None:
        query = query.where(Material.subject_id == subject_id)

    course = next((c for c in Course if c.value == params.get("curso")), None)
    if course is not None:
        query = query.where(Material.course == course)

    kind = next((k for k in MaterialKind if k.value == params.get("tipo")), None)
    if kind is not None:
        query = query.where(Material.kind == kind)

    if params.get("profesores") == "1":
        query = query.where(Material.author_id.in_(select(User.id).where(User.is_teacher.is_(True))))

    order = params.get("orden")
    if order == "relevantes" and match is None:
        order = None
    elif order not in ("valorados", "recientes") and match is not None:
        order = "relevantes"  # por defecto con texto de búsqueda

    if order == "relevantes":
        query = query.order_by(func.bm25(literal_column("material_fts"), 10.0, 3.0, 1.0, 1.0), Material.created_at.desc(),
                               Material.id.desc())
    elif order == "valorados":
        stats = (select(Rating.material_id.label("material_id"),
                        func.avg(Rating.stars).label("average"),
                        func.count(Rating.stars).label("votes"))
                 .group_by(Rating.material_id).subquery())
        query = (query.outerjoin(stats, stats.c.material_id == Material.id)
                 .order_by(stats.c.average.desc().nulls_last(), stats.c.votes.desc().nulls_last(),
                           Material.created_at.desc(), Material.id.desc()))
    else:
        query = query.order_by(Material.created_at.desc(), Material.id.desc())
    return query


@materials.route("/explorar")
@login_required
def explore():
    params = request.args
    page = page_param(params.get("pagina"))
    pagination = db.paginate(build_feed_query(params, current_user).options(*feed_loader_options()), page=page,
                             per_page=PER_PAGE, error_out=False)

    def page_url(number):
        args = {k: v for k, v in params.items() if k != "pagina" and v != ""}
        if number > 1:
            args["pagina"] = number
        return url_for("materials.explore", **args)

    context = {"pagination": pagination, "page": pagination.page, "pages": pagination.pages,
               "page_url": page_url, "favorite_ids": favorite_ids(pagination.items)}
    # Misma URL para fragmento y página completa: las cachés deben distinguirlas (Vary) y al
    # volver con «Atrás» htmx pide la página completa (HX-History-Restore-Request).
    if request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request"):
        response = make_response(render_template("partials/material_list.html", **context))
    else:
        subjects = Subject.query.order_by(Subject.name_key).all()
        response = make_response(render_template("materials/explore.html", subjects=subjects, courses=list(Course),
                                                 kinds=list(MaterialKind), filters=params, **context))
    response.vary.add("HX-Request")
    return response
