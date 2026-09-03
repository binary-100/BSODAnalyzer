"""Tests for timestamped session_log.jsonl."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import session_log as slog


def test_session_log_begin_end_records_elapsed(tmp_path: Path) -> None:
    with patch.object(slog, "_log_dir", return_value=tmp_path):
        token = slog.begin("hardware_scan", "Scan started")
        slog.progress("hardware_scan", "Reading WMI…")
        slog.end(token, "hardware_scan", "Scan finished")

    lines = (tmp_path / "session_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    start = json.loads(lines[0])
    progress = json.loads(lines[1])
    end = json.loads(lines[2])
    assert start["phase"] == "start"
    assert "local_at" in start
    assert "T" in start["at"]
    assert progress["phase"] == "progress"
    assert end["phase"] == "end"
    assert isinstance(end.get("elapsed_ms"), int)
    assert end["elapsed_ms"] >= 0


def test_session_log_end_returns_elapsed(tmp_path: Path) -> None:
    with patch.object(slog, "_log_dir", return_value=tmp_path):
        token = slog.begin("driver_catalog", "Search started")
        elapsed = slog.end(token, "driver_catalog", "Search finished")
    assert isinstance(elapsed, int)
    assert elapsed >= 0


def test_session_log_progress_includes_since_start(tmp_path: Path) -> None:
    with patch.object(slog, "_log_dir", return_value=tmp_path):
        token = slog.begin("driver_catalog", "Search started")
        slog.progress("driver_catalog", "145/152 device(s)")
        slog.end(token, "driver_catalog", "Search finished")

    lines = (tmp_path / "session_log.jsonl").read_text(encoding="utf-8").splitlines()
    progress = json.loads(lines[1])
    assert progress["phase"] == "progress"
    assert isinstance(progress.get("since_start_ms"), int)
    assert progress["since_start_ms"] >= 0
    assert "." in progress.get("local_at", "")


def test_format_events_shows_elapsed_seconds() -> None:
    text = slog.format_events_plain([
        {
            "local_at": "2026-07-19 15:30:00",
            "kind": "load_devices",
            "phase": "end",
            "message": "Loaded 120 device(s)",
            "elapsed_ms": 4500,
        }
    ])
    assert "15:30:00" in text
    assert "4.5 s" in text


def test_log_path_portable_uses_temp_subfolder(tmp_path: Path) -> None:
    with patch.object(slog.app_set, "allows_persistent_driver_data", return_value=False):
        with patch.dict("os.environ", {"TEMP": str(tmp_path)}, clear=False):
            path = slog.log_path()
    assert path.parent.name == "BSODAnalyzer"
    assert path.name == "session_log.jsonl"


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_session_log_begin_end_records_elapsed(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_session_log_end_returns_elapsed(Path(tmp))
    test_format_events_shows_elapsed_seconds()
    with tempfile.TemporaryDirectory() as tmp:
        test_log_path_portable_uses_temp_subfolder(Path(tmp))
    print("OK")
