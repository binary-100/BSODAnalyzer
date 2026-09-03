"""Event parsing and incident grouping for crash reports (extracted from bsod_crash_report)."""

from __future__ import annotations

from datetime import datetime


def parse_p1(p1_str: str) -> int | None:
    """Parse bugcheck parameter 1 to int (handles 0, 0x0, hex, decimal)."""
    if not p1_str or p1_str == "0":
        return 0
    s = str(p1_str).strip().lower()
    try:
        if s.startswith("0x"):
            return int(s, 16)
        return int(s, 10)
    except (ValueError, TypeError):
        return None


def decode_exception_code(code_str: str) -> str:
    """Return human-readable meaning for Windows exception codes (Event 1000)."""
    if not code_str:
        return ""
    s = str(code_str).strip().lower().replace("0x", "")
    try:
        code = int(s, 16)
    except (ValueError, TypeError):
        return code_str
    exception_meanings = {
        0xC0000005: "Access violation (invalid memory read/write)",
        0xE0434352: "CLR/.NET exception (application or framework error)",
        0x80000003: "Breakpoint (debugger or intentional)",
        0xC0000409: "Stack buffer overrun",
        0xC00000FD: "Stack overflow",
        0xE06D7363: "C++ exception (Microsoft Visual C++)",
        0xC0000135: "DLL not found",
        0xC000007B: "Invalid executable format",
    }
    if code in exception_meanings:
        return exception_meanings[code]
    return code_str


def group_events_by_incident(events: list, window_minutes: int = 2) -> list[list[dict]]:
    """Group crash events into incidents (events within window_minutes = same incident)."""
    if not events:
        return []
    sorted_events = sorted(events, key=lambda e: e.get("time", ""), reverse=True)
    groups: list[list[dict]] = []
    current = [sorted_events[0]]
    for evt in sorted_events[1:]:
        t = evt.get("time", "")
        if not t:
            current.append(evt)
            continue
        try:
            et = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
            ref = datetime.strptime(current[0].get("time", t), "%Y-%m-%d %H:%M:%S")
            if abs((et - ref).total_seconds()) <= window_minutes * 60:
                current.append(evt)
            else:
                groups.append(current)
                current = [evt]
        except ValueError:
            current.append(evt)
    groups.append(current)
    return groups
