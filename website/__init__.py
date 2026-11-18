import os
import secrets

from flask import Flask, Response, redirect, request, url_for
from flask_compress import Compress
from flask_login import current_user
from sqlalchemy import func, select
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import get_config
from .extensions import csrf, db, limiter, login_manager, migrate

__all__ = ["create_app", "db"]


def create_app(test_config=None):
    # test_config: diccionario opcional que sobrescribe la configuración ANTES de
    # inicializar las extensiones (necesario para que los tests usen su propia BD).
    app = Flask(__name__)

    env = os.environ.get("APP_ENV", "development").lower()
    if test_config and test_config.get("TESTING"):
        env = "testing"
    app.config.from_object(get_config(env))
    app.config["ENV_NAME"] = env
    app.config["UPLOAD_ROOT"] = os.path.join(app.instance_path, "uploads")

    # SECRET_KEY: nunca en el código. En producción es obligatoria; en otros
    # entornos, si falta, se usa una clave aleatoria temporal con un aviso.
    secret_key = (test_config or {}).get("SECRET_KEY") or os.environ.get("SECRET_KEY")
    if not secret_key:
        if env == "production":
            raise RuntimeError("SECRET_KEY must be set in production")
        secret_key = secrets.token_hex(32)
        if env != "testing":
            app.logger.warning(
                "SECRET_KEY no está definida: usando una clave aleatoria temporal. "
                "Defínela en el entorno para producción."
            )
    app.config["SECRET_KEY"] = secret_key

    if test_config:
        app.config.update(test_config)

    trusted_proxies = os.environ.get("TRUSTED_PROXIES")
    if trusted_proxies:
        hops = int(trusted_proxies)
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops)

    Compress(app)
    csrf.init_app(app)
    limiter.init_app(app)
    db.init_app(app)
    # Las tablas se crean con `flask --app main db upgrade` (render_as_batch: ALTER en SQLite).
    migrate.init_app(app, db, render_as_batch=True)

    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(id):
        user = db.session.get(User, int(id))
        # SEC-07: un usuario bloqueado pierde la sesión en la siguiente petición.
        return None if user is None or user.is_blocked else user

    from werkzeug.routing import IntegerConverter

    class BoundedIntConverter(IntegerConverter):
        """Como `int`, pero fuera del rango de SQLite (64 bits) no casa: 404 en vez de 500."""

        def __init__(self, map, fixed_digits=0, min=None, max=2**63 - 1, signed=False):
            super().__init__(map, fixed_digits=fixed_digits, min=min, max=max, signed=signed)

    app.url_map.converters["int"] = BoundedIntConverter

    from .blueprints.admin import admin
    from .blueprints.auth import auth
    from .blueprints.files import files
    from .blueprints.main import main
    from .blueprints.materials import materials
    from .blueprints.messages import messages
    from .blueprints.users import users

    app.register_blueprint(auth, url_prefix="/")
    app.register_blueprint(files)
    app.register_blueprint(main)
    app.register_blueprint(admin)
    app.register_blueprint(materials)
    app.register_blueprint(messages)
    app.register_blueprint(users)

    # No se crean usuarios por defecto. El primer administrador se crea con:
    #   flask --app main create-admin
    from .commands import create_admin_command

    app.cli.add_command(create_admin_command)

    from .filters import register_filters

    register_filters(app)

    from .services.headers import register_security_headers

    register_security_headers(app)

    @app.context_processor
    def inject_globals():
        from .models import Message

        unread = 0
        if current_user.is_authenticated:
            unread = db.session.scalar(
                select(func.count(Message.id)).where(Message.receiver_id == current_user.id,
                                                     Message.read_at.is_(None))) or 0
        return {"app_name": app.config["APP_NAME"], "unread_messages_count": unread}

    @login_manager.unauthorized_handler
    def unauthorized():
        # Peticiones htmx: 401 + HX-Redirect para no incrustar el login en un fragmento.
        target = url_for("auth.login", next=request.full_path.rstrip("?"))
        if request.headers.get("HX-Request"):
            return Response("", status=401, headers={"HX-Redirect": target})
        return redirect(target)

    return app
