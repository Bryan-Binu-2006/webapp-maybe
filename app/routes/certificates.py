"""
routes/certificates.py — Certificate generation & management
==============================================================
Core business logic: upload template + Excel → generate certs.

SECURITY NOTES:
- Every route is protected by @login_required.
- Ownership checks prevent horizontal privilege escalation.
- File uploads are validated for extension AND magic bytes.
- Filenames are NEVER user-controlled on disk.
- All database operations use the ORM (parameterised queries)
  to prevent SQL injection.
- Temporary files are cleaned up in finally blocks.

FLOW:
1. User uploads a PNG template.
2. User uploads an .xlsx with participant names.
3. App shows column headers; user picks the name column.
4. User sets text position (x, y), font size, font colour.
5. App generates one certificate per name and stores on disk.
6. Metadata (paths, verification codes) stored in PostgreSQL.
"""

import os
import uuid
import shutil
import logging
import time
import zipfile
import io

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    session,
    request,
    send_file,
    current_app,
    abort,
    jsonify,
)

from app.models.database import db
from app.models.certificate import CertificateBatch, Certificate
from app.utils.security import login_required, validate_uuid, require_ownership
from app.utils.file_helpers import (
    allowed_image,
    allowed_excel,
    validate_image,
    validate_excel_magic,
    safe_create_directory,
    generate_safe_filename,
    cleanup_file,
)
from app.utils.excel_helpers import get_column_headers, extract_names
from app.utils.image_helpers import generate_certificate, ALLOWED_FONTS

logger = logging.getLogger(__name__)

# ── Blueprint ───────────────────────────────────────────────────────
cert_bp = Blueprint("certificates", __name__)

# ====================================================================
# TEMPLATE PREVIEW — serve the pending template for the visual editor
# ====================================================================
@cert_bp.route("/template-preview")
@login_required
def template_preview():
    """
    Serve the pending template image so the configure page can
    display it in the visual editor canvas.

    SECURITY:
    - Only the owner's session-stored path is served.
    - Path traversal is checked against UPLOAD_DIR.
    """
    template_path = session.get("pending_template")
    if not template_path:
        abort(404)

    upload_dir = os.path.realpath(current_app.config["UPLOAD_DIR"])
    real_path = os.path.realpath(template_path)

    if not real_path.startswith(upload_dir):
        logger.warning("Path traversal attempt on template preview: %s", real_path)
        abort(403)

    if not os.path.isfile(real_path):
        abort(404)

    return send_file(real_path, mimetype="image/png")


# ====================================================================
# DASHBOARD — list all batches for the logged-in user
# ====================================================================
@cert_bp.route("/dashboard")
@login_required
def dashboard():
    """
    Show the user's certificate batches, newest first.
    """
    user_id = session["user_id"]
    batches = (
        CertificateBatch.query
        .filter_by(user_id=user_id, is_deleted=False)
        .order_by(CertificateBatch.created_at.desc())
        .all()
    )
    return render_template("dashboard.html", batches=batches)


# ====================================================================
# STEP 1 — Upload template and Excel
# ====================================================================
@cert_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    """
    GET  → show upload form for template + Excel.
    POST → validate files, save temporarily, redirect to configure.
    """
    if request.method == "GET":
        return render_template("upload.html")

    # ── Retrieve files from the form ────────────────────────────────
    template_file = request.files.get("template")
    excel_file = request.files.get("excel")

    if not template_file or not template_file.filename:
        flash("Please upload a certificate template image.", "danger")
        return render_template("upload.html"), 400

    if not excel_file or not excel_file.filename:
        flash("Please upload an Excel file (.xlsx).", "danger")
        return render_template("upload.html"), 400

    # ── Validate extensions (first pass) ────────────────────────────
    if not allowed_image(template_file.filename):
        flash("Template must be a PNG file.", "danger")
        return render_template("upload.html"), 400

    if not allowed_excel(excel_file.filename):
        flash("Only .xlsx Excel files are accepted.", "danger")
        return render_template("upload.html"), 400

    # ── Check sizes BEFORE saving ───────────────────────────────────
    # Read content to check size (werkzeug doesn't always know
    # content length before reading).
    template_data = template_file.read()
    if len(template_data) > current_app.config["MAX_TEMPLATE_SIZE"]:
        flash("Template image exceeds 5 MB limit.", "danger")
        return render_template("upload.html"), 400

    excel_data = excel_file.read()
    if len(excel_data) > current_app.config["MAX_EXCEL_SIZE"]:
        flash("Excel file exceeds 2 MB limit.", "danger")
        return render_template("upload.html"), 400

    # ── Save to temporary upload directory ──────────────────────────
    upload_dir = os.path.realpath(current_app.config["UPLOAD_DIR"])
    os.makedirs(upload_dir, exist_ok=True)

    template_safe_name = generate_safe_filename("png")
    excel_safe_name = generate_safe_filename("xlsx")

    template_path = os.path.join(upload_dir, template_safe_name)
    excel_path = os.path.join(upload_dir, excel_safe_name)

    with open(template_path, "wb") as f:
        f.write(template_data)
    with open(excel_path, "wb") as f:
        f.write(excel_data)

    # ── Validate file content (magic bytes) ─────────────────────────
    if not validate_image(template_path):
        cleanup_file(template_path)
        cleanup_file(excel_path)
        flash("Uploaded file is not a valid PNG image.", "danger")
        return render_template("upload.html"), 400

    if not validate_excel_magic(excel_path):
        cleanup_file(template_path)
        cleanup_file(excel_path)
        flash("Uploaded file is not a valid Excel .xlsx file.", "danger")
        return render_template("upload.html"), 400

    # ── Read column headers ─────────────────────────────────────────
    try:
        headers = get_column_headers(excel_path)
    except Exception as e:
        cleanup_file(template_path)
        cleanup_file(excel_path)
        logger.error("Error reading Excel headers: %s", e)
        flash("Could not read the Excel file. Is it a valid .xlsx?", "danger")
        return render_template("upload.html"), 400

    if not headers:
        cleanup_file(template_path)
        cleanup_file(excel_path)
        flash("Excel file has no column headers.", "danger")
        return render_template("upload.html"), 400

    # ── Store paths in session for step 2 ───────────────────────────
    session["pending_template"] = template_path
    session["pending_excel"] = excel_path
    session["pending_headers"] = headers

    return redirect(url_for("certificates.configure"))


# ====================================================================
# STEP 2 — Configure text placement & select column
# ====================================================================
@cert_bp.route("/configure", methods=["GET", "POST"])
@login_required
def configure():
    """
    GET  → show settings form (column picker, x, y, font size, colour).
    POST → generate certificates.
    """
    # Ensure step 1 was completed
    if "pending_template" not in session:
        flash("Please upload files first.", "warning")
        return redirect(url_for("certificates.upload"))

    headers = session.get("pending_headers", [])

    if request.method == "GET":
        return render_template("configure.html", headers=headers)

    # ── Read form values ────────────────────────────────────────────
    try:
        column_index = int(request.form.get("column_index", 0))
        text_x = int(request.form.get("text_x", 100))
        text_y = int(request.form.get("text_y", 100))
        font_size = int(request.form.get("font_size", 40))
        text_area_width = int(request.form.get("text_area_width", 0))
    except (ValueError, TypeError):
        flash("Invalid numeric input.", "danger")
        return render_template("configure.html", headers=headers), 400

    font_color = request.form.get("font_color", "#000000").strip()
    font_family = request.form.get("font_family", "Inter").strip()
    text_align = request.form.get("text_align", "center").strip()

    # ── Validate ranges ─────────────────────────────────────────────
    if font_family not in ALLOWED_FONTS:
        font_family = "Inter"  # safe default
    if text_align not in ("left", "center", "right"):
        text_align = "center"

    if column_index < 0 or column_index >= len(headers):
        flash("Invalid column selection.", "danger")
        return render_template("configure.html", headers=headers), 400
    if font_size < 8 or font_size > 200:
        flash("Font size must be between 8 and 200.", "danger")
        return render_template("configure.html", headers=headers), 400
    if text_x < 0 or text_y < 0 or text_x > 10000 or text_y > 10000:
        flash("Text coordinates must be between 0 and 10000.", "danger")
        return render_template("configure.html", headers=headers), 400
    if text_area_width < 0 or text_area_width > 10000:
        text_area_width = 0

    # ── Extract names ───────────────────────────────────────────────
    excel_path = session["pending_template"]  # stored in step 1
    excel_path = session["pending_excel"]
    template_path = session["pending_template"]

    try:
        names, warnings = extract_names(excel_path, column_index)
    except Exception as e:
        logger.error("Error extracting names: %s", e)
        flash("Error reading names from Excel file.", "danger")
        return render_template("configure.html", headers=headers), 400

    if not names:
        flash("No valid names found in the selected column.", "danger")
        return render_template("configure.html", headers=headers), 400

    # ── Create batch record ─────────────────────────────────────────
    user_id = session["user_id"]
    batch = CertificateBatch(
        user_id=user_id,
        template_filename=os.path.basename(template_path),
    )
    db.session.add(batch)
    db.session.flush()  # get batch.id before commit

    # ── Prepare storage directory ───────────────────────────────────
    storage_base = os.path.realpath(current_app.config["STORAGE_DIR"])
    batch_dir = safe_create_directory(storage_base, user_id, str(batch.id))

    db.session.commit()

    # ── Store generation params in session for the generate endpoint ─
    session["gen_params"] = {
        "batch_id": str(batch.id),
        "template_path": template_path,
        "excel_path": excel_path,
        "column_index": column_index,
        "batch_dir": batch_dir,
        "text_x": text_x,
        "text_y": text_y,
        "font_size": font_size,
        "font_color": font_color,
        "font_family": font_family,
        "text_align": text_align,
        "text_area_width": text_area_width,
        "cert_count": len(names),
    }

    # Clear pending upload session data
    session.pop("pending_template", None)
    session.pop("pending_excel", None)
    session.pop("pending_headers", None)

    # ── Redirect to progress page ───────────────────────────────────
    return redirect(url_for("certificates.progress_page", batch_id=batch.id))


# ====================================================================
# PROGRESS PAGE — loading screen while certificates are generated
# ====================================================================
@cert_bp.route("/batch/<batch_id>/progress")
@login_required
def progress_page(batch_id):
    """Show the loading page while certificates are generated."""
    parsed = validate_uuid(batch_id)
    if not parsed:
        abort(404)

    batch = CertificateBatch.query.get_or_404(parsed)
    require_ownership(batch.user_id, session["user_id"])

    # If certificates already exist, skip straight to the batch view
    existing = Certificate.query.filter_by(batch_id=batch.id).count()
    if existing > 0:
        return redirect(url_for("certificates.view_batch", batch_id=batch_id))

    gen_params = session.get("gen_params", {})
    cert_count = gen_params.get("cert_count", 0)

    return render_template("progress.html", batch=batch, cert_count=cert_count)


# ====================================================================
# GENERATE — synchronous certificate generation (called via fetch)
# ====================================================================
@cert_bp.route("/batch/<batch_id>/do-generate", methods=["POST"])
@login_required
def do_generate(batch_id):
    """
    Generate all certificates synchronously in a single request.
    Called by the progress page via fetch().
    Returns JSON with count and elapsed time.
    """
    parsed = validate_uuid(batch_id)
    if not parsed:
        return jsonify({"error": "Invalid batch ID"}), 404

    batch = CertificateBatch.query.get_or_404(parsed)
    require_ownership(batch.user_id, session["user_id"])

    # Prevent double generation
    existing = Certificate.query.filter_by(batch_id=batch.id).count()
    if existing > 0:
        return jsonify({"count": existing, "elapsed": 0, "error": None})

    gen_params = session.pop("gen_params", None)
    if not gen_params or gen_params.get("batch_id") != str(batch.id):
        return jsonify({"error": "Generation parameters expired. Please start over."}), 400

    template_path = gen_params["template_path"]
    excel_path = gen_params["excel_path"]
    column_index = gen_params["column_index"]
    batch_dir = gen_params["batch_dir"]
    text_x = gen_params["text_x"]
    text_y = gen_params["text_y"]
    font_size = gen_params["font_size"]
    font_color = gen_params["font_color"]
    font_family = gen_params["font_family"]
    text_align = gen_params["text_align"]
    text_area_width = gen_params["text_area_width"]
    user_id = session["user_id"]

    # Re-extract names from the Excel file
    try:
        names, _ = extract_names(excel_path, column_index)
    except Exception as e:
        logger.error("Error re-reading names for batch %s: %s", batch.id, e)
        cleanup_file(template_path)
        cleanup_file(excel_path)
        return jsonify({"error": "Failed to read Excel file."}), 500

    if not names:
        cleanup_file(template_path)
        cleanup_file(excel_path)
        return jsonify({"error": "No valid names found."}), 400

    # ── Generate certificates synchronously ─────────────────────────
    start_time = time.time()
    generated_count = 0

    try:
        for name in names:
            cert_id = uuid.uuid4()
            verification_code = uuid.uuid4()
            filename = f"{cert_id}.png"
            cert_path = os.path.join(batch_dir, filename)
            relative_path = os.path.join(str(user_id), str(batch.id), filename)

            try:
                generate_certificate(
                    template_path=template_path,
                    output_path=cert_path,
                    name=name,
                    x=text_x,
                    y=text_y,
                    font_size=font_size,
                    font_color=font_color,
                    verification_code=str(verification_code),
                    font_family=font_family,
                    text_align=text_align,
                    text_area_width=text_area_width,
                )
            except Exception as e:
                logger.error("Failed to generate certificate for '%s': %s", name, e)
                continue

            cert = Certificate(
                id=cert_id,
                batch_id=batch.id,
                user_id=user_id,
                participant_name=name,
                file_path=relative_path,
                verification_code=verification_code,
            )
            db.session.add(cert)
            generated_count += 1

        db.session.commit()
    except Exception as e:
        logger.error("Generation error for batch %s: %s", batch.id, e)
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cleanup_file(template_path)
        cleanup_file(excel_path)

    elapsed = round(time.time() - start_time, 1)
    logger.info(
        "Batch %s created: %d certificates by user %s (%.1fs)",
        batch.id, generated_count, user_id, elapsed,
    )

    return jsonify({"count": generated_count, "elapsed": elapsed, "error": None})


# ====================================================================
# VIEW BATCH — list certificates in a batch
# ====================================================================
@cert_bp.route("/batch/<batch_id>")
@login_required
def view_batch(batch_id):
    """Show all certificates in a batch. Ownership enforced."""
    parsed = validate_uuid(batch_id)
    if not parsed:
        abort(404)

    batch = CertificateBatch.query.get_or_404(parsed)
    require_ownership(batch.user_id, session["user_id"])

    certs = (
        Certificate.query
        .filter_by(batch_id=batch.id)
        .order_by(Certificate.participant_name)
        .all()
    )
    return render_template("batch.html", batch=batch, certificates=certs)


# ====================================================================
# DOWNLOAD CERTIFICATE — serve individual file (owner only)
# ====================================================================
@cert_bp.route("/certificate/<cert_id>/download")
@login_required
def download_certificate(cert_id):
    """
    Serve the certificate PNG for download.

    SECURITY:
    - Ownership check prevents User A from downloading User B's
      certificate by guessing the UUID.
    - We resolve the path and verify it's within STORAGE_DIR
      to prevent path traversal.
    """
    parsed = validate_uuid(cert_id)
    if not parsed:
        abort(404)

    cert = Certificate.query.get_or_404(parsed)
    require_ownership(cert.user_id, session["user_id"])

    storage_base = os.path.realpath(current_app.config["STORAGE_DIR"])
    full_path = os.path.realpath(os.path.join(storage_base, cert.file_path))

    # Path traversal check
    if not full_path.startswith(storage_base):
        logger.warning("Path traversal attempt: %s", full_path)
        abort(403)

    if not os.path.isfile(full_path):
        abort(404)

    return send_file(
        full_path,
        mimetype="image/png",
        as_attachment=True,
        download_name=f"certificate_{cert.participant_name}.png",
    )


# ====================================================================
# DOWNLOAD ALL — ZIP of all certificates in a batch
# ====================================================================
@cert_bp.route("/batch/<batch_id>/download-zip")
@login_required
def download_zip(batch_id):
    """
    Stream a ZIP file containing every certificate PNG in the batch.

    SECURITY:
    - Ownership enforced.
    - Path traversal checked against STORAGE_DIR.
    """
    parsed = validate_uuid(batch_id)
    if not parsed:
        abort(404)

    batch = CertificateBatch.query.get_or_404(parsed)
    require_ownership(batch.user_id, session["user_id"])

    storage_base = os.path.realpath(current_app.config["STORAGE_DIR"])
    batch_dir = os.path.realpath(
        os.path.join(storage_base, str(batch.user_id), str(batch.id))
    )

    if not batch_dir.startswith(storage_base):
        logger.warning("Path traversal attempt on ZIP download: %s", batch_dir)
        abort(403)

    if not os.path.isdir(batch_dir):
        flash("Certificate files have been deleted.", "warning")
        return redirect(url_for("certificates.view_batch", batch_id=batch_id))

    # Build a lookup: file_path basename -> participant name
    certs = Certificate.query.filter_by(batch_id=batch.id).all()
    name_map = {}
    for c in certs:
        basename = os.path.basename(c.file_path)
        safe_name = c.participant_name.replace("/", "_").replace("\\", "_")
        name_map[basename] = f"certificate_{safe_name}.png"

    # Create ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(batch_dir):
            fpath = os.path.join(batch_dir, fname)
            if os.path.isfile(fpath) and fname.lower().endswith(".png"):
                archive_name = name_map.get(fname, fname)
                zf.write(fpath, archive_name)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"certificates_batch_{str(batch.id)[:8]}.zip",
    )


# ====================================================================
# DELETE BATCH — remove files from storage, keep DB records
# ====================================================================
@cert_bp.route("/batch/<batch_id>/delete", methods=["POST"])
@login_required
def delete_batch(batch_id):
    """
    Delete certificate FILES from storage while keeping database
    records intact for verification purposes.

    SECURITY:
    - Ownership enforced.
    - Path traversal checked against STORAGE_DIR.
    """
    parsed = validate_uuid(batch_id)
    if not parsed:
        abort(404)

    batch = CertificateBatch.query.get_or_404(parsed)
    require_ownership(batch.user_id, session["user_id"])

    storage_base = os.path.realpath(current_app.config["STORAGE_DIR"])
    batch_dir = os.path.realpath(
        os.path.join(storage_base, str(batch.user_id), str(batch.id))
    )

    # Path traversal check
    if not batch_dir.startswith(storage_base):
        logger.warning("Path traversal attempt on batch delete: %s", batch_dir)
        abort(403)

    if os.path.isdir(batch_dir):
        shutil.rmtree(batch_dir)
        logger.info("Deleted batch files: %s", batch_dir)

    # Soft-delete: hide from dashboard but keep DB records for verification
    batch.is_deleted = True
    db.session.commit()

    flash(
        "Batch deleted. Verification records are preserved.",
        "success",
    )
    return redirect(url_for("certificates.dashboard"))
