"""Incident timeline and verified stop-code resolution (extracted from bsod_crash_report)."""

from __future__ import annotations

from datetime import datetime

import log_read_windows as lrw

from bsod_minidump import _DUMP_EVENT_MATCH_HOURS
from crash_report_events import group_events_by_incident as _group_events_by_incident


def _bc(name: str):
    """Lazy bsod_crash_report lookup — avoids import cycles during module load."""
    import bsod_crash_report as bc

    return getattr(bc, name)


def _parse_event_time(time_str: str) -> datetime | None:
    if not time_str or time_str == "?":
        return None
    try:
        return datetime.strptime(time_str.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

def _dump_matches_event_time(
    windbg_analysis: dict | None,
    evt_time: str,
    *,
    window_hours: int = _DUMP_EVENT_MATCH_HOURS,
) -> bool:
    if not windbg_analysis or not evt_time:
        return False
    dump_dt = _parse_event_time(windbg_analysis.get("dump_time") or "")
    evt_dt = _parse_event_time(evt_time)
    if not dump_dt or not evt_dt:
        return False
    return abs((dump_dt - evt_dt).total_seconds()) <= window_hours * 3600

def _dump_matches_recent_events(
    windbg_analysis: dict | None,
    events: list,
    *,
    window_hours: int = _DUMP_EVENT_MATCH_HOURS,
) -> bool:
    if not windbg_analysis:
        return False
    if not events:
        return True
    latest_time = events[0].get("time", "")
    return _dump_matches_event_time(windbg_analysis, latest_time, window_hours=window_hours)

def build_incident_timeline(
    events: list | None,
    *,
    reliability_ctx: dict | None = None,
    windbg_analysis: dict | None = None,
    kernel_dumps: list | None = None,
    extended_log_attribution: dict | None = None,
) -> dict:
    """Structured shutdown / BSOD / boot-recovery / minidump timeline for the Summary UI."""
    rel = reliability_ctx or {}
    boot_recovery = rel.get("boot_recovery") or []
    evts = events or []
    dump_matches_latest = _dump_matches_recent_events(windbg_analysis, evts)
    dump_time = (windbg_analysis or {}).get("dump_time") or ""
    dump_file = (windbg_analysis or {}).get("dump_file") or ""
    faulting = (windbg_analysis or {}).get("faulting_driver") or ""
    latest_anchor = evts[0].get("time", "") if evts else ""
    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _is_historical(time_s: str, incident_index: int | None, *, dump_match: bool | None) -> bool:
        if incident_index is not None and incident_index > 1:
            return True
        if dump_match is False:
            return True
        if latest_anchor and time_s and lrw.is_outside_primary_window(time_s, latest_anchor):
            return True
        return False

    def _add(
        time_s: str,
        kind: str,
        label: str,
        detail: str = "",
        *,
        verified_stop: bool | None = None,
        dump_match: bool | None = None,
        incident_index: int | None = None,
        historical: bool | None = None,
    ) -> None:
        key = (time_s, kind)
        if key in seen:
            return
        seen.add(key)
        is_hist = historical if historical is not None else _is_historical(
            time_s, incident_index, dump_match=dump_match
        )
        display_label = f"Historical — {label}" if is_hist and not label.startswith("Historical") else label
        entries.append({
            "time": time_s,
            "kind": kind,
            "label": display_label,
            "detail": detail,
            "verified_stop": verified_stop,
            "dump_match": dump_match,
            "incident_index": incident_index,
            "historical": is_hist,
            "relevance": "historical" if is_hist else "current",
        })

    groups = _group_events_by_incident(evts, window_minutes=lrw.INCIDENT_GROUP_WINDOW_MINUTES) if evts else []
    for idx, group in enumerate(groups[:6]):
        evt = next((e for e in group if e.get("type") == "BugCheck"), group[0])
        evt = next(
            (e for e in group if e.get("type") == "KernelPower" and evt.get("type") != "BugCheck"),
            evt,
        )
        t = evt.get("time") or "?"
        types = sorted(set(e.get("type", "") for e in group if e.get("type")))
        code_val, stop_name, _stop_desc, verified = _verified_stop_for_incident(
            group, windbg_analysis, events=evts
        )
        if evt.get("type") == "BugCheck" and verified:
            kind = "bugcheck"
            label = stop_name.replace("_", " ") if stop_name else "BugCheck (verified)"
            detail = f"Events: {', '.join(types)}"
            stop_verified: bool | None = True
        elif evt.get("type") == "KernelPower" or "UnexpectedShutdown" in types:
            kind = "shutdown"
            if verified and stop_name:
                label = f"Unexpected shutdown — {stop_name.replace('_', ' ')}"
                stop_verified = True
            else:
                label = "Unexpected shutdown (no verified BSOD stop code)"
                stop_verified = (
                    False
                    if evt.get("code_source") == "event41_bugcheck"
                    else None
                )
            note = (evt.get("note") or "").strip()
            detail = note or f"Events: {', '.join(types)}"
            if code_val and not verified:
                detail += " — Event 41 stop code not verified without WER/minidump."
        else:
            kind = "event"
            label = types[0] if types else "Crash-related event"
            detail = f"Events: {', '.join(types)}"
            stop_verified = verified if code_val is not None else None
        _add(
            t,
            kind,
            label,
            detail,
            verified_stop=stop_verified,
            dump_match=(
                _dump_matches_event_time(windbg_analysis, t)
                if windbg_analysis and idx == 0
                else None
            ),
            incident_index=idx + 1,
        )

    crash_times = [e.get("time", "") for e in evts if e.get("time")]
    for br in boot_recovery[:10]:
        t = br.get("time") or "?"
        if not _bc("_match_event_to_crash")(t, crash_times, _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN")):
            continue
        sub = br.get("subtype") or "BootRecovery"
        msg = (br.get("message") or br.get("note") or "").strip()
        label = {
            "StartupRepair": "Startup / Automatic Repair",
            "KernelBoot": "Kernel boot failure signal",
            "Wininit": "Wininit boot recovery",
        }.get(sub, "Boot / recovery event")
        _add(t, "boot_recovery", label, msg[:160])

    for d in (kernel_dumps or [])[:6]:
        t = d.get("time") or "?"
        name = d.get("name") or "minidump"
        size = d.get("size_mb")
        size_bit = f", {size} MB" if size not in (None, "") else ""
        is_this_dump = bool(dump_time and t and dump_time[:16] == t[:16])
        matches = is_this_dump and dump_matches_latest
        if matches and faulting:
            label = f"Minidump matches latest incident — {faulting}"
        elif is_this_dump:
            label = f"Minidump analyzed — {faulting or name}"
        else:
            label = f"Older minidump on disk — {name}"
        detail = f"{name}{size_bit}"
        if not matches and evts:
            detail += " — does not match the latest shutdown/BSOD time (historical)."
        elif matches:
            detail += " — matches the latest incident window."
        _add(
            t,
            "minidump",
            label,
            detail,
            dump_match=matches,
            historical=not matches,
        )

    ext = extended_log_attribution or {}
    for hint in (ext.get("wer_module_hints") or [])[:8]:
        t = hint.get("event_time") or "?"
        mod = hint.get("module") or "?"
        src = hint.get("wer_source") or hint.get("source") or "WER"
        is_hist = bool(hint.get("historical"))
        matches = bool(hint.get("matches_latest_incident"))
        label = f"WER report — {mod}"
        detail = f"{src}; bucket={hint.get('bucket') or '—'}"
        if matches and not dump_matches_latest:
            detail += " — suggests module for latest incident (no matching minidump)."
        elif is_hist:
            detail += " — historical WER report (different incident window)."
        _add(
            t,
            "wer_attribution",
            label,
            detail,
            dump_match=False if is_hist else (matches if not dump_matches_latest else None),
            historical=is_hist,
        )

    for row in (ext.get("setupapi_changes") or [])[:4]:
        t = row.get("time") or "?"
        ref = row.get("driver_ref") or "driver package"
        _add(
            t,
            "setupapi",
            f"Driver change — {ref}",
            (row.get("detail") or "")[:160],
            historical=bool(latest_anchor and t and lrw.is_outside_primary_window(t, latest_anchor)),
        )

    for row in (ext.get("cbs_hints") or [])[:3]:
        t = row.get("time") or "?"
        _add(
            t,
            "cbs_servicing",
            row.get("category") or "Component servicing",
            (row.get("detail") or "")[:160],
            historical=bool(latest_anchor and t and lrw.is_outside_primary_window(t, latest_anchor)),
        )

    entries.sort(key=lambda e: e.get("time") or "", reverse=True)

    stale_dump_note = ""
    if not dump_matches_latest:
        stale_dump_note = lrw.build_stale_dump_note(
            windbg_analysis,
            latest_incident_date=latest_anchor,
        )

    summary_lines: list[str] = []
    if not entries:
        summary_lines.append("No crash or boot events in the recent log window.")
    else:
        hist_n = sum(1 for e in entries if e.get("historical"))
        summary_lines.append(
            f"{len(entries)} timeline item(s); focus on the newest non-historical row first."
        )
        if hist_n:
            summary_lines.append(
                f"{hist_n} item(s) marked Historical (outside the latest incident or primary window)."
            )
        if not dump_matches_latest and dump_time and evts:
            summary_lines.append(
                "Latest minidump is from a different day — driver name may not apply to the newest shutdown."
            )

    return {
        "entries": entries[:lrw.INCIDENT_TIMELINE_ENTRIES_MAX],
        "dump_matches_latest": dump_matches_latest,
        "newest_dump_mismatch": bool(
            windbg_analysis and dump_time and evts and not dump_matches_latest
        ),
        "stale_dump_note": stale_dump_note,
        "primary_incident_days": lrw.PRIMARY_INCIDENT_DAYS,
        "read_windows": lrw.read_windows_as_dict(),
        "summary_lines": summary_lines,
    }

def _incident_group_for_event(evt: dict, events: list, *, window_minutes: int = 2) -> list[dict]:
    """Return the incident group containing *evt* (by time), or a singleton."""
    t = (evt.get("time") or "").strip()
    if not t:
        return [evt]
    for group in _group_events_by_incident(events or [], window_minutes=window_minutes):
        if any((e.get("time") or "").strip() == t for e in group):
            return group
    return [evt]

def _event41_stop_verified(
    evt: dict,
    events: list,
    windbg_analysis: dict | None,
    *,
    window_minutes: int = 2,
) -> bool:
    """Event 41 BugcheckCode alone is often stale — require WER 1001 or a matching dump."""
    if (evt.get("code_source") or "") != "event41_bugcheck":
        return True
    group = _incident_group_for_event(evt, events, window_minutes=window_minutes)
    if any(e.get("type") == "BugCheck" for e in group):
        return True
    if windbg_analysis and _dump_matches_event_time(
        windbg_analysis, evt.get("time", "")
    ):
        return True
    return False

def _stop_from_event(evt: dict) -> tuple[int | None, str, str]:
    code = (evt.get("code") or "").strip()
    if not code or code in ("?", "N/A", "0x00000000", "0"):
        return None, "", ""
    try:
        code_val = int(str(code).replace("0x", ""), 16)
        stop_name, stop_desc = _bc("get_bugcheck_info")(code_val)
        return code_val, stop_name, stop_desc
    except (ValueError, TypeError):
        return None, str(code), ""

def _verified_stop_for_incident(
    group: list[dict],
    windbg_analysis: dict | None,
    *,
    events: list | None = None,
) -> tuple[int | None, str, str, bool]:
    """Verified stop code for one incident group (newest incident first in callers)."""
    events = events if events is not None else group
    evt = next((e for e in group if e.get("type") == "BugCheck"), None)
    if evt:
        code_val, stop_name, stop_desc = _stop_from_event(evt)
        if code_val is not None or stop_name:
            return code_val, stop_name, stop_desc, True
    kp = next((e for e in group if e.get("type") == "KernelPower"), None)
    if kp and kp.get("code_source") == "event41_bugcheck":
        if _event41_stop_verified(kp, events, windbg_analysis):
            code_val, stop_name, stop_desc = _stop_from_event(kp)
            if code_val is not None or stop_name:
                return code_val, stop_name, stop_desc, True
    if windbg_analysis and group:
        ref_time = group[0].get("time", "")
        if ref_time and _dump_matches_event_time(windbg_analysis, ref_time):
            raw = windbg_analysis.get("bugcheck_code")
            if raw is not None:
                try:
                    code_val = int(str(raw).replace("0x", ""), 16)
                    stop_name, stop_desc = _bc("get_bugcheck_info")(code_val)
                    return code_val, stop_name, stop_desc, False
                except (ValueError, TypeError):
                    pass
    return None, "", "", False

def _usable_bugcheck_events(
    events: list,
    windbg_analysis: dict | None = None,
) -> list:
    out: list[dict] = []
    for e in events or []:
        etype = (e.get("type") or "").strip()
        code = (e.get("code") or "").strip()
        if code in ("?", "N/A", "0x00000000", "0"):
            continue
        try:
            int(str(code).replace("0x", ""), 16)
        except (ValueError, TypeError):
            continue
        if etype == "BugCheck":
            out.append(e)
        elif etype == "KernelPower":
            if e.get("code_source") != "event41_bugcheck":
                continue
            if not _event41_stop_verified(e, events, windbg_analysis):
                continue
            merged = dict(e)
            merged["type"] = "BugCheck"
            merged["note"] = (
                (e.get("note") or "").strip()
                or "Stop code from Kernel-Power Event 41 (WER 1001 not recorded)."
            )
            out.append(merged)
    return out

def resolve_crash_code(
    events: list,
    windbg_analysis: dict | None,
) -> tuple[int | None, str, str, bool]:
    """Resolve stop code from the newest incident with verified evidence.

    Returns (code_val, stop_name, stop_desc, has_usable_event_bugcheck).
    """
    incidents = _group_events_by_incident(events or [])
    if incidents:
        code_val, stop_name, stop_desc, verified = _verified_stop_for_incident(
            incidents[0], windbg_analysis, events=events
        )
        if verified or code_val is not None or stop_name:
            return code_val, stop_name, stop_desc, verified
    if windbg_analysis and _dump_matches_recent_events(windbg_analysis, events):
        code_val = None
        stop_name = ""
        stop_desc = ""
        raw = windbg_analysis.get("bugcheck_code")
        if raw is not None:
            try:
                code_val = int(str(raw).replace("0x", ""), 16)
                stop_name, stop_desc = _bc("get_bugcheck_info")(code_val)
            except (ValueError, TypeError):
                stop_name = windbg_analysis.get("bugcheck_str") or str(raw)
        elif windbg_analysis.get("bugcheck_str"):
            stop_name = str(windbg_analysis["bugcheck_str"])
        return code_val, stop_name, stop_desc, False
    return None, "", "", False
