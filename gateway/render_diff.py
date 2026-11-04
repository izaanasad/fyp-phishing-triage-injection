"""
Optional render-vs-extract OCR verification (FR-6, strongest form).

The default PDF path reconstructs the visible layer from the renderer's span
attributes, which is fast and dependency-light. This module provides the
*gold-standard* realisation of the render-vs-extract principle: rasterise each
page to an image (what a human's eyes receive), OCR it (what the eye reads), and
confirm that the gateway's forwarded text is actually present in the rendered
image — i.e. nothing invisible slipped through, and nothing visible was lost.

It is OPTIONAL: it needs Tesseract + pytesseract + Pillow. When those are
absent the gateway runs on the span-attribute path alone and records a warning
instead of failing. OCR also inherently launders encoding tricks (it reads
pixels, so a homoglyph renders to its Latin look-alike and zero-width glyphs
leave no ink), which is why it is a useful cross-check on V7/V8.
"""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

try:  # optional dependencies
    import pytesseract
    from PIL import Image
    import io
    _OCR_IMPORTS = True
except Exception:  # pragma: no cover - environment-dependent
    _OCR_IMPORTS = False

_WORD = re.compile(r"[A-Za-z0-9]{3,}")


def ocr_available() -> bool:
    """True only if the OCR toolchain (library AND binary) is usable."""
    if not _OCR_IMPORTS:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # pragma: no cover - binary missing
        return False


def ocr_pdf_text(path: Path, dpi: int = 200) -> str:
    """Rasterise every page and return the OCR'd text (requires OCR toolchain)."""
    if not ocr_available():
        raise RuntimeError("OCR toolchain not available")
    out: list[str] = []
    doc = pymupdf.open(path)
    try:
        zoom = dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        for pno in range(doc.page_count):
            pix = doc.load_page(pno).get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            out.append(pytesseract.image_to_string(img))
    finally:
        doc.close()
    return "\n".join(out)


def verify_against_render(sanitised_text: str, path: Path) -> dict:
    """Cross-check forwarded text against OCR of the rendered pages.

    Returns a report: tokens the gateway forwarded that OCR did NOT see
    (possible leak of invisible text) and tokens a reader saw that the gateway
    dropped (possible over-removal). Empty sets mean the gateway's forwarded
    text matches what a human would read.
    """
    ocr_text = ocr_pdf_text(path)
    seen = {w.lower() for w in _WORD.findall(ocr_text)}
    fwd = {w.lower() for w in _WORD.findall(sanitised_text)}
    return {
        "forwarded_not_in_render": sorted(fwd - seen),   # should be ~empty
        "render_not_forwarded": sorted(seen - fwd),       # dropped-but-visible
        "ocr_token_count": len(seen),
        "forwarded_token_count": len(fwd),
    }
