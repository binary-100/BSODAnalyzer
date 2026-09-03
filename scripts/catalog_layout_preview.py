"""Compare catalog tab layout presets using the real BSOD Analyzer UI.

Interactive (on-screen window):
  py -3 scripts/catalog_layout_preview.py

Capture PNG screenshots for each preset (Drivers + Firmware tabs):
  py -3 scripts/catalog_layout_preview.py --capture
  py -3 scripts/catalog_layout_preview.py --capture docs/catalog_layout_previews

Opens docs/catalog_layout_previews/index.html when capture finishes.
"""
from __future__ import annotations

import argparse
import html
import sys
import tempfile
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gui_theme as theme

DEFAULT_CAPTURE_DIR = ROOT / "docs" / "catalog_layout_previews"
WINDOW_SIZE = (1536, 960)


def _sample_driver_rows() -> list[dict]:
    return [
        {
            "name": "Realtek Audio",
            "display_name": "Realtek Audio",
            "version": "6.0.9738.1",
            "manufacturer": "Realtek",
            "_tier": "outdated",
            "_check_status": "newer",
            "_dual_version_profile": True,
            "_installed_lines": [
                "WDM: 6.0.9738.1",
                "Effects: 13.0.6000.1167",
            ],
        },
        {
            "name": "Realtek Gaming 2.5GbE Family Controller",
            "display_name": "Realtek Gaming 2.5GbE Family Controller",
            "version": "10.73.1125.2025",
            "manufacturer": "Realtek",
            "_tier": "normal",
            "_check_status": "same",
            "_dual_version_profile": True,
            "_installed_lines": [
                "Net: 10.73.1125.2025",
                "Package: 1167.25.1125.2025",
            ],
        },
        {
            "name": "AMD Radeon(TM) Graphics",
            "display_name": "AMD Radeon(TM) Graphics",
            "version": "32.0.21043.19003",
            "manufacturer": "Advanced Micro Devices, Inc.",
            "_tier": "outdated",
            "_check_status": "newer",
        },
        {
            "name": "NVIDIA GeForce RTX 3070 Ti Laptop GPU",
            "display_name": "NVIDIA GeForce RTX 3070 Ti Laptop GPU",
            "version": "32.0.15.8097",
            "manufacturer": "NVIDIA",
            "_tier": "outdated",
            "_check_status": "newer",
            "_dual_version_profile": True,
            "_installed_lines": [
                "WDM: 32.0.15.8097",
                "Branch: 581.42",
            ],
        },
        {
            "name": "Intel(R) Wi-Fi 6E AX210 160MHz",
            "display_name": "Intel(R) Wi-Fi 6E AX210 160MHz",
            "version": "23.160.0.8",
            "manufacturer": "Intel",
            "_tier": "normal",
            "_check_status": "same",
        },
    ]


def _sample_firmware_rows(prof: dict) -> None:
    prof["bios_driver_info"] = {
        "bios": {"version": "1.2.7.0", "manufacturer": "Alienware"}
    }
    prof["ssd_firmware"] = [
        {"model": "Samsung SSD 990 PRO 4TB", "firmware_revision": "8B2QJXD7"},
    ]
    prof["secondary_firmware"] = [
        {
            "key": "peripheral:046d:c081",
            "component": "Logitech G900 Gaming Mouse",
            "installed": "—",
            "vendor_key": "logitech",
        },
        {
            "key": "peripheral:1532:0277",
            "component": "Razer Pro Type Ultra",
            "installed": "—",
            "vendor_key": "razer",
        },
        {
            "key": "peripheral:046d:408a",
            "component": "HID Keyboard Device",
            "installed": "—",
            "vendor_key": "logitech",
        },
    ]
    prof["system_ctx"] = prof.get("system_ctx") or {}


def _count_list_viewport_rows(table) -> tuple[int, int]:
    """Return (fully_visible_rows, partially_visible_tail_rows)."""
    if table is None:
        return 0, 0
    vp_h = max(0, int(table.viewport().height()))
    full = 0
    partial = 0
    for row in range(table.rowCount()):
        y = table.rowViewportPosition(row)
        if y < 0:
            continue
        h = max(1, table.rowHeight(row))
        bottom = y + h
        if bottom <= vp_h:
            full += 1
        elif y < vp_h:
            partial += 1
    return full, partial


def _prime_preview_window(win, *, preset_id: str) -> None:
    prof = win._hardware_profile or {}
    _sample_firmware_rows(prof)
    win._hardware_profile = prof
    win._ssd_firmware_loaded = True
    win._drv_unified_cache = _sample_driver_rows()
    win._all_devices_loaded = True
    win.apply_catalog_layout_preset(preset_id)
    win._populate_drivers_tab()
    win._populate_firmware_tab(load_support_links=False)


def _pump_render(app, *, passes: int = 8) -> None:
    from PySide6 import QtCore

    for _ in range(passes):
        app.processEvents()
        QtCore.QThread.msleep(30)


def _capture_tab_png(win, tab_index: int, dest: Path) -> tuple[int, int]:
    from PySide6 import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    win.tabs.setCurrentIndex(tab_index)
    _pump_render(app)
    pixmap = win.grab()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(dest)):
        raise RuntimeError(f"Failed to save screenshot: {dest}")
    table = win.drv_unified_table if tab_index == win._drivers_tab_index() else win.fw_unified_table
    return _count_list_viewport_rows(table)


def _write_capture_index(
    out_dir: Path,
    *,
    rows: list[dict[str, object]],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    index = out_dir / "index.html"
    cards = []
    for entry in rows:
        preset_id = str(entry["id"])
        label = html.escape(str(entry["label"]))
        desc = html.escape(str(entry["description"]))
        drv_file = html.escape(str(entry["drivers_png"]))
        fw_file = html.escape(str(entry["firmware_png"]))
        drv_vis = html.escape(str(entry["drivers_visible"]))
        fw_vis = html.escape(str(entry["firmware_visible"]))
        cards.append(
            f"""
<section class="preset">
  <h2>{label}</h2>
  <p class="desc">{desc}</p>
  <p class="counts">Drivers list: {drv_vis} · Firmware list: {fw_vis}</p>
  <div class="pair">
    <figure>
      <figcaption>Drivers tab</figcaption>
      <img src="{drv_file}" alt="{label} — Drivers tab" loading="lazy" />
    </figure>
    <figure>
      <figcaption>Firmware tab</figcaption>
      <img src="{fw_file}" alt="{label} — Firmware tab" loading="lazy" />
    </figure>
  </div>
</section>
"""
        )
    index.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>BSOD Analyzer — catalog layout presets</title>
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; background: #1e1e1e; color: #e0e0e0; margin: 0; padding: 24px; }}
    h1 {{ margin-top: 0; }}
    .intro {{ max-width: 960px; line-height: 1.5; color: #b0b0b0; }}
    .preset {{ margin: 32px 0 48px; border-top: 1px solid #333; padding-top: 24px; }}
    .desc, .counts {{ color: #b0b0b0; }}
    .counts {{ font-weight: 600; color: #7ec8ff; }}
    .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 12px; }}
    figure {{ margin: 0; }}
    figcaption {{ margin-bottom: 8px; font-size: 14px; color: #9aa0a6; }}
    img {{ width: 100%; height: auto; border: 1px solid #444; border-radius: 4px; display: block; }}
    @media (max-width: 1100px) {{ .pair {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <h1>Catalog layout presets — real UI captures</h1>
  <p class="intro">
    Window size {WINDOW_SIZE[0]}×{WINDOW_SIZE[1]} px, sample driver/firmware rows from your machine profile.
    Count full rows in the scroll list (blue count line). Pick A–D and tell the agent which preset to ship.
    Re-capture anytime: <code>py -3 scripts/catalog_layout_preview.py --capture</code>
  </p>
  {''.join(cards)}
</body>
</html>
""",
        encoding="utf-8",
    )
    return index


def run_measure() -> int:
    """Offscreen — print visible row counts per preset (no PNG; safe in CI/agents)."""
    from tests.gui_test_harness import offscreen_main_window, process_events_until

    print(f"Window {WINDOW_SIZE[0]}×{WINDOW_SIZE[1]} — sample driver/firmware rows\n")
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win.resize(*WINDOW_SIZE)
            process_events_until(lambda: win.isVisible(), timeout_ms=8000)
            from PySide6 import QtWidgets

            app = QtWidgets.QApplication.instance()
            for preset_id, preset in theme.CATALOG_LAYOUT_PRESETS.items():
                _prime_preview_window(win, preset_id=preset_id)
                process_events_until(
                    lambda: win.drv_unified_table.rowCount() > 0, timeout_ms=3000
                )
                if app is not None:
                    _pump_render(app, passes=6)
                win.tabs.setCurrentIndex(win._drivers_tab_index())
                if app is not None:
                    _pump_render(app, passes=4)
                df, dp = _count_list_viewport_rows(win.drv_unified_table)
                win.tabs.setCurrentIndex(win._firmware_tab_index())
                if app is not None:
                    _pump_render(app, passes=4)
                ff, fp = _count_list_viewport_rows(win.fw_unified_table)
                drv = f"{df} full" + (f" + {dp} partial" if dp else "")
                fw = f"{ff} full" + (f" + {fp} partial" if fp else "")
                print(f"{preset['label']}")
                print(f"  {preset.get('description', '')}")
                print(f"  Drivers: {drv}  |  Firmware: {fw}\n")
    return 0


def run_capture(out_dir: Path) -> int:
    """Capture using a briefly visible real Qt window (offscreen grab hangs on Windows)."""
    from PySide6 import QtCore, QtWidgets

    from tests.gui_test_harness import isolated_settings, teardown_main_window
    import bsod_gui_qt as gui

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    preset_ids = list(theme.CATALOG_LAYOUT_PRESETS.keys())
    summary: list[dict[str, object]] = []
    state = {"index": 0}

    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
            win = gui.MainWindow()
            win.resize(*WINDOW_SIZE)
            win.move(80, 40)
            win.show()
            win.raise_()
            win.activateWindow()

            def _capture_step() -> None:
                idx = state["index"]
                if idx >= len(preset_ids):
                    index = _write_capture_index(out_dir, rows=summary)
                    print(
                        f"\nWrote {len(summary) * 2} PNGs and {index}",
                        flush=True,
                    )
                    teardown_main_window(win)
                    try:
                        webbrowser.open(index.as_uri())
                    except OSError:
                        pass
                    QtCore.QTimer.singleShot(0, app.quit)
                    return

                preset_id = preset_ids[idx]
                preset = theme.CATALOG_LAYOUT_PRESETS[preset_id]
                _prime_preview_window(win, preset_id=preset_id)
                _pump_render(app, passes=12)

                drv_png = out_dir / f"{preset_id}_drivers.png"
                fw_png = out_dir / f"{preset_id}_firmware.png"
                drv_full, drv_part = _capture_tab_png(
                    win, win._drivers_tab_index(), drv_png
                )
                fw_full, fw_part = _capture_tab_png(
                    win, win._firmware_tab_index(), fw_png
                )
                drv_vis = f"{drv_full} full" + (
                    f" + {drv_part} partial" if drv_part else ""
                )
                fw_vis = f"{fw_full} full" + (
                    f" + {fw_part} partial" if fw_part else ""
                )
                summary.append(
                    {
                        "id": preset_id,
                        "label": preset["label"],
                        "description": preset.get("description", ""),
                        "drivers_png": drv_png.name,
                        "firmware_png": fw_png.name,
                        "drivers_visible": drv_vis,
                        "firmware_visible": fw_vis,
                    }
                )
                print(
                    f"{preset_id}: drivers {drv_vis}, firmware {fw_vis} -> {drv_png.name}, {fw_png.name}",
                    flush=True,
                )
                state["index"] = idx + 1
                QtCore.QTimer.singleShot(120, _capture_step)

            QtCore.QTimer.singleShot(400, _capture_step)
            return app.exec()

    return 0


def run_interactive(start: str) -> int:
    from PySide6 import QtWidgets

    from tests.gui_test_harness import isolated_settings
    import bsod_gui_qt as gui

    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            app = QtWidgets.QApplication(sys.argv)
            win = gui.MainWindow()
            win.resize(*WINDOW_SIZE)
            win.show()

            _prime_preview_window(win, preset_id=start)

            bar = QtWidgets.QWidget()
            lay = QtWidgets.QHBoxLayout(bar)
            lay.setContentsMargins(8, 4, 8, 4)
            lay.addWidget(QtWidgets.QLabel("Layout preset:"))
            combo = QtWidgets.QComboBox()
            for key, preset in theme.CATALOG_LAYOUT_PRESETS.items():
                combo.addItem(str(preset["label"]), key)
            idx = combo.findData(start)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            lay.addWidget(combo, 1)
            counts = QtWidgets.QLabel("")
            counts.setWordWrap(True)
            lay.addWidget(counts, 2)

            def _on_preset(_index: int) -> None:
                key = str(combo.currentData())
                preset = theme.CATALOG_LAYOUT_PRESETS.get(key, {})
                win.apply_catalog_layout_preset(key)
                win._populate_drivers_tab()
                win._populate_firmware_tab(load_support_links=False)
                _pump_render(app)
                df, dp = _count_list_viewport_rows(win.drv_unified_table)
                ff, fp = _count_list_viewport_rows(win.fw_unified_table)
                drv = f"{df} full" + (f" + {dp} partial" if dp else "")
                fw = f"{ff} full" + (f" + {fp} partial" if fp else "")
                counts.setText(
                    f"{preset.get('description', '')}  ·  Drivers: {drv}  ·  Firmware: {fw}"
                )

            combo.currentIndexChanged.connect(_on_preset)
            _on_preset(combo.currentIndex())

            win.statusBar().addPermanentWidget(bar, 1)

            print("Catalog layout preview — use the status-bar dropdown (A–D).")
            print("Counts update live; this is the real app UI with sample rows.")
            return app.exec()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Catalog layout preset preview")
    parser.add_argument(
        "--measure",
        action="store_true",
        help="Offscreen row-count table only (for agents/CI)",
    )
    parser.add_argument(
        "--capture",
        nargs="?",
        const=str(DEFAULT_CAPTURE_DIR),
        metavar="DIR",
        help="Save real UI PNGs locally (requires a display; opens index.html)",
    )
    parser.add_argument(
        "--save",
        metavar="PRESET",
        help="Persist preset id to an isolated preview settings dir and exit",
    )
    parser.add_argument(
        "--start",
        default="current",
        choices=list(theme.CATALOG_LAYOUT_PRESETS.keys()),
        help="Initial preset for interactive mode",
    )
    args = parser.parse_args()

    if args.save:
        from tests.gui_test_harness import isolated_settings
        import app_settings as app_set

        with tempfile.TemporaryDirectory() as tmp:
            with isolated_settings(tmp):
                settings = app_set.load_settings()
                settings[theme.CATALOG_LAYOUT_PRESET_KEY] = args.save
                app_set.save_settings(settings)
                print(f"Saved preset {args.save!r} to preview settings only.")
        return 0

    if args.measure:
        return run_measure()

    if args.capture is not None:
        return run_capture(Path(args.capture))

    return run_interactive(args.start)


if __name__ == "__main__":
    raise SystemExit(main())
