"""Tests for manufacturer lookup page audit."""
from __future__ import annotations

from unittest import mock

import vendor_endpoint_audit as vea


def test_recommended_patches_from_audit_rows() -> None:
    rows = [
        vea.EndpointAuditRow(
            vendor="intel",
            endpoint_key="chipset_product",
            label="Intel chipset",
            current_url="https://old.example/chipset",
            status="update_available",
            recommended_url="https://new.example/chipset",
            version_sample="10.1.2.3",
        ),
        vea.EndpointAuditRow(
            vendor="nvidia",
            endpoint_key="ajax_base",
            label="NVIDIA",
            current_url="https://nvidia.example/ajax",
            status="ok",
            version_sample="610.62",
        ),
    ]
    patches = vea.recommended_patches(rows)
    assert patches == {"intel": {"chipset_product": "https://new.example/chipset"}}


def test_intel_audit_finds_alternate_chipset_page() -> None:
    old = "https://www.intel.com/content/www/us/en/download/17608/intel-chipset-inf-utility.html"
    new = "https://www.intel.com/content/www/us/en/download/19347/chipset-inf-utility.html"

    def fake_probe(url: str, hint: str) -> str:
        if url == new:
            return "10.1.20398.8776"
        return ""

    with mock.patch.object(vea, "_probe_intel_page", side_effect=fake_probe):
        with mock.patch.object(vea.veh, "get_endpoint", return_value=old):
            row = vea._audit_intel_page("chipset_product", {"cpu_vendor": "intel"})
    assert row.status == "update_available"
    assert row.recommended_url == new
    assert row.version_sample.startswith("10.1")


def test_format_audit_report_lists_update() -> None:
    text = vea.format_audit_report(
        [
            vea.EndpointAuditRow(
                vendor="intel",
                endpoint_key="chipset_product",
                label="Intel chipset download page",
                current_url="https://old",
                status="update_available",
                recommended_url="https://new",
                version_sample="10.1.2.3",
            )
        ]
    )
    assert "UPDATE AVAILABLE" in text
    assert "https://new" in text
    assert "Apply" in text


def test_intel_audit_dsa_discovery() -> None:
    old = "https://www.intel.com/content/www/us/en/download/17608/intel-chipset-inf-utility.html"
    discovered = "https://www.intel.com/content/www/us/en/download/19347/chipset-inf-utility.html"

    with mock.patch.object(vea, "_probe_intel_page", side_effect=lambda url, hint: "10.1.2.3" if url == discovered else ""):
        with mock.patch.object(vea.veh, "get_endpoint", return_value=old):
            with mock.patch.object(vea, "_intel_candidate_urls", return_value=[discovered]):
                row = vea._audit_intel_page("chipset_product", {"cpu_vendor": "intel"})
    assert row.status == "update_available"
    assert row.recommended_url == discovered


if __name__ == "__main__":
    test_recommended_patches_from_audit_rows()
    test_intel_audit_finds_alternate_chipset_page()
    test_intel_audit_dsa_discovery()
    test_format_audit_report_lists_update()
    print("vendor_endpoint_audit tests OK")
