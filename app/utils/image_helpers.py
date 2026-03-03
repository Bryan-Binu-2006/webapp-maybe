"""
utils/image_helpers.py — Certificate image generation
======================================================
Uses Pillow to overlay participant names onto a template image.

SECURITY & PERFORMANCE NOTES:
- The original template is NEVER modified; we work on a copy.
- Image objects are explicitly closed after saving to free
  memory (important when generating hundreds of certificates
  in a batch).
- The verification UUID is rendered as small text on the
  certificate so it can be visually confirmed.
- We use a try/finally pattern to guarantee cleanup even if
  rendering fails partway through.
"""

import os
import logging
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Default font ────────────────────────────────────────────────────
# Pillow ships a small built-in font.  For production you would
# install a TTF and set CERTIFICATE_FONT env var.
DEFAULT_FONT_PATH = os.environ.get("CERTIFICATE_FONT", None)

# ── Font family → TTF mapping ──────────────────────────────────────
# Fonts are bundled in app/static/fonts/ (downloaded from Google Fonts).
_FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "fonts")

FONT_MAP = {
    "Inter":             os.path.join(_FONTS_DIR, "Inter-Regular.ttf"),
    "Roboto":            os.path.join(_FONTS_DIR, "Roboto-Regular.ttf"),
    "Open Sans":         os.path.join(_FONTS_DIR, "OpenSans-Regular.ttf"),
    "Montserrat":        os.path.join(_FONTS_DIR, "Montserrat-Regular.ttf"),
    "Poppins":           os.path.join(_FONTS_DIR, "Poppins-Regular.ttf"),
    "Raleway":           os.path.join(_FONTS_DIR, "Raleway-Regular.ttf"),
    "Playfair Display":  os.path.join(_FONTS_DIR, "PlayfairDisplay-Regular.ttf"),
    "Lora":              os.path.join(_FONTS_DIR, "Lora-Regular.ttf"),
    "Oswald":            os.path.join(_FONTS_DIR, "Oswald-Regular.ttf"),
    "Great Vibes":       os.path.join(_FONTS_DIR, "GreatVibes-Regular.ttf"),
    "Dancing Script":    os.path.join(_FONTS_DIR, "DancingScript-Regular.ttf"),
}

# Allowed font family names (for validation)
ALLOWED_FONTS = set(FONT_MAP.keys())


def _get_font(size: int, font_family: str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Load a TrueType font at the given size.

    Priority:
    1. If font_family is specified and exists in FONT_MAP, use it.
    2. If CERTIFICATE_FONT env var is set, use that.
    3. Fall back to system arial / DejaVu / Pillow default.
    """
    # 1) Try the requested font family
    if font_family and font_family in FONT_MAP:
        ttf_path = FONT_MAP[font_family]
        if os.path.isfile(ttf_path):
            try:
                return ImageFont.truetype(ttf_path, size)
            except OSError:
                logger.warning("Could not load font %s, trying fallbacks.", ttf_path)

    # 2) Try env-configured default
    if DEFAULT_FONT_PATH and os.path.isfile(DEFAULT_FONT_PATH):
        try:
            return ImageFont.truetype(DEFAULT_FONT_PATH, size)
        except OSError:
            logger.warning("Could not load font %s, using default.", DEFAULT_FONT_PATH)

    # 3) System fallbacks
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()


def _parse_color(color_str: str) -> Tuple[int, int, int]:
    """
    Parse a hex color string like '#FF0000' or 'FF0000' into
    an (R, G, B) tuple.

    Falls back to black if parsing fails.
    """
    color_str = color_str.strip().lstrip("#")
    if len(color_str) != 6:
        return (0, 0, 0)
    try:
        r = int(color_str[0:2], 16)
        g = int(color_str[2:4], 16)
        b = int(color_str[4:6], 16)
        return (r, g, b)
    except ValueError:
        return (0, 0, 0)


def generate_certificate(
    template_path: str,
    output_path: str,
    name: str,
    x: int,
    y: int,
    font_size: int,
    font_color: str,
    verification_code: str,
    font_family: str | None = None,
    text_align: str = "center",
    text_area_width: int = 0,
) -> None:
    """
    Generate a single certificate image.

    Steps:
    1. Open a COPY of the template (original stays untouched).
    2. Draw the participant name at (x, y).
    3. Draw the verification code in small text at the bottom.
    4. Save the result to *output_path*.
    5. Close the image to free memory.

    Parameters:
        template_path:    Path to the PNG template on disk.
        output_path:      Where to write the finished certificate.
        name:             Participant's name to render.
        x, y:             Pixel coordinates (top-left of text area).
        font_size:        Size in points for the name text.
        font_color:       Hex colour string (e.g. '#000000').
        verification_code: UUID string printed at the bottom.
        font_family:      Font family name (must be in FONT_MAP).
        text_align:       'left', 'center', or 'right'.
        text_area_width:  Width of the user-defined text area in px.
                          When > 0, alignment is computed within this area.
    """
    img = None
    try:
        # Open a copy — the original template must remain unchanged
        img = Image.open(template_path).copy()
        draw = ImageDraw.Draw(img)

        # ── Draw participant name ───────────────────────────────────
        name_font = _get_font(font_size, font_family)
        color_tuple = _parse_color(font_color)

        # ── Compute draw position based on text alignment ───────
        # x, y = top-left corner of the text area.
        # If the user resized the placeholder (text_area_width > 0),
        # we offset x so the text is centred/right-aligned within
        # that area.  Otherwise, draw at (x, y) directly.
        draw_x = x
        if text_area_width > 0:
            # Measure actual text width at the chosen font/size
            bbox = draw.textbbox((0, 0), name, font=name_font)
            text_w = bbox[2] - bbox[0]

            if text_align == "center":
                draw_x = x + (text_area_width - text_w) // 2
            elif text_align == "right":
                draw_x = x + text_area_width - text_w
            # else left — draw_x stays at x
        elif text_align == "center":
            # No box width — fallback: use anchor-based centering
            draw.text((x, y), name, fill=color_tuple, font=name_font, anchor="mt")
            draw_x = None  # signal we already drew
        elif text_align == "right":
            draw.text((x, y), name, fill=color_tuple, font=name_font, anchor="rt")
            draw_x = None

        if draw_x is not None:
            draw.text((draw_x, y), name, fill=color_tuple, font=name_font)

        # ── Draw verification code (small, bottom-right area) ──────
        verify_font = _get_font(max(12, font_size // 3))
        verify_text = f"Verification Code: {verification_code}"
        # Position near the bottom-left with a small margin
        img_width, img_height = img.size
        verify_y = img_height - 40
        verify_x = 20
        draw.text(
            (verify_x, verify_y),
            verify_text,
            fill=(100, 100, 100),  # subtle grey
            font=verify_font,
        )

        # ── Save ────────────────────────────────────────────────────
        img.save(output_path, "PNG")
        logger.debug("Generated certificate: %s", output_path)

    finally:
        # ALWAYS close the image to free memory, even on error
        if img is not None:
            img.close()
