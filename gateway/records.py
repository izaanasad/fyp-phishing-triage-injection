"""
Data structures for the sanitisation gateway (OBJ-5 / FR-6, FR-7, FR-8).

A GatewayResult is the normalised output of passing one document through the
gateway. `sanitised_text` is the ONLY text the defended triage agent sees: the
reconstruction of what a human reading the rendered document would read, with
every deception channel removed. `dropped` itemises what was withheld and why,
which is the evidence that the gateway acts on channels (not on content) and
that it does not mangle legitimate documents.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class DroppedSpan:
    """One unit of content the gateway withheld from the agent."""

    mechanism: str        # 'render_visibility' | 'non_body_channel' | 'encoding_deception'
    reason: str           # human-readable justification
    location: str = ""    # page / paragraph / field locator
    preview: str = ""     # a short, safe preview of the withheld text
    n_chars: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GatewayResult:
    """Result of sanitising one document."""

    ok: bool
    source_path: str
    file_type: Optional[str] = None       # 'pdf' | 'docx' | None
    error: Optional[str] = None

    sanitised_text: str = ""              # the ONLY text forwarded to the defended agent
    dropped: list[DroppedSpan] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    ocr_used: bool = False                # whether the render-vs-extract OCR check ran
    kept_chars: int = 0
    dropped_chars: int = 0
    latency_s: float = 0.0

    # --- convenience views -------------------------------------------------
    @property
    def by_mechanism(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.dropped:
            out[d.mechanism] = out.get(d.mechanism, 0) + 1
        return out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["by_mechanism"] = self.by_mechanism
        return d

    def summary(self) -> str:
        if not self.ok:
            return f"[GATEWAY ERROR] {self.source_path}: {self.error}"
        lines = [
            f"[SANITISED] {self.source_path}  ({self.file_type})",
            f"  forwarded:   {self.kept_chars} chars",
            f"  withheld:    {self.dropped_chars} chars in {len(self.dropped)} span(s)",
        ]
        for mech, n in sorted(self.by_mechanism.items()):
            lines.append(f"    - {mech}: {n}")
        if self.ocr_used:
            lines.append("  render-vs-extract OCR check: ON")
        for w in self.warnings:
            lines.append(f"  ! {w}")
        return "\n".join(lines)
