"""Crear, editar y borrar material didáctico (spec §5.1, §5.2)."""
from collections.abc import Mapping

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import Select, func, or_, select

from ..extensions import db
from ..forms import MaterialForm
from ..models import Course, Material, MaterialFile, MaterialKind, Rating, Subject, User
from ..services.permissions import can_view_material
from ..services.uploads import (
    ALLOWED_MATERIAL_EXTENSIONS,
    UploadError,
    delete_upload,
    save_upload,
    validate_upload,
)

materials = Blueprint("materials", __name__)

MAX_FILES = 5
PER_PAGE = 12
MAX_PAGE = 1_000_000
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


@materials.route("/material/<int:material_id>")
@login_required
def detail(material_id):
    material = _get_or_404(material_id)
    if not can_view_material(current_user, material):
        abort(404)
    return render_template("materials/detail.html", material=material)


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


def _int_param(value, minimum=1):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= minimum else None


def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_feed_query(params: Mapping[str, str], viewer: User) -> Select:
    """Consulta del feed (sin paginar). Los valores inválidos se ignoran.

    El material oculto no aparece en el feed para nadie, ni para su autor.
    """
    _ = viewer  # reservado: los perfiles reutilizan esta función con reglas por espectador
    query = select(Material).where(Material.is_hidden.is_(False))

    text = (params.get("q") or "").strip()
    if text:
        pattern = f"%{_escape_like(text)}%"
        query = query.where(or_(Material.title.ilike(pattern, escape="\\"),
                                Material.description.ilike(pattern, escape="\\")))

    subject_id = _int_param(params.get("asignatura"))
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

    if params.get("orden") == "valorados":
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
    page = min(_int_param(params.get("pagina")) or 1, MAX_PAGE)
    pagination = db.paginate(build_feed_query(params, current_user), page=page,
                             per_page=PER_PAGE, error_out=False)

    def page_url(number):
        args = {k: v for k, v in params.items() if k != "pagina" and v != ""}
        if number > 1:
            args["pagina"] = number
        return url_for("materials.explore", **args)

    context = {"pagination": pagination, "page": pagination.page, "pages": pagination.pages,
               "page_url": page_url}
    if request.headers.get("HX-Request"):
        return render_template("partials/material_list.html", **context)
    subjects = Subject.query.order_by(Subject.name_key).all()
    return render_template("materials/explore.html", subjects=subjects, courses=list(Course),
                           kinds=list(MaterialKind), filters=params, **context)
