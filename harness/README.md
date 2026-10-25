# Harness — Evaluation (FR-5)

Runs the generated corpus through the triage agent, grades every poisoned
variant against its ground truth **and its matched clean baseline**, and
aggregates the five project metrics. This is the component that produces the
Chapter 4 numbers.

## Metrics

| Metric | Meaning |
|---|---|
| **ASR** | overall attack success rate (objective achieved) |
| **VFR** (O1) | verdict flip malicious→benign, over intrinsically-malicious (lure) bases the agent caught at baseline |
| **IOR / O2 ASR** (O2) | ground-truth IOCs the clean run extracted but the poisoned run omitted (differential) |
| **O3 ASR** | poisoned run fails to produce a usable verdict (denial) while the clean run succeeded |
| **runtime** | per-document latency |
| clean accuracy / agent FPs | baseline: are clean lures classified malicious and clean contracts benign? (precursor to the gateway's FPR) |

Grading is **matched-pair differential** (clean vs poisoned for the same base),
which isolates the injection's effect from the model's baseline behaviour.

## Usage (run from `code/`)

```bash
# a tractable first run (~budgeted sample); resumable
python -m harness --corpus corpus/data/run1 --out harness/out --sample 40

# focus on verdict flips: O1 on the malicious lures
python -m harness --corpus corpus/data/run1 --out harness/out --objectives O1 --labels malicious --sample 0

# re-grade existing results without any model calls
python -m harness --corpus corpus/data/run1 --out harness/out --regrade
```

- `--sample N` keeps the run tractable on CPU-only hardware (0 = all). At ~25s/call,
  40 variants + their clean baselines ≈ 25–40 min.
- `--runs R` repeats each variant R times for variance (report on key cells).
- The run is **resumable**: every call is checkpointed to `results.jsonl`; re-running
  continues where it stopped.
- `--vectors`, `--objectives`, `--labels` filter the sample.

## Outputs (`harness/out/`)

- `results.jsonl` — every model call (clean + poisoned), the raw record (resume log).
- `graded.jsonl` — per-variant grading.
- `metrics.json` — the aggregated metric tables.
- summary table printed to the console.

## Tests

```bash
cd code
python harness/tests/test_harness.py     # mock vulnerable model; no Ollama needed
```

## Layout

```
harness/
  __init__.py     public API: run(), grade(), aggregate()
  __main__.py     CLI
  runner.py       load corpus, sample, run agent, checkpoint/resume
  grading.py      matched-pair grading per objective
  metrics.py      aggregate -> ASR/VFR/IOR/O3/runtime tables
  tests/test_harness.py
```

## Note

FPR in the formal sense (clean documents the **gateway** wrongly flags) is
produced once the sanitisation gateway exists and the harness is run with the
gateway enabled vs bypassed. Until then this reports the triage agent's baseline
attack rates and clean-document accuracy.
