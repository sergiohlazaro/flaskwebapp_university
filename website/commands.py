"""Comandos de línea de órdenes de la aplicación (flask --app main <comando>)."""
import click
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import User, utcnow
from .services.search import reindex_all

MIN_PASSWORD_LENGTH = 8
MAX_EMAIL_LENGTH = 100  # tamaño de la columna user.email


@click.command("create-admin")
@click.option("--email", prompt=True, help="Email del administrador.")
@click.option("--name", default="Admin", show_default=True, help="Nombre.")
@click.option("--surname", default="Admin", show_default=True, help="Apellido.")
@click.password_option(help="Contraseña (se pide por teclado si no se indica).")
def create_admin_command(email, name, surname, password):
    """Crea una cuenta de administrador con la contraseña indicada."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise click.ClickException(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    email = email.strip().lower()
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise click.ClickException(f"Invalid email: {exc}") from None
    if len(email) > MAX_EMAIL_LENGTH:
        raise click.ClickException("Invalid email: it is too long")
    if User.query.filter(func.lower(User.email) == email).first():
        raise click.ClickException("A user with this email already exists")

    admin = User(
        name=name,
        surname=surname,
        email=email,
        password=generate_password_hash(password),
        role=0,
        is_blocked=False,
        email_verified_at=utcnow(),
    )
    db.session.add(admin)
    db.session.commit()
    click.echo(f"Admin {email} created.")


@click.command("reindex-search")
def reindex_search_command():
    """Reconstruye el índice de búsqueda de texto completo."""
    count = reindex_all()
    db.session.commit()
    click.echo(f"Reindexed {count} materials.")
