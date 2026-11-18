import importlib
import logging
import smtplib

import pytest

from website import config as config_module
from website import create_app
from website.config import BaseConfig, get_config
from website.services.mail import MAIL_LOGGER, send_email, sent_emails


@pytest.fixture(autouse=True)
def _close_mail_handlers():
    yield
    logger = logging.getLogger(MAIL_LOGGER)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def _mail_app(tmp_path, **cfg):
    config = {"TESTING": True, "SECRET_KEY": "k", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
              "MAIL_LOG_FILE": str(tmp_path / "mail.log"), **cfg}
    return create_app(config)


def test_memory_backend_collects_email(app):
    send_email("ana@example.com", "Hola", "email/password_reset.txt", name="Ana",
               link="http://x/abc")
    sent = sent_emails()
    assert len(sent) == 1
    assert sent[0]["to"] == "ana@example.com"
    assert sent[0]["subject"] == "Hola"
    assert "Ana" in sent[0]["body"] and "http://x/abc" in sent[0]["body"]


def test_memory_backend_is_per_app(app, tmp_path):
    send_email("a@example.com", "S", "email/email_verify.txt", name="A", link="l")
    other = _mail_app(tmp_path)
    with other.app_context():
        assert sent_emails() == []


def test_log_backend_writes_mail_log_not_app_log(tmp_path, caplog):
    app = _mail_app(tmp_path, MAIL_BACKEND="log")
    with app.app_context(), caplog.at_level(logging.DEBUG):
        send_email("ana@example.com", "Hola", "email/password_reset.txt", name="Ana",
                   link="http://x/SECRETLINK")
    content = (tmp_path / "mail.log").read_text()
    assert "SECRETLINK" in content and "ana@example.com" in content
    assert "SECRETLINK" not in caplog.text


def test_log_handler_not_duplicated_across_apps(tmp_path):
    _mail_app(tmp_path, MAIL_BACKEND="log")
    _mail_app(tmp_path, MAIL_BACKEND="log")
    assert len(logging.getLogger(MAIL_LOGGER).handlers) == 1


def test_smtp_backend_failure_does_not_raise(tmp_path, monkeypatch, caplog):
    app = _mail_app(tmp_path, MAIL_BACKEND="smtp", MAIL_SERVER="smtp.invalid")

    def boom(*args, **kwargs):
        raise OSError("no connection")

    monkeypatch.setattr(smtplib, "SMTP", boom)
    with app.app_context(), caplog.at_level(logging.DEBUG):
        send_email("ana@example.com", "Hola", "email/password_reset.txt", name="Ana",
                   link="http://x/SECRETLINK")
    assert "SECRETLINK" not in caplog.text
    assert "no connection" in caplog.text


def test_smtp_backend_sends_message(tmp_path, monkeypatch):
    app = _mail_app(tmp_path, MAIL_BACKEND="smtp", MAIL_SERVER="smtp.test", MAIL_USERNAME="u",
                    MAIL_PASSWORD="p")
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("init", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, u, p):
            calls.append(("login", u, p))

        def send_message(self, msg):
            calls.append(("send", msg["To"], msg["Subject"]))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    with app.app_context():
        send_email("ana@example.com", "Hola", "email/email_verify.txt", name="Ana", link="l")
    assert calls == [("init", "smtp.test", 587, 10), ("starttls",), ("login", "u", "p"),
                     ("send", "ana@example.com", "Hola")]


def test_require_verification_defaults_follow_backend(monkeypatch):
    def cfg(backend, flag=None):
        monkeypatch.setenv("MAIL_BACKEND", backend)
        if flag is None:
            monkeypatch.delenv("REQUIRE_EMAIL_VERIFICATION", raising=False)
        else:
            monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", flag)
        return importlib.reload(config_module).BaseConfig.REQUIRE_EMAIL_VERIFICATION

    try:
        assert cfg("log") is False
        assert cfg("smtp") is True
        assert cfg("smtp", "0") is False
        assert cfg("log", "1") is True
    finally:
        monkeypatch.undo()
        importlib.reload(config_module)


def test_config_defaults():
    assert get_config("testing").MAIL_BACKEND == "memory"
    assert BaseConfig.MAIL_PORT == 587 and BaseConfig.MAIL_USE_TLS is True
    assert BaseConfig.MAIL_DEFAULT_SENDER == "no-reply@localhost"
    assert BaseConfig.MAIL_LOG_RETENTION_DAYS == 30
