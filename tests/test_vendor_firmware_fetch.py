"""Tests for vendor_firmware_fetch — ASUS robust API + Seagate Download Finder."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vendor_firmware_fetch as vff

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_asus_html_fallback_parses_bios_rows() -> None:
    html = (FIXTURES / "asus_support_bios_snippet.html").read_text(encoding="utf-8")
    rows = vff._parse_asus_support_html_firmware_rows(html, "GL702VM")
    assert rows
    assert any("BIOS" in (r.get("category") or "") or "bios" in (r.get("title") or "").lower() for r in rows)
    assert any(r.get("url") for r in rows)


def test_asus_json_api_success() -> None:
    payload = {
        "Status": "OK",
        "Result": {
            "Obj": [{
                "Files": [{
                    "Title": "BIOS 306",
                    "Version": "306",
                    "DownloadUrl": {"Global": "https://example.test/bios306.zip"},
                    "ReleaseDate": "2024-01-01",
                }],
                "Name": "BIOS",
            }],
        },
    }

    def fake_robust(url: str, **kwargs):
        if "GetPDDrivers" in url:
            return True, json.dumps(payload)
        return False, ""

    with mock.patch.object(vff, "fetch_http_robust", side_effect=fake_robust):
        rows, _fallback, status = vff.fetch_asus_product_rows({
            "system_manufacturer": "ASUSTeK COMPUTER INC.",
            "system_model": "GL702VM",
        })
    assert status == "ok"
    assert rows
    assert rows[0]["category"] == "BIOS"


def test_seagate_parse_download_finder_fixture() -> None:
    html = (FIXTURES / "seagate_download_finder_st2000lx_snippet.html").read_text(encoding="utf-8")
    parsed = vff.parse_seagate_download_finder_html(html, "ST2000LX001-1RG174")
    assert parsed["version"] == "CC44"
    assert parsed["url"]


def test_seagate_normalize_model() -> None:
    assert vff.normalize_seagate_model("ST2000LX001-1RG174") == "ST2000LX001"


if __name__ == "__main__":
    test_asus_html_fallback_parses_bios_rows()
    test_asus_json_api_success()
    test_seagate_parse_download_finder_fixture()
    test_seagate_normalize_model()
    print("OK")
