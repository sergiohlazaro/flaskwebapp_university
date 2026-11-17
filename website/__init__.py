import os
import secrets

from flask import Flask, Response, redirect, request, url_for
from flask_compress import Compress
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import get_config
from .extensions import csrf, db, limiter, login_manager

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

    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(id):
        return db.session.get(User, int(id))

    from .auth import auth
    from .blueprints.files import files
    from .blueprints.main import main
    from .views import views

    app.register_blueprint(views, url_prefix="/")
    app.register_blueprint(auth, url_prefix="/")
    app.register_blueprint(files)
    app.register_blueprint(main)

    # No se crean usuarios por defecto. El primer administrador se crea con:
    #   flask --app main create-admin
    from .commands import create_admin_command

    with app.app_context():
        db.create_all()

    app.cli.add_command(create_admin_command)

    from .filters import register_filters

    register_filters(app)

    from .services.headers import register_security_headers

    register_security_headers(app)

    @app.context_processor
    def inject_globals():
        # Task 13 hará real el contador de mensajes sin leer.
        return {"app_name": app.config["APP_NAME"], "unread_messages_count": 0}

    @login_manager.unauthorized_handler
    def unauthorized():
        # Peticiones htmx: 401 + HX-Redirect para no incrustar el login en un fragmento.
        target = url_for("auth.login", next=request.full_path.rstrip("?"))
        if request.headers.get("HX-Request"):
            return Response("", status=401, headers={"HX-Redirect": target})
        return redirect(target)

    return app
