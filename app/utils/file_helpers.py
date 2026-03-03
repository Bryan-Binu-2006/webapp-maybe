"""
utils/file_helpers.py — Safe file-handling utilities
=====================================================
Every function here is designed to prevent common file-handling
vulnerabilities:
- Path traversal (../../etc/passwd)
- Unrestricted file upload (uploading .exe disguised as .png)
- Denial-of-service via huge files

PRINCIPLES:
1. NEVER use a user-supplied filename on disk.
2. Always generate filenames internally (UUID).
3. Always validate MIME type with magic bytes, not just extension.
4. Always enforce size limits BEFORE writing to disk.
"""

import os
import uuid
import logging
import imghdr

from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

# ── Allowed MIME types ──────────────────────────────────────────────
ALLOWED_IMAGE_EXTENSIONS = {"png"}
ALLOWED_EXCEL_EXTENSIONS = {"xlsx"}


def allowed_image(filename: str) -> bool:
    """
    Check that *filename* has a .png extension.

    NOTE: This is a first-pass filter.  We also validate actual
    file content (magic bytes) after upload — see validate_image().
    """
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


def allowed_excel(filename: str) -> bool:
    """Check that *filename* has a .xlsx extension."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXCEL_EXTENSIONS
    )


def validate_image(file_path: str) -> bool:
    """
    Verify the file at *file_path* is actually a PNG by reading
    its magic bytes (file header).

    WHY:
    - An attacker can rename malware.exe → malware.png.
    - Checking the extension alone is not sufficient.
    - imghdr reads the first few bytes and returns 'png' only
      if the PNG signature (\\x89PNG) is present.
    """
    detected = imghdr.what(file_path)
    if detected != "png":
        logger.warning(
            "Image validation failed for %s: detected type '%s'",
            file_path,
            detected,
        )
        return False
    return True


def validate_excel_magic(file_path: str) -> bool:
    """
    Verify the file at *file_path* starts with the ZIP magic bytes
    (PK\\x03\\x04), since .xlsx files are ZIP archives.

    WHY:
    - Prevents uploading a CSV or script renamed to .xlsx.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(4)
        return header == b"PK\x03\x04"
    except OSError:
        return False


def safe_create_directory(base: str, *parts: str) -> str:
    """
    Create a directory under *base* using the supplied *parts*,
    and verify the result is actually inside *base*.

    RISK: Path traversal.
    MITIGATION:
    - We resolve both paths to absolute and check that the result
      starts with the base.
    - Parts are converted to strings (UUIDs) before joining — no
      user input reaches the filesystem.

    Returns the absolute path of the created directory.
    """
    # Convert everything to strings (handles UUID objects)
    str_parts = [str(p) for p in parts]
    target = os.path.join(base, *str_parts)
    target = os.path.realpath(target)
    base = os.path.realpath(base)

    if not target.startswith(base):
        raise ValueError("Path traversal detected!")

    os.makedirs(target, exist_ok=True)
    return target


def generate_safe_filename(extension: str = "png") -> str:
    """
    Generate a random UUID-based filename.

    WHY:
    - User-supplied filenames can contain path separators,
      null bytes, or very long strings.
    - A UUID filename is guaranteed safe.
    """
    return f"{uuid.uuid4()}.{extension}"


def cleanup_file(path: str) -> None:
    """
    Remove a file if it exists.  Silently ignores missing files.

    Used to clean up temporary uploads after processing.
    """
    try:
        if os.path.isfile(path):
            os.remove(path)
            logger.debug("Cleaned up file: %s", path)
    except OSError as e:
        logger.error("Failed to clean up %s: %s", path, e)
