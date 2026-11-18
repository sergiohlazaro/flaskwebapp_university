import os

import pytest

from website import create_app

MEMORY_DB = {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_production_sets_secure_cookies(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    app = create_app(MEMORY_DB)
    assert app.config["SESSION_COOKIE_SECURE"] is True


def test_development_cookie_not_secure(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    assert create_app(MEMORY_DB).config["SESSION_COOKIE_SECURE"] is False


def test_proxyfix_only_with_trusted_proxies(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("TRUSTED_PROXIES", "1")
    app = create_app(MEMORY_DB)
    assert type(app.wsgi_app).__name__ == "ProxyFix"


def test_no_proxyfix_without_trusted_proxies(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    app = create_app(MEMORY_DB)
    assert type(app.wsgi_app).__name__ != "ProxyFix"


def test_upload_root_is_absolute_and_under_instance(app):
    assert os.path.isabs(app.config["UPLOAD_ROOT"])


def test_app_name_default(app):
    assert app.config["APP_NAME"] == "Campus Share"


def test_no_flask_caching_extension(app):
    assert "cache" not in app.extensions


def test_remember_cookie_hardening(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    prod = create_app(MEMORY_DB)
    assert prod.config["REMEMBER_COOKIE_SECURE"] is True
    assert prod.config["REMEMBER_COOKIE_HTTPONLY"] is True
    assert prod.config["REMEMBER_COOKIE_SAMESITE"] == "Lax"
    monkeypatch.setenv("APP_ENV", "development")
    dev = create_app(MEMORY_DB)
    assert dev.config["REMEMBER_COOKIE_SECURE"] is False
    assert dev.config["REMEMBER_COOKIE_HTTPONLY"] is True
    assert dev.config["REMEMBER_COOKIE_SAMESITE"] == "Lax"
