"""Boot/recovery playbook and catalog export comparison."""

from __future__ import annotations

import bsod_analyzer as core
import catalog_export as cexp


def test_boot_playbook_when_recovery_without_verified_stop() -> None:
    boot = [{"time": "2026-08-09 22:00:00", "summary": "Startup repair"}]
    steps = core.build_boot_failure_playbook_steps(
        boot,
        system_ctx={"has_amd_chipset": True, "cpu_vendor": "amd"},
        dump_matches_latest=False,
        has_verified_stop=False,
    )
    assert steps
    assert any("Boot/recovery playbook" in s for s in steps)
    assert any("AMD chipset" in s for s in steps)


def test_boot_playbook_skipped_when_dump_matches() -> None:
    boot = [{"time": "2026-08-09 22:00:00", "summary": "Startup repair"}]
    assert not core.build_boot_failure_playbook_steps(
        boot,
        dump_matches_latest=True,
        has_verified_stop=False,
    )


def test_fix_focus_boot_recovery_amd_chipset() -> None:
    events = [{"time": "2026-08-09 22:00:00", "type": "Shutdown", "code": ""}]
    reliability = {
        "boot_recovery": [{"time": "2026-08-09 22:01:00", "summary": "Kernel-Boot recovery"}],
        "livekernel": [],
        "wer_errors": [],
    }
    focus = core.derive_report_fix_focus(
        None,
        {"crash_times": ["2026-08-09 22:00:00"]},
        None,
        None,
        {"driver_actionable": False},
        reliability,
        events,
        [],
        [],
        system_ctx={"has_amd_chipset": True},
    )
    assert focus["focus"] == core.FIX_CPU_PLATFORM
    assert any("Boot/recovery" in e for e in focus["evidence"])


def test_fix_focus_boot_recovery_without_chipset() -> None:
    events = [{"time": "2026-08-09 22:00:00", "type": "Shutdown", "code": ""}]
    reliability = {
        "boot_recovery": [{"time": "2026-08-09 22:01:00", "summary": "Kernel-Boot recovery"}],
        "livekernel": [],
        "wer_errors": [],
    }
    focus = core.derive_report_fix_focus(
        None,
        {"crash_times": ["2026-08-09 22:00:00"]},
        None,
        None,
        {"driver_actionable": False},
        reliability,
        events,
        [],
        [],
        system_ctx={},
    )
    assert focus["focus"] == core.FIX_BOOT_RECOVERY


def test_fix_plan_boot_recovery_amd_without_stop_code() -> None:
    boot = [{"time": "2026-08-09 22:01:00", "summary": "Kernel-Boot recovery"}]
    focus = core.derive_report_fix_focus(
        None,
        {"crash_times": ["2026-08-09 22:00:00"]},
        None,
        None,
        {"driver_actionable": False},
        {"boot_recovery": boot, "livekernel": [], "wer_errors": []},
        [{"time": "2026-08-09 22:00:00", "type": "Shutdown"}],
        [],
        [],
        system_ctx={"has_amd_chipset": True},
    )
    plan = core.build_crash_fix_plan(
        focus,
        code_val=None,
        stop_name="",
        faulting_driver=None,
        windbg_analysis=None,
        system_ctx={"has_amd_chipset": True},
        cause_type={"driver_actionable": False},
        boot_recovery=boot,
        dump_matches_latest=False,
        has_verified_stop=False,
    )
    assert "Boot / recovery" in plan["headline"]
    assert any("Boot/recovery playbook" in s for s in plan["steps"])


def test_compare_catalog_exports_status_change() -> None:
    a = {
        "app_version": "6.4.68",
        "exported_at": "2026-08-10",
        "hardware_summary": {"machine_fingerprint": "test"},
        "summary": {"drivers": {"device_count": 1, "by_status": {"none": 1}}},
        "drivers": [
            {"display_name": "AMD Chipset", "status": "none", "installed_version": "8.07"},
        ],
    }
    b = {
        "app_version": "6.4.68",
        "exported_at": "2026-08-11",
        "hardware_summary": {"machine_fingerprint": "test"},
        "summary": {"drivers": {"device_count": 1, "by_status": {"current": 1}}},
        "drivers": [
            {"display_name": "AMD Chipset", "status": "current", "installed_version": "8.07.16.1035"},
        ],
    }
    text = cexp.compare_catalog_exports(a, b)
    assert "AMD Chipset: none -> current" in text
    assert "Installed version changes" in text


if __name__ == "__main__":
    test_boot_playbook_when_recovery_without_verified_stop()
    test_boot_playbook_skipped_when_dump_matches()
    test_fix_focus_boot_recovery_amd_chipset()
    test_fix_focus_boot_recovery_without_chipset()
    test_fix_plan_boot_recovery_amd_without_stop_code()
    test_compare_catalog_exports_status_change()
    print("boot playbook + export compare tests OK")
