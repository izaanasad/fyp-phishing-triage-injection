"""
Triage agent for the document-borne prompt-injection test rig (FR-3).

    from triage import TriageAgent
    agent = TriageAgent(model="qwen2.5:3b")
    verdict = agent.triage_file("attachment.pdf")
    print(verdict.classification, verdict.iocs)
"""
from .agent import TriageAgent, Verdict, build_model_input
from .ollama_client import DEFAULT_MODEL, OllamaUnavailable, is_available

__all__ = [
    "TriageAgent",
    "Verdict",
    "build_model_input",
    "DEFAULT_MODEL",
    "OllamaUnavailable",
    "is_available",
]
