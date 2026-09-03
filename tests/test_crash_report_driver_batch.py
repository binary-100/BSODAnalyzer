"""Crash-report driver batch helpers (post-analysis path, not user Include search)."""

from __future__ import annotations

from unittest import mock

import bsod_analyzer as core


def test_crash_synthetic_device_split() -> None:
    """Synthetic .sys-only rows are checked separately from matched PnP devices."""
    batch = [
        "Intel(R) Ethernet Adapter",
        core.crash_synthetic_device_key("bad_driver.sys"),
    ]
    real = [n for n in batch if not core.is_crash_synthetic_device_key(n)]
    synth = [n for n in batch if core.is_crash_synthetic_device_key(n)]
    assert real == ["Intel(R) Ethernet Adapter"]
    assert len(synth) == 1
    assert core.is_crash_synthetic_device_key(synth[0])


def test_single_batch_completion_index() -> None:
    """One batch list behaves like the GUI crash-report scheduler (idx 0 -> 1 -> done)."""
    batches = [["dev-a", "dev-b"]]
    batch_idx = 0
    batch = batches[batch_idx]
    batch_idx += 1
    assert batch == ["dev-a", "dev-b"]
    assert batch_idx >= len(batches)


def test_minidump_capture_step_skips_when_admin_and_dumps_ok() -> None:
    with mock.patch.object(core, "is_user_admin", return_value=True):
        assert core.minidump_capture_action_step(needs_config=False) is None


def test_minidump_capture_step_admin_when_dumps_disabled() -> None:
    with mock.patch.object(core, "is_user_admin", return_value=True):
        step = core.minidump_capture_action_step(needs_config=True)
    assert step is not None
    assert "Enable memory dumps" in step
    assert "Run analysis as Administrator" not in step


def test_minidump_capture_step_non_admin() -> None:
    with mock.patch.object(core, "is_user_admin", return_value=False):
        assert core.minidump_capture_action_step(needs_config=False) is not None
        step = core.minidump_capture_action_step(needs_config=True)
    assert step is not None
    assert "Administrator" in step


def test_fix_plan_omits_admin_step_when_elevated_and_dumps_enabled() -> None:
    fix_focus = {"focus": core.FIX_UNCERTAIN, "evidence": []}
    with mock.patch.object(core, "is_user_admin", return_value=True):
        plan = core.build_crash_fix_plan(
            fix_focus,
            code_val=None,
            stop_name="",
            faulting_driver=None,
            windbg_analysis=None,
            system_ctx={"has_amd_chipset": True},
            cause_type=None,
            needs_config=False,
        )
    joined = " ".join(plan.get("steps") or [])
    assert "Run analysis as Administrator" not in joined


if __name__ == "__main__":
    test_crash_synthetic_device_split()
    test_single_batch_completion_index()
    test_minidump_capture_step_skips_when_admin_and_dumps_ok()
    test_minidump_capture_step_admin_when_dumps_disabled()
    test_minidump_capture_step_non_admin()
    test_fix_plan_omits_admin_step_when_elevated_and_dumps_enabled()
    print("Crash report driver batch tests OK")
