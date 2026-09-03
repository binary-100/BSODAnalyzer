"""Minidump stack parsing — actionable frame detection."""

from __future__ import annotations

import bsod_minidump as mdump


def test_first_actionable_skips_kernel_modules() -> None:
    frames = [
        "ntoskrnl!KeBugCheckEx",
        "nt!KiDispatchException",
        "nvlddmkm!nvDumpReg",
        "nvlddmkm!someFunc",
    ]
    assert mdump.first_actionable_stack_frame(frames) == "nvlddmkm!nvDumpReg"


def test_first_actionable_none_when_kernel_only() -> None:
    frames = ["ntoskrnl!KeBugCheckEx", "hal!HalpTimerClockInterrupt"]
    assert mdump.first_actionable_stack_frame(frames) is None


def test_enrich_adds_actionable_stack_frame() -> None:
    parsed = {
        "faulting_driver": "ntoskrnl.exe",
        "stack_frames": [
            "ntoskrnl!KeBugCheckEx",
            "Wdf01000!FxDevice",
        ],
    }
    out = mdump.enrich_windbg_analysis(parsed)
    assert out.get("actionable_stack_frame") == "Wdf01000!FxDevice"
