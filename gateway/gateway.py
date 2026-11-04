"""
Sanitisation gateway orchestration (OBJ-5 / FR-6, FR-7, FR-8).

The gateway sits IN FRONT OF the triage agent. Given a document, it returns the
text a human reading the rendered document would read, with every deception
channel removed:

    FR-6  render-vs-extract : forward only content visible on the rendered page
    FR-7  encoding normalise: withhold visible-but-encoding-deceptive content
    FR-8  channel stripping : never forward metadata / comments / annotations

The defended experiment feeds `sanitise(path).sanitised_text` to the SAME agent
with the SAME prompt that the undefended experiment used. The only thing that
changes between the two passes is whether this gateway is in the path, so the
difference in attack-success rate is attributable to the gateway alone.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .records import GatewayResult
from .pdf_sanitizer import sanitise_pdf
from .docx_sanitizer import sanitise_docx
from . import render_diff


def _file_type(path: Path) -> Optional[str]:
    suf = path.suffix.lower()
    if suf == ".pdf":
        return "pdf"
    if suf in (".docx", ".docm"):
        return "docx"
    return None


class Gateway:
    """Render-vs-extract sanitisation gateway (OBJ-5)."""

    def __init__(self, use_ocr: bool = False):
        # use_ocr enables the OCR render-vs-extract cross-check for PDFs when the
        # toolchain is present; it is a verification layer, not the primary path.
        self.use_ocr = use_ocr and render_diff.ocr_available()

    def sanitise(self, path: str | Path) -> GatewayResult:
        path = Path(path)
        t0 = time.perf_counter()
        ftype = _file_type(path)
        res = GatewayResult(ok=True, source_path=str(path), file_type=ftype)

        if not path.exists():
            res.ok = False
            res.error = "file not found"
            return res

        try:
            if ftype == "pdf":
                text, dropped, warnings = sanitise_pdf(path)
            elif ftype == "docx":
                text, dropped, warnings = sanitise_docx(path)
            else:
                res.ok = False
                res.error = f"unsupported file type: {path.suffix!r}"
                return res
        except Exception as exc:  # defensive: a malformed doc must not crash a run
            res.ok = False
            res.error = f"{type(exc).__name__}: {exc}"
            return res

        res.sanitised_text = text
        res.dropped = dropped
        res.warnings = warnings
        res.kept_chars = len(text)
        res.dropped_chars = sum(d.n_chars for d in dropped)

        # optional OCR cross-check (PDF only); record, do not fail on mismatch
        if self.use_ocr and ftype == "pdf":
            try:
                report = render_diff.verify_against_render(text, path)
                res.ocr_used = True
                leaked = report["forwarded_not_in_render"]
                if leaked:
                    res.warnings.append(
                        f"OCR check: {len(leaked)} forwarded token(s) not seen in render")
            except Exception as exc:  # pragma: no cover
                res.warnings.append(f"OCR check skipped: {exc}")
        elif self.use_ocr and ftype != "pdf":
            res.warnings.append("OCR check applies to PDF only; skipped")

        res.latency_s = round(time.perf_counter() - t0, 4)
        return res

    def sanitise_to_text(self, path: str | Path) -> str:
        """Convenience: just the forwarded text (empty string on failure)."""
        return self.sanitise(path).sanitised_text
