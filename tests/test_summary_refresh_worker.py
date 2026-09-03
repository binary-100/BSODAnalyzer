"""Unit test for summary refresh merge + build_display_model (no GUI)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import bsod_analyzer as core
import bsod_workflow as wf
from gui_test_harness import minimal_fmt_args


def test_build_display_model_after_hardware_merge() -> None:
    prof = {
        "bios_driver_info": {"drivers": [{"name": "NIC", "version": "1"}]},
        "system_ctx": {"pnp_list": [{"name": "NIC"}]},
        "devices_with_driver_problems": [],
        "devices_with_generic_driver": [],
    }
    merged = wf.merge_hardware_into_fmt_args(minimal_fmt_args(), prof)
    model = core.build_display_model(merged)
    assert model.get("plain_english")
    assert model.get("severity_name")


if __name__ == "__main__":
    test_build_display_model_after_hardware_merge()
    print("summary refresh worker tests OK")
