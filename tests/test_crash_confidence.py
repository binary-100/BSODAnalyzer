"""Crash confidence ladder and Action Plan merge helpers."""

from __future__ import annotations

import bsod_analyzer as core


def test_confidence_verified_when_dump_matches() -> None:
    events = [{"type": "BugCheck", "code": "0x0A", "time": "2026-08-09 12:00:00"}]
    windbg = {"faulting_driver": "nvlddmkm.sys", "dump_time": "2026-08-09 12:00:00"}
    conf = core.build_crash_confidence_summary(events, windbg, needs_config=False, has_bugcheck=True)
    assert conf["level"] == "verified"
    assert conf["can_name_faulting_driver"]


def test_merge_verification_action_steps_dedupes() -> None:
    merged = core.merge_verification_action_steps(
        {"action_plan_steps": ["Check chipset drivers"]},
        ["Check chipset drivers", "Run memtest"],
    )
    assert merged == ["Check chipset drivers", "Run memtest"]


if __name__ == "__main__":
    test_confidence_verified_when_dump_matches()
    test_merge_verification_action_steps_dedupes()
    print("crash confidence tests OK")
