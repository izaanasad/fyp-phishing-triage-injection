"""
Tests for the corpus generator (FR-4).

Run from `code/`:
    python -m pytest corpus/tests -q
or:
    python corpus/tests/test_corpus.py

Builds clean base documents, generates the full variant set, and asserts that
every accepted variant carries ground truth and genuinely passes R1/R2, that
clean/poisoned verdicts are correct, and that any rejections are the expected
encoding-vector cases — exercising the reject-and-log path of FR-4.
"""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # make `corpus` importable

import pymupdf  # noqa: E402

from corpus import generate, payloads  # noqa: E402
from corpus.inject_docx import W_NS  # noqa: E402

_PIPELINE = Path(__file__).resolve().parents[2] / "pipeline"
sys.path.insert(0, str(_PIPELINE))
from extraction import extract  # noqa: E402


# ---------------------------------------------------------------------------
# clean base-document builders (contain an IOC so target_iocs is non-empty)
# ---------------------------------------------------------------------------
def build_clean_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "ACME SUPPLIES — PURCHASE ORDER PO-5521",
        "Vendor portal: https://portal.acme-supplies.example/orders",
        "Support line: 198.51.100.23   Email: ap@acme-supplies.example",
        "Net 30 terms. Please confirm receipt.",
    ]
    y = 72
    for ln in lines:
        page.insert_text((60, y), ln, fontsize=11, color=(0, 0, 0))
        y += 20
    doc.save(path)
    doc.close()
    return path


def build_clean_docx(path: Path) -> Path:
    body = (
        '<w:p><w:r><w:t xml:space="preserve">MASTER SERVICES AGREEMENT</w:t></w:r></w:p>'
        '<w:p><w:r><w:t xml:space="preserve">Provider portal: https://vendor.example/portal</w:t></w:r></w:p>'
        '<w:p><w:r><w:t xml:space="preserve">Escalations: 203.0.113.10 or legal@vendor.example</w:t></w:r></w:p>'
        '<w:p><w:r><w:t xml:space="preserve">This agreement is governed by the laws of England.</w:t></w:r></w:p>'
    )
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", ct)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    return path


# ---------------------------------------------------------------------------
def _assert_accepted_are_valid(out: Path):
    """Every accepted variant has ground truth, passes R1/R2, and re-validates."""
    for gt_file in (out / "poisoned").glob("*.gt.json"):
        gt = json.loads(gt_file.read_text(encoding="utf-8"))
        assert gt["accepted"] and gt["r1_pass"] and gt["r2_pass"], gt["variant_id"]
        assert gt["correct_verdict"] == "malicious"
        marker = payloads.marker_for(gt["variant_id"])
        rec = extract(gt["variant_path"])
        assert rec.ok
        recoverable = rec.all_extractable_text + rec.concealed_text()
        assert marker in recoverable, f"R1 re-check failed for {gt['variant_id']}"
        if gt["concealment_class"] == "visual_structural":
            assert marker not in rec.visible_text, f"R2 re-check failed for {gt['variant_id']}"


def test_docx_generation(tmp_path: Path):
    base = build_clean_docx(tmp_path / "msa.docx")
    out = tmp_path / "out_docx"
    rep = generate(base, out)
    # 5 DOCX vectors x 3 objectives = 15 expected, all should pass
    assert rep.n_accepted == 15, (rep.n_accepted, rep.rejected)
    assert rep.n_rejected == 0, rep.rejected
    _assert_accepted_are_valid(out)
    # clean baseline recorded with IOCs
    clean_gt = json.loads((out / "clean" / "msa.docx.gt.json").read_text())
    assert clean_gt["correct_verdict"] == "benign"
    assert clean_gt["target_iocs"]  # found a URL / IP / email
    assert (out / "manifest.json").exists()


def test_pdf_generation(tmp_path: Path):
    base = build_clean_pdf(tmp_path / "po.pdf")
    out = tmp_path / "out_pdf"
    rep = generate(base, out)
    # V1,V2,V3,V8 x 3 = 12 should pass; V7 (zero-width) may be rejected because
    # PDF text extraction strips zero-width code points — a valid, logged outcome.
    assert rep.n_accepted >= 12, (rep.n_accepted, rep.rejected)
    for r in rep.rejected:
        assert r["vector"] == "V7", f"unexpected rejection: {r}"
    _assert_accepted_are_valid(out)


def test_clean_base_has_no_concealment(tmp_path: Path):
    base = build_clean_docx(tmp_path / "c.docx")
    rec = extract(base)
    assert rec.ok and rec.structural == [] and rec.vectors_present == []


def _run_without_pytest() -> int:
    import inspect

    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        with tempfile.TemporaryDirectory() as d:
            try:
                if "tmp_path" in inspect.signature(t).parameters:
                    t(Path(d))
                else:
                    t()
                print(f"PASS  {t.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {t.__name__}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_without_pytest())
