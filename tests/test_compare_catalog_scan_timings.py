"""Tests for compare_catalog_scan_timings.py (read-only log parser)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.compare_catalog_scan_timings import (
    ScanRun,
    TimingStats,
    build_report,
    filter_runs,
    load_full_scans,
)


def _write_log(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_load_full_scans_min_devices(tmp_path: Path) -> None:
    log = tmp_path / "session_log.jsonl"
    _write_log(
        log,
        [
            {
                "kind": "driver_catalog",
                "phase": "end",
                "local_at": "2026-07-19 16:08:21",
                "elapsed_ms": 1_226_792,
                "message": "Checked 152 device(s); 3 update(s) available",
                "status": "ok",
            },
            {
                "kind": "driver_catalog",
                "phase": "end",
                "local_at": "2026-07-28 00:17:42",
                "elapsed_ms": 101_662,
                "message": "Checked 5 device(s); 2 update(s) available",
                "status": "ok",
            },
        ],
    )
    runs = load_full_scans(log, min_devices=140)
    assert len(runs) == 1
    assert runs[0].devices == 152
    assert runs[0].elapsed_ms == 1_226_792


def test_filter_before_after() -> None:
    runs = [
        ScanRun("2026-07-19 16:08:21", 152, 1_000_000, "ok", 3),
        ScanRun("2026-07-21 16:49:17", 152, 400_000, "ok", 2),
    ]
    before = filter_runs(runs, before="2026-07-21")
    assert len(before) == 1
    assert before[0].local_at.startswith("2026-07-19")
    after = filter_runs(runs, after="2026-07-21")
    assert len(after) == 1
    assert after[0].local_at.startswith("2026-07-21")


def test_build_report_compare(tmp_path: Path) -> None:
    log = tmp_path / "session_log.jsonl"
    _write_log(
        log,
        [
            {
                "kind": "driver_catalog",
                "phase": "end",
                "local_at": "2026-07-19 16:08:21",
                "elapsed_ms": 1_200_000,
                "message": "Checked 152 device(s); 3 update(s) available",
                "status": "ok",
            },
            {
                "kind": "driver_catalog",
                "phase": "end",
                "local_at": "2026-07-21 16:49:17",
                "elapsed_ms": 250_000,
                "message": "Checked 152 device(s); 2 update(s) available",
                "status": "ok",
            },
        ],
    )
    runs = load_full_scans(log)
    report = build_report(
        runs,
        before="2026-07-21",
        after=None,
        last=None,
        min_devices=140,
        log_path=log,
    )
    assert report["compare"]["before"]["p50_min"] == 20.0
    assert report["compare"]["on_or_after"]["p50_min"] == 4.17
    assert report["compare"]["p50_delta_min"] < 0


def test_timing_stats_empty() -> None:
    assert TimingStats.from_runs([]) is None


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tp = Path(tmp)
        test_load_full_scans_min_devices(tp)
        test_build_report_compare(tp)
    test_filter_before_after()
    test_timing_stats_empty()
    print("OK")
