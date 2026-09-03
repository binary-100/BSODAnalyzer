"""Tests for bundled MSCatalogLTS portable module helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import catalog_ps_module as cps
import product_version as pv

if not pv.is_v6_line():
    print("SKIP (v6 only)")
    raise SystemExit(0)


def test_bundled_module_present_in_repo() -> None:
    dirs = cps._bundled_module_candidates()
    assert dirs, "PowerShellModules/MSCatalogLTS not vendored — run scripts/vendor_mscataloglts.ps1"
    ver = cps.read_module_version(dirs[0])
    assert ver == cps.MSCATALOG_PINNED_VERSION, ver


def test_ensure_local_copy() -> None:
    ok, path = cps.ensure_local_mscatalog_module()
    assert ok and path
    assert os.path.isfile(os.path.join(path, "MSCatalogLTS.psd1"))


def test_catalog_search_queries_shape() -> None:
    import driver_catalog as dc

    queries = dc._catalog_search_queries_for_ctx({
        "instance_id": "PCI\\VEN_10EC&DEV_8168&SUBSYS_01234567&REV_15",
        "device_label": "Realtek PCIe GbE",
        "vendor_key": "realtek",
        "pnp_class": "net",
    })
    assert any("VEN_10EC" in q for q in queries)
    assert any("SUBSYS" in q for q in queries)
    assert any("Realtek" in q for q in queries)


def test_extract_version_from_title() -> None:
    assert cps._extract_version_from_catalog_title("Realtek - Net - 1125.29.50.2026") == "1125.29.50.2026"
    assert cps._extract_version_from_catalog_title("Audio driver 6.0.9980.1") == "6.0.9980.1"


def test_prepare_uses_newest_local() -> None:
    ok, path = cps.prepare_mscatalog_module(check_online=False)
    assert ok and path
    assert os.path.isfile(os.path.join(path, "MSCatalogLTS.psd1"))


def test_parse_catalog_search_html_gotodetails() -> None:
    html = """
    <html><body>
    <a onclick="goToDetails('abc12345-6789-0123-4567-890123456789')">
      Samsung SSD 990 PRO Firmware 7B2QJXD7
    </a>
    <td>3/15/2026</td>
    </body></html>
    """
    rows = cps.parse_catalog_search_html(html, limit=4)
    assert len(rows) == 1
    assert rows[0]["update_id"] == "abc12345-6789-0123-4567-890123456789"
    assert "990 PRO" in rows[0]["title"]
    assert rows[0]["source"] == "microsoft_catalog_html"


def test_normalize_catalog_date_dotnet_json() -> None:
    # Feb 1, 2026 UTC-ish ms epoch (catalog LastUpdated JSON form)
    assert cps._normalize_catalog_date("/Date(1769904000000)/") == "2026-02-01"
    assert cps._normalize_catalog_date("2/1/2026") == "2026-02-01"
    assert cps._normalize_catalog_date("/Date(1769") == ""


def test_catalog_update_id_from_guid_property() -> None:
    uid = cps.catalog_update_id_from_row({
        "Title": "Realtek MEDIA Driver Update (6.0.9992.1)",
        "UpdateID": None,
        "Guid": "40de8e23-7272-443a-84f6-15237cceee92",
    })
    assert uid == "40de8e23-7272-443a-84f6-15237cceee92"
    assert cps.catalog_update_id_from_row({
        "UpdateID": "11111111-1111-1111-1111-111111111111",
    }) == "11111111-1111-1111-1111-111111111111"
    assert cps.catalog_update_id_from_url(
        "https://www.catalog.update.microsoft.com/ScopedViewInline.aspx?updateid=22222222-2222-2222-2222-222222222222"
    ) == "22222222-2222-2222-2222-222222222222"


def test_is_online_cached() -> None:
    from unittest.mock import patch

    cps.reset_mscatalog_session()
    calls = {"n": 0}

    class FakeSock:
        def settimeout(self, _timeout: float) -> None:
            pass

        def connect(self, _addr: tuple[str, int]) -> None:
            calls["n"] += 1

        def close(self) -> None:
            pass

    with patch("socket.socket", lambda *a, **k: FakeSock()):
        assert cps._is_online() is True
        assert cps._is_online() is True
    assert calls["n"] == 1


def test_prepare_offline_skips_gallery() -> None:
    cps.reset_mscatalog_session()
    ok, path = cps.prepare_mscatalog_module(check_online=False)
    assert ok and path


if __name__ == "__main__":
    test_bundled_module_present_in_repo()
    test_ensure_local_copy()
    test_prepare_uses_newest_local()
    test_prepare_offline_skips_gallery()
    test_is_online_cached()
    test_catalog_search_queries_shape()
    test_extract_version_from_title()
    test_parse_catalog_search_html_gotodetails()
    test_normalize_catalog_date_dotnet_json()
    test_catalog_update_id_from_guid_property()
    print("OK")
