"""Regression tests from Aug 2026 field test (ASUS / Fowle)."""

from __future__ import annotations

import bsod_crash_report as bc
import catalog_cache as ccat
import driver_verification as dv
from bsod_runtime import get_logged_in_user_paths


def test_get_logged_in_user_paths_uses_drive_backslash() -> None:
    import os
    from unittest import mock

    with mock.patch.dict(
        os.environ,
        {
            "SystemDrive": "C:",
            "LOCALAPPDATA": "",
            "USERNAME": "Fowle",
        },
        clear=False,
    ):
        with mock.patch("bsod_runtime.run_powershell", return_value=(True, "Fowle")):
            with mock.patch("os.path.isdir", return_value=True):
                with mock.patch("os.listdir", return_value=[]):
                    _user, primary, _all = get_logged_in_user_paths()
    assert primary.startswith("C:\\Users\\Fowle\\")
    assert "C:Users" not in primary


def test_placeholder_service_tag_rejected() -> None:
    assert not bc._valid_pc_service_tag("System Serial Number")
    assert not bc._valid_pc_service_tag("To be filled by O.E.M.")
    assert bc._valid_pc_service_tag("ABC1234")


def test_machine_fingerprint_uses_board_when_tag_placeholder() -> None:
    ctx = {
        "system_manufacturer": "ASUS",
        "system_model": "System Product Name",
        "service_tag": "System Serial Number",
        "baseboard_product": "ROG STRIX B650E-I GAMING WIFI",
    }
    fp = ccat.machine_fingerprint(ctx)
    assert "tag:system serial number" not in fp
    assert "mtm:rogstrixb650e" in fp


def test_asus_board_support_url_without_serial() -> None:
    url = bc._pc_support_drivers_url(
        {
            "system_manufacturer": "ASUS",
            "system_model": "System Product Name",
            "service_tag": "System Serial Number",
            "baseboard_product": "ROG STRIX B650E-I GAMING WIFI",
        }
    )
    assert url is not None
    assert "asus.com" in url
    assert "ROG" in url or "B650E" in url


def test_narrative_boot_only_no_crash_events() -> None:
    boot = [{"time": "2026-08-22 12:43:14", "subtype": "KernelBoot", "message": "boot ok"}]
    n = dv.build_crash_repair_narrative([], None, boot_recovery=boot, system_ctx={})
    assert "boot activity" in n["what_happened"].lower()
    assert "no blue-screen" in n["what_happened"].lower()
    assert "Boot & recovery" in n["what_happened"]
    assert "boot activity only" in n["headline"].lower()
    assert "stable" in (n.get("why_this_order") or "").lower()
