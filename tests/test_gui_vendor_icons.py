"""Tests for gui_vendor_icons vendor key inference and bundled SVG assets."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PySide6 import QtGui, QtWidgets

import gui_vendor_icons as vicons

AMD_PNG_MD5_APPROVED = "13f64ac7a99b47b2dbc0131e4e78e3c7"


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    """Qt aborts the process when a QPixmap is built before any QGuiApplication exists.

    This file has no `__main__` block, so none of these tests ran under the old runpy
    runner and the missing application only surfaced once pytest began collecting them.
    """
    yield QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

# Every bundled SVG must load (official/manufacturer artwork audit).
BUNDLED_VENDOR_KEYS = sorted(
    p.stem for p in (Path(__file__).resolve().parent.parent / "assets" / "vendor_icons").glob("*.svg")
)


def test_vendor_key_for_dell_technologies_manufacturer():
    dev = {
        "name": "DBUtilDrv2 Device",
        "display_name": "DBUtilDrv2 Device",
        "manufacturer": "Dell Technologies",
        "device_class": "DELLUTILS",
    }
    assert vicons.vendor_key_for_device(dev) == "dell"


def test_vendor_key_for_device_amd_driver():
    dev = {
        "name": "AMD Radeon RX 7900 XTX",
        "manufacturer": "Advanced Micro Devices, Inc.",
        "driver": "amdkmdag.sys",
    }
    assert vicons.vendor_key_for_device(dev) == "amd"


def test_vendor_key_for_firmware_bios_dell():
    ent = {
        "key": "bios",
        "component": "Motherboard BIOS (Dell Inc.)",
        "manufacturer": "Dell Inc.",
    }
    assert vicons.vendor_key_for_firmware(ent) == "dell"


def test_vendor_key_for_firmware_ssd_samsung():
    ent = {
        "key": "ssd:Samsung SSD 990 PRO 2TB",
        "component": "SSD — Samsung SSD 990 PRO 2TB",
        "model": "Samsung SSD 990 PRO 2TB",
    }
    assert vicons.vendor_key_for_firmware(ent) == "samsung"


def test_vendor_key_for_firmware_peripheral_logitech_vid():
    ent = {
        "key": "peripheral:046d:c52b",
        "component": "Logitech G HUB Virtual Keyboard",
        "vendor_key": "",
    }
    assert vicons.vendor_key_for_firmware(ent) == "logitech"


def test_vendor_key_for_device_amd_chipset_name():
    dev = {
        "name": "AMD Chipset / Platform drivers",
        "manufacturer": "",
        "driver": "",
    }
    assert vicons.vendor_key_for_device(dev) == "amd"


def test_all_bundled_vendor_svgs_load():
    missing = [key for key in BUNDLED_VENDOR_KEYS if vicons._load_file_icon(key, 24) is None]
    assert not missing, f"SVG failed to load: {missing}"


def test_amd_png_matches_approved_golden_hash():
    png = Path(__file__).resolve().parent.parent / "assets" / "vendor_icons" / "amd.png"
    assert png.is_file(), f"Missing {png} — run scripts/build_amd_logo_png.py"
    digest = hashlib.md5(png.read_bytes()).hexdigest()
    assert digest == AMD_PNG_MD5_APPROVED, (
        f"amd.png changed ({digest}); expected approved {AMD_PNG_MD5_APPROVED}. "
        "Restore from BSODAnalyzer_StableBuilds/v6.2.3 or fix build_amd_logo_png.py."
    )


def test_amd_asset_from_user_reference_png():
    png = Path(__file__).resolve().parent.parent / "assets" / "vendor_icons" / "amd.png"
    assert png.is_file(), f"Missing {png} — run scripts/build_amd_logo_png.py"
    ref = Path(__file__).resolve().parent.parent / "assets" / "vendor_icons" / "amd_reference.png"
    assert ref.is_file(), f"Missing master reference {ref}"
    svg = png.with_suffix(".svg")
    assert not svg.is_file(), "Remove amd.svg so the reference PNG is used (svg takes precedence)"


def test_amd_png_loads_in_gui():
    icon = vicons.icon_for_vendor_key("amd", size=44)
    assert not icon.isNull()
    pm = icon.pixmap(44, 44)
    assert not pm.isNull()
    # Corners should be transparent after the black matte is stripped for display.
    for corner in ((0, 0), (43, 0), (0, 43), (43, 43)):
        assert QtGui.QColor(pm.toImage().pixelColor(*corner)).alpha() == 0


def test_microsoft_svg_equal_square_grid():
    svg = (Path(__file__).resolve().parent.parent / "assets" / "vendor_icons" / "microsoft.svg").read_text()
    assert "h11.5v11.5" in svg
    assert "M12.5 0H24v11.5" in svg
    assert "11.408" not in svg


def test_microsoft_icon_loads():
    icon = vicons.icon_for_vendor_key("microsoft", size=44)
    assert not icon.isNull()


def test_icon_for_vendor_key_not_null():
    for key in ("amd", "intel", "realtek", "kingston", "western_digital"):
        icon = vicons.icon_for_vendor_key(key)
        assert not icon.isNull(), key
