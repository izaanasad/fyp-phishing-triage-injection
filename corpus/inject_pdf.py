"""
PDF payload injection for the corpus generator (FR-4).

Applicable PDF vectors: V1 (background-matched text), V2 (sub-visible font),
V3 (metadata), V7 (zero-width), V8 (homoglyph). Each function writes a poisoned
copy of `base` to `out` and returns the exact injected text (so the generator
can validate R1/R2). Nothing in the base is executed (NFR-4).
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

from . import payloads
from .fonts import unicode_font_path

PDF_VECTORS = ("V1", "V2", "V3", "V7", "V8")

_UNICODE_FONT_ALIAS = "injfont"


def _insert_unicode_text(page, point, text, fontsize, color):
    """Insert text that may contain non-Latin code points, embedding a font."""
    font_path = unicode_font_path()
    if font_path is None:
        raise RuntimeError("no Unicode-capable system font found for PDF encoding vectors")
    page.insert_font(fontname=_UNICODE_FONT_ALIAS, fontfile=font_path)
    page.insert_text(point, text, fontsize=fontsize, color=color, fontname=_UNICODE_FONT_ALIAS)


def inject_pdf(base: Path, vector: str, payload: str, out: Path) -> str:
    """Inject `payload` into `base` via `vector`, writing to `out`.

    Returns the exact text injected (obfuscated form for V7/V8).
    """
    doc = pymupdf.open(base)
    try:
        page = doc.load_page(0)
        h = page.rect.height
        injected = payload

        if vector == "V1":  # background-matched (white on white)
            page.insert_text((40, h - 40), payload, fontsize=10, color=(1, 1, 1))
        elif vector == "V2":  # sub-visible font
            page.insert_text((40, h - 28), payload, fontsize=0.8, color=(0, 0, 0))
        elif vector == "V3":  # metadata field
            md = doc.metadata or {}
            md["subject"] = payload
            doc.set_metadata(md)
        elif vector == "V7":  # zero-width (encoding) — keep the marker plain
            marker_part, _, rest = payload.partition(" ")
            injected = marker_part + " " + payloads.zero_width_obfuscate(rest)
            _insert_unicode_text(page, (40, h - 16), injected, 9, (0, 0, 0))
        elif vector == "V8":  # homoglyph (encoding) — keep the marker plain
            marker_part, _, rest = payload.partition(" ")
            injected = marker_part + " " + payloads.homoglyph_obfuscate(rest)
            _insert_unicode_text(page, (40, h - 16), injected, 9, (0, 0, 0))
        else:
            raise ValueError(f"vector {vector} is not a PDF vector")

        doc.save(out)
        return injected
    finally:
        doc.close()
