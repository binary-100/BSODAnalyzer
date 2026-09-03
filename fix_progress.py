"""Notes when installed driver package dates fall after the last BSOD."""
from __future__ import annotations

from datetime import datetime

from driver_catalog import parse_driver_package_date


def parse_last_crash_time(last_crash: str | None) -> datetime | None:
    """Parse a crash label into an aware local datetime.

    The label is local wall-clock time. Older saved models carry a ` UTC` suffix from
    when `compute_crash_timeline` mislabelled it; those readings were local too, so both
    forms parse the same way.
    """
    raw = (last_crash or "").strip()
    if not raw:
        return None
    text = raw.replace(" UTC", "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).astimezone()
        except ValueError:
            continue
    return None


def resolve_last_crash(model: dict | None = None) -> tuple[str, datetime | None]:
    """
    Last BSOD time from the analysis model when present, otherwise a lightweight
    System event-log query (no full Run Analysis required).
    """
    label = ((model or {}).get("last_crash") or "").strip()
    if not label:
        timeline = (model or {}).get("crash_timeline") or {}
        label = (timeline.get("last_crash") or "").strip()
    if label:
        return label, parse_last_crash_time(label)

    try:
        import bsod_events as ev

        events, failed = ev.query_bugcheck_events()
        if failed:
            return "", None
        timeline = ev.compute_crash_timeline(events)
        label = (timeline.get("last_crash") or "").strip()
        if not label:
            return "", None
        return label, parse_last_crash_time(label)
    except ImportError:
        return "", None


def fix_progress_note(
    dev: dict,
    *,
    last_crash_dt: datetime | None,
    last_crash_label: str = "",
) -> str | None:
    """
    True troubleshooting signal: driver package date is newer than the last BSOD.
    Uses WMI DriverDate on the device row (no analysis-time snapshot required).
    """
    if last_crash_dt is None:
        return None

    cur_date = (dev.get("date") or "").strip()
    cur_d = parse_driver_package_date(cur_date)
    if not cur_d:
        return None

    crash_d = last_crash_dt.date()
    if cur_d <= crash_d:
        return None

    when = (last_crash_label or "").split(" UTC")[0].strip() or crash_d.isoformat()
    ver = (dev.get("version") or dev.get("_installed_at_scan") or "").strip()
    if ver and ver not in ("?", "—", "N/A"):
        return (
            f"Driver package dated {cur_d.isoformat()} ({ver}) — "
            f"after last BSOD ({when})"
        )
    return f"Driver package dated {cur_d.isoformat()} — after last BSOD ({when})"
