"""Workflow gating (full install vs portable crash-first)."""

from __future__ import annotations

import bsod_workflow as wf


def test_crash_details_refresh_requires_full_install_and_context() -> None:
    model, fmt = {"driver": "x.sys"}, (1,)
    assert wf.should_refresh_crash_details_after_hardware(
        full_install=True,
        model=model,
        fmt_args=fmt,
        hardware_ready=True,
    )
    assert not wf.should_refresh_crash_details_after_hardware(
        full_install=False,
        model=model,
        fmt_args=fmt,
        hardware_ready=True,
    )
    assert not wf.should_refresh_crash_details_after_hardware(
        full_install=True,
        model=None,
        fmt_args=fmt,
        hardware_ready=True,
    )
    assert not wf.should_refresh_crash_details_after_hardware(
        full_install=True,
        model=model,
        fmt_args=fmt,
        hardware_ready=False,
    )


def test_drv_banner_full_install_phase() -> None:
    text = wf.drv_workflow_banner_text(
        full_install=True,
        crash_context=False,
        hardware_ready=True,
        phase="full_install",
    )
    assert "search for updates" in text.lower()
    assert "Include" in text


def test_drv_banner_hardware_ready_uses_include() -> None:
    text = wf.drv_workflow_banner_text(
        full_install=False,
        crash_context=False,
        hardware_ready=True,
        phase="hardware_ready",
    )
    assert "Include" in text
    assert "common/uncommon" not in text.lower()


def test_manual_queue_status_generic_busy() -> None:
    text = wf.drv_manual_queue_status_text(
        queued_devices=2,
        queued_jobs=1,
        block_reason=wf.drv_manual_queue_block_reason(),
        generic_driver_busy=True,
    )
    assert "2 device(s) queued" in text
    assert "current catalog check" in text


def test_manual_queue_block_reason_always_none() -> None:
    assert wf.drv_manual_queue_block_reason() is None
    text = wf.drv_manual_queue_status_text(
        queued_devices=3,
        queued_jobs=2,
        block_reason=None,
        generic_driver_busy=True,
    )
    assert "current catalog check" in text
    assert "2 searches in queue" in text


def test_fw_banner_failed_phase() -> None:
    text = wf.fw_workflow_banner_text(
        full_install=True,
        crash_context=True,
        hardware_ready=True,
        phase="failed",
    )
    assert "failed" in text.lower()
    assert "complete" not in text.lower()


def test_fw_banner_no_combined_prompt() -> None:
    text = wf.fw_workflow_banner_text(
        full_install=True,
        crash_context=True,
        hardware_ready=True,
        phase="",
    )
    assert "combined prompt" not in text.lower()
    assert "Search for updates" in text


if __name__ == "__main__":
    test_crash_details_refresh_requires_full_install_and_context()
    test_drv_banner_full_install_phase()
    test_drv_banner_hardware_ready_uses_include()
    test_manual_queue_status_generic_busy()
    test_manual_queue_block_reason_always_none()
    test_fw_banner_failed_phase()
    test_fw_banner_no_combined_prompt()
    print("Workflow gating tests OK")
