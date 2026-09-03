"""Light regression smoke tests (Phase 1 #5 — no GUI launch)."""

from __future__ import annotations

import io

import bsod_analyzer as core
import bsod_runtime as rt
import bsod_workflow as wf
import driver_catalog as drvcat


def test_version_string_present() -> None:
    assert core.VERSION
    parts = core.VERSION.split(".")
    assert len(parts) >= 3


def test_workflow_banners_importable() -> None:
    text = wf.drv_workflow_banner_text(
        full_install=False,
        crash_context=False,
        hardware_ready=True,
        phase="hardware_ready",
    )
    assert "Include" in text


def test_driver_catalog_multi_device_has_no_cap() -> None:
    assert not hasattr(drvcat, "max_batch_driver_devices")


def test_minidump_gap_helper_exported() -> None:
    assert hasattr(core, "minidump_without_bugcheck_gap")


def test_console_print_survives_cp1252() -> None:
    """CLI report text uses arrows and dashes; must not crash on Windows consoles."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    sample = "Call stack: nvlddmkm.sys → ntoskrnl.exe → …"
    rt.console_print(sample, file=stream, flush=True)
    stream.detach()
    body = raw.getvalue().decode("cp1252", errors="replace")
    assert "Call stack" in body
    assert "nvlddmkm" in body


if __name__ == "__main__":
    test_version_string_present()
    test_workflow_banners_importable()
    test_driver_catalog_multi_device_has_no_cap()
    test_minidump_gap_helper_exported()
    test_console_print_survives_cp1252()
    print("Regression smoke tests OK")
