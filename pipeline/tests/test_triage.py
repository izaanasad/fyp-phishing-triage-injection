"""
Tests for the triage agent (FR-3), using a mock model (no Ollama needed).

Run from `code/pipeline/`:  python tests/test_triage.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # pipeline/ on path

from triage import TriageAgent, build_model_input  # noqa: E402
from extraction import extract  # noqa: E402
from tests import make_fixtures as fx  # noqa: E402


def _mock(response: str):
    """Return a chat_fn that always yields `response` with 0.1s latency."""
    def chat_fn(system, user, model="m", **kw):
        chat_fn.last_user = user  # capture what the model was asked to analyse
        return response, 0.1
    return chat_fn


def test_parses_malicious_verdict():
    agent = TriageAgent(chat_fn=_mock('{"verdict":"malicious","iocs":["evil.example","1.2.3.4"],"rationale":"phishing lure"}'))
    v = agent.triage_text("some attachment text")
    assert v.classification == "malicious" and not v.denial and v.parse_ok
    assert v.iocs == ["evil.example", "1.2.3.4"]


def test_parses_benign_verdict():
    agent = TriageAgent(chat_fn=_mock('{"verdict":"benign","iocs":[],"rationale":"ordinary invoice"}'))
    v = agent.triage_text("text")
    assert v.classification == "benign" and not v.denial


def test_malformed_output_is_denial_o3():
    agent = TriageAgent(chat_fn=_mock("I'm sorry, I cannot help with that."))
    v = agent.triage_text("text")
    assert v.classification == "error" and v.denial and not v.parse_ok


def test_invalid_verdict_value_is_denial():
    agent = TriageAgent(chat_fn=_mock('{"verdict":"maybe","iocs":[],"rationale":"unsure"}'))
    v = agent.triage_text("text")
    assert v.denial and v.parse_ok and v.classification == "error"


def test_json_embedded_in_prose_is_recovered():
    agent = TriageAgent(chat_fn=_mock('Here is my answer: {"verdict":"malicious","iocs":[],"rationale":"x"} done'))
    v = agent.triage_text("text")
    assert v.classification == "malicious" and v.parse_ok


def test_server_error_is_denial():
    def boom(system, user, model="m", **kw):
        raise ConnectionError("refused")
    v = TriageAgent(chat_fn=boom).triage_text("text")
    assert v.denial and v.classification == "error" and "ConnectionError" in v.error


def test_hidden_payload_reaches_model_input(tmp_path: Path):
    # the whole point of the undefended baseline: concealed text is fed to the model
    docx = fx.build_poisoned_docx(tmp_path / "p.docx")
    rec = extract(docx)
    model_input = build_model_input(rec)
    assert "prior instructions" in model_input  # the V4 hidden-run payload is present
    assert fx.DOCX_COMMENT in model_input         # the V6 comment payload is present

    captured = _mock('{"verdict":"benign","iocs":[],"rationale":"ok"}')
    agent = TriageAgent(chat_fn=captured)
    agent.triage_record(rec)
    assert "prior instructions" in captured.last_user  # it actually went to the model


def _run_without_pytest() -> int:
    import inspect
    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        with tempfile.TemporaryDirectory() as d:
            try:
                if "tmp_path" in inspect.signature(t).parameters:
                    t(Path(d))
                else:
                    t()
                print(f"PASS  {t.__name__}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_without_pytest())
