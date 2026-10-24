"""
Encoding-level obfuscation detection (surfaces V7 and V8).

The extractor flags these; the sanitisation gateway (FR-7) is what neutralises
them. Detection here is deliberately conservative — it reports suspects, it does
not modify text.
"""
from __future__ import annotations

import unicodedata

from .records import EncodingFlags

# V7 — zero-width / invisible formatting code points commonly used to splice
# instructions into otherwise-visible text.
ZERO_WIDTH = {
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "⁠",  # word joiner
    "﻿",  # zero-width no-break space / BOM
    "­",  # soft hyphen
}

# V8 — a small, high-signal set of Cyrillic/Greek letters that are visually
# confusable with ASCII Latin letters. A fuller confusables table lives in the
# gateway; this is just enough to *flag* homoglyph use at extraction time.
_CONFUSABLE_LATIN = {
    # Cyrillic -> Latin look-alike
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "х": "x", "у": "y", "і": "i", "ѕ": "s", "н": "H",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M",
    "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
    # Greek -> Latin look-alike
    "ο": "o", "α": "a", "ε": "e", "Α": "A", "Β": "B",
    "Ε": "E", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O",
    "Ρ": "P", "Τ": "T", "Χ": "X",
}


def scan(text: str) -> EncodingFlags:
    """Return an EncodingFlags report for `text` without modifying it."""
    flags = EncodingFlags()
    if not text:
        return flags

    for i, ch in enumerate(text):
        if ch in ZERO_WIDTH:
            flags.zero_width_count += 1
            if len(flags.zero_width_positions) < 50:
                flags.zero_width_positions.append(i)

    # Homoglyph heuristic: a confusable code point that appears adjacent to
    # ASCII letters (i.e. inside a word that is otherwise Latin) is a strong
    # signal of substitution, as opposed to genuine Cyrillic/Greek prose.
    seen: set[str] = set()
    for i, ch in enumerate(text):
        if ch in _CONFUSABLE_LATIN:
            prev_ascii = i > 0 and text[i - 1].isascii() and text[i - 1].isalpha()
            next_ascii = i + 1 < len(text) and text[i + 1].isascii() and text[i + 1].isalpha()
            if prev_ascii or next_ascii:
                flags.homoglyph_count += 1
                name = unicodedata.name(ch, "?")
                sample = f"{ch!r} ({name}) -> {_CONFUSABLE_LATIN[ch]!r}"
                if sample not in seen and len(flags.homoglyph_samples) < 25:
                    flags.homoglyph_samples.append(sample)
                    seen.add(sample)
    return flags
