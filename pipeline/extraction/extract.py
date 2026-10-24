"""
Extraction entry point (FR-1 + FR-2).

`extract(path)` validates an attachment and returns a single ExtractionRecord.
Invalid or corrupt files produce a record with ok=False and a logged reason
rather than raising (FR-1). A parse failure inside a *valid* file is likewise
captured on the record, not propagated.

CLI:
    python -m extraction <file> [<file> ...] [--json]
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import encoding_scan
from .docx_extractor import extract_docx
from .pdf_extractor import extract_pdf
from .records import ExtractionRecord
from .validate import sha256_of, validate


def extract(path: str | Path) -> ExtractionRecord:
    """Validate and extract one document into an ExtractionRecord."""
    p = Path(path)
    ok, ftype, error = validate(p)
    if not ok:
        return ExtractionRecord(ok=False, source_path=str(p), error=error)

    try:
        size = p.stat().st_size
        digest = sha256_of(p)
    except OSError as exc:
        return ExtractionRecord(ok=False, source_path=str(p), error=f"cannot read file: {exc}")

    try:
        fields = extract_pdf(p) if ftype == "pdf" else extract_docx(p)
    except Exception as exc:  # a valid-but-broken file: record, do not crash (FR-1)
        return ExtractionRecord(
            ok=False,
            source_path=str(p),
            file_type=ftype,
            size_bytes=size,
            sha256=digest,
            error=f"{ftype} extraction failed: {type(exc).__name__}: {exc}",
        )

    flags = encoding_scan.scan(fields["all_extractable_text"])

    return ExtractionRecord(
        ok=True,
        source_path=str(p),
        file_type=ftype,
        size_bytes=size,
        sha256=digest,
        visible_text=fields["visible_text"],
        all_extractable_text=fields["all_extractable_text"],
        metadata=fields["metadata"],
        structural=fields["structural"],
        encoding_flags=flags,
        warnings=fields["warnings"],
    )


def extract_many(paths) -> list[ExtractionRecord]:
    return [extract(p) for p in paths]


def _main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    as_json = "--json" in argv
    if not args:
        print(__doc__)
        return 2
    records = extract_many(args)
    if as_json:
        import json

        print(json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False))
    else:
        for r in records:
            print(r.summary())
            print()
    return 0 if all(r.ok for r in records) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main(sys.argv[1:]))
