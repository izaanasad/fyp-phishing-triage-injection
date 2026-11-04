# Software Requirements Specification

## Document-Borne Prompt Injection Against AI-Assisted Phishing-Triage Agents

| | |
|---|---|
| **Project** | Document-Borne Prompt Injection Against AI-Assisted Phishing-Triage Agents |
| **Category** | Research & Development |
| **Programme** | BS Cybersecurity, FAST-NUCES Karachi |
| **Group leader** | Izaan Ullah Asad (22K-4704) |
| **Supervisor** | Javeria Farooq |
| **Deliverable** | FYP-I — Software Requirements Specification (Task B1) |
| **Document version** | 1.1 (single-model scope update) |
| **Date** | 20 October 2026 |

---

## Revision history

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-10-15 | Izaan Ullah Asad | Initial SRS derived from the approved proposal. |
| 1.1 | 2026-10-20 | Izaan Ullah Asad | Scope reduced to a single locally-hosted model (zero-budget constraint); cross-model comparison deferred to FYP-II (OBJ-7). Updates OBJ-4 references (FR-5, FR-9), overall description, operating environment, interfaces and NFR-2. |

---

## 1. Introduction

### 1.1 Purpose

This document specifies the software requirements for the system built in this Final Year Project. The system is an **experimental test rig and defence**, not a commercial product: its purpose is to measure, under controlled conditions, whether document-borne prompt-injection payloads concealed inside PDF and DOCX attachments can subvert an LLM-based phishing-triage agent, and to design and evaluate a sanitisation gateway that blocks those payloads before they reach the agent.

The requirements below define exactly what the software must do and the conditions under which each requirement is satisfied, so that implementation, testing and evaluation can proceed against an agreed, checkable baseline. The document is the authoritative reference for the functional and non-functional requirements first stated in the approved project proposal; where the proposal stated a requirement in one line, this document expands it into inputs, processing, outputs, priority and an acceptance condition.

### 1.2 Document conventions

- Functional requirements are identified as **FR-n** and non-functional requirements as **NFR-n**, carrying the same numbering as the approved proposal so that traceability is preserved.
- The key words **shall** denotes a mandatory requirement, **should** a recommended one, and **may** an optional one.
- Each functional requirement carries a **priority**: *Core* (required for a defensible FYP-I result), *Required* (needed for completeness), or *Desirable* (improves the deliverable but may be reduced if time is constrained).
- British spelling is used throughout ("sanitisation", "normalise") for consistency with the proposal.

### 1.3 Intended audience and reading order

The document is written for the FYP supervisor and evaluation panel, and for the project team as the implementation reference. Evaluators seeking the scope and context should read Sections 1 and 2; implementers should read Sections 3 to 5; the traceability matrix in Section 7 maps every requirement back to a project objective and to the architecture component that realises it.

### 1.4 Project scope

The system constructs a realistic AI phishing-triage pipeline, generates a labelled corpus of matched clean and poisoned document attachments, measures the pipeline's susceptibility to concealed injection across a fixed taxonomy of eight vectors, and places a render-versus-extract sanitisation gateway in front of the pipeline to measure the reduction in attack success it provides.

**In scope (FYP-I):** PDF and DOCX attachments; eight injection vectors fixed at the outset; three attacker objectives (verdict flipping, indicator omission, denial of processing); **one locally-hosted model served via Ollama** (no paid/hosted API — zero-budget constraint); a corpus of 50–100 base documents yielding 400–800 poisoned variants; the sanitisation gateway and a results dashboard.

**Out of scope:** execution of any live malware or referenced code; attacker objectives beyond the three listed (cross-message context leakage and content fabrication are deferred to FYP-II); vectors beyond the locked eight; **cross-model comparison (deferred to FYP-II, OBJ-7)**; the full false-positive operating-curve evaluation and matrix expansion (FYP-II objectives 6 and 7). No component ever executes code contained in or referenced by a submitted document.

### 1.5 Definitions, acronyms and abbreviations

| Term | Meaning |
|------|---------|
| **Indirect prompt injection** | An attack in which instructions hidden in content consumed by an LLM steer its behaviour, without the attacker interacting with the model directly. |
| **Document-borne** | The injection payload is carried inside a document attachment (PDF or DOCX) rather than in the message body. |
| **Phishing-triage agent** | An LLM-based component that classifies an email and its attachments as benign or malicious and extracts indicators of compromise. |
| **Render-versus-extract** | A detection principle: compare the text a human sees when the document is *rendered* against the text a machine *extracts* from the file; a large discrepancy indicates concealed content. |
| **Vector** | A concealment technique that hides a payload so it survives text extraction but is invisible in the rendered page (the eight are fixed in `corpus/vectors.md`). |
| **Attacker objective** | The outcome the injection seeks: O1 verdict flip, O2 indicator (IOC) omission, O3 denial of processing. |
| **Attack success rate (ASR)** | The fraction of poisoned variants for which the attacker's objective is achieved. |
| **IOC** | Indicator of Compromise (e.g. a URL, domain, hash or address extracted from a document). |
| **Ground truth** | The known-correct verdict and attack intent recorded for every generated sample, enabling mechanical grading. |
| **Gateway** | The sanitisation service placed in front of the triage pipeline. |
| **CUAD / SEC EDGAR** | Public document corpora used as realistic base documents. |

---

## 2. Overall description

### 2.1 Product perspective

The system is a self-contained experimental platform composed of six cooperating components, shown in Figure 1 of the proposal (`Fig1_Architecture.png`):

1. **Ingestion & extraction pipeline** — accepts attachments and extracts text, metadata and structure.
2. **Triage agent** — the LLM-based classifier under test, returning a structured verdict.
3. **Corpus generator** — produces matched clean/poisoned document pairs with machine-checkable ground truth.
4. **Evaluation harness** — runs the corpus through the pipeline and computes the metrics.
5. **Sanitisation gateway** — the render-versus-extract defence, deployable in front of the pipeline.
6. **Results dashboard** — presents attack-success and defence-performance figures.

The system has no external users in production sense; it is operated by the project team to run experiments. It depends on external, publicly available document corpora and on a single locally-hosted LLM (served via Ollama; no paid/hosted API is used in FYP-I).

### 2.2 Product functions (summary)

At a high level the software shall: ingest and parse PDF/DOCX attachments; produce a structured triage verdict; generate labelled clean/poisoned corpora from a declarative vector definition; measure attack success across vector and attacker objective on a single local model with repeated runs; detect render-versus-extract discrepancies and normalise encoding-level obfuscation; operate as a drop-in gateway in front of the pipeline without modifying the agent; and present results in tabular and graphical form.

### 2.3 User classes and characteristics

| User class | Characteristics | Interaction |
|------------|-----------------|-------------|
| **Researcher / operator** (the project team) | Technical; runs experiments, inspects results, tunes the gateway. | Command-line harness and the dashboard. |
| **Supervisor / evaluator** | Reviews results and the dashboard; does not operate the pipeline. | Reads the dashboard and generated reports. |

There is no untrusted end-user: the only documents entering the system are those the team selects or generates.

### 2.4 Operating environment

- **Hardware:** commodity laptop/desktop, no dedicated GPU required (NFR-2).
- **Operating system:** cross-platform (developed on Windows; reproducible via a container image).
- **Runtime:** Python 3.11+; a single locally-hosted model served via Ollama (no hosted/paid API — zero-budget constraint).
- **Key libraries:** `pdfplumber`, `PyMuPDF`, `pypdfium2`, `pdf2image`, `pytesseract`, `python-docx`, an LLM-orchestration library (LangChain / LlamaIndex), `pandas`, `scikit-learn`, and a web framework (FastAPI/Uvicorn) for the gateway service.
- **Reproducibility:** a container image with pinned dependencies and fixed random seeds where the model exposes them (NFR-1).

### 2.5 Design and implementation constraints

- **Single-semester tractability.** The corpus is bounded to 50–100 base documents and 400–800 variants, yielding roughly 1,200–2,400 model invocations (400–800 variants × 1 model × 3 repeated runs, plus clean baselines). The matrix size is a fixed design constraint, not a target to exceed in FYP-I.
- **Zero-budget, single model.** With no API budget, all experiments run against one locally-hosted model via Ollama. This also maximises reproducibility (no external API drift). Cross-model comparison is deferred to FYP-II (OBJ-7).
- **Closed vector list.** The eight injection vectors are fixed at the outset; new vectors discovered mid-project are deferred to FYP-II and are not added to the active experiment.
- **No code execution.** No component may execute code contained in or referenced by a submitted document (NFR-4); payloads are text only.
- **Ethical containment.** All testing is confined to the project's own pipeline using publicly available documents (NFR-6).
- **Agent non-modification.** The gateway must sit in front of the pipeline without altering the triage agent (FR-8), so that measured effects are attributable to the gateway alone.
- **Plagiarism ceiling.** All written documentation must remain within the 15% similarity ceiling; requirement text is original to this document.

### 2.6 Assumptions and dependencies

- Public corpora (CUAD, SEC EDGAR) remain accessible for base-document selection.
- A single locally-hosted model (via Ollama) runs the entire experiment; there is no dependency on any external API being available or affordable.
- Because the team authors every injection, the correct verdict and attack intent are known for all samples, making success mechanically checkable without manual labelling.
- The locally hosted model runs within acceptable latency on commodity hardware for the bounded corpus size.

---

## 3. Functional requirements

Each requirement below expands the one-line statement from the approved proposal. The *Source objective* column links to the objective table in the proposal (OBJ-1…7).

### FR-1 — Accept PDF and DOCX attachments

- **Statement:** The system shall accept PDF and DOCX attachments for analysis.
- **Priority:** Core. **Component:** Ingestion & extraction pipeline. **Source objective:** OBJ-1.
- **Inputs:** A file path or upload of a `.pdf` or `.docx` document.
- **Processing:** Validate the file type and integrity; reject unsupported or corrupt files with a logged reason rather than failing silently.
- **Outputs:** An accepted-document handle passed to extraction, or a logged rejection.
- **Acceptance:** Given a valid PDF or DOCX, the system accepts it; given an unsupported or malformed file, it rejects it with a recorded reason and does not crash.

### FR-2 — Extract text, metadata and structural content

- **Statement:** The system shall extract text, metadata and structural content from submitted documents.
- **Priority:** Core. **Component:** Ingestion & extraction pipeline. **Source objective:** OBJ-1.
- **Inputs:** An accepted document.
- **Processing:** Extract the visible text layer, document metadata (PDF Info/XMP; DOCX core/app properties), and structural content (DOCX comments, tracked changes, hidden runs; PDF annotations and content-stream text). The extractor must surface content that is present in the file but not shown in the default rendered view, since that is precisely where payloads hide.
- **Outputs:** A normalised extraction record: `{ visible_text, metadata{...}, structural_content{...} }`.
- **Acceptance:** For a document carrying a payload in any of the eight vectors, the extracted record contains the payload text (confirming the "survives extraction" property, rule R1).

### FR-3 — Return a structured triage verdict

- **Statement:** The triage agent shall return a structured verdict comprising classification, extracted indicators and a rationale.
- **Priority:** Core. **Component:** Triage agent. **Source objective:** OBJ-1.
- **Inputs:** The extraction record from FR-2.
- **Processing:** Prompt the LLM-based agent to classify the document and extract IOCs, under a fixed prompt template held constant across the experiment.
- **Outputs:** A structured verdict `{ classification: benign|malicious, iocs: [...], rationale: text, confidence? }` in a machine-parseable schema (e.g. JSON).
- **Acceptance:** Every run yields a schema-valid verdict; a malformed model output is detected and recorded as a parse failure rather than silently mislabelled.

### FR-4 — Generate matched clean/poisoned pairs

- **Statement:** The corpus generator shall produce matched clean and poisoned document pairs given a technique and an attacker objective.
- **Priority:** Core. **Component:** Corpus generator. **Source objective:** OBJ-3.
- **Inputs:** A base document, a vector (V1–V8) and an attacker objective (O1–O3).
- **Processing:** Produce a poisoned variant differing from the clean document only by the injected span, parameterised by exactly one vector and one objective. Validate each variant against R1 (payload survives extraction) and R2 (payload invisible when rendered); a variant failing either is rejected and logged, not kept. Record ground truth (correct verdict, targeted IOC, injected span) alongside each file.
- **Outputs:** A clean/poisoned file pair plus a ground-truth record per variant.
- **Acceptance:** For 50–100 base documents the generator yields 400–800 validated variants; every retained variant passes R1 and R2 and carries complete ground truth.

### FR-5 — Compute attack success rate with variance

- **Statement:** The evaluation harness shall compute attack success rate per technique and attacker objective on the configured model, with variance across repeated runs.
- **Priority:** Core. **Component:** Evaluation harness. **Source objective:** OBJ-4.
- **Inputs:** The labelled corpus, a model identifier (a single locally-hosted model in FYP-I), and a repeat count.
- **Processing:** Submit each variant through the pipeline, grade the verdict mechanically against ground truth, and tally the five metrics (attack success rate, verdict-flip rate, IOC-omission rate, false-positive rate, runtime). Run key experiments three times to report variance. Record all raw outputs for audit. The model is passed as a parameter so that additional models can be added in FYP-II (OBJ-7) without altering the harness.
- **Outputs:** A results table broken down by vector × attacker objective, with mean and spread.
- **Acceptance:** Given the corpus and the single local model with three repeats on key experiments, the harness produces the complete metric breakdown and variance without manual grading.

### FR-6 — Detect render-versus-extract discrepancy

- **Statement:** The sanitisation gateway shall detect content present in the extracted text layer but absent from the rendered page.
- **Priority:** Core. **Component:** Sanitisation gateway. **Source objective:** OBJ-5.
- **Inputs:** A submitted document.
- **Processing:** Rasterise the document and OCR the rendered image to obtain the human-visible text; extract the machine-readable text layer; diff the two. A discrepancy beyond a configured threshold flags concealed content. Strip or quarantine the concealed span before the document reaches the agent.
- **Outputs:** A gateway decision `{ flagged: bool, discrepancy_score, removed_spans[...] }` and a sanitised document.
- **Acceptance:** Documents carrying any visual- or structural-concealment vector (V1–V6) are flagged; a clean document produces a discrepancy below threshold and passes unflagged.

### FR-7 — Normalise encoding-level obfuscation

- **Statement:** The gateway shall normalise encoding-level obfuscation including zero-width characters and homoglyphs.
- **Priority:** Core. **Component:** Sanitisation gateway. **Source objective:** OBJ-5.
- **Inputs:** Extracted text (which render-versus-extract alone will not catch, since these vectors can be visible yet misparsed).
- **Processing:** Remove zero-width code points (U+200B/U+200C/U+200D and related); map confusable/homoglyph code points (Cyrillic/Greek look-alikes) to their canonical ASCII form via a Unicode confusables table; re-check the normalised text for injected instructions.
- **Outputs:** Normalised text plus a record of substitutions made.
- **Acceptance:** For variants using V7 (zero-width) and V8 (homoglyph), the payload is neutralised after normalisation and no longer parses as an instruction.

### FR-8 — Deployable as a drop-in gateway

- **Statement:** The gateway shall be deployable in front of the triage pipeline without modification to the agent.
- **Priority:** Required. **Component:** Sanitisation gateway. **Source objective:** OBJ-5.
- **Inputs:** The same attachment stream the pipeline consumes.
- **Processing:** Expose the gateway as a service (HTTP API) that the pipeline calls before triage; the agent's code and prompt remain unchanged whether the gateway is present or bypassed.
- **Outputs:** A sanitised document (or a block decision) handed to the unmodified pipeline.
- **Acceptance:** The same experiment runs with the gateway enabled and disabled through configuration only, with no change to the agent, so that measured differences are attributable to the gateway.

### FR-9 — Present results in tabular and graphical form

- **Statement:** The dashboard shall present attack success rates and defence performance in tabular and graphical form.
- **Priority:** Required. **Component:** Results dashboard. **Source objective:** OBJ-4 / OBJ-6.
- **Inputs:** The harness results (with and without the gateway).
- **Processing:** Aggregate metrics by vector and attacker objective; render tables and charts comparing baseline attack success against post-gateway attack success, and show the false-positive cost alongside.
- **Outputs:** A dashboard view and exportable figures for the report.
- **Acceptance:** A reader can see, for each vector and objective, the attack-success rate before and after the gateway and the associated false-positive rate.

---

## 4. External interface requirements

### 4.1 User interfaces

- **Command-line harness.** Operators configure a run (corpus path, model, repeat count, gateway on/off) and launch it from the command line; progress and the metric summary are printed and written to a results file.
- **Results dashboard.** A read-only view (local web page or notebook) presenting the tables and charts of FR-9.

### 4.2 Software interfaces

- **Local model** via the Ollama runtime (local HTTP endpoint). This is the only model used in FYP-I; a hosted-API adapter is a FYP-II extension (OBJ-7).
- **Document libraries:** `pdfplumber`/`PyMuPDF`/`pypdfium2` (PDF), `python-docx` (DOCX), `pdf2image`+`pytesseract` (rasterise + OCR for the gateway).
- **Gateway API:** an HTTP service (FastAPI) accepting a document and returning the sanitised document and decision record.

### 4.3 Hardware interfaces

None beyond a commodity host; no dedicated accelerator is required (NFR-2).

### 4.4 Communications interfaces

Local loopback HTTP only — between the pipeline, the gateway, and the locally-hosted model. No outbound model traffic is required; the system runs fully offline for inference. (Base-document download from public corpora is a one-off, out-of-band step.)

---

## 5. Non-functional requirements

### NFR-1 — Reproducibility
All experiments shall be re-runnable from a container image with fixed random seeds where the model exposes them.
**Acceptance:** A clean checkout built into the container image reproduces a reported result table (within model-nondeterminism variance) with no manual setup beyond documented commands.

### NFR-2 — Portability
The system shall run on commodity hardware without dedicated accelerators, using a single locally-hosted model (served via Ollama) and no paid or hosted API, so that the entire experiment reproduces at zero cost.
**Acceptance:** The full pipeline and a corpus run complete on a standard laptop/desktop with no GPU and no external API access.

### NFR-3 — Performance
The gateway shall process a typical document within a time budget compatible with automated triage.
**Acceptance:** Median per-document gateway processing time is recorded and reported; it stays within a stated budget (target: seconds, not minutes) for a typical document in the corpus.

### NFR-4 — Safety
No component shall execute code contained in, or referenced by, a submitted document.
**Acceptance:** A review of every component confirms payloads are handled strictly as text; no macro, script, embedded object or referenced URL is ever executed or fetched for execution.

### NFR-5 — Maintainability
Injection techniques shall be defined declaratively so new vectors can be added without altering the harness.
**Acceptance:** Adding a (future) vector is a change to the declarative vector definition (`corpus/vectors.md` and the generator's vector table) and its generator handle only; the harness and grading code are untouched.

### NFR-6 — Ethical containment
All testing shall be confined to the project's own pipeline using publicly available documents.
**Acceptance:** No external system is targeted; all base documents come from public corpora; the ethics statement (Task A5) documents containment.

---

## 6. Other requirements

### 6.1 Data requirements
- Base documents are drawn from CUAD and SEC EDGAR (public). Between 50 and 100 are selected to represent realistic lures (invoices, contracts, statements).
- Every generated variant stores its ground truth: correct verdict, targeted IOC, injected span, vector ID and objective ID.
- Corpus and generated data are excluded from version control (repository `.gitignore`); only the generator and vector definitions are tracked, so the corpus is regenerated deterministically rather than stored.

### 6.2 Documentation requirements
Project documentation comprises this SRS, the design documentation, test cases and bug reports, and the final report. All written material stays within the 15% plagiarism ceiling and is drafted in the team's own words at reading time.

---

## 7. Requirements traceability matrix

| Requirement | Proposal objective | Architecture component | Attacker objective exercised | Vectors exercised | Priority |
|-------------|--------------------|------------------------|------------------------------|-------------------|----------|
| FR-1 | OBJ-1 | Ingestion & extraction | — | — | Core |
| FR-2 | OBJ-1 | Ingestion & extraction | — | V1–V8 (R1 check) | Core |
| FR-3 | OBJ-1 | Triage agent | O1, O2, O3 | — | Core |
| FR-4 | OBJ-3 | Corpus generator | O1, O2, O3 | V1–V8 | Core |
| FR-5 | OBJ-4 | Evaluation harness | O1, O2, O3 | V1–V8 | Core |
| FR-6 | OBJ-5 | Sanitisation gateway | O1, O2, O3 | V1–V6 | Core |
| FR-7 | OBJ-5 | Sanitisation gateway | O1, O2, O3 | V7, V8 | Core |
| FR-8 | OBJ-5 | Sanitisation gateway | — | — | Required |
| FR-9 | OBJ-4 / OBJ-6 | Results dashboard | O1, O2, O3 | V1–V8 | Required |
| NFR-1 | Cross-cutting | All | — | — | Core |
| NFR-2 | Cross-cutting | All | — | — | Required |
| NFR-3 | OBJ-5/6 | Sanitisation gateway | — | — | Required |
| NFR-4 | Cross-cutting | All | — | — | Core |
| NFR-5 | OBJ-2 | Corpus generator / harness | — | V1–V8 | Required |
| NFR-6 | Cross-cutting | All | — | — | Core |

**Coverage check:** every FYP-I objective (OBJ-1…5) is realised by at least one functional requirement, and every functional requirement traces to an objective. No requirement introduces capability beyond the approved scope.

---

*Vector definitions referenced throughout are fixed in `code/corpus/vectors.md` (eight vectors, locked 2026-10-13). This SRS is the source of the requirements chapter of the design documentation and feeds the methodology chapter (Chapter 3) of the mid-term report.*
