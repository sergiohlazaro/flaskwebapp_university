"""Comandos de línea de órdenes de la aplicación (flask --app main <comando>)."""
import click
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import User

MIN_PASSWORD_LENGTH = 8


@click.command("create-admin")
@click.option("--email", prompt=True, help="Email del administrador.")
@click.option("--name", default="Admin", show_default=True, help="Nombre.")
@click.option("--surname", default="Admin", show_default=True, help="Apellido.")
@click.password_option(help="Contraseña (se pide por teclado si no se indica).")
def create_admin_command(email, name, surname, password):
    """Crea una cuenta de administrador con la contraseña indicada."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise click.ClickException(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    if User.query.filter_by(email=email).first():
        raise click.ClickException("A user with this email already exists")

    admin = User(
        name=name,
        surname=surname,
        email=email,
        password=generate_password_hash(password),
        role=0,
        is_blocked=False,
    )
    db.session.add(admin)
    db.session.commit()
    click.echo(f"Admin {email} created.")
