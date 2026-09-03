"""Unit tests for maintenance_log (full-install activity JSONL)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import maintenance_log as mlog


def test_format_events_plain_empty() -> None:
    assert "No maintenance activity" in mlog.format_events_plain([])


def test_format_events_plain_one_row() -> None:
    text = mlog.format_events_plain(
        [{"local_at": "2026-05-01 12:00:00", "kind": "backup", "summary": "Driver backup"}]
    )
    assert "[backup]" in text
    assert "Driver backup" in text


def test_append_and_read_events_full_install() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "maintenance_log.jsonl"
        with mock.patch.object(mlog, "_log_path", return_value=log_path):
            mlog.append_event("test", "hello", detail="line1")
            events = mlog.read_events(limit=10)
            assert len(events) == 1
            assert events[0]["summary"] == "hello"
            assert log_path.is_file()
