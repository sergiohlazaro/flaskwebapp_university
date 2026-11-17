"""Formularios WTForms (mensajes de validación en español)."""

import unicodedata

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

REQUIRED = "Este campo es obligatorio."


def _strip_lower(value):
    return value.strip().lower() if isinstance(value, str) else value


def _strip(value):
    return value.strip() if isinstance(value, str) else value


class LoginForm(FlaskForm):
    # Sin validador Email: el login debe responder igual ante cualquier credencial errónea.
    email = StringField("Email", filters=[_strip_lower], validators=[DataRequired(REQUIRED)])
    password = PasswordField("Contraseña", validators=[DataRequired(REQUIRED)])


class SignupForm(FlaskForm):
    name = StringField("Nombre", filters=[_strip], validators=[
        DataRequired(REQUIRED),
        Length(min=2, max=100, message="El nombre debe tener entre 2 y 100 caracteres."),
    ])
    surname = StringField("Apellidos", filters=[_strip], validators=[
        DataRequired(REQUIRED),
        Length(min=2, max=100, message="Los apellidos deben tener entre 2 y 100 caracteres."),
    ])
    email = StringField("Email", filters=[_strip_lower], validators=[
        DataRequired(REQUIRED),
        Email(message="Introduce un email válido."),
        Length(max=100, message="El email es demasiado largo."),
    ])
    password = PasswordField("Contraseña", validators=[
        DataRequired(REQUIRED),
        Length(min=8, message="La contraseña debe tener al menos 8 caracteres."),
    ])
    password2 = PasswordField("Repite la contraseña", validators=[
        DataRequired(REQUIRED),
        EqualTo("password", message="Las contraseñas no coinciden."),
    ])

    def validate_email(self, field):
        from .models import User
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("Ya existe una cuenta con ese email.")


def _normalize_text(value):
    return unicodedata.normalize("NFC", value).strip() if isinstance(value, str) else value


class SubjectForm(FlaskForm):
    name = StringField("Nombre de la asignatura", filters=[_normalize_text], validators=[
        DataRequired("Escribe el nombre de la asignatura."),
        Length(min=1, max=100, message="El nombre debe tener entre 1 y 100 caracteres."),
    ])
