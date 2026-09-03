"""Action Plan display filtering and inline action mapping."""

from __future__ import annotations

import action_plan_ui as apui
import crash_report_fix_plan as fixplan


def test_filter_drops_narrative_and_driver_tab_steps() -> None:
    raw = [
        "The minidump lists ntoskrnl.exe for IRQL NOT LESS OR EQUAL — that usually means a driver issue.",
        "Fix the fault Windows logged: CPU (machine check exception).",
        "Install the latest AMD chipset drivers for this PC.",
        "Drivers -> Needs attention: run Search for updates on PSP (installed 5.46.0.0).",
        "Restart the PC after BIOS, chipset, or driver changes before testing again.",
        "Lower priority: replace generic drivers on non-critical devices (Drivers tab).",
    ]
    out = apui.filter_action_plan_display_steps(raw)
    assert out == ["Install the latest AMD chipset drivers for this PC."]


def test_build_rows_attach_chipset_and_unmatched_links() -> None:
    steps = [
        "Install the latest AMD chipset drivers for this PC.",
        "Update BIOS/UEFI from Alienware m17 R5 AMD for your exact model.",
        "If crashes continue: run Windows Memory Diagnostic (mdsched.exe).",
    ]
    options = [
        {"id": "amd_chipset", "label": "AMD chipset drivers", "kind": "url", "url": "https://amd.example/chipset"},
        {"id": "bios_model_search", "label": "BIOS / UEFI updates", "kind": "url", "url": "https://dell.example/bios"},
        {"id": "oem_model_support", "label": "Download drivers for this PC", "kind": "url", "url": "https://dell.example/drivers"},
        {"id": "wu_optional_platform", "label": "Open Windows Update", "kind": "uri", "uri": "ms-settings:windowsupdate"},
    ]
    rows = apui.build_action_plan_rows(steps, options)
    assert len(rows) == 5
    assert rows[0]["driver_options"][0]["id"] == "amd_chipset"
    assert rows[1]["driver_options"][0]["id"] == "bios_model_search"
    assert rows[2]["health_kinds"] == ["memory_test"]
    unmatched_ids = {r["driver_options"][0]["id"] for r in rows[3:] if r["driver_options"]}
    assert unmatched_ids == {"oem_model_support", "wu_optional_platform"}


def test_cpu_platform_fix_plan_has_no_narrative_steps() -> None:
    plan = fixplan.build_crash_fix_plan(
        {
            "focus": fixplan.FIX_CPU_PLATFORM,
            "evidence": ["Minidumps name ntoskrnl.exe"],
            "p1_source_label": "CPU (machine check exception)",
        },
        code_val=0x0A,
        stop_name="IRQL_NOT_LESS_OR_EQUAL",
        faulting_driver="ntoskrnl.exe",
        windbg_analysis=None,
        system_ctx={"has_amd_chipset": True, "system_manufacturer": "Alienware", "system_model": "m17 R5 AMD"},
        cause_type={"driver_actionable": False},
    )
    filtered = apui.filter_action_plan_display_steps(plan.get("steps") or [])
    joined = " ".join(filtered).lower()
    assert "minidump lists" not in joined
    assert "fix the fault windows logged" not in joined
    assert "lower priority" not in joined
    assert "restart the pc after" not in joined
    assert "chipset" in joined
    assert "machine check" in (plan.get("headline") or "").lower()


if __name__ == "__main__":
    test_filter_drops_narrative_and_driver_tab_steps()
    test_build_rows_attach_chipset_and_unmatched_links()
    test_cpu_platform_fix_plan_has_no_narrative_steps()
    print("OK")
