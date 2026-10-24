"""CLI: python -m corpus <base.pdf|base.docx> [...] --out <dir>"""
from __future__ import annotations

import sys
from pathlib import Path

from .generator import generate


def _main(argv: list[str]) -> int:
    bases = [a for a in argv if not a.startswith("--")]
    out = "corpus_out"
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = argv[i + 1]
            bases = [b for b in bases if b != out]
    if not bases:
        print(__doc__)
        return 2

    total_a = total_r = 0
    for base in bases:
        try:
            rep = generate(base, out)
        except Exception as exc:  # noqa: BLE001
            print(f"[SKIP] {base}: {exc}")
            continue
        total_a += rep.n_accepted
        total_r += rep.n_rejected
        print(f"[{rep.file_type}] {Path(base).name}: "
              f"{rep.n_accepted} accepted, {rep.n_rejected} rejected")
        for r in rep.rejected:
            print(f"    - rejected {r['variant_id']}: {r['reason']}")
    print(f"\nTotal: {total_a} accepted, {total_r} rejected  ->  {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
