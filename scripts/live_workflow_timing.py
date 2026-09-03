"""Live timing — firmware load, tab refresh, export (same code paths as the GUI).

Run from app root:
  py -3 scripts/live_workflow_timing.py
  py -3 scripts/live_workflow_timing.py --with-search
  py -3 scripts/live_workflow_timing.py --with-export

Writes live_workflow_timing.json with phase timestamps and deltas.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Offscreen Qt before gui import.
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _mono() -> float:
    return time.monotonic()


def _ms(start: float, end: float | None = None) -> int:
    return int(((end if end is not None else _mono()) - start) * 1000)


def _snap(win, label: str, events: list[dict]) -> None:
    load_running = bool(
        win._ssd_fw_thread is not None and win._ssd_fw_thread.isRunning()
    )
    fw_search_running = bool(
        win._fw_thread is not None and win._fw_thread.isRunning()
    )
    export_running = win._catalog_export_job.is_running()
    search_enabled = (
        win.fw_btn_check.isEnabled() if hasattr(win, "fw_btn_check") else None
    )
    load_enabled = (
        win.fw_btn_scan_components.isEnabled()
        if hasattr(win, "fw_btn_scan_components")
        else None
    )
    search_primary = (
        win.fw_btn_check.objectName() == "Primary"
        if hasattr(win, "fw_btn_check")
        else None
    )
    load_primary = (
        win.fw_btn_scan_components.objectName() == "Primary"
        if hasattr(win, "fw_btn_scan_components")
        else None
    )
    status = win.statusBar().currentMessage() if hasattr(win, "statusBar") else ""
    prog_vis = (
        win._task_progress_frame.isVisible()
        if hasattr(win, "_task_progress_frame")
        else None
    )
    row_count = (
        win.fw_unified_table.rowCount() if hasattr(win, "fw_unified_table") else 0
    )
    events.append(
        {
            "t_ms": _ms(events[0]["t0"]),
            "label": label,
            "load_thread": load_running,
            "fw_search_thread": fw_search_running,
            "export_job": export_running,
            "search_enabled": search_enabled,
            "load_enabled": load_enabled,
            "search_primary": search_primary,
            "load_primary": load_primary,
            "progress_visible": prog_vis,
            "table_rows": row_count,
            "ssd_loaded_flag": bool(getattr(win, "_ssd_firmware_loaded", False)),
            "status": status[:120],
        }
    )


def _wait_until(
    win,
    events: list[dict],
    predicate,
    *,
    timeout_s: float,
    poll_label: str,
) -> bool:
    deadline = _mono() + timeout_s
    last_poll = 0.0
    while _mono() < deadline:
        if predicate():
            return True
        now = _mono()
        if now - last_poll >= 0.25:
            _snap(win, poll_label, events)
            last_poll = now
        from PySide6 import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents()
        QtCore.QThread.msleep(50)
    return bool(predicate())


def _time_worker_phases() -> dict:
    from bsod_hardware_wmi import get_hardware_profile_wmi_bundle, get_ssd_firmware_inventory
    import firmware_peripheral_discovery as fpdisc

    out: dict = {}
    t0 = _mono()
    prof = get_hardware_profile_wmi_bundle()
    out["wmi_profile_ms"] = _ms(t0)
    if not prof:
        out["error"] = "WMI profile unavailable"
        return out

    pnp = prof.get("pnp_list") or []
    drivers = prof.get("drivers") or []
    out["pnp_count"] = len(pnp)
    out["driver_count"] = len(drivers)

    t1 = _mono()
    ssd = get_ssd_firmware_inventory()
    out["ssd_inventory_ms"] = _ms(t1)
    out["ssd_count"] = len(ssd)

    t2 = _mono()
    secondary = fpdisc.discover_secondary_firmware_devices(
        pnp, drivers, query_pnp_firmware=True, has_bios=True
    )
    out["secondary_discovery_ms"] = _ms(t2)
    out["secondary_count"] = len(secondary)

    out["worker_total_ms"] = _ms(t0)
    return out


def _run_gui_workflow(*, with_search: bool, with_export: bool) -> dict:
    from PySide6 import QtCore, QtWidgets
    from tests.gui_test_harness import isolated_settings, offscreen_application

    import bsod_gui_qt as gui

    report: dict = {"phases": {}, "timeline": []}
    t_session = _mono()
    events: list[dict] = [{"t0": t_session}]

    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                win = gui.MainWindow()
                win.show()

                # Real hardware profile (same as post-scan state).
                from bsod_hardware_wmi import get_hardware_profile_wmi_bundle

                prof = get_hardware_profile_wmi_bundle()
                if not prof:
                    report["error"] = "No WMI profile for GUI test"
                    return report
                win._hardware_profile = prof
                win._last_model = win._last_model or {}

                idx = win._firmware_tab_index()
                if idx >= 0:
                    win.tabs.setCurrentIndex(idx)

                _snap(win, "gui_ready", events)

                # --- Load components (step 1) ---
                t_load = _mono()
                win._on_scan_for_components()
                _snap(win, "load_clicked", events)

                loaded = _wait_until(
                    win,
                    events,
                    lambda: bool(win._ssd_firmware_loaded),
                    timeout_s=180.0,
                    poll_label="poll_load",
                )
                t_loaded = _mono()
                report["phases"]["load_to_flag_ms"] = _ms(t_load, t_loaded)
                _snap(win, "load_flag_set", events)

                search_ready = _wait_until(
                    win,
                    events,
                    lambda: win.fw_btn_check.isEnabled(),
                    timeout_s=60.0,
                    poll_label="poll_search_enable",
                )
                t_search_ready = _mono()
                report["phases"]["load_to_search_enabled_ms"] = _ms(t_load, t_search_ready)
                report["phases"]["flag_to_search_enabled_ms"] = _ms(t_loaded, t_search_ready)
                _snap(win, "search_enabled", events)

                thread_clear = _wait_until(
                    win,
                    events,
                    lambda: win._ssd_fw_thread is None
                    or not win._ssd_fw_thread.isRunning(),
                    timeout_s=30.0,
                    poll_label="poll_thread_cleanup",
                )
                t_thread_done = _mono()
                report["phases"]["load_to_thread_cleanup_ms"] = _ms(t_load, t_thread_done)
                _snap(win, "thread_cleanup", events)

                report["load_ok"] = loaded
                report["search_ready_ok"] = search_ready
                report["thread_cleanup_ok"] = thread_clear

                # --- Optional firmware search (step 2) ---
                if with_search and search_ready:
                    keys = win._fw_checked_target_keys()
                    report["search_target_keys"] = keys
                    t_search = _mono()
                    win._on_check_firmware_catalog()
                    _snap(win, "search_clicked", events)

                    search_done = _wait_until(
                        win,
                        events,
                        lambda: win._fw_thread is None
                        or not win._fw_thread.isRunning(),
                        timeout_s=300.0,
                        poll_label="poll_fw_search",
                    )
                    report["phases"]["fw_search_ms"] = _ms(t_search)
                    report["fw_search_ok"] = search_done
                    _snap(win, "search_done", events)

                # --- Optional export ---
                if with_export:
                    export_dir = Path(tmp) / "export_out"
                    export_dir.mkdir()
                    from gui_mixin_catalog import ExportFileChoices

                    choices = ExportFileChoices(
                        include_crash_report=False,
                        include_catalog_summary=True,
                        include_catalog_json=True,
                    )
                    win._unified_export_dest_dir = str(export_dir)
                    win._unified_export_choices = choices
                    t_export = _mono()
                    win._begin_task_progress("Saving export…", maximum=0)

                    from bsod_gui_workers import CatalogExportWorker

                    def _export_task() -> dict:
                        payload = win._build_catalog_export_payload(
                            redact_sensitive=False
                        )
                        file_entries, summary = win._write_session_export_files(
                            str(export_dir),
                            catalog_payload=payload,
                            choices=choices,
                        )
                        return {
                            "file_entries": file_entries,
                            "summary": summary,
                            "catalog_payload": payload,
                        }

                    worker = CatalogExportWorker(_export_task)
                    win._catalog_export_job.start(
                        worker,
                        connections=[
                            (worker.finished, win._on_catalog_export_ready),
                            (worker.failed, win._on_catalog_export_failed),
                        ],
                    )
                    _snap(win, "export_started", events)

                    export_done = _wait_until(
                        win,
                        events,
                        lambda: not win._catalog_export_job.is_running(),
                        timeout_s=120.0,
                        poll_label="poll_export",
                    )
                    files = list(export_dir.glob("BSODAnalyzer_*"))
                    report["phases"]["export_job_ms"] = _ms(t_export)
                    report["export_ok"] = export_done
                    report["export_files"] = [p.name for p in files]
                    report["export_files_on_disk_during_run"] = len(files)
                    _snap(win, "export_done", events)

                report["phases"]["gui_session_total_ms"] = _ms(t_session)
                report["timeline"] = events[1:]

                win._shutting_down = True
                for attr in (
                    "_ssd_fw_thread",
                    "_fw_thread",
                    "_hw_thread",
                    "_ctx_thread",
                ):
                    th = getattr(win, attr, None)
                    if th is not None and th.isRunning():
                        th.quit()
                        th.wait(3000)

    return report


def _time_firmware_search(prof: dict, ssd: list, secondary: list) -> dict:
    import driver_catalog as dc
    import firmware_catalog as fwcat

    pnp = prof.get("pnp_list") or []
    keys = ["bios"]
    for d in ssd:
        keys.append(f"ssd:{d.get('model')}")
    for d in secondary[:8]:
        k = d.get("key")
        if k:
            keys.append(k)
    progress: list[dict] = []
    t3 = _mono()
    dc.set_gui_catalog_session(True)
    try:

        def prog(m: str) -> None:
            progress.append({"t_ms": _ms(t3), "msg": (m or "")[:80]})

        result = fwcat.build_firmware_comparison(
            (prof.get("bios_driver_info") or {}).get("bios"),
            prof,
            pnp,
            ssd,
            progress=prog,
            target_keys=keys,
            secondary_firmware=secondary,
        )
    finally:
        dc.set_gui_catalog_session(False)
    return {
        "fw_search_ms": _ms(t3),
        "target_keys": keys,
        "offer_count": len(result.get("offers") or []),
        "progress_tail": progress[-10:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Live GUI workflow timing")
    parser.add_argument(
        "--with-search",
        action="store_true",
        help="Also run firmware catalog search after load",
    )
    parser.add_argument(
        "--with-export",
        action="store_true",
        help="Also run catalog export after load/search",
    )
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="Skip GUI; time worker + firmware catalog search only",
    )
    args = parser.parse_args()

    import bsod_analyzer as core

    print("=" * 70)
    print(f"Live workflow timing — BSOD Analyzer v{core.VERSION}")
    print("=" * 70)

    worker = _time_worker_phases()
    print("\n[Worker phases — no GUI]")
    for k, v in worker.items():
        print(f"  {k}: {v}")

    search_report: dict | None = None
    if args.with_search or args.search_only:
        from bsod_hardware_wmi import get_hardware_profile_wmi_bundle, get_ssd_firmware_inventory
        import firmware_peripheral_discovery as fpdisc

        prof = get_hardware_profile_wmi_bundle() or {}
        ssd = get_ssd_firmware_inventory()
        secondary = fpdisc.discover_secondary_firmware_devices(
            prof.get("pnp_list") or [],
            prof.get("drivers") or [],
            query_pnp_firmware=True,
            has_bios=True,
        )
        print("\n[Firmware catalog search — no GUI]")
        search_report = _time_firmware_search(prof, ssd, secondary)
        for k, v in search_report.items():
            if k != "progress_tail":
                print(f"  {k}: {v}")

    if args.search_only:
        out = ROOT / "live_workflow_timing.json"
        out.write_text(
            json.dumps(
                {
                    "app_version": core.VERSION,
                    "worker": worker,
                    "search": search_report,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON: {out}")
        return 0

    print("\n[GUI workflow — offscreen, real hardware]")
    gui = _run_gui_workflow(
        with_search=args.with_search,
        with_export=args.with_export or args.with_search,
    )
    phases = gui.get("phases") or {}
    for k, v in phases.items():
        print(f"  {k}: {v} ms")
    print(f"  load_ok: {gui.get('load_ok')}")
    print(f"  search_ready_ok: {gui.get('search_ready_ok')}")
    print(f"  thread_cleanup_ok: {gui.get('thread_cleanup_ok')}")
    if "fw_search_ok" in gui:
        print(f"  fw_search_ok: {gui.get('fw_search_ok')}")
    if "export_ok" in gui:
        print(f"  export_ok: {gui.get('export_ok')}")
        print(f"  export_files: {gui.get('export_files')}")

    # Highlight gaps where UI looked done but search wasn't ready.
    timeline = gui.get("timeline") or []
    gaps = []
    for i, ev in enumerate(timeline):
        if ev.get("label") == "load_flag_set" and not ev.get("search_enabled"):
            # find when search became enabled
            for later in timeline[i:]:
                if later.get("search_enabled"):
                    gaps.append(
                        {
                            "from": ev.get("label"),
                            "gap_ms": later["t_ms"] - ev["t_ms"],
                            "status_at_gap_start": ev.get("status"),
                            "load_thread_at_start": ev.get("load_thread"),
                        }
                    )
                    break
            else:
                gaps.append(
                    {
                        "from": ev.get("label"),
                        "gap_ms": None,
                        "note": "search never enabled in timeline",
                    }
                )
    if gaps:
        print("\n[Search-enable gap after load flag]")
        for g in gaps:
            print(f"  {g}")

    out = ROOT / "live_workflow_timing.json"
    payload = {
        "app_version": core.VERSION,
        "worker": worker,
        "search": search_report,
        "gui": gui,
        "search_enable_gaps": gaps,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nJSON: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
