"""
Tests for the extraction pipeline (FR-1, FR-2).

Run from `code/pipeline/`:
    python -m pytest tests/ -q
or without pytest:
    python tests/test_extraction.py

The core property under test (FR-2): for every injection channel, the payload
must appear in the extracted structural content AND must NOT appear in the
visible text — the render-versus-extract gap the gateway later exploits.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `extraction` importable

from extraction import extract, validate  # noqa: E402
from tests import make_fixtures as fx  # noqa: E402


# ---------------------------------------------------------------------------
# FR-1 — validation / ingestion
# ---------------------------------------------------------------------------
def test_rejects_missing_file():
    rec = extract("/no/such/file.pdf")
    assert not rec.ok and "does not exist" in rec.error


def test_rejects_unsupported_extension(tmp_path: Path):
    p = tmp_path / "note.txt"
    p.write_text("hello")
    rec = extract(p)
    assert not rec.ok and "unsupported extension" in rec.error


def test_rejects_mislabelled_file(tmp_path: Path):
    p = tmp_path / "fake.pdf"
    p.write_bytes(b"this is not a pdf")
    rec = extract(p)
    assert not rec.ok and "does not match file contents" in rec.error


def test_rejects_empty_file(tmp_path: Path):
    p = tmp_path / "empty.docx"
    p.write_bytes(b"")
    rec = extract(p)
    assert not rec.ok


# ---------------------------------------------------------------------------
# FR-2 — PDF extraction surfaces hidden content (V1, V2, V3)
# ---------------------------------------------------------------------------
def test_pdf_surfaces_hidden_and_hides_it_from_visible(tmp_path: Path):
    pdf = fx.build_poisoned_pdf(tmp_path / "p.pdf")
    rec = extract(pdf)
    assert rec.ok and rec.file_type == "pdf"

    # visible text contains the visible line, not the concealed payloads
    assert "invoice" in rec.visible_text.lower()
    assert fx.PDF_WHITE not in rec.visible_text          # V1 excluded from visible
    assert fx.PDF_TINY not in rec.visible_text           # V2 excluded from visible

    # concealed payloads are surfaced in structural channels
    low_vis = " ".join(s.text for s in rec.spans_for_channel("pdf_low_visibility_spans"))
    assert fx.PDF_WHITE in low_vis                         # V1 surfaced
    assert fx.PDF_TINY in low_vis                          # V2 surfaced
    meta = " ".join(s.text for s in rec.spans_for_channel("pdf_metadata"))
    assert fx.PDF_META_SUBJECT in meta                     # V3 surfaced

    # taxonomy vectors detected
    assert {"V1", "V2", "V3"}.issubset(set(rec.vectors_present))
    # everything hidden is recoverable (R1)
    assert fx.PDF_WHITE in rec.concealed_text()


# ---------------------------------------------------------------------------
# FR-2 — DOCX extraction surfaces hidden content (V4, V5, V6) + encoding (V7, V8)
# ---------------------------------------------------------------------------
def test_docx_surfaces_hidden_and_hides_it_from_visible(tmp_path: Path):
    docx = fx.build_poisoned_docx(tmp_path / "d.docx")
    rec = extract(docx)
    assert rec.ok and rec.file_type == "docx"

    assert "agreement" in rec.visible_text.lower()
    # none of the concealed payloads leak into the visible layer
    assert "ignore" not in rec.visible_text.lower()       # V4 vanish excluded
    assert fx.DOCX_DEL not in rec.visible_text             # V5 deletion excluded
    assert fx.DOCX_COMMENT not in rec.visible_text         # V6 comment excluded

    hidden = " ".join(s.text for s in rec.spans_for_channel("docx_hidden_run"))
    assert "prior instructions" in hidden                  # V4 surfaced
    deletion = " ".join(s.text for s in rec.spans_for_channel("docx_tracked_deletion"))
    assert fx.DOCX_DEL in deletion                          # V5 surfaced
    comment = " ".join(s.text for s in rec.spans_for_channel("docx_comment"))
    assert fx.DOCX_COMMENT in comment                       # V6 surfaced
    meta = " ".join(s.text for s in rec.spans_for_channel("docx_metadata"))
    assert fx.DOCX_TITLE in meta                            # metadata surfaced

    # encoding-level obfuscation flagged (the vanish payload carries them)
    assert rec.encoding_flags.zero_width_count >= 1        # V7
    assert rec.encoding_flags.homoglyph_count >= 1         # V8
    assert {"V4", "V5", "V6", "V7", "V8"}.issubset(set(rec.vectors_present))


def test_clean_docx_has_no_concealed_content(tmp_path: Path):
    # a document with only a visible paragraph should surface nothing hidden
    import zipfile

    p = tmp_path / "clean.docx"
    body = '<w:p><w:r><w:t xml:space="preserve">Just a normal paragraph.</w:t></w:r></w:p>'
    document = fx._docx_part(body)
    ct = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("[Content_Types].xml", ct)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    rec = extract(p)
    assert rec.ok
    assert rec.structural == []
    assert rec.vectors_present == []
    assert "normal paragraph" in rec.visible_text.lower()


def _run_without_pytest() -> int:
    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        with tempfile.TemporaryDirectory() as d:
            try:
                import inspect

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
