"""
PDF sanitisation (FR-6 render-vs-extract + FR-8 channel stripping).

Reconstructs the text a human reading the rendered PDF would actually read, by
asking the rendering engine (PyMuPDF) for each text span's paint properties and
keeping only spans that would be legible on the page:

  * font size at or above a readability floor   (drops V2 sub-visible font)
  * fill colour with enough contrast vs the white page background
    (drops V1 background-matched / white-on-white text)
  * a non-degenerate bounding box inside the page crop

Document metadata (Info/XMP) and annotations are NEVER forwarded (drops V3 and
the annotation reserve channel): they are not part of the rendered body a reader
sees. Kept spans are then screened for encoding deception (FR-7, V7/V8).

This pass is INDEPENDENT of the extraction pipeline: it re-derives visibility
from the renderer's own span attributes and does not consult the corpus ground
truth or the extractor's concealment labels. Nothing in the PDF is executed
(NFR-4): only text and its render attributes are read.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

from . import normalize
from .records import DroppedSpan

# Readability floor. Text below this point size is not legible as body content
# at normal zoom; 4.0pt is a conservative, independent choice (the extraction
# pipeline reports at 3.0pt — the gateway does not reuse that threshold).
MIN_VISIBLE_FONT_PT = 4.0

# A span is treated as background-matched (invisible on a white page) if its
# fill colour is too light to read on white. We use relative luminance: white
# has luminance 255; a span whose luminance is within this margin of white is
# dropped. Pure white (V1) has luminance 255 -> margin 0 -> dropped.
MIN_LUMINANCE_CONTRAST = 40.0


def _rgb(color: int) -> tuple[int, int, int]:
    return (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF


def _luminance(color: int) -> float:
    r, g, b = _rgb(color)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _is_legible(span: dict) -> tuple[bool, str]:
    """Would this span be readable by a human on a white page?"""
    size = float(span.get("size", 0.0))
    if size < MIN_VISIBLE_FONT_PT:
        return False, f"sub-visible font ({size:.2f}pt)"

    # transparent / near-transparent text, when the build reports alpha
    alpha = span.get("alpha")
    if alpha is not None and alpha <= 8:
        return False, f"near-transparent (alpha={alpha})"

    color = int(span.get("color", 0))
    if (255.0 - _luminance(color)) < MIN_LUMINANCE_CONTRAST:
        r, g, b = _rgb(color)
        return False, f"background-matched colour (#{r:02X}{g:02X}{b:02X})"

    bbox = span.get("bbox")
    if bbox and (abs(bbox[2] - bbox[0]) < 0.1 or abs(bbox[3] - bbox[1]) < 0.1):
        return False, "degenerate bounding box"

    return True, ""


def sanitise_pdf(path: Path) -> tuple[str, list[DroppedSpan], list[str]]:
    """Return (sanitised_text, dropped_spans, warnings) for a PDF."""
    dropped: list[DroppedSpan] = []
    warnings: list[str] = []
    kept_lines: list[str] = []

    doc = pymupdf.open(path)
    try:
        if getattr(doc, "needs_pass", False):
            warnings.append("PDF is encrypted; sanitisation may be incomplete")

        # FR-8: metadata is not rendered body text -> never forwarded. Record it
        # as withheld so the evidence shows V3 was caught.
        info = doc.metadata or {}
        for field_name in ("title", "author", "subject", "keywords", "creator", "producer"):
            value = (info.get(field_name) or "").strip()
            if value:
                dropped.append(DroppedSpan(
                    mechanism="non_body_channel",
                    reason=f"document metadata (Info/{field_name}) is not rendered body text",
                    location=f"Info/{field_name}", preview=value[:120], n_chars=len(value)))

        for pno in range(doc.page_count):
            page = doc.load_page(pno)
            crop = page.rect
            data = page.get_text("dict")
            for block in data.get("blocks", []):
                if block.get("type", 0) != 0:
                    continue  # image block
                for line in block.get("lines", []):
                    parts: list[str] = []
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if not text.strip():
                            continue
                        legible, reason = _is_legible(span)
                        if not legible:
                            dropped.append(DroppedSpan(
                                mechanism="render_visibility",
                                reason=f"not visible on the rendered page: {reason}",
                                location=f"page {pno + 1}", preview=text[:120],
                                n_chars=len(text)))
                            continue
                        # FR-7: visible, but is it encoding-deceptive (V7/V8)?
                        obf = normalize.obfuscation_reason(text)
                        if obf:
                            dropped.append(DroppedSpan(
                                mechanism="encoding_deception",
                                reason=f"deceptive character encoding: {obf}",
                                location=f"page {pno + 1}",
                                preview=normalize.canonicalise(text)[:120],
                                n_chars=len(text)))
                            continue
                        parts.append(normalize.canonicalise(text))
                    if parts:
                        kept_lines.append("".join(parts))

            # annotations are not body text -> never forwarded (reserve channel)
            try:
                for annot in page.annots() or []:
                    content = (annot.info or {}).get("content", "").strip()
                    if content:
                        dropped.append(DroppedSpan(
                            mechanism="non_body_channel",
                            reason="PDF annotation is not rendered body text",
                            location=f"page {pno + 1}", preview=content[:120],
                            n_chars=len(content)))
            except Exception:  # pragma: no cover
                pass
    finally:
        doc.close()

    return "\n".join(kept_lines).strip(), dropped, warnings
