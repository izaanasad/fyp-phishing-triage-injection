"""
DOCX payload injection for the corpus generator (FR-4).

Applicable DOCX vectors: V4 (w:vanish hidden run), V5 (w:del tracked deletion),
V6 (comment), V7 (zero-width), V8 (homoglyph). Each function writes a poisoned
copy of `base` to `out` by rewriting the OOXML zip, and returns the exact
injected text. Nothing is executed (NFR-4).
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from . import payloads

DOCX_VECTORS = ("V4", "V5", "V6", "V7", "V8")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_COMMENTS_PART = "word/comments.xml"
_CT_PART = "[Content_Types].xml"
_DOC_RELS_PART = "word/_rels/document.xml.rels"
_COMMENTS_CT = (
    '<Override PartName="/word/comments.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>'
)
_COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"


def _read_members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _write_members(out: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _insert_before(xml: str, needle: str, fragment: str) -> str:
    idx = xml.rfind(needle)
    if idx == -1:
        raise ValueError(f"could not find {needle} in document XML")
    return xml[:idx] + fragment + xml[idx:]


def _para_fragment(payload: str, vector: str) -> str:
    text = escape(payload)
    if vector == "V4":  # hidden run
        return (f'<w:p><w:r><w:rPr><w:vanish/></w:rPr>'
                f'<w:t xml:space="preserve">{text}</w:t></w:r></w:p>')
    if vector == "V5":  # tracked-change deletion
        return (f'<w:p><w:del w:id="90001" w:author="corpusgen" w:date="2026-01-01T00:00:00Z">'
                f'<w:r><w:delText xml:space="preserve">{text}</w:delText></w:r></w:del></w:p>')
    if vector in ("V7", "V8"):  # visible (encoding-concealed) run
        return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    raise ValueError(f"no paragraph fragment for vector {vector}")


def _add_comment(members: dict[str, bytes], payload: str) -> None:
    """Add a single comment carrying `payload` (V6), wiring up all parts."""
    cid = "90001"
    text = escape(payload)
    comment_xml = (
        f'<w:comment w:id="{cid}" w:author="corpusgen" w:date="2026-01-01T00:00:00Z">'
        f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p></w:comment>'
    )

    # 1) comments.xml — append to existing, or create new
    if _COMMENTS_PART in members:
        doc = members[_COMMENTS_PART].decode("utf-8")
        members[_COMMENTS_PART] = _insert_before(doc, "</w:comments>", comment_xml).encode("utf-8")
    else:
        members[_COMMENTS_PART] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:comments xmlns:w="{W_NS}">{comment_xml}</w:comments>'
        ).encode("utf-8")

    # 2) document.xml — add a comment reference so the part is valid
    doc_xml = members["word/document.xml"].decode("utf-8")
    ref = f'<w:p><w:r><w:commentReference w:id="{cid}"/></w:r></w:p>'
    members["word/document.xml"] = _insert_before(doc_xml, "</w:body>", ref).encode("utf-8")

    # 3) [Content_Types].xml — ensure the comments override exists
    ct = members[_CT_PART].decode("utf-8")
    if "word/comments.xml" not in ct:
        ct = _insert_before(ct, "</Types>", _COMMENTS_CT)
        members[_CT_PART] = ct.encode("utf-8")

    # 4) document.xml.rels — ensure a relationship to comments.xml exists
    rel = (f'<Relationship Id="rIdCorpusCmt" Type="{_COMMENTS_REL_TYPE}" '
           'Target="comments.xml"/>')
    if _DOC_RELS_PART in members:
        rels = members[_DOC_RELS_PART].decode("utf-8")
        if "comments.xml" not in rels:
            rels = _insert_before(rels, "</Relationships>", rel)
            members[_DOC_RELS_PART] = rels.encode("utf-8")
    else:
        members[_DOC_RELS_PART] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{rel}</Relationships>'
        ).encode("utf-8")


def inject_docx(base: Path, vector: str, payload: str, out: Path) -> str:
    """Inject `payload` into `base` via `vector`, writing to `out`.

    Returns the exact text injected (obfuscated form for V7/V8).
    """
    members = _read_members(base)
    if "word/document.xml" not in members:
        raise ValueError("base DOCX has no word/document.xml")

    injected = payload
    if vector == "V6":
        _add_comment(members, payload)
    else:
        if vector == "V7":  # keep the marker plain so R1 can locate the span
            marker_part, _, rest = payload.partition(" ")
            injected = marker_part + " " + payloads.zero_width_obfuscate(rest)
        elif vector == "V8":
            marker_part, _, rest = payload.partition(" ")
            injected = marker_part + " " + payloads.homoglyph_obfuscate(rest)
        fragment = _para_fragment(injected, vector)
        doc_xml = members["word/document.xml"].decode("utf-8")
        members["word/document.xml"] = _insert_before(doc_xml, "</w:body>", fragment).encode("utf-8")

    _write_members(out, members)
    return injected
