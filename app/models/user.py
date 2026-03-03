"""
models/user.py — User model
============================
Stores user credentials.  Passwords are NEVER stored in plaintext.

SECURITY NOTES:
- We use bcrypt for hashing.  bcrypt is intentionally slow, which
  makes brute-force attacks orders of magnitude harder than fast
  hashes like SHA-256.
- check_password uses bcrypt's built-in constant-time comparison
  to prevent timing-side-channel attacks (where an attacker can
  deduce how many characters of a password are correct by measuring
  response time).
- UUID primary keys prevent enumeration attacks (sequential IDs
  let attackers guess valid user IDs).
"""

import uuid
from datetime import datetime, timezone

import bcrypt
from sqlalchemy.dialects.postgresql import UUID

from app.models.database import db


class User(db.Model):
    """Represents a registered user of the application."""

    __tablename__ = "users"

    # ── Columns ─────────────────────────────────────────────────────
    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Randomly generated UUID — not sequential.",
    )
    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True,
        comment="Login name (case-sensitive).",
    )
    password_hash = db.Column(
        db.String(128),
        nullable=False,
        comment="bcrypt hash — never the raw password.",
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ───────────────────────────────────────────────
    batches = db.relationship(
        "CertificateBatch", backref="owner", lazy="dynamic"
    )
    certificates = db.relationship(
        "Certificate", backref="owner", lazy="dynamic"
    )

    # ── Password helpers ────────────────────────────────────────────
    def set_password(self, plaintext: str) -> None:
        """
        Hash *plaintext* with bcrypt and store the result.

        WHY bcrypt?
        - It includes a per-hash random salt automatically.
        - Its work factor (rounds) can be increased as hardware
          gets faster.
        - It is the industry standard for password storage.
        """
        hashed = bcrypt.hashpw(
            plaintext.encode("utf-8"), bcrypt.gensalt(rounds=12)
        )
        self.password_hash = hashed.decode("utf-8")

    def check_password(self, plaintext: str) -> bool:
        """
        Verify *plaintext* against the stored hash.

        bcrypt.checkpw performs constant-time comparison internally,
        so an attacker cannot infer partial password correctness
        from response timing.
        """
        return bcrypt.checkpw(
            plaintext.encode("utf-8"),
            self.password_hash.encode("utf-8"),
        )

    def __repr__(self) -> str:
        return f"<User {self.username}>"
