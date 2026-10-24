"""
PDF extraction (FR-2).

Recovers the visible text layer, document metadata, annotations, and — crucially
for this project — text spans that survive extraction but are not visible on the
rendered page: background-matched text (V1) and sub-visible font sizes (V2).

PyMuPDF provides per-span colour and font size (needed to classify visibility);
pdfplumber provides the "standard extractor" text layer used for the R1 view.
No embedded code, script, or link is executed (NFR-4): only text is read.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pdfplumber
import pymupdf

from .records import StructuralSpan

# A span is treated as "not visible to a human" if its font is smaller than this
# (points) or its colour is within this distance of the assumed white page
# background. These thresholds are configuration, not magic: they are the
# operating point the corpus generator's R2 check must agree with.
MIN_VISIBLE_FONT_PT = 3.0
NEAR_WHITE_MIN_CHANNEL = 240  # r,g,b all >= this => treated as background-matched

# PDF Info fields that can carry a payload (V3).
_METADATA_PAYLOAD_FIELDS = ("title", "author", "subject", "keywords", "creator", "producer")


def _int_to_rgb(color: int) -> tuple[int, int, int]:
    return (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF


def _is_low_visibility(size: float, color: int) -> tuple[bool, str]:
    if size < MIN_VISIBLE_FONT_PT:
        return True, f"sub-visible font ({size:.2f}pt)"
    r, g, b = _int_to_rgb(color)
    if r >= NEAR_WHITE_MIN_CHANNEL and g >= NEAR_WHITE_MIN_CHANNEL and b >= NEAR_WHITE_MIN_CHANNEL:
        return True, f"background-matched colour (#{r:02X}{g:02X}{b:02X})"
    return False, ""


def extract_pdf(path: Path) -> dict[str, Any]:
    """Return the fields needed to build an ExtractionRecord for a PDF."""
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    structural: list[StructuralSpan] = []
    visible_parts: list[str] = []

    doc = pymupdf.open(path)
    try:
        if doc.needs_pass:
            warnings.append("PDF is encrypted; extraction may be incomplete")

        # --- metadata (V3) ------------------------------------------------
        info = doc.metadata or {}
        for key, value in info.items():
            if value:
                metadata[key] = value
        for field in _METADATA_PAYLOAD_FIELDS:
            value = (info.get(field) or "").strip()
            if value:
                structural.append(
                    StructuralSpan(
                        channel="pdf_metadata",
                        text=value,
                        location=f"Info/{field}",
                        attrs={"field": field},
                    )
                )
        try:
            xmp = doc.get_xml_metadata()
            if xmp:
                metadata["xmp"] = xmp
        except Exception:  # pragma: no cover - XMP is optional
            pass

        # --- visible vs low-visibility spans (V1, V2) ---------------------
        for pno in range(doc.page_count):
            page = doc.load_page(pno)
            data = page.get_text("dict")
            for block in data.get("blocks", []):
                if block.get("type", 0) != 0:
                    continue  # skip image blocks
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if not text.strip():
                            continue
                        size = float(span.get("size", 0.0))
                        color = int(span.get("color", 0))
                        hidden, reason = _is_low_visibility(size, color)
                        if hidden:
                            r, g, b = _int_to_rgb(color)
                            structural.append(
                                StructuralSpan(
                                    channel="pdf_low_visibility_spans",
                                    text=text,
                                    location=f"page {pno + 1}",
                                    attrs={
                                        "font_size_pt": round(size, 3),
                                        "color_rgb": [r, g, b],
                                        "reason": reason,
                                    },
                                )
                            )
                        else:
                            visible_parts.append(text)
                    visible_parts.append("\n")

            # --- annotations (reserve channel) ----------------------------
            try:
                for annot in page.annots() or []:
                    content = (annot.info or {}).get("content", "").strip()
                    if content:
                        structural.append(
                            StructuralSpan(
                                channel="pdf_annotations",
                                text=content,
                                location=f"page {pno + 1}",
                                attrs={"type": annot.type[1] if annot.type else "?"},
                            )
                        )
            except Exception:  # pragma: no cover
                pass
    finally:
        doc.close()

    visible_text = "".join(visible_parts).strip()

    # --- all extractable text via the standard parser (R1 view) -----------
    all_text = ""
    try:
        with pdfplumber.open(path) as pdf:
            pages = [(p.extract_text() or "") for p in pdf.pages]
        all_text = "\n".join(pages).strip()
    except Exception as exc:
        warnings.append(f"pdfplumber extraction failed ({exc}); using PyMuPDF text layer")
        all_text = "\n".join(
            s for s in ([visible_text] + [sp.text for sp in structural]) if s
        ).strip()

    return {
        "visible_text": visible_text,
        "all_extractable_text": all_text,
        "metadata": metadata,
        "structural": structural,
        "warnings": warnings,
    }
