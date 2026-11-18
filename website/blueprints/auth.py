"""Autenticación: login, registro y logout."""

import time
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, limiter
from ..forms import ForgotPasswordForm, LoginForm, ResetPasswordForm, SignupForm
from ..models import LoginRecord, User
from ..services.mail import send_email
from ..services.tokens import bump_session_version, load_reset_token, make_reset_token

# Creación de un Blueprint llamado 'auth' para agrupar todas las rutas relacionadas con autenticación
auth = Blueprint('auth', __name__)

# Estructura para almacenar intentos fallidos → en memoria por IP
FAILED_LOGINS = {}

# Configuración del bloqueo temporal
MAX_FAILED_ATTEMPTS = 5
BLOCK_TIME_SECONDS = 600  # 10 minutos bloqueado tras superar el límite

# Cuentas que versiones anteriores creaban automáticamente con contraseñas públicas.
LEGACY_DEFAULT_CREDENTIALS = {
    'admin@admin.com': 'admin',
    'user1@user.com': 'password1',
}

# -----------------------
# LOGIN
# -----------------------

GENERIC_LOGIN_ERROR = "Email o contraseña incorrectos."


def _register_failure(ip_address):
    FAILED_LOGINS[ip_address] = [FAILED_LOGINS.get(ip_address, [0, 0])[0] + 1, time.time()]


def _safe_next(target):
    """Solo se siguen rutas relativas internas; cualquier otra cosa va a /explorar."""
    default = url_for('materials.explore')
    if not target or not target.startswith('/') or target.startswith('//') or '\\' in target:
        return default
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return default
    return target


@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per hour", methods=["POST"])  # Limite por IP; solo cuentan los envíos
def login():
    ip_address = request.remote_addr
    form = LoginForm()

    # Verificar si la IP está bloqueada
    block_info = FAILED_LOGINS.get(ip_address)
    if block_info:
        failed_attempts, last_attempt_time = block_info
        if failed_attempts >= MAX_FAILED_ATTEMPTS:
            if time.time() - last_attempt_time < BLOCK_TIME_SECONDS:
                flash("Demasiados intentos fallidos. Inténtalo de nuevo más tarde.", category='error')
                return render_template("auth/login.html", form=form)
            # Pasó el tiempo de bloqueo: resetear intentos
            FAILED_LOGINS[ip_address] = [0, 0]

    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = User.query.filter_by(email=email).first()

        # Credenciales por defecto publicadas por versiones anteriores (SEC-03):
        # se rechazan aunque la contraseña coincida en una BD antigua.
        if LEGACY_DEFAULT_CREDENTIALS.get(email) == password:
            flash('Las credenciales por defecto están desactivadas. Pide a un administrador '
                  'que cree una cuenta nueva (flask create-admin).', category='error')
            _register_failure(ip_address)
        # Email inexistente, contraseña errónea o cuenta bloqueada: mismo mensaje (SEC-09)
        elif not user or user.is_blocked or not check_password_hash(user.password, password):
            flash(GENERIC_LOGIN_ERROR, category='error')
            _register_failure(ip_address)
        else:
            login_user(user, remember=form.remember.data)
            db.session.add(LoginRecord(user_id=user.id, ip_address=ip_address))
            db.session.commit()
            FAILED_LOGINS[ip_address] = [0, 0]
            flash('Sesión iniciada correctamente.', category='success')
            return redirect(_safe_next(request.args.get('next')))

    return render_template("auth/login.html", form=form)

# -----------------------
# SIGN UP (Registro)
# -----------------------


@auth.route('/registro', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        # Solo se leen los campos del formulario: role/is_teacher del POST se ignoran.
        new_user = User(
            name=form.name.data,
            surname=form.surname.data,
            email=form.email.data,
            password=generate_password_hash(form.password.data, method='pbkdf2:sha256'),
        )
        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            # Carrera: otro registro con el mismo email se coló tras la comprobación del formulario.
            db.session.rollback()
            form.email.errors = list(form.email.errors) + ["Ya existe una cuenta con ese email."]
            return render_template("auth/signup.html", form=form)

        login_user(new_user, remember=False)
        db.session.add(LoginRecord(user_id=new_user.id, ip_address=request.remote_addr))
        db.session.commit()

        flash('Cuenta creada correctamente. ¡Bienvenido!', category='success')
        return redirect(url_for('materials.explore'))

    return render_template("auth/signup.html", form=form)


# URL antigua → nueva, conservando método y cuerpo (308)
@auth.route('/signup', methods=['GET', 'POST'])
def old_signup():
    return redirect(url_for('auth.signup'), 308)

# -----------------------
# RECUPERAR CONTRASEÑA
# -----------------------

FORGOT_MESSAGE = "Si existe una cuenta con ese email, te hemos enviado un enlace para restablecer la contraseña."
RESET_DONE_MESSAGE = "Contraseña actualizada. Ya puedes iniciar sesión."


@auth.route('/recuperar', methods=['GET', 'POST'])
@limiter.limit("5 per hour", methods=["POST"])  # Por IP; solo cuentan los envíos
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        # Misma respuesta exista, no exista o esté bloqueada la cuenta (sin enumeración).
        if user and not user.is_blocked:
            link = url_for('auth.reset_password', token=make_reset_token(user), _external=True)
            send_email(user.email, "Restablece tu contraseña", "email/password_reset.txt",
                       name=user.name, link=link)
        flash(FORGOT_MESSAGE, category='info')
        return redirect(url_for('auth.login'))
    return render_template("auth/forgot.html", form=form)


@auth.route('/recuperar/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = load_reset_token(token)
    if user is None:
        return render_template("auth/link_invalid.html"), 400
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        bump_session_version(user)  # un único commit: hash y versión juntos; no inicia sesión
        flash(RESET_DONE_MESSAGE, category='success')
        return redirect(url_for('auth.login'))
    return render_template("auth/reset.html", form=form, token=token)


# -----------------------
# LOGOUT
# -----------------------

@auth.route('/logout', methods=['POST'])
@login_required  # Solo usuarios autenticados pueden hacer logout
def logout():
    logout_user()
    return redirect('/')
