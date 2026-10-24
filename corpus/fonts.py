"""Locate a Unicode-capable TrueType font for PDF encoding-vector injection.

The encoding vectors (V7/V8) insert Cyrillic confusables / zero-width code
points, which the Base-14 PDF fonts cannot encode. This finds a system font that
covers them, trying common locations on Windows, Linux and macOS. If none is
found the caller falls back gracefully (the variant is validated and rejected
with a logged reason, which is itself a valid FR-4 outcome).
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    # macOS
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


@lru_cache(maxsize=1)
def unicode_font_path() -> Optional[str]:
    for path in _CANDIDATES:
        if os.path.isfile(path):
            return path
    return None
