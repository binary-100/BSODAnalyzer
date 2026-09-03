"""Tests for fix-progress notes (driver dated after last BSOD)."""
from __future__ import annotations

from datetime import datetime, timezone

import fix_progress as fp


def test_parse_last_crash_time() -> None:
    """The label is local wall-clock time; a legacy ` UTC` suffix reads the same."""
    dt = fp.parse_last_crash_time("2026-05-28 14:32")
    assert dt is not None
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2026, 5, 28, 14, 32)
    assert dt.tzinfo is not None, "crash time must be timezone-aware"
    assert fp.parse_last_crash_time("2026-05-28 14:32 UTC") == dt


def test_fix_progress_note_after_crash() -> None:
    crash = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    dev = {
        "name": "NVIDIA GeForce RTX 4080",
        "version": "610.62",
        "date": "2026-06-16",
    }
    note = fp.fix_progress_note(
        dev,
        last_crash_dt=crash,
        last_crash_label="2026-05-20 10:00 UTC",
    )
    assert note is not None
    assert "2026-06-16" in note
    assert "610.62" in note
    assert "2026-05-20" in note


def test_fix_progress_note_before_crash() -> None:
    crash = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)
    dev = {
        "name": "NVIDIA GeForce RTX 4080",
        "version": "581.42",
        "date": "2025-01-10",
    }
    assert fp.fix_progress_note(dev, last_crash_dt=crash) is None


def test_resolve_last_crash_from_model() -> None:
    label, dt = fp.resolve_last_crash({"last_crash": "2026-05-28 14:32 UTC"})
    assert label == "2026-05-28 14:32 UTC"
    assert dt is not None


if __name__ == "__main__":
    test_parse_last_crash_time()
    test_fix_progress_note_after_crash()
    test_fix_progress_note_before_crash()
    test_resolve_last_crash_from_model()
    print("fix_progress tests OK")
