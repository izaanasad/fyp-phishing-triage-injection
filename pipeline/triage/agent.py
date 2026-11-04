"""
Triage agent (FR-3).

Given the text of an attachment, prompts the local model and returns a structured
verdict: classification (benign/malicious enum), extracted IOCs, and a rationale.
Malformed / refused / empty responses are captured as a denial-of-processing
outcome (objective O3) rather than crashing.

`build_model_input` constructs what an UNDEFENDED agent would ingest: everything
the extractor surfaces, concealed channels included — that is exactly how a hidden
payload reaches the model. The defended path feeds sanitised text instead (the
gateway produces it later); the agent itself just triages whatever text it is given.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

from . import prompts
from .ollama_client import DEFAULT_MODEL, chat as _ollama_chat

# allow `extraction` to be imported when run from within pipeline/
_PIPELINE = Path(__file__).resolve().parents[1]
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))


@dataclass
class Verdict:
    classification: str                 # 'benign' | 'malicious' | 'error'
    iocs: list[str] = field(default_factory=list)
    rationale: str = ""
    denial: bool = False                # O3: refusal / malformed / empty
    parse_ok: bool = False
    latency_s: float = 0.0
    model: str = ""
    raw_response: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_model_input(record, max_chars: int = 6000) -> str:
    """Assemble the text an undefended agent ingests from an extraction record.

    Visible text first, then the concealed channels and metadata payloads the
    extractor surfaced — because a standard extraction pipeline passes all of it
    into the prompt. Truncated to `max_chars` to bound context and CPU latency;
    concealed spans are short and are appended so they are not truncated away.
    """
    visible = record.visible_text or ""
    concealed = record.concealed_text() if hasattr(record, "concealed_text") else ""
    budget_visible = visible[: max(0, max_chars - len(concealed) - 2)]
    parts = [budget_visible]
    if concealed:
        parts.append(concealed)
    return "\n".join(p for p in parts if p).strip()


def _extract_json(text: str) -> Optional[dict]:
    """Parse a JSON object from the model output, tolerating stray text."""
    if not text or not text.strip():
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class TriageAgent:
    """LLM-based phishing-triage agent with a fixed prompt (FR-3)."""

    def __init__(self, model: str = DEFAULT_MODEL,
                 chat_fn: Callable[..., tuple[str, float]] = _ollama_chat,
                 max_input_chars: int = 6000):
        self.model = model
        self._chat = chat_fn
        self.max_input_chars = max_input_chars

    def triage_text(self, document_text: str) -> Verdict:
        user = prompts.USER_TEMPLATE.format(document_text=document_text[: self.max_input_chars])
        try:
            raw, latency = self._chat(prompts.SYSTEM_PROMPT, user, model=self.model)
        except Exception as exc:  # server down, timeout, etc.
            return Verdict(classification="error", denial=True, model=self.model,
                           error=f"{type(exc).__name__}: {exc}")

        obj = _extract_json(raw)
        if obj is None:
            # no parseable JSON -> denial of processing (O3)
            return Verdict(classification="error", denial=True, parse_ok=False,
                           latency_s=latency, model=self.model, raw_response=raw,
                           error="model output was not valid JSON")

        verdict = str(obj.get("verdict", "")).strip().lower()
        iocs_raw = obj.get("iocs", [])
        iocs = [str(x) for x in iocs_raw] if isinstance(iocs_raw, list) else []
        rationale = str(obj.get("rationale", ""))

        if verdict not in ("benign", "malicious"):
            # schema present but classification missing/invalid -> O3
            return Verdict(classification="error", iocs=iocs, rationale=rationale,
                           denial=True, parse_ok=True, latency_s=latency,
                           model=self.model, raw_response=raw,
                           error=f"invalid verdict value: {verdict!r}")

        return Verdict(classification=verdict, iocs=iocs, rationale=rationale,
                       denial=False, parse_ok=True, latency_s=latency,
                       model=self.model, raw_response=raw)

    def triage_record(self, record) -> Verdict:
        return self.triage_text(build_model_input(record, self.max_input_chars))

    def triage_file(self, path: str | Path) -> Verdict:
        from extraction import extract
        rec = extract(path)
        if not rec.ok:
            return Verdict(classification="error", denial=True, model=self.model,
                           error=f"extraction failed: {rec.error}")
        return self.triage_record(rec)
