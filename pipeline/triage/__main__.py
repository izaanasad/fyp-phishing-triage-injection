"""
CLI: triage one or more attachments with the local model.

Run from `code/pipeline/`:
    python -m triage attachment.pdf another.docx
    python -m triage attachment.pdf --model qwen2.5:3b --json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .agent import TriageAgent
from .ollama_client import DEFAULT_MODEL, is_available


def _main(argv: list[str]) -> int:
    files = [a for a in argv if not a.startswith("--")]
    model = DEFAULT_MODEL
    if "--model" in argv:
        i = argv.index("--model")
        if i + 1 < len(argv):
            model = argv[i + 1]
            files = [f for f in files if f != model]
    as_json = "--json" in argv
    if not files:
        print(__doc__)
        return 2

    if not is_available():
        print("! Ollama server not reachable at http://localhost:11434")
        print(f"  Start Ollama and pull the model:  ollama pull {model}")
        return 3

    agent = TriageAgent(model=model)
    results = []
    for f in files:
        v = agent.triage_file(f)
        results.append((f, v))

    if as_json:
        print(json.dumps([{"file": f, **v.to_dict()} for f, v in results],
                         indent=2, ensure_ascii=False))
    else:
        for f, v in results:
            print(f"\n{Path(f).name}")
            if v.denial:
                print(f"  verdict:   DENIAL/ERROR (O3)  [{v.error}]")
            else:
                print(f"  verdict:   {v.classification.upper()}")
                print(f"  iocs:      {v.iocs}")
                print(f"  rationale: {v.rationale}")
            print(f"  latency:   {v.latency_s:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
