"""
Data structures for the extraction pipeline (FR-2).

An ExtractionRecord is the normalised output of ingesting one attachment. It
separates what a human *sees* (visible_text) from everything a text extractor
can *recover* (all_extractable_text), and itemises the concealed channels where
document-borne injection payloads hide. The render-versus-extract gateway and
the corpus generator both consume this record.

The channel names are stable identifiers; CHANNEL_VECTORS maps each to the
injection vectors (V1-V8) it surfaces, per the locked taxonomy in
`code/corpus/vectors.md`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# Which locked taxonomy vectors each structural channel surfaces.
# (V7/V8 are encoding-level and are reported separately in `encoding_flags`.)
CHANNEL_VECTORS: dict[str, list[str]] = {
    "pdf_low_visibility_spans": ["V1", "V2"],   # background-matched text, sub-visible font
    "pdf_metadata": ["V3"],                       # Info/XMP metadata fields
    "pdf_annotations": [],                         # reserve (FYP-II); surfaced for completeness
    "docx_hidden_run": ["V4"],                    # w:vanish hidden runs
    "docx_tracked_deletion": ["V5"],              # w:del tracked-change deletions
    "docx_comment": ["V6"],                       # w:comment comment text
    "docx_metadata": [],                          # core/app properties (not a locked vector)
}


@dataclass
class StructuralSpan:
    """A single piece of content recovered from a concealed channel."""

    channel: str                      # one of CHANNEL_VECTORS
    text: str                         # the recovered text
    location: str = ""                # human-readable locator (page N, para N, comment id, field)
    attrs: dict[str, Any] = field(default_factory=dict)  # channel-specific detail

    @property
    def vectors(self) -> list[str]:
        return CHANNEL_VECTORS.get(self.channel, [])


@dataclass
class EncodingFlags:
    """Encoding-level obfuscation detected in the extractable text (V7/V8)."""

    zero_width_count: int = 0                       # V7: U+200B/C/D and related
    zero_width_positions: list[int] = field(default_factory=list)
    homoglyph_count: int = 0                         # V8: Cyrillic/Greek look-alikes in ASCII words
    homoglyph_samples: list[str] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return self.zero_width_count > 0 or self.homoglyph_count > 0


@dataclass
class ExtractionRecord:
    """Normalised result of extracting one document (FR-2)."""

    ok: bool
    source_path: str
    file_type: Optional[str] = None       # 'pdf' | 'docx' | None
    size_bytes: int = 0
    sha256: str = ""
    error: Optional[str] = None           # set when ok is False (FR-1 rejection, parse failure)

    visible_text: str = ""                # what a human reading the rendered page would see
    all_extractable_text: str = ""        # everything a text extractor recovers (visible + hidden)
    metadata: dict[str, Any] = field(default_factory=dict)
    structural: list[StructuralSpan] = field(default_factory=list)
    encoding_flags: EncodingFlags = field(default_factory=EncodingFlags)
    warnings: list[str] = field(default_factory=list)

    # --- convenience views -------------------------------------------------
    def spans_for_channel(self, channel: str) -> list[StructuralSpan]:
        return [s for s in self.structural if s.channel == channel]

    def concealed_text(self) -> str:
        """All text that survives extraction but is NOT in the visible layer.

        This is the material a render-versus-extract gateway must catch: the gap
        between all_extractable_text and visible_text.
        """
        return "\n".join(s.text for s in self.structural if s.text.strip())

    @property
    def vectors_present(self) -> list[str]:
        found: set[str] = set()
        for s in self.structural:
            if s.text.strip():
                found.update(s.vectors)
        if self.encoding_flags.zero_width_count:
            found.add("V7")
        if self.encoding_flags.homoglyph_count:
            found.add("V8")
        return sorted(found)

    # --- serialisation -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["vectors_present"] = self.vectors_present
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def summary(self) -> str:
        if not self.ok:
            return f"[REJECTED] {self.source_path}: {self.error}"
        lines = [
            f"[OK] {self.source_path}  ({self.file_type}, {self.size_bytes} bytes)",
            f"  visible_text:        {len(self.visible_text)} chars",
            f"  all_extractable:     {len(self.all_extractable_text)} chars",
            f"  concealed channels:  {len(self.structural)} span(s)",
        ]
        by_channel: dict[str, int] = {}
        for s in self.structural:
            by_channel[s.channel] = by_channel.get(s.channel, 0) + 1
        for ch, n in sorted(by_channel.items()):
            vs = ",".join(CHANNEL_VECTORS.get(ch, [])) or "-"
            lines.append(f"    - {ch}: {n}  [{vs}]")
        if self.encoding_flags.any:
            lines.append(
                f"  encoding: zero-width={self.encoding_flags.zero_width_count} "
                f"homoglyph={self.encoding_flags.homoglyph_count}"
            )
        if self.vectors_present:
            lines.append(f"  vectors present:     {', '.join(self.vectors_present)}")
        if self.warnings:
            lines.append(f"  warnings:            {len(self.warnings)}")
        return "\n".join(lines)
