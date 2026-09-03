"""Tests for Phase 5 — repair UX (action plan labels, why this order, confident copy)."""
from __future__ import annotations

import driver_verification as dv


def _shutdown_narrative(**kwargs):
    events = [
        {
            "time": "2026-08-09 20:59:35",
            "type": "KernelPower",
            "code_source": "event41_bugcheck",
        },
    ]
    boot = [{"time": "2026-08-09 21:00:00", "subtype": "KernelBoot", "message": "boot fail"}]
    windbg = {"dump_time": "2026-08-04 12:00:00", "faulting_driver": "ntoskrnl.exe"}
    defaults = dict(
        events=events,
        windbg_analysis=windbg,
        boot_recovery=boot,
        system_ctx={"has_amd_chipset": True},
        bios_driver_info={"all_drivers": []},
        attribution={"platform_chipset_focus": True, "dump_matches_latest": False},
        suspects=[],
    )
    defaults.update(kwargs)
    return dv.build_crash_repair_narrative(**defaults)


def test_no_unknown_wording_in_what_failed() -> None:
    n = _shutdown_narrative()
    summary = (n.get("what_failed") or {}).get("summary") or ""
    assert "Unknown" not in summary
    assert "logging gap" in summary.lower()
    assert n.get("why_this_order")
    assert "Why this order" not in (n.get("why_this_order") or "")  # field value, not label


def test_why_this_order_not_how_sure_label() -> None:
    n = _shutdown_narrative()
    assert n.get("why_this_order")
    assert "how_sure" not in n or not n.get("how_sure")
    lines = dv.format_repair_narrative_quick_answer(n)
    assert any("WHY THIS ORDER" in ln for ln in lines)
    assert not any("HOW SURE WE ARE" in ln for ln in lines)


def test_action_steps_use_exact_repair_target_labels() -> None:
    inv = [
        {"display_name": "AMD PSP 11.0 Device", "version": "5.46.0.0"},
        {"display_name": "AMD SMBus", "version": "2.0.0.26"},
    ]
    n = _shutdown_narrative(bios_driver_info={"all_drivers": inv})
    steps = n.get("action_steps") or []
    targets = n.get("repair_targets") or []
    labels = {t["label"] for t in targets if t.get("label")}
    assert "AMD Chipset Software" in labels or any("Chipset" in lb for lb in labels)
    for step in steps:
        if "Drivers -> Needs attention" not in step:
            continue
        assert any(lb in step for lb in labels), f"step missing exact label: {step}"
    assert not any("suite component" in s.lower() for s in steps)
    assert not any("Verify each suite component is current" in s for s in steps)


def test_verified_case_why_this_order() -> None:
    events = [{"time": "2026-08-04 12:00:00", "type": "BugCheck", "code": "0x0000000A"}]
    windbg = {"dump_time": "2026-08-04 12:00:00", "faulting_driver": "nvlddmkm.sys"}
    suspects = [
        {
            "module": "nvlddmkm",
            "map_status": "mapped",
            "devices": [{"name": "NVIDIA GeForce RTX 4080", "version": "551.23"}],
        },
    ]
    n = dv.build_crash_repair_narrative(
        events,
        windbg,
        suspects=suspects,
        attribution={"dump_matches_latest": True},
    )
    assert "minidump" in (n.get("why_this_order") or "").lower()
    steps = n.get("action_steps") or []
    assert any("NVIDIA GeForce RTX 4080" in s or "nvlddmkm" in s.lower() for s in steps)


def test_kernel_fault_does_not_suggest_ntoskrnl_driver_update() -> None:
    events = [{"time": "2026-08-21 20:02:15", "type": "BugCheck", "code": "0x0000000A"}]
    windbg = {
        "dump_time": "2026-08-21 20:02:15",
        "faulting_driver": "ntoskrnl.exe",
        "stack_frames": ["ntoskrnl.exe!KeBugCheckEx", "nvlddmkm.sys!unknown"],
    }
    n = dv.build_crash_repair_narrative(
        events,
        windbg,
        system_ctx={
            "has_amd_chipset": True,
            "extended_log_attribution": {
                "cbs_hints": [{"category": "Windows Update package activity"}],
            },
        },
        bios_driver_info={"all_drivers": []},
        attribution={"dump_matches_latest": True},
        suspects=[],
    )
    steps = " ".join(n.get("action_steps") or []).lower()
    summary = ((n.get("what_failed") or {}).get("summary") or "").lower()
    assert "update or roll back ntoskrnl" not in steps
    assert "kernel" in summary or "caught a fault" in summary
    assert any("windows update" in s.lower() for s in (n.get("action_steps") or []))
    targets = {t.get("kind") for t in (n.get("repair_targets") or [])}
    assert "faulting_driver" not in targets


if __name__ == "__main__":
    tests = [
        test_no_unknown_wording_in_what_failed,
        test_why_this_order_not_how_sure_label,
        test_action_steps_use_exact_repair_target_labels,
        test_verified_case_why_this_order,
        test_kernel_fault_does_not_suggest_ntoskrnl_driver_update,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    raise SystemExit(1 if failed else 0)
