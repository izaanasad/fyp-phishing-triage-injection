# Gateway — Sanitisation (OBJ-5 / FR-6, FR-7, FR-8)

The project's **contribution**: a render-vs-extract gateway that screens an
attachment *before* the LLM triage agent reads it, forwarding only the text a
human reading the rendered document would read. Document-borne prompt injection
depends on a payload that the agent ingests but a human never sees; the gateway
closes that gap by construction.

## The principle

> Forward only what the rendered document shows a reader. Content that is in the
> file but **not** on the page a human sees, or that is on the page only by means
> of **deceptive character encoding**, is a deception channel — withhold it.

This is independent of the attack: the gateway re-derives visibility from the
document itself. It does **not** read the corpus ground truth or the extraction
pipeline's concealment labels, so it is not a mirror of the injector — it would
catch concealment methods the injector never produced.

## Three mechanisms → the eight vectors

| Mechanism | What it does | Vectors caught |
|---|---|---|
| **FR-6 render-vs-extract** | forward only spans/runs that paint visibly (PDF: font size ≥ 4pt, colour contrast vs white, non-transparent; DOCX: not `w:vanish`) | V1 white text, V2 sub-visible font, V4 hidden run |
| **FR-8 channel stripping** | never forward content that isn't rendered body text (PDF metadata & annotations; DOCX comments, tracked deletions `w:del`, core/app metadata) | V3 metadata, V5 tracked deletion, V6 comment |
| **FR-7 encoding normalisation** | withhold visible runs that use zero-width splicing or Latin+Cyrillic/Greek mixed-script confusable tokens | V7 zero-width, V8 homoglyph |

V7/V8 are the subtle case: they render visibly, so FR-6 keeps them — FR-7 is
what catches them, by detecting the *technique* (not the meaning). Pure foreign
text (e.g. a genuinely Cyrillic word) is **not** flagged; only Latin tokens
laced with look-alikes, the homoglyph signature.

> Design note — the gateway de-obfuscates and **withholds** V7/V8 spans rather
> than normalising-and-forwarding them. Forwarding a de-obfuscated instruction
> would hand the attacker a cleaner payload; a span that relies on deceptive
> encoding is treated as untrusted, like a hidden run.

## Optional: OCR render-vs-extract cross-check

`render_diff.py` provides the gold-standard form — rasterise each PDF page, OCR
it, and confirm the forwarded text matches what the pixels show. It needs
Tesseract + `pytesseract` + `Pillow`; when absent the gateway runs on the
span-attribute path and records a warning. Enable with `Gateway(use_ocr=True)`
or `--gateway-ocr`.

## Usage

```python
from gateway import Gateway
gw = Gateway()
res = gw.sanitise("doc.pdf")
agent.triage_text(res.sanitised_text)   # feed ONLY this to the defended agent
print(res.summary())                     # what was withheld, and why
```

CLI (from `code/`):

```bash
python -m gateway <file-or-dir>              # show withheld channels
python -m gateway <file> --show-text         # also print forwarded text
python -m gateway <dir> --quiet              # one line per document
```

Defended evaluation (Pass 2) — same corpus, same agent, same prompt, gateway on:

```bash
python -m harness --corpus corpus/data/run1 --out harness/out_gw --gateway --sample 80
```

Compare `harness/out/metrics.json` (baseline) with `harness/out_gw/metrics.json`
(defended): the fall in ASR / VFR is the defence result.

## Tests

```bash
cd code
python gateway/tests/test_gateway.py     # per-vector neutralisation + clean pass-through
python harness/tests/test_harness.py     # end-to-end: gateway defeats a fully-compliant model
```

## Layout

```
gateway/
  __init__.py        public API: Gateway, GatewayResult
  gateway.py         orchestration (dispatch by type, assemble sanitised text)
  pdf_sanitizer.py   FR-6/FR-8 for PDF (render visibility + metadata/annotation strip)
  docx_sanitizer.py  FR-6/FR-8 for DOCX (OOXML display semantics + channel strip)
  normalize.py       FR-7 encoding-deception detection + normalisation
  render_diff.py     optional OCR render-vs-extract cross-check
  records.py         GatewayResult / DroppedSpan
  __main__.py        CLI
  tests/test_gateway.py
```
