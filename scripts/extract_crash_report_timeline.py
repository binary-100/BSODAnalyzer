"""One-shot: extract incident timeline + crash code resolution from bsod_crash_report.py."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "bsod_crash_report.py"
OUT = APP / "crash_report_timeline.py"

# 1-based inclusive: _parse_event_time through resolve_crash_code (excl. get_bugcheck_info)
FUNC_RANGE = (2439, 2839)

_BC_CALLS = ("get_bugcheck_info", "_match_event_to_crash")
_BC_NAMES = ("_RELIABILITY_NEAR_CRASH_WINDOW_MIN",)


def _patch_bc_refs(text: str) -> str:
    for name in _BC_CALLS:
        text = re.sub(rf"(?<![.\w]){re.escape(name)}\(", f'_bc("{name}")(', text)
    for name in _BC_NAMES:
        text = re.sub(rf"(?<![.\w]){re.escape(name)}\b", f'_bc("{name}")', text)
    return text


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = FUNC_RANGE
    body = _patch_bc_refs("".join(lines[start - 1 : end]))

    header = '''"""Incident timeline and verified stop-code resolution (extracted from bsod_crash_report)."""

from __future__ import annotations

from datetime import datetime

import log_read_windows as lrw

from bsod_minidump import _DUMP_EVENT_MATCH_HOURS
from crash_report_events import group_events_by_incident as _group_events_by_incident


def _bc(name: str):
    """Lazy bsod_crash_report lookup — avoids import cycles during module load."""
    import bsod_crash_report as bc

    return getattr(bc, name)


'''

    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len((header + body).splitlines())} lines approx)")

    del lines[start - 1 : end]
    text = "".join(lines)

    import_block = """from crash_report_timeline import (
    _dump_matches_event_time,
    _dump_matches_recent_events,
    _event41_stop_verified,
    _incident_group_for_event,
    _parse_event_time,
    _stop_from_event,
    _usable_bugcheck_events,
    _verified_stop_for_incident,
    build_incident_timeline,
    resolve_crash_code,
)

"""
    needle = "from crash_report_events import ("
    if needle not in text:
        raise SystemExit("crash_report_events import anchor not found")
    idx = text.index(needle)
    end_idx = text.index("\n)\n", idx) + len("\n)\n")
    text = text[:end_idx] + "\n" + import_block + text[end_idx:]

    SRC.write_text(text, encoding="utf-8")
    print(f"Updated {SRC}")


if __name__ == "__main__":
    main()
