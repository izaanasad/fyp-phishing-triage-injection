"""
CLI for the sanitisation gateway (OBJ-5).

Run from `code/`:

    # sanitise one document and show what a human sees vs what was withheld
    python -m gateway corpus/data/run1/poisoned/lure_00__V1__O1.pdf

    # a whole directory, summary only
    python -m gateway corpus/data/run1/poisoned --quiet

    # turn on the OCR render-vs-extract cross-check (needs Tesseract)
    python -m gateway some.pdf --ocr --show-text
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import Gateway


def _iter_docs(target: Path):
    if target.is_dir():
        yield from sorted(p for p in target.rglob("*")
                          if p.suffix.lower() in (".pdf", ".docx", ".docm"))
    else:
        yield target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gateway", description="render-vs-extract sanitisation gateway")
    ap.add_argument("target", help="a document or a directory of documents")
    ap.add_argument("--ocr", action="store_true", help="enable the OCR render-vs-extract cross-check (PDF)")
    ap.add_argument("--show-text", action="store_true", help="print the forwarded (sanitised) text")
    ap.add_argument("--quiet", action="store_true", help="one line per document")
    args = ap.parse_args(argv)

    target = Path(args.target)
    if not target.exists():
        print(f"not found: {target}", file=sys.stderr)
        return 2

    gw = Gateway(use_ocr=args.ocr)
    if args.ocr and not gw.use_ocr:
        print("! OCR requested but toolchain unavailable; running span-attribute path\n", file=sys.stderr)

    n = 0
    for doc in _iter_docs(target):
        n += 1
        res = gw.sanitise(doc)
        if args.quiet:
            mech = ", ".join(f"{k}={v}" for k, v in sorted(res.by_mechanism.items())) or "nothing dropped"
            print(f"{doc.name}: kept {res.kept_chars}c / withheld {res.dropped_chars}c  [{mech}]")
            continue
        print(res.summary())
        for d in res.dropped:
            print(f"      · [{d.mechanism}] {d.location}: {d.reason}")
            if d.preview:
                print(f"          withheld: {d.preview!r}")
        if args.show_text:
            print("    --- forwarded text ---")
            print("    " + res.sanitised_text.replace("\n", "\n    "))
        print()

    if n == 0:
        print("no .pdf/.docx documents found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
