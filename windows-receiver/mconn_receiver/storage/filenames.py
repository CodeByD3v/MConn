"""Filename safety (DESIGN.md section 6). The phone's name is untrusted input."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_NAME = 200
MAX_EXT = 50


def sanitize_filename(name: str, max_len: int = MAX_NAME) -> str:
    """Return a safe Windows base name. Never returns an empty string or a path."""
    name = unicodedata.normalize("NFC", name or "")
    name = name.replace("\\", "/").split("/")[-1]       # base name only
    name = _ILLEGAL.sub("_", name).strip(" ").rstrip(" .")  # Windows forbids trailing dots/spaces
    if not name:
        return "file"
    stem, ext = os.path.splitext(name)
    if len(ext) > MAX_EXT:
        ext = ext[:MAX_EXT]
    stem = stem.rstrip(" .") or "file"
    if stem.split(".")[0].upper() in _RESERVED:         # CON, CON.tar, NUL.txt ...
        stem = "_" + stem
    stem = stem[: max(1, max_len - len(ext))].rstrip(" .") or "file"
    return stem + ext


def resolve_conflict(directory: Path, name: str) -> Path:
    """Never overwrite: 'a.zip' -> 'a (1).zip' -> 'a (2).zip' ..."""
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem, ext = os.path.splitext(name)
    n = 1
    while True:
        candidate = directory / f"{stem} ({n}){ext}"
        if not candidate.exists():
            return candidate
        n += 1
