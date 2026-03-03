"""
config.py — Application Configuration
======================================
Centralizes all configuration for the Flask application.
Uses environment variables so secrets never live in source code.

WHY:
- Hardcoded secrets are the #1 cause of credential leaks.
- Environment variables let us change settings per environment
  (dev / staging / production) without touching code.
- A config class hierarchy (Base → Dev → Production) prevents
  accidentally running with debug=True in production.
"""

import os
from datetime import timedelta


class BaseConfig:
    """
    Base configuration shared by all environments.
    Every setting here can be overridden by subclasses or env vars.
    """

    # ── Secret key for signing session cookies ──────────────────────
    # RISK: If this is weak or predictable, an attacker can forge
    #       session cookies and impersonate any user.
    # MITIGATION: Read from env var; fall back only in dev.
    SECRET_KEY = os.environ.get("SECRET_KEY", "CHANGE-ME-IN-PRODUCTION")

    # ── Database ────────────────────────────────────────────────────
    # We use PostgreSQL exclusively. SQLite is NOT acceptable for
    # concurrent writes in production.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://certapp:certapp@localhost:5432/certapp",
    )
    # Disable the Flask-SQLAlchemy event system we don't use;
    # it consumes extra memory.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Session security ────────────────────────────────────────────
    # HttpOnly: JavaScript cannot read the cookie → prevents XSS
    #           from stealing session tokens.
    SESSION_COOKIE_HTTPONLY = True
    # Secure: Cookie only sent over HTTPS → prevents sniffing on
    #         plain HTTP.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "True").lower() == "true"
    # SameSite=Strict: Cookie not sent on cross-origin requests →
    #                  strong CSRF mitigation at the cookie level.
    SESSION_COOKIE_SAMESITE = "Strict"
    # Session lifetime — idle sessions expire after this duration.
    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=int(os.environ.get("SESSION_LIFETIME_MINUTES", "30"))
    )

    # ── Upload limits ───────────────────────────────────────────────
    # Prevents denial-of-service via huge file uploads.
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB global default
    MAX_TEMPLATE_SIZE = 5 * 1024 * 1024   # 5 MB for certificate template
    MAX_EXCEL_SIZE = 2 * 1024 * 1024      # 2 MB for Excel file

    # ── File storage ────────────────────────────────────────────────
    STORAGE_DIR = os.environ.get("STORAGE_DIR", os.path.join(os.path.dirname(__file__), "..", "storage"))
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads"))

    # ── Certificate generation ──────────────────────────────────────
    MAX_BATCH_SIZE = int(os.environ.get("MAX_BATCH_SIZE", "300"))
    MAX_NAME_LENGTH = int(os.environ.get("MAX_NAME_LENGTH", "120"))

    # ── Logging ─────────────────────────────────────────────────────
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


class DevelopmentConfig(BaseConfig):
    """
    Development overrides — more verbose, less strict cookies so
    we can test without HTTPS locally.
    """
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # localhost is HTTP
    LOG_LEVEL = "DEBUG"


class ProductionConfig(BaseConfig):
    """
    Production hardening.
    RISK: Running with DEBUG=True exposes stack traces and the
          interactive debugger to attackers.
    """
    DEBUG = False
    SESSION_COOKIE_SECURE = True

    @classmethod
    def init_app(cls):
        """
        Validates that critical env vars are set before the app
        starts in production.  Fail fast > silent misconfiguration.
        """
        assert os.environ.get("SECRET_KEY"), (
            "SECRET_KEY environment variable must be set in production!"
        )
        assert os.environ.get("DATABASE_URL"), (
            "DATABASE_URL environment variable must be set in production!"
        )


# ── Quick lookup by name ────────────────────────────────────────────
config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
