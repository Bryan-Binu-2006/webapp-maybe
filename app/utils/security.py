"""
utils/security.py — Security helpers
======================================
Contains decorators and functions used across routes to enforce
authentication and authorisation rules.

SECURITY NOTES:
- login_required is a decorator that redirects unauthenticated
  users to the login page.  Without it, any route would be
  accessible to anonymous visitors.
- validate_uuid prevents malformed UUID strings from reaching
  the database layer, where they would cause exceptions or
  unexpected behaviour.
"""

import uuid
import logging
from functools import wraps

from flask import session, redirect, url_for, flash, abort

logger = logging.getLogger(__name__)


def login_required(f):
    """
    Decorator: ensures the user is logged in before accessing
    the wrapped route.

    HOW IT WORKS:
    - Flask's session dict is a signed cookie.  If 'user_id'
      is present, the user authenticated successfully in a
      previous request.
    - If missing, we redirect to the login page.

    WHY:
    - Without this check, any visitor could hit protected
      endpoints directly by typing the URL.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated_function


def validate_uuid(value: str) -> uuid.UUID | None:
    """
    Attempt to parse *value* as a UUID.

    Returns the UUID object on success, or None on failure.

    WHY:
    - Passing un-validated strings to DB queries (even
      parameterised ones) can cause 500 errors.
    - Early validation gives us a clean error path.
    """
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def require_ownership(resource_user_id, current_user_id):
    """
    Abort with 403 if the current user does not own the resource.

    WHY:
    - Even authenticated users must only access THEIR OWN data.
    - This is called "horizontal privilege escalation" prevention.
      Without it, User A could view User B's certificates by
      changing the UUID in the URL.
    """
    if str(resource_user_id) != str(current_user_id):
        logger.warning(
            "Ownership violation: user %s tried to access resource owned by %s",
            current_user_id,
            resource_user_id,
        )
        abort(403)
