"""Unit tests for qt_isolated_runner pass detection."""

from __future__ import annotations

from qt_isolated_runner import pytest_reported_all_passed


def test_detects_quiet_mode_full_pass() -> None:
    out = "..                                                                       [100%]\n"
    assert pytest_reported_all_passed(out)


def test_detects_verbose_pass_line() -> None:
    out = "2 passed in 2.66s\n"
    assert pytest_reported_all_passed(out)


def test_rejects_failed_run() -> None:
    out = "..F                                                                      [100%]\n"
    assert not pytest_reported_all_passed(out)


def test_rejects_failed_summary() -> None:
    out = "1 failed, 1 passed in 0.5s\n"
    assert not pytest_reported_all_passed(out)


def test_accepts_pass_after_teardown_crash_note() -> None:
    out = "..                                                                       [100%]\nWindows fatal exception: access violation\n"
    assert pytest_reported_all_passed(out)


def test_rejects_empty_child_output() -> None:
    assert not pytest_reported_all_passed("")
