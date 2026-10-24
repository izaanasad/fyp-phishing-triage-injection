"""
Corpus generator (FR-4).

Takes a clean base document and, for each applicable injection vector and each
attacker objective, produces a poisoned variant, validates it against rules R1
and R2 using the extraction pipeline, and records machine-checkable ground
truth. Variants that fail validation are rejected and logged — a valid,
informative outcome, not a crash.

Validation is concealment-class aware:
  * visual / structural vectors (V1-V6):
        R1  payload is recoverable by extraction (survives extraction)
        R2  payload is NOT in the rendered/visible text (invisible when rendered)
  * encoding vectors (V7, V8):
        R1  payload is recoverable by extraction
        R2' the extracted payload carries character-level obfuscation
            (zero-width for V7, homoglyph for V8) — concealment is at the
            encoding level, not the visual level. [See note in README.]

Ground truth per poisoned variant: correct verdict (malicious), the target IOCs
a faithful agent should extract, the exact injected span, vector, objective.
"""
from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from . import payloads
from .inject_docx import DOCX_VECTORS, inject_docx
from .inject_pdf import PDF_VECTORS, inject_pdf

# Reuse the extraction pipeline for R1/R2 validation.
_PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))
from extraction import extract  # noqa: E402

_ENCODING_VECTORS = {"V7", "V8"}


@dataclass
class GroundTruth:
    variant_id: str
    base_path: str
    variant_path: str
    file_type: str
    vector: str
    objective: str
    concealment_class: str          # 'visual_structural' | 'encoding'
    correct_verdict: str            # 'malicious' for poisoned variants
    injected_text: str              # exact span injected (obfuscated form for V7/V8)
    injected_text_normalized: str   # de-obfuscated form
    target_iocs: dict               # IOCs a faithful agent should still extract
    r1_pass: bool
    r2_pass: bool
    accepted: bool
    reject_reason: Optional[str] = None


@dataclass
class GenerationReport:
    base_path: str
    file_type: str
    out_dir: str
    clean_path: str
    accepted: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    @property
    def n_accepted(self) -> int:
        return len(self.accepted)

    @property
    def n_rejected(self) -> int:
        return len(self.rejected)


def applicable_vectors(file_type: str) -> tuple[str, ...]:
    return PDF_VECTORS if file_type == "pdf" else DOCX_VECTORS


def _validate(vector: str, marker: str, rec) -> tuple[bool, bool, str]:
    """Return (r1_pass, r2_pass, detail) for a poisoned variant's record."""
    recoverable = rec.all_extractable_text + "\n" + rec.concealed_text()
    r1 = marker in recoverable
    if not r1:
        return False, False, "R1 failed: injected payload not recoverable by extraction"

    if vector in _ENCODING_VECTORS:
        if vector == "V7":
            r2 = rec.encoding_flags.zero_width_count > 0
            detail = "" if r2 else "R2' failed: no zero-width obfuscation detected"
        else:
            r2 = rec.encoding_flags.homoglyph_count > 0
            detail = "" if r2 else "R2' failed: no homoglyph obfuscation detected"
    else:
        r2 = marker not in rec.visible_text
        detail = "" if r2 else "R2 failed: injected payload is visible in the rendered text"
    return r1, r2, detail


def generate(base_path: str | Path, out_dir: str | Path,
             objectives: tuple[str, ...] = payloads.OBJECTIVES) -> GenerationReport:
    """Generate the clean + poisoned variants for one base document."""
    base = Path(base_path)
    out = Path(out_dir)
    (out / "clean").mkdir(parents=True, exist_ok=True)
    (out / "poisoned").mkdir(parents=True, exist_ok=True)
    (out / "rejected").mkdir(parents=True, exist_ok=True)

    base_rec = extract(base)
    if not base_rec.ok:
        raise ValueError(f"base document failed validation: {base_rec.error}")
    file_type = base_rec.file_type
    target_iocs = payloads.find_iocs(base_rec.visible_text)

    # clean baseline (ground truth: benign)
    clean_path = out / "clean" / base.name
    shutil.copy2(base, clean_path)
    clean_gt = {
        "variant_id": f"{base.stem}__clean",
        "base_path": str(base),
        "variant_path": str(clean_path),
        "file_type": file_type,
        "vector": None,
        "objective": None,
        "correct_verdict": payloads.CORRECT_VERDICT_CLEAN,
        "target_iocs": target_iocs,
    }
    (clean_path.with_suffix(clean_path.suffix + ".gt.json")).write_text(
        json.dumps(clean_gt, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    report = GenerationReport(
        base_path=str(base), file_type=file_type, out_dir=str(out), clean_path=str(clean_path)
    )

    for vector in applicable_vectors(file_type):
        for objective in objectives:
            variant_id = f"{base.stem}__{vector}_{objective}"
            marker = payloads.marker_for(variant_id)
            payload = payloads.build_payload(variant_id, objective)
            variant_name = variant_id + base.suffix
            variant_path = out / "poisoned" / variant_name

            try:
                if file_type == "pdf":
                    injected = inject_pdf(base, vector, payload, variant_path)
                else:
                    injected = inject_docx(base, vector, payload, variant_path)
            except Exception as exc:  # injection itself failed (e.g. no font) — log, continue
                report.rejected.append(
                    {"variant_id": variant_id, "vector": vector, "objective": objective,
                     "reason": f"injection failed: {type(exc).__name__}: {exc}"}
                )
                continue

            rec = extract(variant_path)
            if not rec.ok:
                report.rejected.append(
                    {"variant_id": variant_id, "vector": vector, "objective": objective,
                     "reason": f"variant failed extraction: {rec.error}"}
                )
                variant_path.unlink(missing_ok=True)
                continue

            r1, r2, detail = _validate(vector, marker, rec)
            concealment = "encoding" if vector in _ENCODING_VECTORS else "visual_structural"
            gt = GroundTruth(
                variant_id=variant_id,
                base_path=str(base),
                variant_path=str(variant_path),
                file_type=file_type,
                vector=vector,
                objective=objective,
                concealment_class=concealment,
                correct_verdict=payloads.CORRECT_VERDICT_POISONED,
                injected_text=injected,
                injected_text_normalized=payloads.normalize(injected),
                target_iocs=target_iocs,
                r1_pass=r1,
                r2_pass=r2,
                accepted=bool(r1 and r2),
                reject_reason=None if (r1 and r2) else detail,
            )

            if gt.accepted:
                variant_path.with_suffix(variant_path.suffix + ".gt.json").write_text(
                    json.dumps(asdict(gt), indent=2, ensure_ascii=False), encoding="utf-8"
                )
                report.accepted.append(str(variant_path))
            else:
                # move the failed variant aside for inspection and log the reason
                dest = out / "rejected" / variant_name
                variant_path.replace(dest)
                report.rejected.append(
                    {"variant_id": variant_id, "vector": vector, "objective": objective,
                     "reason": gt.reject_reason, "r1_pass": r1, "r2_pass": r2,
                     "path": str(dest)}
                )

    # write the manifest + rejection log
    (out / "manifest.json").write_text(
        json.dumps({
            "base": str(base), "file_type": file_type,
            "accepted": report.accepted, "rejected": report.rejected,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if report.rejected:
        with (out / "rejections.log").open("a", encoding="utf-8") as fh:
            for r in report.rejected:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return report


def generate_many(base_paths, out_dir) -> list[GenerationReport]:
    return [generate(b, out_dir) for b in base_paths]
