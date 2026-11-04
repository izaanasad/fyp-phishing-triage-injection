"""
CLI for the evaluation harness (FR-5).

Run from `code/`:
  python -m harness --corpus corpus/data/run1 --out harness/out --sample 60
  python -m harness --corpus corpus/data/run1 --out harness/out --objectives O1 --labels malicious
  python -m harness --corpus corpus/data/run1 --out harness/out --regrade     # no model calls

Sampling keeps runs tractable on CPU-only hardware. The run is resumable:
re-running continues from results.jsonl.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import metrics, runner

_PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))


def _set(arg):
    return set(x.strip() for x in arg.split(",")) if arg else None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="harness")
    ap.add_argument("--corpus", default="corpus/data/run1")
    ap.add_argument("--out", default="harness/out")
    ap.add_argument("--sample", type=int, default=60, help="approx variants to run (0 = all)")
    ap.add_argument("--runs", type=int, default=1, help="repeats per variant (variance)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--model", default=None, help="Ollama model (default from env/qwen2.5:3b)")
    ap.add_argument("--objectives", default=None, help="comma list e.g. O1,O2")
    ap.add_argument("--vectors", default=None, help="comma list e.g. V1,V4")
    ap.add_argument("--labels", default=None, help="comma list e.g. malicious,benign")
    ap.add_argument("--regrade", action="store_true", help="re-grade existing results, no model calls")
    ap.add_argument("--gateway", action="store_true",
                    help="DEFENDED run: sanitise every document through the gateway before the agent "
                         "(Pass 2). Use a different --out than the baseline.")
    ap.add_argument("--gateway-ocr", action="store_true",
                    help="with --gateway, also run the OCR render-vs-extract cross-check (needs Tesseract)")
    args = ap.parse_args(argv)

    out = Path(args.out)
    if args.regrade:
        poisoned, _ = runner.load_corpus(Path(args.corpus))
        m = runner.grade_and_aggregate(Path(args.corpus), out, poisoned)
        mode_file = out / "run_mode.txt"
        title = ("Evaluation summary (DEFENDED, gateway ON)"
                 if mode_file.exists() and mode_file.read_text().strip() == "gateway-on"
                 else "Evaluation summary (baseline, undefended)")
        print(metrics.format_summary(m, title))
        return 0

    from triage import TriageAgent, is_available
    from triage.ollama_client import DEFAULT_MODEL

    model = args.model or DEFAULT_MODEL
    if not is_available():
        print("! Ollama not reachable at http://localhost:11434 — start it and pull the model.")
        return 3

    gateway = None
    if args.gateway:
        _CODE = Path(__file__).resolve().parents[1]
        if str(_CODE) not in sys.path:
            sys.path.insert(0, str(_CODE))
        from gateway import Gateway
        gateway = Gateway(use_ocr=args.gateway_ocr)
        mode = "DEFENDED (gateway ON" + (", OCR" if gateway.use_ocr else "") + ")"
        print(f"[{mode}] sanitising every document before the agent sees it.")
    else:
        print("[BASELINE (gateway OFF)] agent reads the raw extraction.")

    agent = TriageAgent(model=model)
    m = runner.run(
        args.corpus, out, agent,
        sample=(None if args.sample == 0 else args.sample),
        runs=args.runs, seed=args.seed,
        objectives=_set(args.objectives), vectors=_set(args.vectors), labels=_set(args.labels),
        gateway=gateway,
    )
    title = ("Evaluation summary (DEFENDED, gateway ON)" if gateway is not None
             else "Evaluation summary (baseline, undefended)")
    print("\n" + metrics.format_summary(m, title))
    print(f"\nmetrics -> {out / 'metrics.json'}   graded -> {out / 'graded.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
