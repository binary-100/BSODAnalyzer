#!/usr/bin/env python3
"""Refresh shipped WinDbg MSIX fallback version/URL from winget-pkgs GitHub manifest.

Run when tests/test_cdb_online_prompt.py::test_windbg_msix_fallback_not_stale_vs_github fails.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bsod_minidump as md  # noqa: E402


def main() -> None:
    url = md._windbg_msix_url_from_github_manifest()
    ver = md._windbg_latest_version_label()
    if not url or not ver:
        raise SystemExit(
            "Could not fetch WinDbg manifest from GitHub (network or API limit)."
        )
    target = ROOT / "bsod_minidump.py"
    text = target.read_text(encoding="utf-8")
    text, n_ver = re.subn(
        r'^WINDDBG_MSIX_FALLBACK_VERSION = "[^"]+"',
        f'WINDDBG_MSIX_FALLBACK_VERSION = "{ver}"',
        text,
        count=1,
        flags=re.M,
    )
    text, n_url = re.subn(
        r"WINDDBG_MSIX_FALLBACK_URL = \(\s*\n\s*\"[^\"]+\"\s*\n\)",
        f'WINDDBG_MSIX_FALLBACK_URL = (\n    "{url}"\n)',
        text,
        count=1,
    )
    if n_ver != 1 or n_url != 1:
        raise SystemExit("Could not update WINDDBG_MSIX_FALLBACK_* constants in bsod_minidump.py")
    target.write_text(text, encoding="utf-8")
    print(f"Updated WinDbg fallback to {ver}")
    print(url)


if __name__ == "__main__":
    main()
