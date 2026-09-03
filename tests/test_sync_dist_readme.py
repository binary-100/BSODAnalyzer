"""Build hygiene: dist README sync from VERSION.txt."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bsod_analyzer as core
from scripts.sync_dist_readme import render_readme, sync_dist_readme


def test_render_readme_uses_version() -> None:
    text = render_readme("9.9.9")
    assert "v9.9.9" in text
    assert "VERSION.txt" in text


def test_sync_dist_readme_writes_matching_version() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = sync_dist_readme(Path(td))
        readme = out.read_text(encoding="utf-8")
        assert core.VERSION in readme


if __name__ == "__main__":
    test_render_readme_uses_version()
    test_sync_dist_readme_writes_matching_version()
    print("sync_dist_readme tests OK")
