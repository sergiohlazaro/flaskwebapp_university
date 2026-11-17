"""Reglas de permisos compartidas (spec §5.1)."""
from functools import wraps

from flask import abort, current_app, request
from flask_login import current_user


def admin_required(view):
    """Restringe una ruta a administradores (role == 0). Responde 403 al resto.

    Debe colocarse DESPUÉS de @login_required para que current_user esté autenticado.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user.role != 0:
            current_app.logger.warning(
                f"Forbidden admin action by user {current_user.id} on {request.path}"
            )
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def can_view_material(user, material) -> bool:
    """Un material oculto solo lo ven su autor y los administradores."""
    if not material.is_hidden:
        return True
    return user.id == material.author_id or user.is_admin


def can_download_message_file(user, message) -> bool:
    """El adjunto de un mensaje solo es accesible para remitente y destinatario."""
    return user.id in (message.sender_id, message.receiver_id)
