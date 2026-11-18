"""Páginas de error en español (el HTML por defecto de Werkzeug está en inglés)."""
from flask import render_template, request
from flask_wtf.csrf import CSRFError

from .extensions import db

MESSAGES = {
    400: ("Petición no válida", "No hemos podido procesar la petición. Revisa los datos e inténtalo de nuevo."),
    403: ("No tienes permiso", "No tienes permiso para hacer esto."),
    404: ("Página no encontrada", "La página que buscas no existe o ya no está disponible."),
    405: ("Método no permitido", "Esta dirección no admite esa acción."),
    413: ("Archivo demasiado grande", "El archivo supera el tamaño máximo de 24 MB."),
    429: ("Demasiadas peticiones", "Demasiadas peticiones. Espera un momento y vuelve a intentarlo."),
    500: ("Error del servidor", "Algo ha ido mal por nuestra parte. Inténtalo de nuevo más tarde."),
}
CSRF_MESSAGE = ("Formulario caducado", "La sesión del formulario ha caducado. Vuelve a intentarlo.")


def _respond(code, title, message):
    if request.headers.get("HX-Request"):
        # Se conserva el código para que htmx dispare htmx:responseError; el cuerpo es solo texto.
        return message, code, {"Content-Type": "text/plain; charset=utf-8"}
    try:
        return render_template("errors/error.html", code=code, title=title, message=message), code
    except Exception:  # noqa: BLE001 - la página de error nunca debe fallar por la BD o la plantilla
        db.session.rollback()
        return f"{title}. {message}", code, {"Content-Type": "text/plain; charset=utf-8"}


def register_error_handlers(app):
    def handle_http(error):
        code = error.code if error.code in MESSAGES else 500
        title, message = MESSAGES[code]
        return _respond(error.code or code, title, message)

    for code in MESSAGES:
        if code != 500:
            app.register_error_handler(code, handle_http)

    @app.errorhandler(CSRFError)
    def handle_csrf(_error):
        return _respond(400, *CSRF_MESSAGE)

    @app.errorhandler(500)
    def handle_500(_error):
        db.session.rollback()
        return _respond(500, *MESSAGES[500])
