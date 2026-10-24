"""
DOCX extraction (FR-2).

Office Open XML keeps several categories of text in the file that the default
Word rendering does not show. This extractor parses the underlying XML directly
(python-docx alone does not cleanly separate these) to surface:

  * hidden runs          -> w:vanish            (V4)
  * tracked deletions    -> w:del / w:delText   (V5)
  * comments             -> word/comments.xml   (V6)
  * core/app metadata    -> docProps/*.xml

Visible text is reconstructed from the runs a reader actually sees: normal runs
and tracked *insertions* (w:ins), excluding vanished runs and deleted text.
Nothing in the document is executed (NFR-4).
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .records import StructuralSpan

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DC = "http://purl.org/dc/elements/1.1/"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"

_FALSE_VALS = {"false", "0", "off", "no"}
_META_PAYLOAD_FIELDS = ("title", "subject", "creator", "description", "keywords", "lastModifiedBy")


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _run_is_vanished(run: etree._Element) -> bool:
    rpr = run.find(_q(W, "rPr"))
    if rpr is None:
        return False
    vanish = rpr.find(_q(W, "vanish"))
    if vanish is None:
        return False
    val = vanish.get(_q(W, "val"))
    return val is None or str(val).lower() not in _FALSE_VALS


def _deleting_ancestor(run: etree._Element):
    for anc in run.iterancestors(_q(W, "del")):
        return anc
    return None


def _run_text(run: etree._Element, deleted: bool) -> str:
    tag = "delText" if deleted else "t"
    return "".join(t.text or "" for t in run.findall(_q(W, tag)))


def _parse_metadata(zf: zipfile.ZipFile) -> tuple[dict[str, Any], list[StructuralSpan]]:
    metadata: dict[str, Any] = {}
    spans: list[StructuralSpan] = []
    try:
        raw = zf.read("docProps/core.xml")
    except KeyError:
        return metadata, spans
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError:
        return metadata, spans
    for el in root:
        local = etree.QName(el).localname
        value = (el.text or "").strip()
        if value:
            metadata[local] = value
            if local in _META_PAYLOAD_FIELDS:
                spans.append(
                    StructuralSpan(
                        channel="docx_metadata",
                        text=value,
                        location=f"core.xml/{local}",
                        attrs={"field": local},
                    )
                )
    return metadata, spans


def _parse_comments(zf: zipfile.ZipFile) -> list[StructuralSpan]:
    spans: list[StructuralSpan] = []
    try:
        raw = zf.read("word/comments.xml")
    except KeyError:
        return spans
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError:
        return spans
    for comment in root.iter(_q(W, "comment")):
        text = "".join(t.text or "" for t in comment.iter(_q(W, "t")))
        if not text.strip():
            continue
        spans.append(
            StructuralSpan(
                channel="docx_comment",
                text=text,
                location=f"comment id={comment.get(_q(W, 'id'))}",
                attrs={
                    "author": comment.get(_q(W, "author")),
                    "date": comment.get(_q(W, "date")),
                },
            )
        )
    return spans


def extract_docx(path: Path) -> dict[str, Any]:
    """Return the fields needed to build an ExtractionRecord for a DOCX."""
    warnings: list[str] = []
    structural: list[StructuralSpan] = []
    visible_lines: list[str] = []

    with zipfile.ZipFile(path) as zf:
        metadata, meta_spans = _parse_metadata(zf)
        structural.extend(meta_spans)
        structural.extend(_parse_comments(zf))

        try:
            doc_xml = zf.read("word/document.xml")
        except KeyError:
            return {
                "visible_text": "",
                "all_extractable_text": "",
                "metadata": metadata,
                "structural": structural,
                "warnings": ["word/document.xml missing"],
            }
        root = etree.fromstring(doc_xml)

        para_index = 0
        for para in root.iter(_q(W, "p")):
            para_index += 1
            parts: list[str] = []
            for run in para.iter(_q(W, "r")):
                del_anc = _deleting_ancestor(run)
                if del_anc is not None:
                    text = _run_text(run, deleted=True)
                    if text.strip():
                        structural.append(
                            StructuralSpan(
                                channel="docx_tracked_deletion",
                                text=text,
                                location=f"para {para_index}",
                                attrs={"author": del_anc.get(_q(W, "author"))},
                            )
                        )
                    continue
                text = _run_text(run, deleted=False)
                if not text:
                    continue
                if _run_is_vanished(run):
                    structural.append(
                        StructuralSpan(
                            channel="docx_hidden_run",
                            text=text,
                            location=f"para {para_index}",
                            attrs={"property": "w:vanish"},
                        )
                    )
                else:
                    parts.append(text)
            if parts:
                visible_lines.append("".join(parts))

    visible_text = "\n".join(visible_lines).strip()
    all_text = "\n".join(
        [visible_text] + [s.text for s in structural if s.text.strip()]
    ).strip()

    return {
        "visible_text": visible_text,
        "all_extractable_text": all_text,
        "metadata": metadata,
        "structural": structural,
        "warnings": warnings,
    }
