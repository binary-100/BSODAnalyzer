"""End-user crash repair narrative (what happened / failed / check)."""

from __future__ import annotations

import driver_verification as dv


def test_narrative_shutdown_with_bundle_targets() -> None:
    events = [
        {
            "time": "2026-08-09 20:59:35",
            "type": "KernelPower",
            "code_source": "event41_bugcheck",
        },
    ]
    boot = [{"time": "2026-08-09 21:00:00", "subtype": "KernelBoot", "message": "boot fail"}]
    windbg = {"dump_time": "2026-08-04 12:00:00", "faulting_driver": "storport.sys"}
    attr = {"platform_chipset_focus": True, "dump_matches_latest": False}
    inv = [
        {"display_name": "AMD PSP Device", "version": "5.36.0.0"},
        {"display_name": "AMD SMBus", "version": "1.0.0.79"},
    ]
    n = dv.build_crash_repair_narrative(
        events,
        windbg,
        boot_recovery=boot,
        system_ctx={"has_amd_chipset": True},
        bios_driver_info={"all_drivers": inv},
        attribution=attr,
        suspects=[],
    )
    assert "shut down unexpectedly" in n["what_happened"].lower()
    assert n["what_failed"]["status"] == "unknown"
    assert n.get("older_incident_note")
    assert "storport" in n["older_incident_note"]
    labels = [t["label"] for t in n["repair_targets"]]
    assert any("PSP" in lb for lb in labels)
    assert n["headline"].startswith("Unexpected shutdown")
    steps = n.get("action_steps") or []
    assert any("AMD Chipset" in s or "PSP" in s for s in steps)
    assert n.get("why_this_order")
    assert "Unknown" not in ((n.get("what_failed") or {}).get("summary") or "")


def test_narrative_verified_faulting_driver() -> None:
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
    assert n["what_failed"]["status"] == "verified"
    assert "nvlddmkm" in n["what_failed"]["summary"]
    assert any(t.get("kind") == "faulting_driver" for t in n["repair_targets"])


def test_format_quick_answer_lines() -> None:
    n = dv.build_crash_repair_narrative(
        [{"time": "2026-08-09 12:00:00", "type": "KernelPower"}],
        None,
        boot_recovery=[],
        system_ctx={},
        attribution={},
    )
    lines = dv.format_repair_narrative_quick_answer(n)
    assert any("WHAT HAPPENED" in ln for ln in lines)


if __name__ == "__main__":
    test_narrative_shutdown_with_bundle_targets()
    test_narrative_verified_faulting_driver()
    test_format_quick_answer_lines()
    print("crash repair narrative tests OK")
