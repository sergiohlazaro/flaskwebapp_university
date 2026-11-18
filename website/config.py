"""Configuración por entorno: development, testing y production."""

import os
from datetime import timedelta

MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "log")


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


class BaseConfig:
    APP_NAME = os.environ.get("APP_NAME", "Campus Share")
    SQLALCHEMY_DATABASE_URI = "sqlite:///database.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 24 * 1024 * 1024  # 24 MB

    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    TESTING = False
    WTF_CSRF_ENABLED = True
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Email: backends "log" (instance/mail.log), "smtp" y "memory" (tests).
    MAIL_BACKEND = MAIL_BACKEND
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = _env_flag("MAIL_USE_TLS", True)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@localhost")
    MAIL_LOG_RETENTION_DAYS = 30
    REQUIRE_EMAIL_VERIFICATION = _env_flag("REQUIRE_EMAIL_VERIFICATION", MAIL_BACKEND == "smtp")


class DevelopmentConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    RATELIMIT_STORAGE_URI = "memory://"
    MAIL_BACKEND = "memory"


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env: str) -> type[BaseConfig]:
    """Devuelve la clase de configuración para `env` (por defecto, development)."""
    return _CONFIGS.get((env or "development").lower(), DevelopmentConfig)
