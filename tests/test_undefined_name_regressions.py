"""Regressions for code paths that failed on a branch the suite never reached.

Most were found by the pyflakes gate in `test_static_analysis.py`: an import dropped
during a module split, on a path no test walked — a machine that actually has a LiveKernel
event, a problem device the enrichment index does not know, a Windows Update row whose
Download button opens Settings. The rest are the same shape but invisible to pyflakes: a
misplaced paren, a tuple that grew a third element, a timestamp labelled with the wrong
zone. These tests pin the behaviour each defect denied, so a refactor that reintroduces it
fails loudly instead of degrading in the field.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import bsod_events as be  # noqa: E402
import bsod_hardware_wmi as hw  # noqa: E402
import catalog_chipset_comparison as ccc  # noqa: E402
import catalog_download as cdl  # noqa: E402
import crash_report_fix_plan as crfp  # noqa: E402
import crash_report_format as crf  # noqa: E402
import firmware_catalog as fwcat  # noqa: E402


def test_reliability_bundle_summarizes_livekernel_events() -> None:
    """A LiveKernel event used to kill the whole bundle, losing WER and stability too."""
    payload = {
        "LiveKernel": [
            {
                "TimeCreated": "2026-08-20 21:14:03",
                "Id": 141,
                "Provider": "Microsoft-Windows-LiveKernelEvent",
                "Message": "The display driver failed to respond in a timely manner.",
            }
        ],
        "Wer": [{"TimeCreated": "2026-08-20 21:14:05", "Id": 1000, "Message": "app fault"}],
        "StabilityIndex": 7.25,
    }
    with mock.patch.object(be, "run_powershell", return_value=(True, json.dumps(payload))):
        bundle = be.query_reliability_livekernel_bundle()

    assert not bundle.get("_query_failed"), "reliability query reported failure"
    assert bundle["stability_index"] == 7.25
    assert len(bundle["wer_errors"]) == 1
    event = bundle["livekernel"][0]
    assert event["id"] == 141
    assert event["summary"] == "Graphics / display driver instability"


def test_problem_device_without_enrichment_still_gets_a_display_name() -> None:
    """The unenriched branch raised, taking down the whole hardware scan."""
    pnp_list = [
        {
            "Name": "PCI Device",
            "ConfigManagerErrorCode": 28,
            "PNPClass": "",
            "Manufacturer": "Realtek",
            "DeviceID": r"PCI\VEN_10EC&DEV_8168",
        }
    ]
    rows = hw.get_devices_with_driver_problems(pnp_list, pnp_enrichment={"Other Device": {}})

    assert len(rows) == 1
    row = rows[0]
    assert row["error_code"] == 28
    assert row["display_name"], "no display label produced for an unenriched problem device"


def test_vendor_lookup_gate_accepts_network_and_peripheral_vendors() -> None:
    """Any vendor outside intel/amd/nvidia/realtek hit an undefined key set."""
    confident_ctx = {
        "pnp_list": [{"Name": "Killer E3100 2.5 Gigabit Ethernet Controller"}],
        "hardware_confident": True,
    }
    for vendor_key in ("killer", "broadcom", "qualcomm", "mediatek", "tplink", "logitech"):
        # Only assert it answers instead of raising: presence depends on the ctx above.
        result = ccc._manufacturer_vendor_lookup_applicable(vendor_key, confident_ctx)
        assert isinstance(result, bool), f"{vendor_key} gate returned {result!r}"


def test_download_optional_updates_row_opens_windows_update() -> None:
    """`sys.platform` was undefined, so Download on a WU optional-updates row raised."""
    offer = {"title": "Realtek audio driver", "url": "", "source": "Windows Update"}
    with mock.patch.object(cdl, "_dc", return_value=lambda _o: "optional_updates"), mock.patch(
        "os.startfile", create=True
    ) as startfile:
        ok, msg, path = cdl.download_driver_offer(offer)

    assert ok, msg
    assert path is None
    startfile.assert_called_once_with("ms-settings:windowsupdate-optionalupdates")


def test_platform_update_options_build_storage_and_whea_search_links() -> None:
    """Both search links quoted their query through an unimported `urllib`."""
    system_ctx = {
        "has_nvme": True,
        "system_manufacturer": "Micro-Star International Co., Ltd.",
        "system_model": "MPG X670E CARBON WIFI",
        "cpu_vendor": "amd",
    }
    options = crfp.build_platform_update_options(
        system_ctx,
        code_val=0x124,
        report_ctx={"p1_int": 4, "whea_component": "PCI Express Root Port"},
        fix_focus={"include_storage": True, "include_whea_search": True},
    )

    by_id = {o["id"]: o for o in options}
    storage = by_id["storage_nvme_search"]
    assert "MPG+X670E" in storage["url"], storage["url"]
    whea = by_id["whea_component_search"]
    assert "PCI+Express+Root+Port" in whea["url"], whea["url"]


def test_vendor_aliases_resolve_to_the_keys_the_catalog_gates_on() -> None:
    """KNOWN_VENDORS listed these keys twice; the shadowed half used hyphenated values.

    `catalog_extended_fetch` gates TP-Link peripheral lookups on the exact string
    `tplink`, so collapsing the duplicates had to keep the unhyphenated canonical.
    """
    assert hw._extract_vendor_from_string("TP-Link Wireless USB Adapter") == "tplink"
    assert hw._extract_vendor_from_string("TPLink Archer T3U") == "tplink"
    assert hw._extract_vendor_from_string("D-Link DWA-182 Wireless AC") == "dlink"
    assert hw._extract_vendor_from_string("C-Media USB Audio Device") == "cmedia"


def test_quick_answer_survives_unexpected_shutdown_with_no_stop_code() -> None:
    """`list(d).get(...)` raised `AttributeError` on every KernelPower Event 41.

    Only masked when a repair narrative existed, because that returns early.
    """
    lines, root_cause, fix = crf._quick_answer_lines(
        events=[{"time": "2026-08-09 03:14:00", "id": 41, "type": "KernelPower"}],
        windbg_analysis=None,
        whea_events=[],
        thermal_events=[],
        driver_verification={"attribution": {"lines": ["Chipset suite is stale"]}},
        crash_confidence={"lines": ["Confidence: medium"]},
        boot_recovery_events=[{"subtype": "BootRecovery", "time": "2026-08-09 03:15:00"}],
    )

    text = "\n".join(lines)
    assert "No stop code was recorded" in text
    assert "Chipset suite is stale" in text, "attribution lines dropped from Quick Answer"
    assert isinstance(root_cause, str) and isinstance(fix, str)


def test_firmware_download_unpacks_the_full_result_tuple() -> None:
    """`open_firmware_offer` returns 3 values; the Firmware tab unpacked 2 and raised."""
    saved = "C:\\dl\\fw.exe"
    with mock.patch.object(
        fwcat.dc, "download_driver_offer", return_value=(True, f"Saved to:\n{saved}", saved)
    ):
        ok, msg, path = fwcat.open_firmware_offer({"url": "https://vendor/fw.exe"})

    assert ok and path == saved
    assert path in msg, "message must name the saved package so the GUI can show it"


def test_firmware_tab_download_button_completes(tmp_path: Path) -> None:
    """The Firmware tab's Download button raised `ValueError` on every click."""
    from PySide6 import QtWidgets

    from gui_test_harness import offscreen_main_window

    saved = str(tmp_path / "fw.exe")
    offer = {
        "kind": "ssd",
        "title": "Samsung 990 PRO firmware 4B2QJXD7",
        "version": "4B2QJXD7",
        "source_label": "Samsung",
        "url": "https://semiconductor.samsung.com/fw.exe",
    }
    with offscreen_main_window(tmp_path) as win:
        with mock.patch.object(
            win.fw_compare_table, "currentRow", return_value=0
        ), mock.patch.object(
            type(win), "_offer_from_compare_row", return_value=(offer, None)
        ), mock.patch.object(
            QtWidgets.QMessageBox, "warning", return_value=QtWidgets.QMessageBox.Yes
        ), mock.patch.object(
            QtWidgets.QMessageBox, "information"
        ) as info, mock.patch.object(
            fwcat, "open_firmware_offer", return_value=(True, f"Saved to:\n{saved}", saved)
        ):
            win._on_download_selected_firmware()

        assert info.called, "no completion dialog — the handler did not finish"
        assert saved in info.call_args.args[2]


def test_crash_timeline_reads_event_times_as_local_not_utc() -> None:
    """Event-log strings are local wall clock; tagging them UTC shifted every timestamp.

    A crash one hour ago must count inside the 7-day window and be labelled with the
    same wall-clock time the user sees in Event Viewer.
    """
    local_now = datetime.now().astimezone()
    recent = local_now - timedelta(hours=1)
    stamp = recent.strftime("%Y-%m-%d %H:%M:%S")

    timeline = be.compute_crash_timeline([{"type": "BugCheck", "time": stamp}])

    assert timeline["count_7d"] == 1, "a crash an hour ago fell outside the 7-day window"
    assert timeline["count_30d"] == 1
    assert timeline["last_crash"] == recent.strftime("%Y-%m-%d %H:%M")
    assert "UTC" not in timeline["last_crash"], "local time must not claim to be UTC"


def test_event_time_parser_keeps_offsets_it_is_given() -> None:
    """Only naive strings are local; an explicit offset must be preserved."""
    aware = be._parse_event_time("2026-08-09T03:14:00+00:00")
    assert aware is not None
    assert aware.utcoffset() == timedelta(0)

    naive = be._parse_event_time("2026-08-09 03:14:00")
    assert naive is not None
    assert naive.utcoffset() == datetime.now().astimezone().utcoffset()
    assert naive.hour == 3 and naive.minute == 14
