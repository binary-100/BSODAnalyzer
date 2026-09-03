"""Product line helpers — version from VERSION.txt beside source or frozen exe."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_MODULE_ROOT = Path(__file__).resolve().parent


def _parse_version_txt(text: str) -> str | None:
    for line in text.splitlines():
        m = re.search(r"Version:\s*(\d+\.\d+\.\d+)", line, re.I)
        if m:
            return m.group(1)
    m = re.search(r"v(\d+\.\d+\.\d+)", text)
    return m.group(1) if m else None


def _version_txt_path() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "VERSION.txt")
    candidates.extend(
        (
            _MODULE_ROOT / "VERSION.txt",
            _MODULE_ROOT / "BSODAnalyzer_v6" / "VERSION.txt",
        )
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def product_version() -> str:
    path = _version_txt_path()
    if path is not None:
        try:
            parsed = _parse_version_txt(path.read_text(encoding="utf-8"))
        except OSError:
            parsed = None
        if parsed:
            return parsed
    return "0.0.0"


def product_major() -> int:
    head = (product_version().split(".")[0] or "0").strip()
    try:
        return int(head)
    except ValueError:
        return 0


def is_v6_line() -> bool:
    """True when building/running BSOD Analyzer v6.x (catalog overhaul and related work)."""
    return product_major() >= 6
