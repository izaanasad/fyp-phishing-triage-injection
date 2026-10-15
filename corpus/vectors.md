# Injection Vector Taxonomy — LOCKED

**Status:** Locked by group agreement, 2026-10-13. **Closed list.**
Newly discovered vectors go to FYP-II — they are NOT added here mid-experiment.
This file is the single source of truth the corpus generator codes against (Objective 2 / Task A2).

Each vector satisfies two validation rules, both of which MUST be re-verified in code for every generated sample:
- **R1 — survives extraction:** the payload is recoverable by a standard text extractor (pdfplumber / PyMuPDF / python-docx).
- **R2 — invisible when rendered:** the payload is not visible to a human reading the rendered page / default document view.

Categories (used for the Chapter 3 taxonomy grouping): **Visual concealment**, **Document structure**, **Character encoding**.

---

## The 8 locked vectors

| ID | Vector | Format | Category | Concealment mechanism | Implementation handle |
|----|--------|--------|----------|-----------------------|-----------------------|
| V1 | Background-matched text | PDF | Visual | Text drawn in the page background colour (e.g. white on white); present in the content stream, unreadable to the eye. | Add text run with fill colour == page background (reportlab / PyMuPDF insert_text with white colour). |
| V2 | Sub-visible font size | PDF | Visual | Text set at ~0.5–1 pt; in the text layer, too small to read. | Insert text at fontsize 0.75 pt. |
| V3 | Metadata fields | PDF | Structural | Payload placed in document Info / XMP fields (Title, Subject, Keywords, Author); never rendered, routinely extracted and passed to the model. | Set PDF metadata dict (PyMuPDF `set_metadata`). |
| V4 | Hidden-text attribute (`w:vanish`) | DOCX | Structural | Word "hidden" run property; stored in document.xml, not shown in the default view. | Set run property `<w:vanish/>` (python-docx: run.font.hidden = True). |
| V5 | Tracked-change deletion | DOCX | Structural | Text wrapped in `<w:del>` — "deleted" with track-changes, still in the XML, absent from the clean rendered view. | Inject `<w:del><w:r><w:delText>…` into document.xml. |
| V6 | Comment text | DOCX | Structural | Payload in a document comment; comment text lives in comments.xml even when comments are hidden/collapsed. | Add comment part + reference (docx comment helper). |
| V7 | Zero-width characters | PDF + DOCX | Encoding | Zero-width space/joiner (U+200B/U+200D) splice an instruction into otherwise-visible text; renders as nothing. | Interleave U+200B between payload glyphs, or append a ZW-delimited span. |
| V8 | Homoglyph substitution | PDF + DOCX | Encoding | Look-alike Unicode characters (Cyrillic/Greek) carry a payload that parses differently from how it reads. | Map ASCII → confusable codepoints in the injected span. |

**Balance:** 3 PDF-specific (V1–V3), 3 DOCX-specific (V4–V6), 2 cross-format encoding (V7–V8).
**Coverage:** Visual (V1–V2) · Structural (V3–V6) · Encoding (V7–V8).

---

## Variant-generation contract (for the corpus generator)

For each base document and each applicable vector, the generator produces one poisoned variant per (vector × attacker-objective) pair. Attacker objectives in scope (FYP-I):
- **O1 — verdict flip** (malicious → benign)
- **O2 — IOC omission** (drop extracted indicators from the output)
- **O3 — denial of processing** (jam the agent so it returns no usable verdict)

Every generated variant MUST be validated against R1 and R2 at creation time; a variant failing either is rejected and logged, not silently kept. Ground truth (correct verdict, which IOC the attack targets, the injected span) is recorded alongside each file so the harness can grade mechanically.

---

## Held in reserve — NOT in the locked 8 (FYP-II candidates)

- Off-page positioning (PDF): text outside the printable margin.
- Text beneath an image in z-order (PDF).
- Footnotes / endnotes / text boxes (DOCX).
- Image alt-text (DOCX).
- Gradient-optimised / cryptic trigger payloads (out of scope — needs white-box access).

---

## Decision-log entry to paste into `08_Decision_Log.md`

```
## 2026-10-13 — 8 injection vectors locked (closed list)

**Decided:** the injection-vector taxonomy is fixed at 8 vectors — V1 background-matched
text (PDF), V2 sub-visible font (PDF), V3 metadata fields (PDF), V4 w:vanish hidden text
(DOCX), V5 tracked-change deletion (DOCX), V6 comment text (DOCX), V7 zero-width
characters (both), V8 homoglyph substitution (both). Full spec in corpus/vectors.md.

**Why:** balanced across both formats and the three concealment categories (visual,
structural, encoding); all buildable with pdfplumber/PyMuPDF/python-docx; all satisfy
survives-extraction + invisible-when-rendered. Closing the list before implementation
prevents scope creep — the single most likely failure mode.

**Reverses if:** a locked vector proves impossible to realise reliably against R1/R2,
in which case it is swapped for a reserve vector (off-page positioning or z-order) and
this entry is amended — the count stays at 8.

**Also recorded 2026-10-13:** Deliverable II mid-term report follows the Research
structure, Chapters 1–3 (Introduction, Literature Review, Methodology) — to be confirmed
in writing by supervisor Javeria Farooq.
```
