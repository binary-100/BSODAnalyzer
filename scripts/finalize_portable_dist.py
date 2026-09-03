"""Finalize BSODAnalyzer_v6 for a clean portable flash-drive layout.

Keeps user-visible files minimal:
  BSODAnalyzer.exe
  README.txt
  Run BSODAnalyzer as Administrator.bat
  VERSION.txt
  _internal/               (runtime — hidden on Windows)

Maintenance USB: durable settings, catalog cache, and default exports live on the
**target PC** under %LOCALAPPDATA%\\BSODAnalyzer\\ — not beside the exe on the stick.

Removes duplicate PowerShellModules / DebuggingTools at the distribution root
when the same payloads already live under _internal/.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ADMIN_BAT = r"""@echo off
REM Launch BSOD Analyzer with Administrator rights (recommended for full logs and driver installs).
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0BSODAnalyzer.exe' -Verb RunAs -WorkingDirectory '%~dp0'"
"""


def _hide_dir(path: Path) -> None:
    if not path.is_dir() or sys.platform != "win32":
        return
    try:
        subprocess.run(
            ["attrib", "+H", "+S", str(path)],
            check=False,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        pass


def _rmtree_force(path: Path) -> None:
    """Remove a directory tree including read-only files (legacy build copies)."""

    def _onerror(func, p, _exc_info) -> None:
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    if path.is_dir():
        shutil.rmtree(path, onerror=_onerror)


def clean_stale_root_runtime(
    dist: Path,
    *,
    require_internal: bool = True,
) -> list[str]:
    """Drop legacy root-level runtime folders (old builds copied them beside the exe)."""
    internal = dist / "_internal"
    removed: list[str] = []
    for folder in ("PowerShellModules", "DebuggingTools"):
        root = dist / folder
        if not root.is_dir():
            continue
        if require_internal and not (internal / folder).is_dir():
            continue
        try:
            _rmtree_force(root)
            if not root.exists():
                removed.append(folder)
        except OSError:
            continue
    legacy_portable = dist / "BSODAnalyzer_portable"
    if legacy_portable.is_dir():
        try:
            _rmtree_force(legacy_portable)
            if not legacy_portable.exists():
                removed.append("BSODAnalyzer_portable")
        except OSError:
            pass
    return removed


def finalize_portable_dist(dist_dir: Path | None = None) -> Path:
    dist = dist_dir or (ROOT / "BSODAnalyzer_v6")
    if not dist.is_dir():
        raise SystemExit(f"Distribution folder not found: {dist}")

    removed = clean_stale_root_runtime(dist, require_internal=True)
    internal = dist / "_internal"

    admin_bat = dist / "Run BSODAnalyzer as Administrator.bat"
    admin_bat.write_text(ADMIN_BAT, encoding="utf-8", newline="\r\n")

    if internal.is_dir():
        _hide_dir(internal)

    print(f"Finalized portable layout: {dist}")
    if removed:
        print(f"  Removed legacy folder(s): {', '.join(removed)}")
    print("  Durable data: %LOCALAPPDATA%\\BSODAnalyzer\\ on the PC being serviced")
    return dist


def main(argv: list[str] | None = None) -> int:
    args = list(argv[1:] if argv else [])
    clean_only = False
    if args and args[0] == "--clean-only":
        clean_only = True
        args = args[1:]
    dist = Path(args[0]) if args else None
    target = dist or (ROOT / "BSODAnalyzer_v6")
    if clean_only:
        removed = clean_stale_root_runtime(target, require_internal=False)
        if removed:
            print(f"Removed legacy folder(s): {', '.join(removed)}")
        return 0
    finalize_portable_dist(dist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
