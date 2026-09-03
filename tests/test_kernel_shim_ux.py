"""Kernel shim (ntoskrnl) must not surface as an updatable driver row or action step."""
from __future__ import annotations

import crash_report_culprit as crc
import crash_report_fix_plan as fixplan
import driver_list_build as dlb
from bsod_crash_report import sanitize_action_plan_steps


def test_has_crash_faulting_driver_excludes_ntoskrnl() -> None:
    assert not crc.has_crash_faulting_driver("ntoskrnl.exe")
    assert crc.is_kernel_shim_fault_module("ntoskrnl.exe")
    assert crc.has_crash_faulting_driver("nvlddmkm.sys")


def test_irql_ntoskrnl_fix_plan_is_platform_not_named_driver() -> None:
    plan = fixplan.build_crash_fix_plan(
        {"focus": fixplan.FIX_CPU_PLATFORM, "evidence": []},
        code_val=0x0A,
        stop_name="IRQL_NOT_LESS_OR_EQUAL",
        faulting_driver="ntoskrnl.exe",
        windbg_analysis=None,
        system_ctx={"has_amd_chipset": True},
        cause_type={"driver_actionable": False},
    )
    joined = " ".join(plan.get("steps") or []).lower()
    assert "update or roll back ntoskrnl" not in joined
    assert plan.get("links_title") == "Chipset, BIOS, and PC maker downloads"
    assert "kernel fault" in (plan.get("headline") or "").lower()


def test_sanitize_strips_ntoskrnl_update_step() -> None:
    raw = [
        "Update or roll back ntoskrnl.exe — the minidump names this module.",
        "Install the latest AMD chipset drivers for this PC.",
    ]
    out = sanitize_action_plan_steps(raw, "ntoskrnl.exe")
    assert len(out) == 1
    assert "chipset" in out[0].lower()


def test_inject_crash_linked_skips_synthetic_ntoskrnl_row() -> None:
    merged: dict[str, dict] = {}
    model = {
        "driver": "ntoskrnl.exe",
        "stop_code_val": 0x0A,
        "system_ctx": {"has_amd_chipset": True},
        "cause_type": {"label": "Mixed — kernel or framework module", "driver_actionable": False},
        "fix_plan": {"focus": fixplan.FIX_CPU_PLATFORM},
    }
    prof = {"system_ctx": {"has_amd_chipset": True}, "bios_driver_info": {"all_drivers": []}}
    dlb.inject_crash_linked_devices(merged, prof, last_model=model, last_fmt_args=((),))
    assert not any(crc.is_crash_synthetic_device_key(k) for k in merged)
    assert not any("ntoskrnl" in (v.get("display_name") or "").lower() for v in merged.values())


if __name__ == "__main__":
    for fn in (
        test_has_crash_faulting_driver_excludes_ntoskrnl,
        test_irql_ntoskrnl_fix_plan_is_platform_not_named_driver,
        test_sanitize_strips_ntoskrnl_update_step,
        test_inject_crash_linked_skips_synthetic_ntoskrnl_row,
    ):
        fn()
        print(f"OK {fn.__name__}")
