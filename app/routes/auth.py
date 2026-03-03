"""
routes/auth.py — Authentication routes
========================================
Handles user registration, login, and logout.

SECURITY NOTES:
- Passwords are hashed with bcrypt BEFORE storing.
- Login uses constant-time comparison (via bcrypt.checkpw).
- Sessions are server-signed cookies with HttpOnly, Secure,
  and SameSite=Strict flags (configured globally in config.py).
- CSRF protection is handled by Flask-WTF's CSRFProtect, which
  requires a hidden token in every POST form.
- We log ALL authentication attempts (without passwords!) for
  audit purposes.
- Generic error messages ("Invalid credentials") prevent
  username enumeration — an attacker cannot tell whether the
  username or password was wrong.
"""

import logging

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    session,
    request,
)

from app.models.database import db
from app.models.user import User

logger = logging.getLogger(__name__)

# ── Blueprint ───────────────────────────────────────────────────────
auth_bp = Blueprint("auth", __name__)


# ── REGISTER ────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """
    GET  → show registration form.
    POST → validate input, create user, redirect to login.
    """
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    confirm = request.form.get("confirm_password", "").strip()

    # ── Input validation ────────────────────────────────────────────
    errors = []
    if not username or len(username) < 3 or len(username) > 80:
        errors.append("Username must be 3-80 characters.")
    if not password or len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if password != confirm:
        errors.append("Passwords do not match.")
    if errors:
        for e in errors:
            flash(e, "danger")
        return render_template("register.html"), 400

    # ── Check uniqueness ────────────────────────────────────────────
    if User.query.filter_by(username=username).first():
        flash("Username already taken.", "danger")
        logger.info("Registration attempt with existing username: %s", username)
        return render_template("register.html"), 409

    # ── Create user ─────────────────────────────────────────────────
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    logger.info("New user registered: %s (id=%s)", username, user.id)
    flash("Registration successful! Please log in.", "success")
    return redirect(url_for("auth.login"))


# ── LOGIN ───────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    GET  → show login form.
    POST → verify credentials, create session.
    """
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    user = User.query.filter_by(username=username).first()

    if user is None or not user.check_password(password):
        # SECURITY: Generic message prevents username enumeration.
        flash("Invalid username or password.", "danger")
        logger.warning("Failed login attempt for username: %s", username)
        return render_template("login.html"), 401

    # ── Create session ──────────────────────────────────────────────
    session.permanent = True  # Uses PERMANENT_SESSION_LIFETIME
    session["user_id"] = str(user.id)
    session["username"] = user.username

    logger.info("Successful login: %s (id=%s)", username, user.id)
    flash(f"Welcome back, {user.username}!", "success")
    return redirect(url_for("certificates.dashboard"))


# ── LOGOUT ──────────────────────────────────────────────────────────
@auth_bp.route("/logout")
def logout():
    """
    Clear the session and redirect to login.

    WHY session.clear()?
    - Removes all session data, not just user_id.
    - Prevents session fixation by ensuring the old session
      token is fully invalidated.
    """
    username = session.get("username", "unknown")
    session.clear()
    logger.info("User logged out: %s", username)
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
