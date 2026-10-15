# Document-Borne Prompt Injection Against AI-Assisted Phishing-Triage Agents

FYP-I (Fall 2026) · BS Cybersecurity · FAST-NUCES, Karachi
Supervisor: Javeria Farooq

**Team**
- Izaan Ullah Asad (22K-4704) — threat model, injection taxonomy, corpus generator, render-vs-extract defence
- Momina (22P-9338) — requirements, extraction/ingestion pipeline, triage agent, gateway service
- Bharti (22K-4832) — design, baseline validation, evaluation harness, results dashboard

## What this is
A study of whether hidden-text prompt injection in document attachments can defeat an AI phishing-triage
agent, plus a sanitisation gateway that stops it. We build a realistic triage pipeline (a test rig, not a
product), manufacture a labelled corpus of matched clean/poisoned attachments, measure attack success,
then build and evaluate a render-vs-extract defence on both attack reduction and false-positive cost.

## Repository layout
| Folder | Contents |
|---|---|
| `pipeline/` | Triage pipeline: extraction, chunk/embed, LLM agent, verdict |
| `corpus/`   | Locked 8-vector taxonomy (`vectors.md`) + corpus generator; `data/` is git-ignored |
| `gateway/`  | Sanitisation gateway (render-vs-extract + normalisation) |
| `harness/`  | Evaluation harness + the five metrics + QA artefacts |
| `report/`   | Report chapter working copies + test log |
| `evidence/` | Submission receipts, screenshots, result snapshots |

## Setup
```
python -m venv .venv
# Windows:  .venv\Scripts\activate
source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
# local model:
ollama pull llama3.1
```

## Ground rules
- The 8 injection vectors are LOCKED (`corpus/vectors.md`). New vectors go to FYP-II, not this list.
- The pipeline is a measurement test rig. Do not turn it into a "good" phishing detector — that is scope creep.
- No live malware is ever executed. Payloads are text only.
- Commit small and often. Never commit `corpus/data/` (large) or `.env` (secrets).
- Write the report and test log continuously, not at the end.

## Key dates (Fall 2026)
- Mid-term evaluation: 6–8 Nov · Final report: 15–26 Dec · Final defense: 28 Dec–12 Jan
