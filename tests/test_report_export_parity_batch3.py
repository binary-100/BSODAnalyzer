"""Batch 3: report/export parity — derivations shared by GUI and text export."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import bsod_analyzer as core
from gui_test_harness import minimal_fmt_args, report_contains


def _fmt_args_with_crash() -> tuple:
    events = [
        {
            "type": "BugCheck",
            "time": "2025-01-01 12:00:00",
            "code": "0x000000D1",
            "p1": "0x0",
        }
    ]
    windbg = {
        "faulting_driver": "nvlddmkm.sys",
        "dumps_analyzed": 1,
        "bugcheck_str": "DRIVER_IRQL_NOT_LESS_OR_EQUAL",
    }
    fa = list(minimal_fmt_args())
    fa[0] = events
    fa[4] = windbg
    fa[14] = {
        "present_drivers": {"nvlddmkm.sys"},
        "has_sata": True,
        "has_nvme": True,
        "gpu_vendor": "NVIDIA",
    }
    return tuple(fa)


def test_build_report_derivations_matches_display_model_recommendations():
    fa = _fmt_args_with_crash()
    deriv = core.build_report_derivations(fa)
    model = core.build_display_model(fa)
    assert deriv["recommendations"] == model["recommendations"]
    assert deriv["fix_plan"] == model["fix_plan"]
    assert deriv["plain_english"] == model["plain_english"]


def test_format_output_section2_uses_fix_plan_steps():
    fa = _fmt_args_with_crash()
    deriv = core.build_report_derivations(fa)
    report = core.format_output_from_fmt_args(fa, include_technical_details=True)
    assert "2. ACTION PLAN" in report
    first_step = deriv["fix_plan"]["steps"][0]
    assert report_contains(report, first_step)


def test_quick_answer_uses_derivations_plain_english():
    fa = _fmt_args_with_crash()
    deriv = core.build_report_derivations(fa)
    events, _, _, _, windbg, whea, thermal = fa[:7]
    lines, _, fix = core._quick_answer_lines(
        events, windbg, whea, thermal,
        fix_plan=deriv["fix_plan"],
        plain_english_override=deriv["plain_english"],
    )
    text = "\n".join(lines)
    assert deriv["plain_english"][:40] in text
    assert fix == deriv["fix_plan"]["steps"][0]


def test_format_output_from_fmt_args_matches_unpack():
    fa = _fmt_args_with_crash()
    rel = fa[17]
    direct = core.format_output(
        *fa[:17], reliability_ctx=rel, include_technical_details=False
    )
    via_helper = core.format_output_from_fmt_args(fa, include_technical_details=False)
    assert direct == via_helper
