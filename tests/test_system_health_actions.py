"""Tests for Action Plan inline system health buttons."""
from __future__ import annotations

import system_health_actions as shealth


def test_memory_step_gets_memory_button() -> None:
    step = "If crashes continue: run Windows Memory Diagnostic (mdsched.exe)."
    assert shealth.action_kinds_for_step(step) == ["memory_test"]


def test_combined_sfc_dism_step_gets_both_buttons() -> None:
    step = (
        "Optional: run sfc /scannow; use DISM /Online /Cleanup-Image "
        "/RestoreHealth if the system feels corrupted."
    )
    assert shealth.action_kinds_for_step(step) == ["sfc", "dism"]


def test_sfc_only_step() -> None:
    step = "Optional: run sfc /scannow only if problems persist after the main fixes above."
    assert shealth.action_kinds_for_step(step) == ["sfc"]


def test_unrelated_step_has_no_buttons() -> None:
    assert shealth.action_kinds_for_step("Restart the PC after driver changes.") == []


def test_chkdsk_step_gets_button() -> None:
    step = "Run chkdsk /f on the system drive (schedule on reboot if needed)"
    assert shealth.action_kinds_for_step(step) == ["chkdsk"]


def test_action_kind_for_step_returns_first_kind() -> None:
    step = "Run sfc /scannow and DISM RestoreHealth"
    assert shealth.action_kind_for_step(step) == "sfc"
