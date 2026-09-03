"""Tests for cross-scheme driver version identity."""

from __future__ import annotations

import driver_version_identity as dvi


def test_realtek_nic_oem_vs_public_equivalent() -> None:
    assert dvi.realtek_nic_versions_equivalent("1125.30.50.508", "11.030.50")
    assert dvi.realtek_nic_versions_equivalent("11.030.50", "1125.30.50.508")


def test_realtek_nic_different_build_not_equivalent() -> None:
    assert not dvi.realtek_nic_versions_equivalent("1125.28.1224.2025", "11.030.50")


def test_versions_equivalent_realtek_net_ctx() -> None:
    eq, note = dvi.versions_equivalent(
        "1125.30.50.508",
        "11.030.50",
        device_ctx={"vendor_key": "realtek", "pnp_class": "net"},
    )
    assert eq
    assert "11.x.y" in note


def test_catalog_offer_matches_installed_equivalent() -> None:
    assert dvi.catalog_offer_matches_installed(
        "1125.30.50.508",
        "11.030.50",
        device_ctx={"vendor_key": "realtek", "pnp_class": "net"},
    )


if __name__ == "__main__":
    test_realtek_nic_oem_vs_public_equivalent()
    test_realtek_nic_different_build_not_equivalent()
    test_versions_equivalent_realtek_net_ctx()
    test_catalog_offer_matches_installed_equivalent()
    print("driver_version_identity tests OK")
