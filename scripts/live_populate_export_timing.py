"""Time GUI populate + export after a completed firmware scan (no network)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    from bsod_hardware_wmi import get_hardware_profile_wmi_bundle, get_ssd_firmware_inventory
    import firmware_peripheral_discovery as fpdisc
    from tests.gui_test_harness import isolated_settings, offscreen_application
    from gui_mixin_catalog import ExportFileChoices
    import bsod_gui_qt as gui
    import bsod_analyzer as core

    t0 = time.monotonic()
    prof = get_hardware_profile_wmi_bundle()
    ssd = get_ssd_firmware_inventory()
    secondary = fpdisc.discover_secondary_firmware_devices(
        prof.get("pnp_list") or [],
        prof.get("drivers") or [],
        query_pnp_firmware=True,
        has_bios=True,
    )
    t_data = time.monotonic()

    report: dict = {"app_version": core.VERSION, "phases": {}}

    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                win = gui.MainWindow()
                win._hardware_profile = prof
                win._hardware_profile["ssd_firmware"] = ssd
                win._hardware_profile["secondary_firmware"] = secondary
                win._ssd_firmware_loaded = True
                win._firmware_comparison = {
                    "fetched_at": "live-test",
                    "offers": [
                        {
                            "kind": "bios",
                            "version": "1.27.0",
                            "vs_installed": "same",
                            "source_label": "OEM",
                            "title": "BIOS",
                        }
                    ],
                    "target_keys": ["bios"],
                }
                win.tabs.setCurrentIndex(win._firmware_tab_index())

                t1 = time.monotonic()
                win._populate_firmware_tab(load_support_links=False)
                t2 = time.monotonic()

                out_dir = Path(tmp) / "export"
                out_dir.mkdir()
                choices = ExportFileChoices(
                    include_crash_report=False,
                    include_catalog_summary=True,
                    include_catalog_json=True,
                )
                t3 = time.monotonic()
                payload = win._build_catalog_export_payload(redact_sensitive=False)
                t4 = time.monotonic()
                files, summary = win._write_session_export_files(
                    out_dir,
                    catalog_payload=payload,
                    choices=choices,
                )
                t5 = time.monotonic()

                report["phases"] = {
                    "hardware_fetch_ms": int((t_data - t0) * 1000),
                    "populate_ms": int((t2 - t1) * 1000),
                    "export_build_ms": int((t4 - t3) * 1000),
                    "export_write_ms": int((t5 - t4) * 1000),
                    "total_ms": int((t5 - t0) * 1000),
                }
                report["search_enabled"] = win.fw_btn_check.isEnabled()
                report["search_primary"] = win.fw_btn_check.objectName()
                report["export_files"] = [p.name for _, p in files]
                win._shutting_down = True

    out = ROOT / "live_populate_export_timing.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"JSON: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
