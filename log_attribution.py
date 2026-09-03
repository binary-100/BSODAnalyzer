"""Phase 4 — extended in-app log attribution (WER, setupapi, CBS).

Read-only parsing of Windows log sources already on disk. Separate from log cleanup (delete).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any

import log_read_windows as lrw

WER_ROOT = os.path.join(
    os.environ.get("ProgramData", r"C:\ProgramData"),
    "Microsoft",
    "Windows",
    "WER",
)
WER_REPORT_ARCHIVE = os.path.join(WER_ROOT, "ReportArchive")
WER_REPORT_QUEUE = os.path.join(WER_ROOT, "ReportQueue")

WINDOWS_DIR = os.environ.get("SystemRoot", r"C:\Windows")
SETUPAPI_DEV_LOG = os.path.join(WINDOWS_DIR, "setupapi.dev.log")
CBS_LOG = os.path.join(WINDOWS_DIR, "Logs", "CBS", "CBS.log")

WER_SCAN_MAX_FOLDERS = 80
WER_INCIDENT_MATCH_MINUTES = 120
SETUPAPI_TAIL_BYTES = 512_000
CBS_TAIL_BYTES = 512_000
CONTEXT_NEAR_HOURS = 72

_SECTION_START_RE = re.compile(
    r"Section start (\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)"
)
_SETUPAPI_DRIVER_RE = re.compile(
    r"(?i)(?:driver package|installing driver|updated drivers|copying files from driver store)"
    r".{0,120}?([\w\\.-]+\.(?:sys|inf|dll))",
)
_SETUPAPI_ROLLBACK_RE = re.compile(
    r"(?i)(?:rollback|failed to install|error.*driver).{0,80}?([\w\\.-]+\.(?:sys|inf))",
)
_CBS_LINE_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),")
_CBS_HINT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)pending restart"), "Windows Update / servicing pending restart"),
    (re.compile(r"(?i)reboot required"), "Component servicing requires reboot"),
    (re.compile(r"(?i)failed to .* package"), "Component package install failure"),
    (re.compile(r"(?i)HRESULT=0x"), "Component store error (HRESULT)"),
    (re.compile(r"(?i)Rollback"), "Component update rollback"),
    (re.compile(r"(?i)Package_for_KB"), "Windows Update package activity"),
)


def _parse_report_time(parsed: dict, folder_mtime: float | None) -> str:
    for key in ("EventTime", "CreationTime", "ReportTime", "TimeStamp"):
        raw = (parsed.get(key) or "").strip()
        if not raw:
            continue
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%m/%d/%Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                return datetime.strptime(raw[:19], fmt).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
    if folder_mtime is not None:
        return datetime.fromtimestamp(folder_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return ""


def _time_delta_minutes(a: str, b: str) -> float | None:
    da = lrw.parse_log_timestamp(a)
    db = lrw.parse_log_timestamp(b)
    if not da or not db:
        return None
    return abs((da - db).total_seconds()) / 60.0


def _near_anchor(event_time: str, anchor_time: str, *, hours: float = CONTEXT_NEAR_HOURS) -> bool:
    da = lrw.parse_log_timestamp(event_time)
    db = lrw.parse_log_timestamp(anchor_time)
    if not da or not db:
        return False
    return abs((da - db).total_seconds()) <= hours * 3600


def _scan_wer_folder(
    folder_path: str,
    *,
    source_label: str,
    max_folders: int = WER_SCAN_MAX_FOLDERS,
) -> list[dict[str, Any]]:
    """4a — scan ReportArchive or ReportQueue subfolders for Report.wer module hints."""
    import bsod_minidump as md

    if not os.path.isdir(folder_path):
        return []
    hints: list[dict[str, Any]] = []
    try:
        entries = sorted(
            (e for e in os.scandir(folder_path) if e.is_dir()),
            key=lambda e: e.stat().st_mtime if e.is_dir() else 0,
            reverse=True,
        )
    except OSError:
        return []
    for entry in entries[:max_folders]:
        report_path = os.path.join(entry.path, "Report.wer")
        if not os.path.isfile(report_path):
            continue
        try:
            folder_mtime = entry.stat().st_mtime
        except OSError:
            folder_mtime = None
        try:
            with open(report_path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(65536)
        except OSError:
            continue
        parsed = md.parse_report_wer(text)
        module = md._wer_report_module_hint(parsed)
        if not module:
            continue
        event_time = _parse_report_time(parsed, folder_mtime)
        hints.append(
            {
                "module": module,
                "event_time": event_time,
                "source": "wer_archive" if "Archive" in source_label else "wer_queue",
                "wer_source": source_label,
                "report_path": report_path,
                "folder": entry.path,
                "bucket": (
                    parsed.get("BucketId")
                    or parsed.get("BucketingStringKey")
                    or parsed.get("Response.BucketId")
                    or ""
                ),
                "event_type": parsed.get("EventType") or parsed.get("Sig[0].Name") or "",
                "dump_file": os.path.basename(parsed.get("DumpFile") or ""),
            }
        )
    return hints


def scan_wer_reports(*, max_folders: int = WER_SCAN_MAX_FOLDERS) -> list[dict[str, Any]]:
    """Scan WER ReportArchive and ReportQueue; dedupe by folder path."""
    combined: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for label, path in (
        ("ReportArchive", WER_REPORT_ARCHIVE),
        ("ReportQueue", WER_REPORT_QUEUE),
    ):
        for hint in _scan_wer_folder(path, source_label=label, max_folders=max_folders):
            folder = hint.get("folder") or ""
            if folder and folder in seen_paths:
                continue
            if folder:
                seen_paths.add(folder)
            combined.append(hint)
    combined.sort(key=lambda h: h.get("event_time") or "", reverse=True)
    return combined


def classify_wer_hints_for_incidents(
    wer_hints: list[dict[str, Any]],
    events: list,
    *,
    windbg_analysis: dict | None = None,
    anchor_time: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Tag WER hints as historical vs matching latest incident."""
    import bsod_minidump as md

    import bsod_crash_report as crash

    anchor = anchor_time or (events[0].get("time", "") if events else "")
    dump_matches = crash._dump_matches_recent_events(windbg_analysis, events)
    enriched: list[dict[str, Any]] = []
    latest_hints: list[dict[str, Any]] = []
    for hint in wer_hints or []:
        row = dict(hint)
        evt_t = row.get("event_time") or ""
        historical = bool(
            anchor and evt_t and lrw.is_outside_primary_window(evt_t, anchor)
        )
        delta = _time_delta_minutes(evt_t, anchor) if anchor and evt_t else None
        matches_latest = (
            bool(anchor and evt_t and delta is not None and delta <= WER_INCIDENT_MATCH_MINUTES)
            and not historical
        )
        if anchor and evt_t and not matches_latest and anchor[:10] != evt_t[:10]:
            historical = True
        row["historical"] = historical
        row["matches_latest_incident"] = matches_latest
        row["incident_delta_minutes"] = round(delta, 1) if delta is not None else None
        enriched.append(row)
        if matches_latest and not dump_matches and row.get("module"):
            latest_hints.append(row)
    return enriched, latest_hints


def _read_log_tail(path: str, max_bytes: int) -> str:
    if not os.path.isfile(path):
        return ""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            data = handle.read()
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def scan_setupapi_dev_log(
    anchor_time: str,
    *,
    window_hours: float = CONTEXT_NEAR_HOURS,
) -> list[dict[str, Any]]:
    """4c — recent driver install/rollback lines near the latest incident."""
    text = _read_log_tail(SETUPAPI_DEV_LOG, SETUPAPI_TAIL_BYTES)
    if not text or not anchor_time:
        return []
    changes: list[dict[str, Any]] = []
    current_time = ""
    for line in text.splitlines():
        m = _SECTION_START_RE.search(line)
        if m:
            raw = m.group(1).replace("/", "-")
            try:
                current_time = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                current_time = ""
            continue
        if not current_time or not _near_anchor(current_time, anchor_time, hours=window_hours):
            continue
        kind = ""
        driver_ref = ""
        if _SETUPAPI_ROLLBACK_RE.search(line):
            kind = "rollback_or_failure"
            dm = _SETUPAPI_ROLLBACK_RE.search(line)
            driver_ref = dm.group(1) if dm else ""
        elif _SETUPAPI_DRIVER_RE.search(line):
            kind = "install_or_update"
            dm = _SETUPAPI_DRIVER_RE.search(line)
            driver_ref = dm.group(1) if dm else ""
        elif ">>>  [Driver Install" in line or "UpdateDriverForPlugAndPlayDevices" in line:
            kind = "driver_install_section"
            driver_ref = line.strip()[:160]
        if not kind:
            continue
        changes.append(
            {
                "time": current_time,
                "kind": kind,
                "detail": line.strip()[:200],
                "driver_ref": os.path.basename(driver_ref) if driver_ref else "",
                "source": "setupapi.dev.log",
            }
        )
    # Dedupe near-identical rows
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for row in changes:
        key = (row.get("time") or "", row.get("kind") or "", row.get("driver_ref") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    unique.sort(key=lambda r: r.get("time") or "", reverse=True)
    return unique[:12]


def scan_cbs_hints(
    anchor_time: str,
    *,
    window_hours: float = CONTEXT_NEAR_HOURS,
) -> list[dict[str, Any]]:
    """4d — CBS / component store hints for boot-loop / update confusion."""
    text = _read_log_tail(CBS_LOG, CBS_TAIL_BYTES)
    if not text or not anchor_time:
        return []
    hints: list[dict[str, Any]] = []
    current_time = ""
    for line in text.splitlines():
        tm = _CBS_LINE_TIME_RE.match(line)
        if tm:
            current_time = tm.group(1)
        if not current_time or not _near_anchor(current_time, anchor_time, hours=window_hours):
            continue
        for pattern, label in _CBS_HINT_PATTERNS:
            if pattern.search(line):
                hints.append(
                    {
                        "time": current_time,
                        "category": label,
                        "detail": line.strip()[:200],
                        "source": "CBS.log",
                    }
                )
                break
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for row in hints:
        key = (row.get("time") or "", row.get("category") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    unique.sort(key=lambda r: r.get("time") or "", reverse=True)
    return unique[:10]


def _merge_wer_dump_recovery_hints(
    wer_hints: list[dict[str, Any]],
    wer_dump_recovery: dict | None,
) -> list[dict[str, Any]]:
    """Include Phase 2f dump-missing hints without duplicating folder scans."""
    merged = list(wer_hints)
    seen = {(h.get("folder") or "", h.get("module") or "") for h in merged}
    for hint in (wer_dump_recovery or {}).get("module_hints") or []:
        mod = hint.get("module")
        if not mod:
            continue
        key = ("", mod)
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "module": mod,
                "event_time": hint.get("event_time") or "",
                "source": hint.get("source") or "wer_archive",
                "wer_source": "DumpFile recovery (2f)",
                "report_path": hint.get("report_path") or "",
                "folder": "",
                "bucket": hint.get("bucket") or "",
                "from_dump_recovery": True,
            }
        )
    merged.sort(key=lambda h: h.get("event_time") or "", reverse=True)
    return merged


def _build_context_lines(
    *,
    latest_wer_hints: list[dict[str, Any]],
    setupapi_changes: list[dict[str, Any]],
    cbs_hints: list[dict[str, Any]],
    dump_matches: bool,
) -> list[str]:
    lines: list[str] = []
    if latest_wer_hints and not dump_matches:
        mods = ", ".join(dict.fromkeys(h["module"] for h in latest_wer_hints if h.get("module")))
        if mods:
            lines.append(
                f"WER archived report(s) near the latest incident suggest: {mods} "
                "(lower confidence than minidump !analyze)."
            )
    for row in setupapi_changes[:3]:
        ref = row.get("driver_ref") or "driver package"
        kind = "installed/updated" if row.get("kind") == "install_or_update" else row.get("kind", "change")
        lines.append(
            f"setupapi.dev.log ({row.get('time', '?')}): {kind} — {ref}."
        )
    for row in cbs_hints[:2]:
        lines.append(
            f"CBS log ({row.get('time', '?')}): {row.get('category')}."
        )
    return lines


def _build_action_steps(
    *,
    latest_wer_hints: list[dict[str, Any]],
    setupapi_changes: list[dict[str, Any]],
    cbs_hints: list[dict[str, Any]],
    dump_matches: bool,
) -> list[str]:
    steps: list[str] = []
    if latest_wer_hints and not dump_matches:
        mods = ", ".join(dict.fromkeys(h["module"] for h in latest_wer_hints if h.get("module")))
        if mods:
            steps.append(
                f"WER crash report archive names {mods} for a recent incident — "
                "check matching device rows on Drivers tab (no minidump proof)."
            )
    if setupapi_changes:
        ref = setupapi_changes[0].get("driver_ref") or "a driver package"
        steps.append(
            f"Recent driver change logged in setupapi.dev.log ({setupapi_changes[0].get('time', '?')}): "
            f"review or roll back {ref} if problems started after that time."
        )
    if cbs_hints and any("pending restart" in (h.get("category") or "").lower() for h in cbs_hints):
        steps.append(
            "Windows component servicing logged a pending restart — finish updates and reboot before chasing drivers."
        )
    elif cbs_hints:
        steps.append(
            "Check CBS / Windows Update history — component servicing activity near the incident may explain boot loops."
        )
    return steps


def collect_extended_log_attribution(
    events: list,
    *,
    windbg_analysis: dict | None = None,
    boot_recovery: list | None = None,
    wer_dump_recovery: dict | None = None,
) -> dict[str, Any]:
    """Main Phase 4 entry — scan WER, setupapi, CBS; classify against latest incident."""
    import bsod_minidump as md

    import bsod_crash_report as crash

    anchor = events[0].get("time", "") if events else ""
    dump_matches = crash._dump_matches_recent_events(windbg_analysis, events)

    raw_wer = scan_wer_reports()
    wer_hints = _merge_wer_dump_recovery_hints(raw_wer, wer_dump_recovery)
    enriched_wer, latest_wer = classify_wer_hints_for_incidents(
        wer_hints, events, windbg_analysis=windbg_analysis, anchor_time=anchor
    )
    setupapi_changes = scan_setupapi_dev_log(anchor) if anchor else []
    cbs_hints = scan_cbs_hints(anchor) if anchor else []

    context_lines = _build_context_lines(
        latest_wer_hints=latest_wer,
        setupapi_changes=setupapi_changes,
        cbs_hints=cbs_hints,
        dump_matches=dump_matches,
    )
    action_steps = _build_action_steps(
        latest_wer_hints=latest_wer,
        setupapi_changes=setupapi_changes,
        cbs_hints=cbs_hints,
        dump_matches=dump_matches,
    )

    return {
        "wer_module_hints": enriched_wer,
        "latest_incident_wer_hints": latest_wer,
        "setupapi_changes": setupapi_changes,
        "cbs_hints": cbs_hints,
        "context_lines": context_lines,
        "action_steps": action_steps,
        "dump_matches_latest": dump_matches,
        "anchor_time": anchor,
        "sources_scanned": {
            "wer_archive": os.path.isdir(WER_REPORT_ARCHIVE),
            "wer_queue": os.path.isdir(WER_REPORT_QUEUE),
            "wer_reports_found": len(enriched_wer),
            "setupapi_dev_log": os.path.isfile(SETUPAPI_DEV_LOG),
            "setupapi_entries": len(setupapi_changes),
            "cbs_log": os.path.isfile(CBS_LOG),
            "cbs_entries": len(cbs_hints),
        },
    }
