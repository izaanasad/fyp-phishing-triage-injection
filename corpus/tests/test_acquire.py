"""
Offline tests for base-document acquisition (corpus/acquire.py).

Only the network-free parts are tested here — HTML cleanup, text->PDF rendering,
and CUAD zip/folder extraction. The EDGAR download path requires internet and
SEC's User-Agent policy, so it is exercised by running it on a real machine, not
in CI.

Run from `code/`:  python corpus/tests/test_acquire.py
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymupdf  # noqa: E402

from corpus import acquire  # noqa: E402


def test_html_to_text_strips_markup_and_scripts():
    html = ("<html><head><style>a{}</style></head><body><h1>Master &amp; Co</h1>"
            "<p>Clause one.</p><script>evil()</script></body></html>")
    txt = acquire.html_to_text(html)
    assert "Master & Co" in txt
    assert "Clause one." in txt
    assert "evil()" not in txt
    assert "<h1>" not in txt and "<p>" not in txt


def test_text_to_pdf_is_valid_and_extractable(tmp_path: Path):
    out = acquire.text_to_pdf(
        "SERVICES AGREEMENT\n\nThis contract is between A and B.\n" * 60,
        tmp_path / "t.pdf", title="Doc",
    )
    doc = pymupdf.open(out)
    assert doc.page_count >= 1
    assert "SERVICES AGREEMENT" in doc.load_page(0).get_text()
    doc.close()


def test_acquire_cuad_from_zip(tmp_path: Path):
    # build a fake CUAD bundle with 3 contract PDFs
    pdfs = []
    for i in range(3):
        p = tmp_path / f"c{i}.pdf"
        acquire.text_to_pdf(f"CONTRACT {i}\n\nThis Agreement is dated 2026.", p, title=f"Contract {i}")
        pdfs.append(p)
    zpath = tmp_path / "CUAD_v1.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for i, p in enumerate(pdfs):
            zf.write(p, arcname=f"full_contract_pdf/Part_I/contract_{i}.pdf")

    out = tmp_path / "base"
    prov = acquire.Provenance()
    n = acquire.acquire_cuad(zpath, 10, out, prov)
    assert n == 3
    assert len(list(out.glob("*.pdf"))) == 3
    assert len(prov.items) == 3 and all(it["source"] == "cuad" for it in prov.items)


def test_acquire_cuad_from_folder(tmp_path: Path):
    src = tmp_path / "cuad_extracted"
    src.mkdir()
    acquire.text_to_pdf("CONTRACT A", src / "a.pdf", title="A")
    acquire.text_to_pdf("CONTRACT B", src / "b.pdf", title="B")
    out = tmp_path / "base"
    prov = acquire.Provenance()
    n = acquire.acquire_cuad(src, 1, out, prov)  # cap at 1
    assert n == 1 and len(list(out.glob("*.pdf"))) == 1


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
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_without_pytest())
