"""Batch 7: catalog honesty — UA sync, cache caps, HTML guard, GUI store copy."""

from __future__ import annotations

from unittest import mock

import bsod_analyzer as core
import catalog_mscatalog_session as mscat
import driver_catalog as dc


def test_catalog_user_agent_matches_version() -> None:
    ua = dc.catalog_user_agent()
    assert core.VERSION in ua
    assert ua.startswith("BSODAnalyzer/")


def test_cap_session_rows() -> None:
    rows = [{"n": i} for i in range(dc._SESSION_ROWS_CAP + 50)]
    capped = dc._cap_session_rows(rows)
    assert len(capped) == dc._SESSION_ROWS_CAP


def test_empty_online_store_not_cached() -> None:
    orig = dc._fetch_online_driver_store_rows_uncached
    mscat._ONLINE_DRIVER_STORE_CACHE = None  # type: ignore[attr-defined]
    mscat._ONLINE_DRIVER_STORE_CACHE_AT = 0.0  # type: ignore[attr-defined]
    dc.set_gui_application_mode(False)
    try:
        dc._fetch_online_driver_store_rows_uncached = lambda: ([], "no data")  # type: ignore[method-assign]
        rows, err = dc._get_cached_online_driver_store_rows()
        assert rows == []
        assert err == "no data"
        assert mscat._ONLINE_DRIVER_STORE_CACHE is None  # type: ignore[attr-defined]
    finally:
        dc._fetch_online_driver_store_rows_uncached = orig  # type: ignore[method-assign]


def test_looks_like_html_payload() -> None:
    assert dc._looks_like_html_payload(b"<!DOCTYPE html><html><body>x</body></html>")
    assert not dc._looks_like_html_payload(b"MZ\x90\x00" + b"\x00" * 100)


def test_gui_skips_online_store_when_include_all_disabled() -> None:
    dc.set_gui_application_mode(True)
    try:
        mscat._ONLINE_DRIVER_STORE_CACHE = None
        mscat._ONLINE_DRIVER_STORE_CACHE_AT = 0.0
        with mock.patch.object(dc, "_gui_batched_online_store_include_all", return_value=False):
            offers = dc.fetch_microsoft_driver_store_offers({})
        assert len(offers) == 1
        assert "skipped in gui" in (offers[0].get("title") or "").lower()
        assert "gui scans" in (offers[0].get("notes") or "").lower()
    finally:
        dc.set_gui_application_mode(False)


def test_gui_never_lazy_loads_all_during_scan() -> None:
    dc.set_gui_application_mode(True)
    mscat._ONLINE_DRIVER_STORE_CACHE = None
    mscat._ONLINE_DRIVER_STORE_CACHE_AT = 0.0
    lazy_calls: list[str] = []

    def fake_lazy(*, progress=None) -> tuple[list[dict], str]:
        lazy_calls.append("lazy")
        return [{
            "Version": "1.2.3.4",
            "ClassName": "net",
            "HardwareDescription": "Example NIC",
            "ProviderName": "Example",
        }], ""

    try:
        with mock.patch.object(
            dc, "_lazy_load_online_driver_store_all", side_effect=fake_lazy
        ), mock.patch.object(
            dc, "_gui_batched_online_store_include_all", return_value=True
        ):
            ctx = {
                "instance_id": "",
                "pnp_class": "net",
                "vendor_key": "realtek",
                "device_label": "Example NIC",
            }
            offers = dc.fetch_microsoft_driver_store_offers(ctx)
        assert lazy_calls == []
        assert any("skipped in gui" in (o.get("title") or "").lower() for o in offers)
    finally:
        dc.set_gui_application_mode(False)


if __name__ == "__main__":
    test_catalog_user_agent_matches_version()
    test_cap_session_rows()
    test_empty_online_store_not_cached()
    test_looks_like_html_payload()
    test_gui_skips_online_store_when_include_all_disabled()
    test_gui_never_lazy_loads_all_during_scan()
    print("Batch 7 catalog tests OK")
