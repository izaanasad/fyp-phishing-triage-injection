"""
Evaluation harness runner (FR-5).

Loads the generated corpus, samples a budgeted subset (stratified by vector x
objective), runs each sampled poisoned variant AND its matched clean baseline
through the triage agent, checkpoints every call (so a long run resumes), and
grades the results into the five metrics.

On CPU-only hardware each call is ~20-40s, so sampling keeps a run tractable:
e.g. 60 variants + their clean baselines ~ 1-1.5 hours.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Optional

from . import grading, metrics

# triage agent lives in pipeline/triage
_PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))


def load_corpus(corpus_dir: Path) -> tuple[list[dict], dict[str, dict]]:
    """Return (poisoned_gts, clean_gt_by_basename)."""
    poisoned = []
    for gt in sorted((corpus_dir / "poisoned").glob("*.gt.json")):
        poisoned.append(json.loads(gt.read_text(encoding="utf-8")))
    clean = {}
    for gt in sorted((corpus_dir / "clean").glob("*.gt.json")):
        d = json.loads(gt.read_text(encoding="utf-8"))
        clean[Path(d["variant_path"]).name] = d
    return poisoned, clean


def sample_variants(poisoned: list[dict], n: Optional[int], seed: int = 0,
                    objectives: Optional[set] = None, vectors: Optional[set] = None,
                    labels: Optional[set] = None) -> list[dict]:
    """Filter then stratified-sample ~n variants across vector x objective cells."""
    pool = [g for g in poisoned
            if (objectives is None or g["objective"] in objectives)
            and (vectors is None or g["vector"] in vectors)
            and (labels is None or g.get("correct_verdict") in labels)]
    if n is None or n >= len(pool):
        return pool
    rng = random.Random(seed)
    cells: dict[tuple, list] = defaultdict(list)
    for g in pool:
        cells[(g["vector"], g["objective"])].append(g)
    for lst in cells.values():
        rng.shuffle(lst)
    # round-robin across cells until we have n
    out, keys = [], list(cells.keys())
    rng.shuffle(keys)
    i = 0
    while len(out) < n and any(cells[k] for k in keys):
        k = keys[i % len(keys)]
        if cells[k]:
            out.append(cells[k].pop())
        i += 1
    return out


def _verdict_dict(v) -> dict[str, Any]:
    return {"classification": v.classification, "iocs": v.iocs, "rationale": v.rationale,
            "denial": v.denial, "latency_s": v.latency_s}


def run(corpus_dir: str | Path, out_dir: str | Path, agent,
        sample: Optional[int] = 60, runs: int = 1, seed: int = 0,
        objectives: Optional[set] = None, vectors: Optional[set] = None,
        labels: Optional[set] = None, progress: Callable[[str], None] = print) -> dict:
    """Run the harness and return the metrics dict. Resumable via results.jsonl."""
    corpus_dir = Path(corpus_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / "results.jsonl"

    poisoned, clean_gts = load_corpus(corpus_dir)
    chosen = sample_variants(poisoned, sample, seed, objectives, vectors, labels)
    bases = {Path(g["base_path"]).name for g in chosen}

    # resume: which (kind, id, run) keys are already recorded
    done: dict[str, dict] = {}
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["key"]] = r

    n_calls = len(bases) + len(chosen) * runs
    progress(f"Sampled {len(chosen)} variants across {len(bases)} base docs "
             f"-> ~{n_calls} model calls (resuming {len(done)} already done)")

    fh = results_path.open("a", encoding="utf-8")

    def record(key, kind, meta, verdict):
        r = {"key": key, "kind": kind, **meta, **_verdict_dict(verdict)}
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.flush()
        done[key] = r
        return r

    # 1) clean baselines (one per base)
    for base in sorted(bases):
        key = f"clean:{base}:0"
        if key in done:
            continue
        clean_path = corpus_dir / "clean" / base
        v = agent.triage_file(clean_path)
        meta = {"base": base, "correct_verdict": clean_gts.get(base, {}).get("correct_verdict")}
        record(key, "clean", meta, v)
        progress(f"  clean  {base}: {v.classification}{' (denial)' if v.denial else ''}")

    # 2) poisoned variants
    for g in chosen:
        for run_idx in range(runs):
            key = f"pois:{g['variant_id']}:{run_idx}"
            if key in done:
                continue
            v = agent.triage_file(g["variant_path"])
            meta = {"variant_id": g["variant_id"], "base": Path(g["base_path"]).name,
                    "vector": g["vector"], "objective": g["objective"], "run_idx": run_idx}
            record(key, "pois", meta, v)
            progress(f"  pois   {g['variant_id']} [{run_idx}]: "
                     f"{v.classification}{' (denial)' if v.denial else ''}")
    fh.close()

    return grade_and_aggregate(corpus_dir, out, chosen)


def grade_and_aggregate(corpus_dir: Path, out: Path, chosen: list[dict]) -> dict:
    """Read results.jsonl, grade poisoned runs against clean baselines, aggregate."""
    poisoned, clean_gts = load_corpus(corpus_dir)
    gt_by_id = {g["variant_id"]: g for g in poisoned}

    records = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    clean_by_base = {r["base"]: r for r in records if r["kind"] == "clean"}
    pois_records = [r for r in records if r["kind"] == "pois"]

    graded = []
    for r in pois_records:
        gt = gt_by_id.get(r["variant_id"])
        if not gt:
            continue
        clean = clean_by_base.get(r["base"])
        if not clean:
            continue
        graded.append(grading.grade(gt, clean, r))

    # clean_results map for accuracy/FPR (carry correct_verdict through)
    clean_results = {b: {**r} for b, r in clean_by_base.items()}

    m = metrics.aggregate(graded, clean_results)
    (out / "graded.jsonl").write_text(
        "\n".join(json.dumps(g, ensure_ascii=False) for g in graded), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    return m
