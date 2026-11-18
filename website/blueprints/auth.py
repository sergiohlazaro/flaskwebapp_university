"""Autenticación: login, registro y logout."""

import time
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
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
from ..models import LoginRecord, User, utcnow
from ..services.mail import send_email
from ..services.tokens import (
    bump_session_version,
    load_reset_token,
    load_verify_token,
    make_reset_token,
    make_verify_token,
)

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
UNACTIVATED_MESSAGE = "Tu cuenta aún no está activada. Revisa tu email o pide un nuevo enlace."


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
        elif current_app.config["REQUIRE_EMAIL_VERIFICATION"] and user.email_verified_at is None:
            # Solo se revela tras acertar la contraseña (sin enumeración de cuentas).
            flash(UNACTIVATED_MESSAGE, category='error')
            return render_template("auth/login.html", form=form, show_resend=True)
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


SIGNUP_VERIFY_MESSAGE = ("Si el email no estaba registrado, te hemos enviado un enlace para activar la cuenta. "
                         "Revísalo para empezar.")
RESEND_MESSAGE = "Si existe una cuenta pendiente de activar con ese email, te hemos enviado un nuevo enlace."


def _send_verification(user, email):
    link = url_for('auth.verify_email', token=make_verify_token(user, email), _external=True)
    send_email(email, "Confirma tu email", "email/email_verify.txt", name=user.name, link=link)


def _signup_existing(email):
    # Misma respuesta que un registro nuevo; el aviso va solo al dueño del email.
    owner = User.query.filter_by(email=email).first()
    if owner is not None:
        link = url_for('auth.forgot_password', _external=True)
        send_email(owner.email, "Intento de registro con tu email", "email/signup_existing.txt",
                   name=owner.name, link=link)
    flash(SIGNUP_VERIFY_MESSAGE, category='info')
    return redirect(url_for('auth.login'))


@auth.route('/registro', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        verify = current_app.config["REQUIRE_EMAIL_VERIFICATION"]
        if verify and User.query.filter_by(email=form.email.data).first():
            return _signup_existing(form.email.data)
        # Solo se leen los campos del formulario: role/is_teacher del POST se ignoran.
        new_user = User(
            name=form.name.data,
            surname=form.surname.data,
            email=form.email.data,
            password=generate_password_hash(form.password.data, method='pbkdf2:sha256'),
            # Con verificación activa la cuenta nace sin verificar; sin ella, verificada (como hasta ahora).
            email_verified_at=None if verify else utcnow(),
        )
        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            # Carrera: otro registro con el mismo email se coló tras la comprobación del formulario.
            db.session.rollback()
            if verify:
                return _signup_existing(form.email.data)
            form.email.errors = list(form.email.errors) + ["Ya existe una cuenta con ese email."]
            return render_template("auth/signup.html", form=form)

        if verify:
            _send_verification(new_user, new_user.email)
            flash(SIGNUP_VERIFY_MESSAGE, category='info')
            return redirect(url_for('auth.login'))

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
# VERIFICACIÓN DE EMAIL
# -----------------------

@auth.route('/verificar/reenviar', methods=['GET', 'POST'])
@limiter.limit("5 per hour", methods=["POST"])  # Por IP; solo cuentan los envíos
def resend_verification():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        # Misma respuesta exista, esté verificada o bloqueada la cuenta (sin enumeración).
        if user and not user.is_blocked and user.email_verified_at is None:
            _send_verification(user, user.email)
        flash(RESEND_MESSAGE, category='info')
        return redirect(url_for('auth.login'))
    return render_template("auth/resend.html", form=form)


@auth.route('/verificar/<token>')
def verify_email(token):
    loaded = load_verify_token(token)
    if loaded is None:
        return render_template("auth/link_invalid.html", resend=True), 400
    user, email = loaded
    if user.pending_email is not None and email == user.pending_email:
        # Cambio de email: otra cuenta pudo quedarse con la dirección desde que se pidió.
        user.email = email
        user.pending_email = None
        user.email_verified_at = utcnow()
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Ya existe una cuenta con ese email.", category='error')
            return redirect(url_for('auth.login'))
    elif email == user.email and user.email_verified_at is None:
        user.email_verified_at = utcnow()
        db.session.commit()
    else:
        # Enlace obsoleto: el email ya no está pendiente ni es el actual sin verificar.
        return render_template("auth/link_invalid.html", resend=True), 400
    flash("Email verificado. Ya puedes iniciar sesión.", category='success')
    return redirect(url_for('auth.login'))


# -----------------------
# LOGOUT
# -----------------------

@auth.route('/logout', methods=['POST'])
@login_required  # Solo usuarios autenticados pueden hacer logout
def logout():
    logout_user()
    return redirect('/')
