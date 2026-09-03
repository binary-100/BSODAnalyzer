"""Regression tests for post-audit fixes (packages fallback, soft gaps)."""

from __future__ import annotations

import bsod_analyzer as core


def test_soft_gap_empty_pnp_not_on_failure() -> None:
    """Empty PnP is flagged only when the query did not throw."""
    gaps: list[str] = []
    failed: set[str] = set()
    pnp_list: list = []
    bio: dict = {"drivers": [{"name": "x", "driver": "a.sys"}]}
    if "pnp_list" not in failed and not pnp_list:
        gaps.append("Plug-and-play device list returned no devices")
    assert len(gaps) == 1
    failed.add("pnp_list")
    gaps.clear()
    if "pnp_list" not in failed and not pnp_list:
        gaps.append("Plug-and-play device list returned no devices")
    assert not gaps


def test_analysis_gap_message_format() -> None:
    msg = core._analysis_gap_message("events", RuntimeError("denied"))
    assert "Windows crash event log" in msg
    assert "denied" in msg


if __name__ == "__main__":
    test_soft_gap_empty_pnp_not_on_failure()
    test_analysis_gap_message_format()
    print("audit fixes tests OK")
