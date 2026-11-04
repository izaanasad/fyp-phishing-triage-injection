"""
DOCX sanitisation (FR-6 display semantics + FR-8 channel stripping).

A DOCX has no pixel render without an Office engine, but its *display* is fully
defined by the OOXML spec, so the visible layer can be reconstructed from the
markup. The gateway forwards only the text a reader sees in the body:

  * normal runs and tracked insertions (w:ins)          -> kept
  * hidden runs (w:vanish)                               -> withheld  (V4)
  * tracked deletions (w:del / w:delText)                -> withheld  (V5)
  * comments (word/comments.xml)                         -> withheld  (V6)
  * core/app metadata (docProps/*)                       -> withheld
  * footnotes/endnotes                                   -> not read as body

Kept paragraphs are then screened for encoding deception (FR-7, V7/V8).

This is an INDEPENDENT re-parse of the document: it honours the OOXML display
rules directly and does not import the extraction pipeline's labels. Nothing is
executed (NFR-4) — the zip's XML parts are read as data.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from . import normalize
from .records import DroppedSpan

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_FALSE_VALS = {"false", "0", "off", "no"}


def _q(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _run_is_vanished(run: etree._Element) -> bool:
    rpr = run.find(_q("rPr"))
    if rpr is None:
        return False
    vanish = rpr.find(_q("vanish"))
    if vanish is None:
        return False
    val = vanish.get(_q("val"))
    return val is None or str(val).lower() not in _FALSE_VALS


def _inside_deletion(run: etree._Element) -> bool:
    for _ in run.iterancestors(_q("del")):
        return True
    return False


def _run_text(run: etree._Element) -> str:
    return "".join(t.text or "" for t in run.findall(_q("t")))


def _deleted_text(run: etree._Element) -> str:
    return "".join(t.text or "" for t in run.findall(_q("delText")))


def sanitise_docx(path: Path) -> tuple[str, list[DroppedSpan], list[str]]:
    """Return (sanitised_text, dropped_spans, warnings) for a DOCX."""
    dropped: list[DroppedSpan] = []
    warnings: list[str] = []
    kept_lines: list[str] = []

    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())

        # FR-8: comments are not body text -> withheld whole (V6)
        if "word/comments.xml" in names:
            try:
                root = etree.fromstring(zf.read("word/comments.xml"))
                for comment in root.iter(_q("comment")):
                    text = "".join(t.text or "" for t in comment.iter(_q("t")))
                    if text.strip():
                        dropped.append(DroppedSpan(
                            mechanism="non_body_channel",
                            reason="Word comment is not rendered body text",
                            location=f"comment id={comment.get(_q('id'))}",
                            preview=text[:120], n_chars=len(text)))
            except etree.XMLSyntaxError:
                warnings.append("comments.xml malformed; skipped")

        # FR-8: document metadata -> withheld
        if "docProps/core.xml" in names:
            try:
                root = etree.fromstring(zf.read("docProps/core.xml"))
                for el in root:
                    value = (el.text or "").strip()
                    if value:
                        local = etree.QName(el).localname
                        dropped.append(DroppedSpan(
                            mechanism="non_body_channel",
                            reason="document metadata is not rendered body text",
                            location=f"core.xml/{local}", preview=value[:120],
                            n_chars=len(value)))
            except etree.XMLSyntaxError:
                warnings.append("core.xml malformed; skipped")

        try:
            root = etree.fromstring(zf.read("word/document.xml"))
        except KeyError:
            return "", dropped, ["word/document.xml missing"]

        para_index = 0
        for para in root.iter(_q("p")):
            para_index += 1
            parts: list[str] = []
            for run in para.iter(_q("r")):
                if _inside_deletion(run):          # V5 tracked deletion
                    dt = _deleted_text(run)
                    if dt.strip():
                        dropped.append(DroppedSpan(
                            mechanism="non_body_channel",
                            reason="tracked deletion (w:del) is not in the displayed document",
                            location=f"para {para_index}", preview=dt[:120], n_chars=len(dt)))
                    continue
                if _run_is_vanished(run):          # V4 hidden run
                    ht = _run_text(run)
                    if ht.strip():
                        dropped.append(DroppedSpan(
                            mechanism="render_visibility",
                            reason="hidden run (w:vanish) is not displayed",
                            location=f"para {para_index}", preview=ht[:120], n_chars=len(ht)))
                    continue
                parts.append(_run_text(run))

            line = "".join(parts)
            if not line.strip():
                continue
            # FR-7: visible paragraph, but encoding-deceptive (V7/V8)?
            obf = normalize.obfuscation_reason(line)
            if obf:
                dropped.append(DroppedSpan(
                    mechanism="encoding_deception",
                    reason=f"deceptive character encoding: {obf}",
                    location=f"para {para_index}",
                    preview=normalize.canonicalise(line)[:120], n_chars=len(line)))
                continue
            kept_lines.append(normalize.canonicalise(line))

    return "\n".join(kept_lines).strip(), dropped, warnings
