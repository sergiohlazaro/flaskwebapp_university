"""Configuración por entorno: development, testing y production."""

import os


class BaseConfig:
    APP_NAME = os.environ.get("APP_NAME", "Campus Share")
    SQLALCHEMY_DATABASE_URI = "sqlite:///database.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 24 * 1024 * 1024  # 24 MB

    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    TESTING = False
    WTF_CSRF_ENABLED = True
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


class DevelopmentConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    RATELIMIT_STORAGE_URI = "memory://"


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
