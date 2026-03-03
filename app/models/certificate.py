"""
models/certificate.py — CertificateBatch & Certificate models
===============================================================
These two models capture:
1. A "batch" — one upload session (template + Excel).
2. Individual "certificates" — one per name in the Excel file.

SECURITY NOTES:
- Certificate files are NEVER stored in the database.  Only the
  *path* on disk is recorded.  This keeps the DB lean and avoids
  binary-blob issues.
- Each certificate gets a random UUID verification_code that is
  independent of the primary key.  This is the only value exposed
  publicly (via /verify/<uuid>).  Using the PK directly would
  invite enumeration.
- Foreign keys enforce data integrity at the DB level.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import UUID

from app.models.database import db


class CertificateBatch(db.Model):
    """
    Groups certificates generated from one template + one Excel file.
    """

    __tablename__ = "certificate_batches"

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of this batch.",
    )
    template_filename = db.Column(
        db.String(255),
        nullable=False,
        comment="Sanitised filename of the uploaded template image.",
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_deleted = db.Column(
        db.Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Soft-delete flag. Files removed, DB records kept for verification.",
    )

    # ── Relationships ───────────────────────────────────────────────
    certificates = db.relationship(
        "Certificate",
        backref="batch",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<CertificateBatch {self.id}>"


class Certificate(db.Model):
    """
    Represents a single generated certificate image for one participant.
    """

    __tablename__ = "certificates"

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    batch_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("certificate_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    participant_name = db.Column(
        db.String(200),
        nullable=False,
    )
    file_path = db.Column(
        db.String(500),
        nullable=False,
        comment="Relative path under STORAGE_DIR on disk.",
    )
    verification_code = db.Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
        index=True,
        comment="Public UUID used in /verify/<uuid>.",
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Certificate {self.participant_name} [{self.verification_code}]>"
