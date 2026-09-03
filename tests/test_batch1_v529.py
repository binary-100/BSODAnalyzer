"""Batch 1 (v5.2.29): migration retry, event-log failure gaps, shutdown guards."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bsod_analyzer as core
import bsod_events as events_mod
import driver_index as drv_index


def test_migration_retries_when_legacy_json_invalid(tmp_path: Path) -> None:
    data_dir = tmp_path / "appdata"
    data_dir.mkdir()
    legacy = data_dir / "check_cache.json"
    legacy.write_text("{not valid json", encoding="utf-8")
    drv_index._reset_session_flags()
    with (
        mock.patch("driver_index.app_set.full_install_data_dir", return_value=data_dir),
        mock.patch("driver_index.app_set.allows_persistent_driver_data", return_value=True),
    ):
        assert drv_index.migrate_legacy_check_cache() is False
        calls: list[int] = []

        def _fail_once() -> bool:
            calls.append(1)
            return False

        with mock.patch.object(drv_index, "migrate_legacy_check_cache", side_effect=_fail_once):
            drv_index._reset_session_flags()
            drv_index._ensure_migrated()
            drv_index._ensure_migrated()
            assert len(calls) == 2


def test_query_bugcheck_events_reports_failure() -> None:
    with mock.patch(
        "bsod_events.run_powershell",
        return_value=(False, "Query timed out."),
    ):
        ev, failed = events_mod.query_bugcheck_events()
    assert ev == []
    assert failed is True


def test_query_bugcheck_events_ok_empty_log() -> None:
    payload = json.dumps({"Events1001": [], "Events41": [], "Events6008": []})
    with mock.patch("bsod_events.run_powershell", return_value=(True, payload)):
        ev, failed = events_mod.query_bugcheck_events()
    assert failed is False
    assert ev == []


def test_list_dumps_permission_raises_clear_message(tmp_path: Path) -> None:
    blocked = tmp_path / "Minidump"
    blocked.mkdir()
    with mock.patch("bsod_analyzer.os.listdir", side_effect=PermissionError("denied")):
        try:
            core.list_dumps(str(blocked), "Kernel")
            assert False, "expected PermissionError"
        except PermissionError as exc:
            assert "Administrator" in str(exc)
            assert "Minidump" in str(exc) or str(blocked) in str(exc)


def test_events_query_failed_adds_data_gap() -> None:
    with mock.patch(
        "bsod_analyzer.query_bugcheck_events",
        return_value=([], True),
    ), mock.patch(
        "bsod_analyzer.get_logged_in_user_paths",
        return_value=("user", r"C:\CrashDumps", [r"C:\CrashDumps"]),
    ), mock.patch(
        "bsod_analyzer.list_dumps",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.check_full_dump",
        return_value=None,
    ), mock.patch(
        "bsod_analyzer.list_dumps_from_paths",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.query_application_crashes",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.get_bios_and_driver_versions",
        return_value={},
    ), mock.patch(
        "bsod_analyzer.get_dump_config",
        return_value=(1, "Small memory dump (minidump)"),
    ), mock.patch(
        "bsod_analyzer.find_cdb",
        return_value=None,
    ), mock.patch(
        "bsod_analyzer.query_whea_hardware_errors",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.query_thermal_events",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.get_pnp_entities_for_analysis",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.get_storage_and_system_context",
        return_value={},
    ), mock.patch(
        "bsod_analyzer.query_reliability_livekernel_bundle",
        return_value={"livekernel": [], "wer_errors": [], "stability_index": None},
    ), mock.patch(
        "bsod_analyzer.get_all_installed_driver_devices",
        return_value=[],
    ):
        fmt_args, _needs = core.gather_report_data(include_reliability=False)
    system_ctx = fmt_args[14] if len(fmt_args) > 14 else {}
    gaps = system_ctx.get("data_gaps") or []
    assert any("event log" in g.lower() and "administrator" in g.lower() for g in gaps)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_migration_retries_when_legacy_json_invalid(Path(tmp))
        test_list_dumps_permission_raises_clear_message(Path(tmp))
    test_query_bugcheck_events_reports_failure()
    test_query_bugcheck_events_ok_empty_log()
    test_events_query_failed_adds_data_gap()
    print("Batch 1 (v5.2.29) tests OK")
