"""
routes/verify.py — Public certificate verification
====================================================
This endpoint is the ONLY public-facing page that does not
require authentication.

Anyone with a verification UUID can check whether a certificate
is valid.  This is useful for employers, event organisers, or
institutions that want to confirm a certificate's authenticity.

SECURITY NOTES:
- No sensitive data is exposed — only the participant name,
  issue date, and validity status.
- The verification code is a random UUID, so brute-forcing
  valid codes is computationally infeasible (2^122 possibilities).
- We do NOT reveal the owner's username or internal IDs.
"""

import logging

from flask import Blueprint, render_template, abort

from app.models.certificate import Certificate
from app.utils.security import validate_uuid

logger = logging.getLogger(__name__)

# ── Blueprint ───────────────────────────────────────────────────────
verify_bp = Blueprint("verify", __name__)

@verify_bp.route("/verify")
def verify_page():
    """Show the verification form (no code submitted yet)."""
    return render_template("verify.html", valid=None, certificate=None)

@verify_bp.route("/verify/<code>")
def verify_certificate(code):
    """
    Public endpoint: check certificate validity.

    If the UUID matches a certificate → show valid info.
    If not → show "invalid certificate" message.
    """
    parsed = validate_uuid(code)
    if not parsed:
        # Malformed UUID — no need to query the database
        return render_template("verify.html", valid=False, certificate=None)

    cert = Certificate.query.filter_by(verification_code=parsed).first()

    if cert:
        logger.info("Certificate verified: %s (name=%s)", code, cert.participant_name)
        return render_template("verify.html", valid=True, certificate=cert)
    else:
        logger.info("Verification failed — code not found: %s", code)
        return render_template("verify.html", valid=False, certificate=None)
