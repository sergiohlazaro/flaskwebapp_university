"""Panel de administración: asignaturas (spec §5.2, §5.9)."""

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..forms import SubjectForm
from ..models import Subject
from ..services.permissions import admin_required

admin = Blueprint("admin", __name__, url_prefix="/admin")

DUPLICATE_MSG = "Ya existe una asignatura con ese nombre."


@admin.context_processor
def _tabs_context():
    # La Tarea 11 sustituirá el 0 por el número real de reportes pendientes.
    return {"pending_reports_count": 0}


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
