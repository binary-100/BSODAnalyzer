#!/usr/bin/env py -3
"""Probe all _ba('sym') and core.sym references against bsod_analyzer."""
from __future__ import annotations

import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import bsod_analyzer as ba  # noqa: E402


def collect(pattern: str) -> set[str]:
    out: set[str] = set()
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if "__pycache__" in rel or path.name == "bsod_analyzer.py":
            continue
        if path.name in ("probe_ba_symbols.py", "audit_facade_complete.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for sym in re.findall(pattern, text):
            out.add(sym)
    return out


def main() -> int:
    ba_syms = collect(r"""_ba\(['"]([A-Za-z_][A-Za-z0-9_]*)['"]""")
    core_syms = collect(r"\bcore\.([A-Za-z_][A-Za-z0-9_]*)")

    # Scripts that shadow `core` as a Path/str — not bsod_analyzer
    script_false = {"find", "read_text", "write_text"}

    ba_broken = sorted(s for s in ba_syms if not hasattr(ba, s))
    core_broken = sorted(s for s in core_syms - script_false if not hasattr(ba, s))

    print(f"_ba symbols: {len(ba_syms)}  broken: {len(ba_broken)}")
    for s in ba_broken:
        print(f"  FAIL _ba('{s}')")
    print(f"core.* symbols: {len(core_syms)}  broken (excl script false pos): {len(core_broken)}")
    for s in core_broken:
        print(f"  FAIL core.{s}")
    return 1 if ba_broken or core_broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
