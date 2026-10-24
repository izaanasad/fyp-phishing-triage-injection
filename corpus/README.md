# Corpus — Generator (FR-4)

Takes a clean base document and produces matched **clean + poisoned** variants
across the locked **V1–V8** taxonomy and the **O1–O3** attacker objectives,
validating every poisoned variant against rules **R1/R2** with the extraction
pipeline, and recording machine-checkable **ground truth**.

Reuses `pipeline/extraction` for validation — generate a variant, extract it,
confirm the payload survives extraction (R1) and is concealed (R2).

## What a run produces

```
<out>/
  clean/<base>.<ext>            + <base>.<ext>.gt.json   (verdict: benign, target IOCs)
  poisoned/<base>__<Vx>_<Oy>.<ext> + .gt.json            (verdict: malicious, ground truth)
  rejected/<...>                                          (variants that failed R1/R2)
  manifest.json                                           (accepted + rejected lists)
  rejections.log                                          (one JSON line per rejection)
```

Applicable vectors by format: **PDF** → V1, V2, V3, V7, V8 · **DOCX** → V4, V5, V6, V7, V8.
So each base yields up to 5 vectors × 3 objectives = **15 poisoned variants** + 1 clean.

## Ground truth (per poisoned variant)

`correct_verdict` (malicious), `target_iocs` (what a faithful agent should still
extract — for measuring O2), `injected_text` (exact span, obfuscated form for
V7/V8), `injected_text_normalized`, `vector`, `objective`, `concealment_class`,
and the `r1_pass` / `r2_pass` results. The clean baseline carries the benign
verdict and the same IOC set.

## R1 / R2 validation (concealment-class aware)

Every variant carries a plain-text **marker** so validation is exact.

| Class | Vectors | R1 (survives extraction) | R2 (concealed) |
|---|---|---|---|
| visual / structural | V1–V6 | marker in extracted text | marker **not** in visible text |
| encoding | V7, V8 | marker in extracted text | obfuscation present (zero-width / homoglyph) |

> **Methodology note (reflect in Chapter 3 / `vectors.md`):** for the encoding
> vectors V7/V8 the concealment is at the **character-encoding level**, not the
> visual level — the glyphs are on the page, but the token sequence the model
> ingests differs from its apparent ASCII form. R2 for these is therefore
> defined as "obfuscation is present and the normalised form is the intended
> instruction," distinct from the pixel-invisibility of V1–V6. A variant that
> cannot satisfy its rule is **rejected and logged** (a valid FR-4 outcome — e.g.
> if a renderer strips zero-width code points, V7 for that format is reported as
> unrealisable rather than silently kept).

## Usage

```python
from corpus import generate
report = generate("base.docx", out_dir="data/run1")
print(report.n_accepted, "accepted,", report.n_rejected, "rejected")
```

CLI (run from `code/`):

```bash
python -m corpus path/to/base.pdf path/to/base.docx --out data/run1
```

## Tests

```bash
cd code
python corpus/tests/test_corpus.py        # or: python -m pytest corpus/tests -q
```

The tests build clean base documents, generate the full set, and re-validate
every accepted variant's R1/R2 independently — exercising both the accept and
the reject-and-log paths.

## Base documents

The generator runs on any valid PDF/DOCX. For the real experiment, point it at
CUAD contracts and SEC EDGAR filings (50–100 base documents → 400–800 variants).
Generated output belongs under `corpus/data/` (git-ignored); only the generator
and `vectors.md` are version-controlled, so the corpus is regenerated
deterministically rather than stored.

## Dependencies

`pymupdf`, `lxml`, plus the extraction pipeline's deps. A Unicode-capable system
font (Arial on Windows, DejaVuSans on Linux) is used for PDF encoding vectors;
`fonts.py` locates it, and absence is handled by rejecting those variants.

## Layout

```
corpus/
  __init__.py        public API: generate(), GroundTruth, GenerationReport
  __main__.py        `python -m corpus`
  payloads.py        objectives, obfuscation (V7/V8), IOC detection
  fonts.py           cross-platform Unicode font discovery
  inject_pdf.py      V1, V2, V3, V7, V8 injection
  inject_docx.py     V4, V5, V6, V7, V8 injection
  generator.py       orchestration + R1/R2 validation + ground truth
  vectors.md         the locked taxonomy (source of truth)
  tests/test_corpus.py
```
