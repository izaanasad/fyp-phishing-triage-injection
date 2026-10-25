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

    import json
    from collections import Counter

    total_a = total_r = 0
    all_accepted: list[str] = []
    all_rejected: list[dict] = []
    per_base: list[dict] = []
    for base in bases:
        try:
            rep = generate(base, out)
        except Exception as exc:  # noqa: BLE001
            print(f"[SKIP] {base}: {exc}")
            continue
        total_a += rep.n_accepted
        total_r += rep.n_rejected
        all_accepted.extend(rep.accepted)
        all_rejected.extend(rep.rejected)
        per_base.append({"base": str(base), "file_type": rep.file_type,
                         "accepted": rep.n_accepted, "rejected": rep.n_rejected})
        print(f"[{rep.file_type}] {Path(base).name}: "
              f"{rep.n_accepted} accepted, {rep.n_rejected} rejected")

    # aggregate manifest across every base document
    rej_by_vector = Counter(r.get("vector") for r in all_rejected)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "manifest.json").write_text(
        json.dumps({
            "n_bases": len(per_base),
            "n_accepted": total_a,
            "n_rejected": total_r,
            "rejected_by_vector": dict(rej_by_vector),
            "per_base": per_base,
            "accepted": all_accepted,
            "rejected": all_rejected,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nTotal: {total_a} accepted, {total_r} rejected  ->  {out}/")
    if rej_by_vector:
        print("Rejected by vector: " + ", ".join(f"{k}={v}" for k, v in sorted(rej_by_vector.items())))
    print(f"Aggregate manifest -> {out}/manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
