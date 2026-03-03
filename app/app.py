"""
app.py — Flask application factory & entry point
===================================================
This is the heart of the application.  It uses the "application
factory" pattern, which means the Flask app is created inside a
function rather than at module level.

WHY the factory pattern?
- Allows creating multiple app instances (useful for testing).
- Prevents circular imports (blueprints import *from* the app,
  but the app is not yet created at import time).
- Makes configuration explicit and testable.

SECURITY NOTES:
- CSRFProtect is initialised globally.  Every POST form MUST
  include {{ csrf_token() }} or it will be rejected with a 400.
- Custom error handlers prevent stack traces from leaking to
  the user in production.
- The secret key is loaded from environment variables.
"""

import os
import logging

from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect

from app.config import config_by_name
from app.models.database import db
from app.utils.logging_config import setup_logging

# ── CSRF protection (initialised with the app later) ───────────────
csrf = CSRFProtect()


def create_app(config_name: str | None = None) -> Flask:
    """
    Application factory.

    Parameters:
        config_name: 'development', 'production', or 'default'.
                     Falls back to FLASK_ENV env var.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")

    # ── Create Flask instance ───────────────────────────────────────
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # ── Load configuration ──────────────────────────────────────────
    config_class = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_class)

    # ── Set up logging ──────────────────────────────────────────────
    setup_logging(app.config.get("LOG_LEVEL", "INFO"))
    logger = logging.getLogger(__name__)
    logger.info("Starting CertIssuer with config: %s", config_name)

    # ── Initialise extensions ───────────────────────────────────────
    db.init_app(app)
    csrf.init_app(app)

    # ── Ensure storage directories exist ────────────────────────────
    for dir_path in [app.config["STORAGE_DIR"], app.config["UPLOAD_DIR"]]:
        os.makedirs(dir_path, exist_ok=True)

    # ── Register blueprints ─────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.certificates import cert_bp
    from app.routes.verify import verify_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(cert_bp)
    app.register_blueprint(verify_bp)

    # ── Exempt the public verify endpoint from CSRF ─────────────────
    # The verify page has a GET-based form (no POST), but we exempt
    # the blueprint just in case to keep it fully public.
    csrf.exempt(verify_bp)

    # ── Create database tables ──────────────────────────────────────
    with app.app_context():
        # Import models so SQLAlchemy knows about them
        from app.models.user import User  # noqa: F401
        from app.models.certificate import CertificateBatch, Certificate  # noqa: F401
        db.create_all()

        # ── Micro-migration: add is_deleted column if missing ───────
        # db.create_all() cannot add columns to existing tables, so
        # we run a one-off ALTER TABLE.  IF NOT EXISTS makes it safe
        # to run multiple times.
        try:
            db.session.execute(db.text(
                "ALTER TABLE certificate_batches "
                "ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

        logger.info("Database tables ensured.")

    # ── Custom error handlers ───────────────────────────────────────
    # SECURITY: Never show stack traces to users.
    @app.errorhandler(400)
    def bad_request(e):
        return render_template(
            "errors.html", error_code=400,
            error_message="Bad request."
        ), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template(
            "errors.html", error_code=403,
            error_message="You do not have permission to access this resource."
        ), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template(
            "errors.html", error_code=404,
            error_message="The page you are looking for does not exist."
        ), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template(
            "errors.html", error_code=413,
            error_message="Uploaded file is too large."
        ), 413

    @app.errorhandler(500)
    def server_error(e):
        logger.error("Internal server error: %s", e)
        return render_template(
            "errors.html", error_code=500,
            error_message="An internal error occurred. Please try again later."
        ), 500

    # ── Root redirect ───────────────────────────────────────────────
    @app.route("/")
    def index():
        from flask import redirect, url_for, session
        if session.get("user_id"):
            return redirect(url_for("certificates.dashboard"))
        return redirect(url_for("auth.login"))

    return app


# ── Direct execution (development only) ────────────────────────────
if __name__ == "__main__":
    application = create_app("development")
    application.run(host="127.0.0.1", port=5000, debug=True)
