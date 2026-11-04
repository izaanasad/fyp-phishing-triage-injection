"""
Encoding-deception detection and normalisation for the gateway (FR-7).

Two of the eight vectors do not hide the payload from the rendered page at all:
they place it in a VISIBLE run but disguise it at the character-encoding level so
a casual reader (and naive keyword filters) skim past it:

  * V7 — zero-width characters spliced between letters (`t​o​k​en`)
  * V8 — Latin letters swapped for visually identical Cyrillic/Greek glyphs
          (`аccount` where the first char is U+0430, not 'a')

The render-vs-extract filter (FR-6) cannot catch these because they DO render.
This module detects the *technique* — not the meaning — on the principle that
legitimate business prose does not rely on zero-width splicing or mixed-script
confusable tokens. Content that does is treated as a deception channel and
withheld, exactly as a hidden run would be.

Detection is deliberately independent of the corpus generator: it keys on
structural signals (zero-width code points; Latin+Cyrillic/Greek inside one
token) rather than on the specific substitution table the injector used, so it
generalises to confusables the injector never produced. Pure non-Latin text
(e.g. a genuinely Cyrillic word) is NOT flagged — only Latin tokens laced with
look-alikes, which is the signature of a homoglyph attack.
"""
from __future__ import annotations

import re
import unicodedata

# Zero-width / invisible formatting code points used to splice text (V7) and
# related format characters that have no business inside running prose.
ZERO_WIDTH = {
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "⁠",  # word joiner
    "﻿",  # BOM / zero-width no-break space
    "­",  # soft hyphen
    "᠎",  # Mongolian vowel separator
}

# Unicode blocks whose letters are routinely used as Latin look-alikes (V8).
_CYRILLIC = (0x0400, 0x04FF)
_GREEK = (0x0370, 0x03FF)
_LATIN_RE = re.compile(r"[A-Za-z]")


def _in(cp: int, block: tuple[int, int]) -> bool:
    return block[0] <= cp <= block[1]


def strip_zero_width(text: str) -> str:
    """Remove zero-width / invisible formatting characters."""
    return "".join(ch for ch in text if ch not in ZERO_WIDTH)


def has_zero_width(text: str) -> bool:
    return any(ch in ZERO_WIDTH for ch in text)


def _token_is_mixed_script(token: str) -> bool:
    """True if a token mixes Latin letters with Cyrillic/Greek look-alikes.

    That mix is the homoglyph signature. A purely Cyrillic or purely Greek token
    (legitimate foreign text) is not flagged.
    """
    has_latin = bool(_LATIN_RE.search(token))
    if not has_latin:
        return False
    for ch in token:
        cp = ord(ch)
        if _in(cp, _CYRILLIC) or _in(cp, _GREEK):
            return True
    return False


def has_mixed_script(text: str) -> bool:
    return any(_token_is_mixed_script(tok) for tok in text.split())


def obfuscation_reason(text: str) -> str | None:
    """Return a reason string if `text` uses an encoding-deception technique."""
    reasons = []
    if has_zero_width(text):
        n = sum(text.count(z) for z in ZERO_WIDTH)
        reasons.append(f"zero-width characters ({n})")
    bad = [t for t in text.split() if _token_is_mixed_script(t)]
    if bad:
        reasons.append(f"mixed-script confusable tokens ({len(bad)})")
    return "; ".join(reasons) if reasons else None


def is_obfuscated(text: str) -> bool:
    return obfuscation_reason(text) is not None


def canonicalise(text: str) -> str:
    """Hygiene applied to kept text: strip zero-width, NFKC-normalise.

    This neutralises residual invisible characters in otherwise-legitimate text.
    It does NOT fold homoglyphs (a confusable-laced token is withheld whole by
    the deception filter, not silently rewritten and forwarded — forwarding a
    de-obfuscated instruction would hand the attacker a cleaner payload).
    """
    return unicodedata.normalize("NFKC", strip_zero_width(text))
