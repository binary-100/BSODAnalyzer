"""VERSION.txt must match bsod_analyzer.VERSION (every run_tests.bat pass)."""

from __future__ import annotations

import re
from pathlib import Path

import bsod_analyzer as core

ROOT = Path(__file__).resolve().parents[1]


def _parse_version_txt(text: str) -> str | None:
    for line in text.splitlines():
        m = re.search(r"Version:\s*(\d+\.\d+\.\d+)", line, re.I)
        if m:
            return m.group(1)
    m = re.search(r"v(\d+\.\d+\.\d+)", text)
    return m.group(1) if m else None


def test_version_matches_version_txt() -> None:
    ver = core.VERSION
    paths = [ROOT / "VERSION.txt"]
    major = ver.split(".")[0]
    dist_ver = ROOT / f"BSODAnalyzer_v{major}" / "VERSION.txt"
    if dist_ver.is_file():
        parsed_dist = _parse_version_txt(dist_ver.read_text(encoding="utf-8"))
        if parsed_dist == ver:
            paths.append(dist_ver)
    for path in paths:
        assert path.is_file(), f"Missing {path.name}"
        parsed = _parse_version_txt(path.read_text(encoding="utf-8"))
        assert parsed == ver, f"{path} has {parsed}, code has {ver}"


if __name__ == "__main__":
    test_version_matches_version_txt()
    print("Version consistency tests OK")
