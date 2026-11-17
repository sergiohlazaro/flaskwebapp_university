# ----------------------------------------------
# IMPORTACIÓN DE LIBRERÍAS Y EXTENSIONES
# ----------------------------------------------

from flask import Flask
from flask_sqlalchemy import SQLAlchemy  # ORM para la base de datos
from flask_login import LoginManager  # Gestión de sesiones de usuario
from flask_wtf import CSRFProtect  # Protección contra ataques CSRF
from flask_limiter import Limiter  # Límite de solicitudes (Rate Limiting)
from flask_limiter.util import get_remote_address  # Obtención de IP del cliente
from flask_caching import Cache  # Sistema de cache para mejorar rendimiento
import logging  # Registro de eventos y errores
import os  # Lectura de variables de entorno (SECRET_KEY)
import secrets  # Generación de claves aleatorias seguras
from flask_compress import Compress

# ----------------------------------------------
# INSTANCIAS GLOBALES DE EXTENSIONES
# ----------------------------------------------

# ORM para la base de datos
db = SQLAlchemy()

# Rate limiter basado en IP
limiter = Limiter(get_remote_address)

# Cache en memoria simple (se puede cambiar a redis, filesystem...)
cache = Cache()

# Nombre del archivo de base de datos SQLite
DB_NAME = "database.db"

# ----------------------------------------------
# CREACIÓN Y CONFIGURACIÓN DE LA APLICACIÓN
# ----------------------------------------------

def create_app(test_config=None):
    # test_config: diccionario opcional que sobrescribe la configuración ANTES de
    # inicializar las extensiones (necesario para que los tests usen su propia BD).

    # Crear la instancia de Flask
    app = Flask(__name__)

    Compress(app)

    # ------------------------------
    # CONFIGURACIÓN DE LA APP
    # ------------------------------

    # Clave para firmar sesiones y tokens CSRF. NUNCA debe estar en el código:
    # se lee de la variable de entorno SECRET_KEY. Si falta, se genera una clave
    # aleatoria temporal (las sesiones se invalidan al reiniciar el servidor).
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        secret_key = secrets.token_hex(32)
        logging.getLogger(__name__).warning(
            "SECRET_KEY no está definida: usando una clave aleatoria temporal. "
            "Defínela en el entorno para producción."
        )
    app.config['SECRET_KEY'] = secret_key
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'  # Base de datos SQLite
    app.config['MAX_CONTENT_LENGTH'] = 24 * 1024 * 1024  # Límite máximo de archivos subidos (24MB)

    # Seguridad en cookies
    app.config['SESSION_COOKIE_SECURE'] = True      # Solo enviar por HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True    # Inaccesibles vía Javascript (mitiga XSS)
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'   # Previene ataques CSRF entre sitios

    if test_config:
        app.config.update(test_config)

    # ------------------------------
    # INICIALIZACIÓN DE EXTENSIONES
    # ------------------------------

    # Protección CSRF
    csrf = CSRFProtect()
    csrf.init_app(app)

    # Inicializar Rate Limiting
    limiter.init_app(app)

    # Inicializar Cache
    cache.init_app(app)

    # Inicializar Base de Datos
    db.init_app(app)

    # ------------------------------
    # REGISTRO DE BLUEPRINTS
    # ------------------------------

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    # ------------------------------
    # CREACIÓN DE TABLAS Y COMANDOS DE ADMINISTRACIÓN
    # ------------------------------
    # No se crean usuarios por defecto (credenciales conocidas = riesgo crítico).
    # El primer administrador se crea con:  flask --app main create-admin

    from .commands import create_admin_command
    from .models import User

    with app.app_context():
        db.create_all()

    app.cli.add_command(create_admin_command)

    # ------------------------------
    # LOGIN MANAGER (gestión de sesiones)
    # ------------------------------

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    # ------------------------------
    # CONFIGURACIÓN DE LOGGING
    # ------------------------------

    logging.basicConfig(
        filename='app.log',
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    # ------------------------------
    # DEVOLVER APLICACIÓN CONFIGURADA
    # ------------------------------
    return app
