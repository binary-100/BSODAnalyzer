"""Batch 2: analysis correctness — newest vs recurring driver, stop-code resolution."""

from __future__ import annotations

import bsod_analyzer as core


def _merge_minidump_results(analyses: list[dict], dumps: list[dict]) -> dict:
    latest = core.newest_minidump_analysis(analyses, dumps) or dict(analyses[0])
    driver_counts: dict[str, int] = {}
    for a in analyses:
        drv = a.get("faulting_driver")
        if drv:
            key = drv.lower()
            driver_counts[key] = driver_counts.get(key, 0) + 1
    recurring = None
    recurring_count = 0
    if driver_counts:
        best_key, recurring_count = max(driver_counts.items(), key=lambda x: x[1])
        if recurring_count >= 2:
            for a in analyses:
                fd = a.get("faulting_driver") or ""
                if fd.lower().replace(".sys", "") == best_key.replace(".sys", ""):
                    recurring = fd
                    break
            if not recurring:
                recurring = best_key if best_key.endswith((".sys", ".dll")) else best_key + ".sys"
    latest["dumps_analyzed"] = len(analyses)
    latest["recurring_faulting_driver"] = recurring
    latest["recurring_count"] = recurring_count
    latest["all_analyses"] = analyses
    return latest


def test_recurring_does_not_overwrite_newest_faulting_driver() -> None:
    dumps = [
        {"name": "newest.dmp", "time": "2026-05-30"},
        {"name": "mid.dmp", "time": "2026-05-29"},
        {"name": "oldest.dmp", "time": "2026-05-28"},
    ]
    analyses = [
        {"dump_file": "oldest.dmp", "faulting_driver": "nvlddmkm.sys"},
        {"dump_file": "mid.dmp", "faulting_driver": "nvlddmkm.sys"},
        {"dump_file": "newest.dmp", "faulting_driver": "amdkmdag.sys"},
    ]
    merged = _merge_minidump_results(analyses, dumps)
    assert merged["faulting_driver"] == "amdkmdag.sys"
    assert merged["recurring_faulting_driver"] == "nvlddmkm.sys"
    assert merged["recurring_count"] == 2


def test_resolve_crash_code_prefers_event_log() -> None:
    events = [{"type": "BugCheck", "code": "0x50", "time": "2026-05-30"}]
    windbg = {"bugcheck_code": "0x0A", "bugcheck_str": "IRQL_NOT_LESS_OR_EQUAL"}
    code_val, stop_name, _desc, has_event = core.resolve_crash_code(events, windbg)
    assert has_event is True
    assert code_val == 0x50
    assert "PAGE_FAULT" in stop_name.upper()


def test_resolve_crash_code_falls_back_to_minidump() -> None:
    events: list[dict] = []
    windbg = {
        "bugcheck_code": "0x0A",
        "bugcheck_str": "IRQL_NOT_LESS_OR_EQUAL",
        "dump_time": "2026-05-30 12:00:00",
    }
    code_val, stop_name, _desc, has_event = core.resolve_crash_code(events, windbg)
    assert has_event is False
    assert code_val == 0x0A
    assert "IRQL" in stop_name.upper()


def test_resolve_crash_code_ignores_stale_minidump() -> None:
    events = [{
        "type": "KernelPower",
        "time": "2026-08-09 20:59:35",
        "code": "N/A",
        "code_source": "event41_shutdown",
    }]
    windbg = {
        "bugcheck_code": "0x0A",
        "bugcheck_str": "IRQL_NOT_LESS_OR_EQUAL",
        "dump_time": "2026-08-04 12:00:00",
    }
    code_val, _stop_name, _desc, has_event = core.resolve_crash_code(events, windbg)
    assert has_event is False
    assert code_val is None


def test_usable_bugcheck_excludes_event41_shutdown_only() -> None:
    events = [{
        "type": "KernelPower",
        "code": "0x0000000A",
        "code_source": "event41_shutdown",
        "time": "2026-08-09",
    }]
    assert core._usable_bugcheck_events(events) == []


def test_usable_bugcheck_excludes_uncorroborated_event41_bugcheck() -> None:
    events = [{
        "type": "KernelPower",
        "code": "0x0000000A",
        "code_source": "event41_bugcheck",
        "time": "2026-08-09 20:59:35",
    }]
    assert core._usable_bugcheck_events(events) == []


def test_usable_bugcheck_includes_event41_with_wer_bugcheck() -> None:
    events = [
        {
            "type": "KernelPower",
            "code": "0x0000000A",
            "code_source": "event41_bugcheck",
            "time": "2026-08-09 20:59:35",
        },
        {
            "type": "BugCheck",
            "code": "0x0000000A",
            "time": "2026-08-09 20:59:35",
        },
    ]
    assert len(core._usable_bugcheck_events(events)) == 2


def test_usable_bugcheck_includes_event41_with_matching_dump() -> None:
    events = [{
        "type": "KernelPower",
        "code": "0x0000000A",
        "code_source": "event41_bugcheck",
        "time": "2026-08-09 20:59:35",
    }]
    windbg = {"bugcheck_code": "0x0A", "dump_time": "2026-08-09 20:59:35"}
    assert len(core._usable_bugcheck_events(events, windbg)) == 1


def test_resolve_crash_code_ignores_stale_event41_on_shutdown() -> None:
    events = [{
        "type": "KernelPower",
        "time": "2026-08-09 20:59:35",
        "code": "0x0000000A",
        "code_source": "event41_bugcheck",
    }, {
        "type": "UnexpectedShutdown",
        "time": "2026-08-09 20:59:35",
        "code": "N/A",
    }]
    windbg = {
        "bugcheck_code": "0x0A",
        "bugcheck_str": "IRQL_NOT_LESS_OR_EQUAL",
        "dump_time": "2026-08-04 12:00:00",
    }
    code_val, stop_name, _desc, has_event = core.resolve_crash_code(events, windbg)
    assert has_event is False
    assert code_val is None
    assert stop_name == ""


def test_enrich_windbg_normalizes_nt_stack() -> None:
    parsed = {
        "stack_frames": ["nt!KeBugCheckEx", "nt!MiSystemFault"],
        "faulting_driver": None,
    }
    out = core.enrich_windbg_analysis(parsed)
    assert "ntoskrnl.exe" in out["stack_frames"][0]
    assert out.get("kernel_stack_top") == "ntoskrnl.exe"


def test_minidump_gap_when_bugcheck_code_unreadable() -> None:
    msg = core.minidump_without_bugcheck_gap(
        [{"name": "dump.dmp"}],
        [{"type": "BugCheck", "time": "2026-01-01", "code": "?"}],
    )
    assert msg is not None
    assert "1001" in msg


def test_newest_minidump_analysis_returns_none_without_match() -> None:
    dumps = [{"name": "newest.dmp", "time": "2026-05-30"}]
    analyses = [{"dump_file": "other.dmp", "faulting_driver": "x.sys"}]
    assert core.newest_minidump_analysis(analyses, dumps) is None


def test_build_display_model_ignores_recurring_when_newest_has_no_driver() -> None:
    fmt_args = (
        [],
        [],
        None,
        [],
        {
            "faulting_driver": None,
            "recurring_faulting_driver": "nvlddmkm.sys",
            "recurring_count": 2,
            "dumps_analyzed": 3,
            "bugcheck_code": "0x0A",
        },
        [],
        [],
        "",
        1,
        False,
        "",
        "",
        [],
        {},
        {},
        [],
        [],
        None,
    )
    model = core.build_display_model(fmt_args)
    assert model["driver"] is None


def test_build_display_model_uses_newest_driver_not_recurring() -> None:
    fmt_args = (
        [],
        [],
        None,
        [],
        {
            "faulting_driver": "amdkmdag.sys",
            "recurring_faulting_driver": "nvlddmkm.sys",
            "recurring_count": 2,
            "dumps_analyzed": 3,
            "bugcheck_code": "0x0A",
        },
        [],
        [],
        "",
        1,
        False,
        "",
        "",
        [],
        {},
        {},
        [],
        [],
        None,
    )
    model = core.build_display_model(fmt_args)
    assert model["driver"] == "amdkmdag.sys"
    assert model.get("attributed_pct") == 67


def test_build_display_model_stop_code_from_minidump_only() -> None:
    fmt_args = (
        [],
        [{"name": "x.dmp"}],
        None,
        [],
        {"bugcheck_code": "0x124", "bugcheck_str": "WHEA_UNCORRECTABLE_ERROR"},
        [],
        [],
        "",
        1,
        False,
        "",
        "",
        [],
        {},
        {},
        [],
        [],
        None,
    )
    model = core.build_display_model(fmt_args)
    assert model.get("stop_code_val") == 0x124
    assert "WHEA" in (model.get("stop_name") or "").upper()


if __name__ == "__main__":
    test_recurring_does_not_overwrite_newest_faulting_driver()
    test_resolve_crash_code_prefers_event_log()
    test_resolve_crash_code_falls_back_to_minidump()
    test_resolve_crash_code_ignores_stale_minidump()
    test_resolve_crash_code_ignores_stale_event41_on_shutdown()
    test_usable_bugcheck_excludes_event41_shutdown_only()
    test_usable_bugcheck_excludes_uncorroborated_event41_bugcheck()
    test_usable_bugcheck_includes_event41_with_wer_bugcheck()
    test_usable_bugcheck_includes_event41_with_matching_dump()
    test_enrich_windbg_normalizes_nt_stack()
    test_minidump_gap_when_bugcheck_code_unreadable()
    test_newest_minidump_analysis_returns_none_without_match()
    test_build_display_model_ignores_recurring_when_newest_has_no_driver()
    test_build_display_model_uses_newest_driver_not_recurring()
    test_build_display_model_stop_code_from_minidump_only()
    print("Analysis correctness batch 2 tests OK")
