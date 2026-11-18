"""Modelos y enumeraciones de la aplicación (spec §7.2)."""

import enum
import unicodedata
from datetime import UTC, datetime

from flask_login import UserMixin
from sqlalchemy import CheckConstraint
from sqlalchemy.orm import validates

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(cls):
    # Se guarda el valor (cadena en español), no el nombre del miembro.
    return db.Enum(cls, values_callable=lambda e: [m.value for m in e],
                   native_enum=False, validate_strings=True, length=20)


class Course(enum.Enum):
    FIRST = "1º"
    SECOND = "2º"
    THIRD = "3º"
    FOURTH = "4º"
    MASTER = "Máster"


class MaterialKind(enum.Enum):
    NOTES = "Apuntes"
    EXERCISES = "Ejercicios"
    EXAM = "Examen"
    SUMMARY = "Resumen"
    OTHER = "Otro"


class ReportReason(enum.Enum):
    INAPPROPRIATE = "Inapropiado"
    WRONG = "Erróneo"
    COPYRIGHT = "Copyright"
    OTHER = "Otro"


class ReportStatus(enum.Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReportTarget(enum.Enum):
    MATERIAL = "material"
    COMMENT = "comment"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text, default="This is my bio.")
    # 0 = administrador, 1 = usuario normal
    role = db.Column(db.Integer, nullable=False, default=1)
    is_teacher = db.Column(db.Boolean, nullable=False, default=False)
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)
    # None = usar el avatar por defecto
    avatar = db.Column(db.String(150), nullable=True, default=None)
    twitter = db.Column(db.String(255), nullable=True)
    linkedin = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    login_records = db.relationship('LoginRecord')

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.surname}".strip()

    @property
    def is_admin(self) -> bool:
        return self.role == 0


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    # Clave normalizada (casefold) para unicidad sin distinguir mayúsculas,
    # también con letras no ASCII (lower() de SQLite no las pliega).
    name_key = db.Column(db.String(200), nullable=False, unique=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)

    @validates("name")
    def _normalize_name(self, _key, value):
        if not isinstance(value, str):
            raise ValueError("El nombre de la asignatura es obligatorio.")  # noqa: TRY004
        value = unicodedata.normalize("NFC", value).strip()
        self.name_key = value.casefold()
        return value


class Material(db.Model):
    # AUTOINCREMENT: SQLite no reutiliza ids de filas borradas (evita heredar reportes huérfanos).
    __table_args__ = ({"sqlite_autoincrement": True},)

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    course = db.Column(_enum(Course), nullable=True)
    kind = db.Column(_enum(MaterialKind), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    # Al crear, updated_at copia created_at (mismo valor); solo cambia al editar.
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda ctx: ctx.get_current_parameters()["created_at"], onupdate=utcnow)
    is_hidden = db.Column(db.Boolean, nullable=False, default=False)

    subject = db.relationship("Subject")
    author = db.relationship("User")
    files = db.relationship("MaterialFile", cascade="all, delete-orphan", backref="material")
    ratings = db.relationship("Rating", cascade="all, delete-orphan", backref="material")
    favorites = db.relationship("Favorite", cascade="all, delete-orphan", backref="material")
    comments = db.relationship("Comment", cascade="all, delete-orphan", backref="material")

    @property
    def average_rating(self) -> float | None:
        if not self.ratings:
            return None
        return sum(r.stars for r in self.ratings) / len(self.ratings)

    @property
    def rating_count(self) -> int:
        return len(self.ratings)


class MaterialFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("material.id", ondelete="CASCADE"), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    mime = db.Column(db.String(100), nullable=False)
    size = db.Column(db.Integer, nullable=False)


class Rating(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("material.id", ondelete="CASCADE"), primary_key=True)
    stars = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (CheckConstraint("stars BETWEEN 1 AND 5", name="ck_rating_stars"),)


class Favorite(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("material.id", ondelete="CASCADE"), primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class Comment(db.Model):
    __table_args__ = ({"sqlite_autoincrement": True},)

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("material.id", ondelete="CASCADE"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    is_hidden = db.Column(db.Boolean, nullable=False, default=False)

    author = db.relationship("User")


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    target_type = db.Column(_enum(ReportTarget), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(_enum(ReportReason), nullable=False)
    details = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(_enum(ReportStatus), nullable=False, default=ReportStatus.PENDING)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])


class LoginRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ip_address = db.Column(db.String(50), nullable=False)
    # Se guarda en UTC; la hora de Madrid se obtiene al mostrarla (filtro localtime).
    login_time = db.Column(db.DateTime(timezone=True), default=utcnow)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete="SET NULL"), nullable=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete="SET NULL"), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    read_at = db.Column(db.DateTime(timezone=True), nullable=True)
    file_stored_name = db.Column(db.String(255), nullable=True)
    file_original_name = db.Column(db.String(255), nullable=True)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
