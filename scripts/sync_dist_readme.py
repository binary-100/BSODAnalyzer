"""Generate BSODAnalyzer_v6/README.txt from VERSION.txt (run during build)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_version(version_path: Path) -> str:
    text = version_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^Version:\s*(\S+)", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    try:
        import bsod_analyzer as core
        return core.VERSION
    except ImportError:
        pass
    first = text.splitlines()[0] if text else ""
    m2 = re.search(r"v(\d+\.\d+\.\d+)", first, re.I)
    if m2:
        return m2.group(1)
    raise SystemExit(f"Could not determine version from {version_path}")


def render_readme(version: str) -> str:
    return (
        "================================================================================\n"
        f"  WINDOWS BSOD ANALYZER v{version}  —  PORTABLE\n"
        "================================================================================\n"
        "\n"
        "QUICK START\n"
        "-----------\n"
        "  1. Double-click BSODAnalyzer.exe  (or use Run BSODAnalyzer as Administrator.bat)\n"
        "  2. Drivers tab → Refresh device list → Search\n"
        "  3. Tools → Export scan results  (choose folder — default is PC-local)\n"
        "\n"
        "COPY TO A FLASH DRIVE\n"
        "---------------------\n"
        "  Copy this entire folder. You only need what you see here — the program\n"
        "  bundles its own runtime. Do not delete the hidden _internal folder.\n"
        "\n"
        "YOUR DATA (on the PC you service)\n"
        "---------------------------------\n"
        "  Settings, driver catalog cache, and default exports are stored under:\n"
        "    %LOCALAPPDATA%\\BSODAnalyzer\\\n"
        "  They are not written beside the exe on the USB stick.\n"
        "\n"
        "  See VERSION.txt for release notes.\n"
        "\n"
        "================================================================================\n"
    )


def sync_dist_readme(dist_dir: Path | None = None) -> Path:
    dist = dist_dir or (ROOT / "BSODAnalyzer_v6")
    dist.mkdir(parents=True, exist_ok=True)
    version = _read_version(ROOT / "VERSION.txt")
    out = dist / "README.txt"
    out.write_text(render_readme(version), encoding="utf-8", newline="\n")
    return out


def main(argv: list[str] | None = None) -> int:
    dist = Path(argv[1]) if argv and len(argv) > 1 else None
    path = sync_dist_readme(dist)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
