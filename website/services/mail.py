"""Envío de email con tres backends: `log` (instance/mail.log), `smtp` y `memory` (tests).

El cuerpo del mensaje solo se escribe en el logger `website.mail` (fichero propio,
sin propagación); el log general de la app nunca lo recibe.
"""
import logging
import os
import smtplib
from email.message import EmailMessage
from logging.handlers import TimedRotatingFileHandler

from flask import current_app

MAIL_LOGGER = "website.mail"


def init_mail(app):
    """Prepara el logger de correo. Sustituye el handler anterior (no se duplican al crear apps)."""
    logger = logging.getLogger(MAIL_LOGGER)
    logger.propagate = False
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    if app.config["MAIL_BACKEND"] != "log":
        return
    path = app.config.get("MAIL_LOG_FILE") or os.path.join(app.instance_path, "mail.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handler = TimedRotatingFileHandler(path, when="midnight",
                                       backupCount=app.config["MAIL_LOG_RETENTION_DAYS"],
                                       encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter("%(asctime)s\n%(message)s\n"))
    logger.addHandler(handler)


def send_email(to: str, subject: str, template: str, **context) -> None:
    """Renderiza `template` y lo envía por el backend configurado. Nunca lanza por fallos de envío."""
    # Sin render_template: los context processors de la web asumen una petición.
    body = current_app.jinja_env.get_template(template).render(
        app_name=current_app.config["APP_NAME"], **context)
    backend = current_app.config["MAIL_BACKEND"]
    if backend == "memory":
        current_app.extensions.setdefault("sent_emails", []).append(
            {"to": to, "subject": subject, "body": body})
    elif backend == "smtp":
        _send_smtp(to, subject, body)
    else:
        logging.getLogger(MAIL_LOGGER).info("To: %s\nSubject: %s\n\n%s", to, subject, body)


def sent_emails() -> list[dict]:
    """Correos recogidos por el backend `memory` en la app actual."""
    return current_app.extensions.setdefault("sent_emails", [])


def _send_smtp(to, subject, body):
    cfg = current_app.config
    try:
        msg = EmailMessage()
        msg["From"] = cfg["MAIL_DEFAULT_SENDER"]
        msg["To"] = to  # CR/LF en cabeceras lanza ValueError
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10) as smtp:
            if cfg["MAIL_USE_TLS"]:
                smtp.starttls()
            if cfg["MAIL_USERNAME"]:
                smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001 - un fallo de correo no debe romper la petición
        # Solo el tipo: str(exc) puede incluir destinatarios u otros datos del mensaje.
        current_app.logger.error("No se pudo enviar el email (%s)", type(exc).__name__)
