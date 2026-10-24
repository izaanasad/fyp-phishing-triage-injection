"""
Extraction pipeline for the document-borne prompt-injection test rig.

Realises FR-1 (ingest and validate PDF/DOCX) and FR-2 (surface visible text,
metadata, and the hidden structural content where injection payloads hide).

Primary entry point:

    from extraction import extract
    record = extract("some_attachment.pdf")
    print(record.summary())
    record.concealed_text()   # everything hidden from the rendered view
"""
from .extract import extract, extract_many
from .records import (
    CHANNEL_VECTORS,
    EncodingFlags,
    ExtractionRecord,
    StructuralSpan,
)
from .validate import detect_file_type, validate

__all__ = [
    "extract",
    "extract_many",
    "ExtractionRecord",
    "StructuralSpan",
    "EncodingFlags",
    "CHANNEL_VECTORS",
    "validate",
    "detect_file_type",
]
