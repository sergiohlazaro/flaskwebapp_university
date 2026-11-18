"""Descargas protegidas de ficheros subidos (SEC-04, SEC-16)."""
import mimetypes
import os

from flask import Blueprint, abort, redirect, send_file, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import MaterialFile, Message, User
from ..services.permissions import can_download_message_file, can_view_material
from ..services.uploads import clean_original_name, upload_path

files = Blueprint("files", __name__)


def _send(kind, stored_name, original_name, mime):
    try:
        path = upload_path(kind, stored_name)
    except ValueError:
        abort(404)
    if not os.path.isfile(path):
        abort(404)
    is_image = (mime or "").startswith("image/")
    response = send_file(
        path,
        mimetype=mime or "application/octet-stream",
        as_attachment=not is_image,
        download_name=clean_original_name(original_name),
        max_age=0,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@files.route("/archivos/material/<int:file_id>")
@login_required
def material_file(file_id):
    material_file = db.session.get(MaterialFile, file_id)
    if material_file is None:
        abort(404)
    if not can_view_material(current_user, material_file.material):
        abort(403)
    return _send("materials", material_file.stored_name, material_file.original_name, material_file.mime)


@files.route("/archivos/mensaje/<int:message_id>")
@login_required
def message_file(message_id):
    message = db.session.get(Message, message_id)
    if message is None or not message.file_stored_name:
        abort(404)
    if not can_download_message_file(current_user, message):
        abort(403)
    mime = mimetypes.guess_type(message.file_stored_name)[0]
    return _send("messages", message.file_stored_name, message.file_original_name, mime)


@files.route("/avatar/<int:user_id>")
@login_required
def avatar(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if not user.avatar:
        return redirect(url_for("static", filename="img/default-avatar.jpg"))
    mime = mimetypes.guess_type(user.avatar)[0] or "image/jpeg"
    return _send("avatars", user.avatar, user.avatar, mime)
