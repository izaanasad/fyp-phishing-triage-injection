"""
Minimal Ollama HTTP client for the triage agent (FR-3).

Talks to a locally-running Ollama server (default http://localhost:11434) via its
/api/chat endpoint, using deterministic decoding (temperature 0, fixed seed) and
JSON-format output so the verdict schema parses reliably. No third-party
dependencies — stdlib urllib only (NFR-2: runs offline on commodity hardware).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")

# Deterministic decoding for reproducibility (NFR-1); bounded output for speed
# on CPU-only hardware (NFR-2/NFR-3).
DEFAULT_OPTIONS = {"temperature": 0, "seed": 0, "num_predict": 384}


class OllamaUnavailable(RuntimeError):
    """Raised when the Ollama server cannot be reached."""


def chat(system: str, user: str, model: str = DEFAULT_MODEL,
         host: str = DEFAULT_HOST, options: dict | None = None,
         timeout: float = 600.0) -> tuple[str, float]:
    """Send a system+user chat and return (assistant_text, latency_seconds).

    Raises OllamaUnavailable if the server is unreachable (e.g. not started or
    the model not pulled).
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
        "options": {**DEFAULT_OPTIONS, **(options or {})},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/chat", data=data,
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise OllamaUnavailable(
            f"cannot reach Ollama at {host} ({exc}). Is it running, and is the "
            f"model '{model}' pulled? Try: ollama run {model} \"ok\""
        ) from exc
    elapsed = time.perf_counter() - start
    content = (body.get("message") or {}).get("content", "")
    return content, elapsed


def is_available(host: str = DEFAULT_HOST, timeout: float = 5.0) -> bool:
    """Quick check that an Ollama server is up (GET /api/tags)."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False
