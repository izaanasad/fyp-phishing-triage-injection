# Pipeline — Triage Agent (FR-3)

The LLM-based phishing-triage agent under test. Given the text extracted from an
attachment, it returns a structured verdict: **classification** (benign/malicious
enum), **extracted IOCs**, and a **rationale**. Runs against a local model via
Ollama; deterministic decoding for reproducibility (NFR-1); no paid API (NFR-2).

## Design (matches Chapter 3)

- **Fixed baseline prompt** (`prompts.py`), held constant across all experiments.
  It is the *undefended* prompt — no "ignore embedded instructions" guard, because
  the defence being measured is the gateway, not prompt hardening. Adding a guard
  here would understate the vulnerability.
- **Hybrid output**: `verdict` is an enum (structural resistance to direct
  override, per Watchtower); `iocs`/`rationale` are free text (the O2-vulnerable
  path). Enforced via Ollama's JSON format mode.
- **O3 handling**: output that is not valid JSON, is empty, a refusal, or carries
  an invalid verdict is recorded as a **denial** (`Verdict.denial = True`), not a
  crash — that is the measurable denial-of-processing outcome.
- **Undefended input** (`build_model_input`): feeds everything the extractor
  surfaces, concealed channels included — which is exactly how a hidden payload
  reaches the model. The defended run will feed gateway-sanitised text instead.
- **Input truncated** (default 6000 chars) to bound context and CPU latency;
  concealed spans are appended so truncation never drops them.

## Usage

```python
from triage import TriageAgent
agent = TriageAgent(model="qwen2.5:3b")
v = agent.triage_file("attachment.pdf")        # extracts, then triages (undefended)
print(v.classification, v.iocs, v.denial, f"{v.latency_s:.1f}s")
```

CLI (run from `code/pipeline/`):

```bash
python -m triage attachment.pdf another.docx            # human-readable
python -m triage attachment.pdf --model qwen2.5:3b --json
```

The agent is model-agnostic — set `OLLAMA_MODEL` / `OLLAMA_HOST` env vars or pass
`model=` to target any pulled model.

## Prerequisites

Install Ollama (ollama.com/download) and pull a model sized for your hardware:

```bash
ollama pull qwen2.5:3b      # ~2 GB; good on an 8 GB CPU-only laptop
```

On CPU-only hardware each call takes ~20–40 s, so the evaluation harness samples a
budgeted subset rather than running all 849 variants × 3 — see the harness module.

## Tests

```bash
cd code/pipeline
python tests/test_triage.py        # uses a mock model; no Ollama required
```

## Layout

```
triage/
  __init__.py        public API: TriageAgent, Verdict
  __main__.py        `python -m triage <file>`
  prompts.py         fixed baseline system prompt + verdict schema
  ollama_client.py   stdlib HTTP client for a local Ollama server
  agent.py           TriageAgent, Verdict, build_model_input
```
