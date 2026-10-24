# Pipeline — Extraction (FR-1 / FR-2)

Ingests a PDF or DOCX attachment and produces a normalised `ExtractionRecord`
that separates **what a human sees** from **everything a text extractor can
recover**, itemising the concealed channels where document-borne prompt-injection
payloads hide.

This is the foundation layer of the test rig: the corpus generator and the
sanitisation gateway both consume `ExtractionRecord`.

## What it surfaces

| Channel (`ExtractionRecord.structural`) | Vector | Source |
|---|---|---|
| `pdf_low_visibility_spans` | V1, V2 | background-matched colour / sub-visible font (PyMuPDF span colour + size) |
| `pdf_metadata` | V3 | PDF Info/XMP fields |
| `docx_hidden_run` | V4 | `w:vanish` runs |
| `docx_tracked_deletion` | V5 | `w:del` / `w:delText` |
| `docx_comment` | V6 | `word/comments.xml` |
| `pdf_annotations`, `docx_metadata` | — | surfaced for completeness |

Encoding-level obfuscation — **V7** zero-width characters and **V8** homoglyphs —
is reported in `ExtractionRecord.encoding_flags` (detected here; neutralised by
the gateway, FR-7).

## Design notes

- **FR-1 validation** checks extension *and* magic bytes, so a `.pdf` that is not
  a PDF (or a corrupt DOCX zip) is rejected with a logged reason — never a crash.
- **`visible_text` vs `all_extractable_text`** is the render-versus-extract gap:
  `concealed_text()` returns exactly what survives extraction but is not visible.
- **No code execution (NFR-4):** only text/bytes are read; macros, scripts,
  embedded objects and links are never executed or fetched.
- **PDF visibility thresholds** (`pdf_extractor.MIN_VISIBLE_FONT_PT`,
  `NEAR_WHITE_MIN_CHANNEL`) are the operating point the corpus generator's R2
  check must agree with — keep them in sync.

## Usage

```python
from extraction import extract

rec = extract("attachment.docx")
if rec.ok:
    print(rec.visible_text)        # what a reader sees
    print(rec.concealed_text())    # everything hidden from the rendered view
    print(rec.vectors_present)     # e.g. ['V4', 'V6', 'V7']
else:
    print("rejected:", rec.error)
```

CLI:

```bash
python -m extraction attachment.pdf another.docx        # human summary
python -m extraction attachment.pdf --json              # full record as JSON
```

## Tests

```bash
cd code/pipeline
python -m pytest tests/ -q        # or: python tests/test_extraction.py
```

`tests/make_fixtures.py` builds poisoned PDF/DOCX fixtures with a known payload
in every channel; the tests assert each payload is surfaced in `structural`
**and** absent from `visible_text`. These fixtures are the first artefacts for
the project's test-case deliverable.

## Dependencies

`pdfplumber`, `pymupdf`, `python-docx`, `lxml` (all in `code/requirements.txt`).

## Layout

```
pipeline/
  extraction/
    __init__.py        public API: extract(), ExtractionRecord, validate()
    __main__.py        `python -m extraction`
    validate.py        FR-1 ingestion & validation
    records.py         ExtractionRecord / StructuralSpan / channel->vector map
    pdf_extractor.py   FR-2 for PDF  (V1, V2, V3, annotations)
    docx_extractor.py  FR-2 for DOCX (V4, V5, V6, metadata)
    encoding_scan.py   V7 / V8 detection
    extract.py         dispatch + CLI
  tests/
    make_fixtures.py   poisoned fixtures
    test_extraction.py FR-1 + FR-2 tests
```
