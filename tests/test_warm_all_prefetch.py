"""Warm phase must not prefetch Get-WindowsDriver -Online -All (hang regression 6.1.22)."""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import catalog_mscatalog_session as mscat
import driver_catalog as dc


def test_warm_does_not_prefetch_all_catalog() -> None:
    lazy_calls: list[str] = []

    def fake_lazy(*, progress=None) -> tuple[list[dict], str]:
        lazy_calls.append("all")
        return [], ""

    contexts = {
        "nic": {"instance_id": "PCI\\VEN_8086&DEV_2725&SUBSYS_00000000&REV_00"},
        "generic": {"instance_id": ""},
    }
    dc.set_gui_application_mode(True)
    dc.configure_catalog(quick_check=False)
    dc._ONLINE_HWID_STORE_CACHE.clear()
    try:
        with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), mock.patch.object(
            dc, "_fetch_online_driver_store_for_hwids_batch",
            return_value={},
        ), mock.patch.object(
            dc, "_lazy_load_online_driver_store_all", side_effect=fake_lazy
        ), mock.patch.object(
            dc, "_gui_batched_online_store_include_all", return_value=True
        ), mock.patch.object(
            mscat, "_GUI_BATCH_INTER_PAUSE_SEC", 0
        ):
            dc.warm_batched_microsoft_online_store(
                contexts,
                {"_gui_driver_catalog": True},
                progress=lambda _m: None,
            )
        assert lazy_calls == []
    finally:
        dc.set_gui_application_mode(False)
        dc._ONLINE_HWID_STORE_CACHE.clear()


if __name__ == "__main__":
    test_warm_does_not_prefetch_all_catalog()
    print("warm all prefetch tests OK")
