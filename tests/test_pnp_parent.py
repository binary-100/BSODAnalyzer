"""Verified PnP parent links (Windows DEVPKEY_Device_Parent only)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import device_enrichment as de


def test_pnp_parent_resolves_when_parent_in_same_snapshot() -> None:
    pnp_list = [
        {
            "Name": "Realtek(R) Audio",
            "PNPClass": "MEDIA",
            "DeviceID": r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0295\1",
        },
        {
            "Name": "Realtek Asio Component",
            "PNPClass": "SoftwareComponent",
            "DeviceID": r"SWD\DRIVERENUM\{GUID}#REALTEKASIO&1",
            "Parent": r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0295\1",
        },
    ]
    id_map = de.build_pnp_id_to_name_map(pnp_list)
    fields = de.pnp_parent_fields_from_row(pnp_list[1], id_map)
    assert fields == {
        "parent_device_id": r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0295\1",
        "parent_device_name": "Realtek(R) Audio",
    }


def test_pnp_parent_omitted_when_parent_not_in_snapshot() -> None:
    pnp_list = [
        {
            "Name": "Realtek Asio Component",
            "PNPClass": "SoftwareComponent",
            "DeviceID": r"SWD\DRIVERENUM\{GUID}#REALTEKASIO&1",
            "Parent": r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0295\1",
        },
    ]
    id_map = de.build_pnp_id_to_name_map(pnp_list)
    assert de.pnp_parent_fields_from_row(pnp_list[0], id_map) == {}


def test_enrich_pnp_device_includes_verified_parent() -> None:
    pnp_list = [
        {
            "Name": "Realtek(R) Audio",
            "PNPClass": "MEDIA",
            "Manufacturer": "Realtek",
            "DeviceID": r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0295\1",
        },
        {
            "Name": "Realtek Asio Component",
            "PNPClass": "SoftwareComponent",
            "Manufacturer": "Realtek",
            "DeviceID": r"SWD\DRIVERENUM\{GUID}#REALTEKASIO&1",
            "Parent": r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0295\1",
        },
    ]
    index = de.build_pnp_enrichment_index(pnp_list, parallel=False)
    assert index["Realtek Asio Component"]["parent_device_name"] == "Realtek(R) Audio"
    assert "parent_device_name" not in index["Realtek(R) Audio"]


if __name__ == "__main__":
    test_pnp_parent_resolves_when_parent_in_same_snapshot()
    test_pnp_parent_omitted_when_parent_not_in_snapshot()
    test_enrich_pnp_device_includes_verified_parent()
    print("PnP parent tests OK")
