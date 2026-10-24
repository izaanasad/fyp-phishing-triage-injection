"""
File ingestion and validation (FR-1).

The system shall accept PDF and DOCX attachments and reject unsupported or
corrupt files with a logged reason rather than failing silently. Validation
checks both the extension and the file's magic bytes, so a `.pdf` that is not a
PDF (or a `.docx` that is not a valid Office Open XML zip) is rejected.

No file content is executed at any point (NFR-4): validation only reads bytes.
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Optional

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
# A DOCX is a zip that must contain these members.
_DOCX_REQUIRED_MEMBERS = ("[Content_Types].xml", "word/document.xml")


class ValidationError(Exception):
    """Raised internally when a file fails FR-1 validation."""


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _looks_like_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            head = fh.read(1024)
    except OSError:
        return False
    # Some PDFs have leading whitespace/BOM before the header.
    return _PDF_MAGIC in head[:1024]


def _looks_like_docx(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            if fh.read(4) != _ZIP_MAGIC:
                return False
    except OSError:
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            return all(member in names for member in _DOCX_REQUIRED_MEMBERS)
    except (zipfile.BadZipFile, OSError):
        return False


def detect_file_type(path: Path) -> Optional[str]:
    """Return 'pdf', 'docx', or None based on extension AND magic bytes."""
    ext = path.suffix.lower()
    if ext == ".pdf" and _looks_like_pdf(path):
        return "pdf"
    if ext == ".docx" and _looks_like_docx(path):
        return "docx"
    return None


def validate(path: str | Path) -> tuple[bool, Optional[str], Optional[str]]:
    """Validate an input file for ingestion.

    Returns (ok, file_type, error). On success error is None; on failure
    file_type is None and error explains why, so callers can log it (FR-1).
    """
    p = Path(path)
    if not p.exists():
        return False, None, f"file does not exist: {p}"
    if not p.is_file():
        return False, None, f"not a regular file: {p}"
    try:
        size = p.stat().st_size
    except OSError as exc:
        return False, None, f"cannot stat file: {exc}"
    if size == 0:
        return False, None, "file is empty"
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return False, None, f"unsupported extension '{ext}' (only .pdf and .docx are accepted)"
    ftype = detect_file_type(p)
    if ftype is None:
        return False, None, f"extension '{ext}' does not match file contents (corrupt or mislabelled)"
    return True, ftype, None
