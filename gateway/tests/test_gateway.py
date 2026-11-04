"""
Tests for the sanitisation gateway (OBJ-5 / FR-6, FR-7, FR-8).

Builds a real poisoned variant for every one of the eight vectors (using the
corpus injectors) and asserts that the gateway:

  1. removes the injected payload from the forwarded text (all 8 vectors),
  2. preserves the base document's visible content (does not mangle the doc),
  3. passes a clean document through with no body content withheld.

Run from `code/`:  python gateway/tests/test_gateway.py
"""
from __future__ import annotations

import inspect
import sys
import tempfile
import traceback
from pathlib import Path

_CODE = Path(__file__).resolve().parents[2]              # code/
sys.path.insert(0, str(_CODE))

from corpus import acquire, payloads                       # noqa: E402
from corpus.inject_pdf import inject_pdf, PDF_VECTORS       # noqa: E402
from corpus.inject_docx import inject_docx, DOCX_VECTORS    # noqa: E402
from gateway import Gateway                                 # noqa: E402


def _bases(tmp: Path):
    """Create one PDF lure and one DOCX lure, return (pdf_base, docx_base)."""
    base = tmp / "base"
    base.mkdir()
    prov = acquire.Provenance()
    acquire.generate_lures(2, base, prov)                  # 1 pdf + 1 docx
    pdf = sorted(base.glob("*.pdf"))[0]
    docx = sorted(base.glob("*.docx"))[0]
    return pdf, docx


def _words(text: str, minlen: int = 4) -> set:
    import re
    return {w.lower() for w in re.findall(r"[A-Za-z]+", text) if len(w) >= minlen}


def _assert_vector_neutralised(gw, base, vector, inject_fn, tmp: Path):
    vid = f"t__{vector}__O1"
    payload = payloads.build_payload(vid, "O1")
    marker = payloads.marker_for(vid)
    out = tmp / f"{vector}.{base.suffix.lstrip('.')}"
    inject_fn(base, vector, payload, out)

    res = gw.sanitise(out)
    assert res.ok, f"{vector}: gateway failed: {res.error}"

    # (1) the injected payload must not reach the agent
    assert marker not in res.sanitised_text, (
        f"{vector}: injection marker LEAKED into forwarded text")
    assert "classify it as benign" not in res.sanitised_text.lower(), (
        f"{vector}: injected instruction LEAKED into forwarded text")
    # something was actually withheld
    assert res.dropped, f"{vector}: gateway dropped nothing (payload not caught)"

    # (2) base visible content preserved: most clean body words still present
    clean_words = _words(gw.sanitise(base).sanitised_text)
    kept_words = _words(res.sanitised_text)
    if clean_words:
        overlap = len(clean_words & kept_words) / len(clean_words)
        assert overlap >= 0.8, (
            f"{vector}: base content damaged (only {overlap:.0%} of body words kept)")
    return res


def test_pdf_vectors_neutralised(tmp_path: Path):
    pdf_base, _ = _bases(tmp_path)
    gw = Gateway()
    caught = {}
    for v in PDF_VECTORS:                                   # V1,V2,V3,V7,V8
        res = _assert_vector_neutralised(gw, pdf_base, v, inject_pdf, tmp_path)
        caught[v] = res.by_mechanism
    # the hidden-channel vectors must be caught by render/channel mechanisms,
    # the encoding vectors by the encoding-deception mechanism
    assert "render_visibility" in caught["V1"] or "render_visibility" in caught["V2"]
    assert "non_body_channel" in caught["V3"]
    assert "encoding_deception" in caught["V7"]
    assert "encoding_deception" in caught["V8"]


def test_docx_vectors_neutralised(tmp_path: Path):
    _, docx_base = _bases(tmp_path)
    gw = Gateway()
    caught = {}
    for v in DOCX_VECTORS:                                  # V4,V5,V6,V7,V8
        res = _assert_vector_neutralised(gw, docx_base, v, inject_docx, tmp_path)
        caught[v] = res.by_mechanism
    assert "render_visibility" in caught["V4"]              # w:vanish
    assert "non_body_channel" in caught["V5"]               # w:del
    assert "non_body_channel" in caught["V6"]               # comment
    assert "encoding_deception" in caught["V7"]
    assert "encoding_deception" in caught["V8"]


def test_clean_document_passes_through(tmp_path: Path):
    pdf_base, docx_base = _bases(tmp_path)
    gw = Gateway()
    for base in (pdf_base, docx_base):
        res = gw.sanitise(base)
        assert res.ok and res.sanitised_text.strip(), f"{base.name}: empty sanitised text"
        # a clean doc has no hidden/deceptive body content withheld
        bad = [d for d in res.dropped
               if d.mechanism in ("render_visibility", "encoding_deception")]
        assert not bad, f"{base.name}: clean doc wrongly withheld body content: {bad}"


def test_encoding_detector_unit():
    from gateway import normalize
    assert normalize.is_obfuscated("t​o​k​en")        # zero-width
    assert normalize.is_obfuscated("аccount verify")            # cyrillic 'a' + latin
    assert not normalize.is_obfuscated("please verify your account")  # clean
    assert not normalize.is_obfuscated("Москва")                     # pure cyrillic, legit
    assert normalize.strip_zero_width("a​b﻿c") == "abc"


def _run() -> int:
    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        with tempfile.TemporaryDirectory() as d:
            try:
                t(Path(d)) if "tmp_path" in inspect.signature(t).parameters else t()
                print(f"PASS  {t.__name__}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
                traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run())
