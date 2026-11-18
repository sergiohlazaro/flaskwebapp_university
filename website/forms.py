"""Formularios WTForms (mensajes de validación en español)."""

import unicodedata

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, MultipleFileField
from wtforms import BooleanField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    Regexp,
    ValidationError,
)

REQUIRED = "Este campo es obligatorio."


def _strip_lower(value):
    return value.strip().lower() if isinstance(value, str) else value


def _strip(value):
    return value.strip() if isinstance(value, str) else value


class LoginForm(FlaskForm):
    # Sin validador Email: el login debe responder igual ante cualquier credencial errónea.
    email = StringField("Email", filters=[_strip_lower], validators=[DataRequired(REQUIRED)])
    password = PasswordField("Contraseña", validators=[DataRequired(REQUIRED)])
    remember = BooleanField("Recordarme", default=False)


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


def _int_or_zero(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class _ChoiceField(SelectField):
    def pre_validate(self, form):
        if self.data not in {value for value, _label in self.choices}:
            raise ValidationError("Selecciona una opción válida.")


class MaterialForm(FlaskForm):
    title = StringField("Título", filters=[_normalize_text], validators=[
        DataRequired("Escribe un título."),
        Length(min=3, max=150, message="El título debe tener entre 3 y 150 caracteres."),
    ])
    description = TextAreaField("Descripción", filters=[_strip], validators=[
        Optional(),
        Length(max=5000, message="La descripción no puede superar los 5000 caracteres."),
    ])
    subject_id = _ChoiceField("Asignatura", coerce=_int_or_zero)
    course = _ChoiceField("Curso", coerce=str)
    kind = _ChoiceField("Tipo", coerce=str)
    files = MultipleFileField("Ficheros")

    def validate_subject_id(self, field):
        if not field.data:
            raise ValidationError("Selecciona una asignatura.")


class CommentForm(FlaskForm):
    body = TextAreaField("Comentario", filters=[_strip], validators=[
        DataRequired("Escribe un comentario."),
        Length(max=2000, message="El comentario no puede superar los 2000 caracteres."),
    ])


class ReportForm(FlaskForm):
    target_type = StringField("Tipo")
    target_id = StringField("Identificador")
    reason = _ChoiceField("Motivo", coerce=str, choices=[
        (value, value) for value in ("Inapropiado", "Erróneo", "Copyright", "Otro")])
    details = TextAreaField("Detalles (opcional)", filters=[_strip], validators=[
        Optional(),
        Length(max=500, message="Los detalles no pueden superar los 500 caracteres."),
    ])


SOCIAL_RE = r"^[A-Za-z0-9_.-]{1,50}$"
SOCIAL_MSG = "Solo letras, números, punto, guion y guion bajo (máximo 50)."
WRONG_PASSWORD = "La contraseña actual no es correcta."


class ProfileForm(FlaskForm):
    name = StringField("Nombre", filters=[_strip], validators=[
        DataRequired(REQUIRED),
        Length(min=2, max=100, message="El nombre debe tener entre 2 y 100 caracteres."),
    ])
    surname = StringField("Apellidos", filters=[_strip], validators=[
        DataRequired(REQUIRED),
        Length(min=2, max=100, message="Los apellidos deben tener entre 2 y 100 caracteres."),
    ])
    bio = TextAreaField("Biografía", filters=[_strip], validators=[
        Optional(),
        Length(max=300, message="La biografía no puede superar los 300 caracteres."),
    ])
    twitter = StringField("Usuario de X (Twitter)", filters=[_strip], validators=[
        Optional(), Regexp(SOCIAL_RE, message=SOCIAL_MSG)])
    linkedin = StringField("Usuario de LinkedIn", filters=[_strip], validators=[
        Optional(), Regexp(SOCIAL_RE, message=SOCIAL_MSG)])


class AvatarForm(FlaskForm):
    avatar = FileField("Foto de perfil", validators=[FileRequired("Selecciona una imagen.")])


class EmailForm(FlaskForm):
    new_email = StringField("Nuevo email", filters=[_strip_lower], validators=[
        DataRequired(REQUIRED),
        Email(message="Introduce un email válido."),
        Length(max=100, message="El email es demasiado largo."),
    ])
    current_password = PasswordField("Contraseña actual", validators=[DataRequired(REQUIRED)])


class PasswordForm(FlaskForm):
    current_password = PasswordField("Contraseña actual", validators=[DataRequired(REQUIRED)])
    new_password = PasswordField("Nueva contraseña", validators=[
        DataRequired(REQUIRED),
        Length(min=8, message="La contraseña debe tener al menos 8 caracteres."),
    ])
    confirm_password = PasswordField("Repite la nueva contraseña", validators=[
        DataRequired(REQUIRED),
        EqualTo("new_password", message="Las contraseñas no coinciden."),
    ])


class DeleteAccountForm(FlaskForm):
    current_password = PasswordField("Contraseña actual", validators=[DataRequired(REQUIRED)])
    confirm = BooleanField("Entiendo que se borrarán mis datos y no se puede deshacer",
                           validators=[DataRequired("Marca la casilla para confirmar.")])
