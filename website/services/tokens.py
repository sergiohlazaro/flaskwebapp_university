"""Tokens firmados de recuperación de contraseña y verificación de email."""
import hashlib
import hmac

from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer

from ..extensions import db
from ..models import User

RESET_SALT = "password-reset"
VERIFY_SALT = "email-verify"
MAX_AGE = {RESET_SALT: 3600, VERIFY_SALT: 48 * 3600}


def _serializer(salt):
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def _load(token, salt):
    try:
        data = _serializer(salt).loads(token, max_age=MAX_AGE[salt])
    except BadData:  # firma, caducidad, formato...
        return None
    return data if isinstance(data, dict) else None


def _fingerprint(user):
    # Cambia con la contraseña (y con session_version): hace el token de un solo uso.
    # HMAC para no dejar material del hash en el payload, legible aunque esté firmado.
    msg = f"{getattr(user, 'session_version', 0)}:{user.password or ''}".encode()
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:16]


def make_reset_token(user) -> str:
    return _serializer(RESET_SALT).dumps({"id": user.id, "fp": _fingerprint(user)})


def load_reset_token(token):
    data = _load(token, RESET_SALT)
    if data is None or not isinstance(data.get("id"), int):
        return None
    user = db.session.get(User, data["id"])
    if (user is None or not isinstance(data.get("fp"), str)
            or not hmac.compare_digest(data["fp"], _fingerprint(user))):
        return None
    return user


def make_verify_token(user, email) -> str:
    return _serializer(VERIFY_SALT).dumps({"id": user.id, "email": email})


def load_verify_token(token):
    """Devuelve `(usuario, email)` o None. No es de un solo uso: quien llama debe comparar
    el email devuelto con el email pendiente/actual del usuario antes de aplicarlo."""
    data = _load(token, VERIFY_SALT)
    if data is None or not isinstance(data.get("id"), int) or not isinstance(data.get("email"), str):
        return None
    user = db.session.get(User, data["id"])
    return None if user is None else (user, data["email"])
