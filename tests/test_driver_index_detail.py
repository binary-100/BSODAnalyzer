"""Driver index detail and pipeline helper regression tests."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import driver_index as drvidx


def test_clamp_detail_matches_batch_cap() -> None:
    big = "x" * 60_000
    clamped = drvidx._clamp_detail(big)
    assert len(clamped) == drvidx._MAX_DETAIL_LEN
    assert len(big) > drvidx._MAX_DETAIL_LEN


def test_sqlite_roundtrip_preserves_offers_json() -> None:
    offers = [
        {
            "source": "microsoft",
            "source_label": "Microsoft",
            "version": "31.0.15.4601",
            "vs_installed": "newer",
            "title": "NVIDIA Display Driver",
        }
    ]
    detail = json.dumps({"offers": offers}, ensure_ascii=False)
    assert len(detail) < drvidx._MAX_DETAIL_LEN

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test_index.sqlite"
        con = sqlite3.connect(str(db))
        con.executescript(drvidx._SCHEMA)
        con.execute(
            """
            INSERT INTO device_checks
            (device_key, device_name, installed_version, status, checked_at, fetched_at, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test-gpu",
                "Test GPU",
                "30.0.1.0",
                "newer",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
                drvidx._clamp_detail(detail),
            ),
        )
        con.commit()
        row = con.execute(
            "SELECT detail FROM device_checks WHERE device_key = ?",
            ("test-gpu",),
        ).fetchone()
        con.close()

    assert row is not None
    payload = json.loads(row[0])
    assert len(payload.get("offers") or []) == 1
    assert payload["offers"][0]["version"] == "31.0.15.4601"


def test_record_batch_detail_not_truncated_to_500() -> None:
    offers = [{"source": "oem", "version": "9.9.9", "title": "t" * 2000}]
    detail = json.dumps({"offers": offers})
    clamped = drvidx._clamp_detail(detail)
    assert len(clamped) > 500


if __name__ == "__main__":
    test_clamp_detail_matches_batch_cap()
    test_sqlite_roundtrip_preserves_offers_json()
    test_record_batch_detail_not_truncated_to_500()
    print("Driver index detail tests OK")
