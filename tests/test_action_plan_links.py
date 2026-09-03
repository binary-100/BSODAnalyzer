"""Action Plan download links — direct OEM/AMD URLs (no Google fallback)."""

from __future__ import annotations

import bsod_analyzer as ba


def test_amd_chipset_link_uses_driver_portal() -> None:
    opts = ba.build_platform_update_options(
        {"has_amd_chipset": True, "cpu_vendor": "amd"},
        code_val=0x124,
    )
    amd = next(o for o in opts if o.get("id") == "amd_chipset")
    assert "chipset.html" not in amd["url"]
    assert amd["url"] == ba._AMD_CHIPSET_DRIVER_URL
    assert "google.com" not in amd["url"]


def test_alienware_service_tag_drivers_url() -> None:
    url = ba._pc_support_drivers_url(
        {
            "system_manufacturer": "Alienware",
            "system_model": "Alienware m17 R5 AMD",
            "service_tag": "ABC1234",
        }
    )
    assert url is not None
    assert "dell.com/support" in url
    assert "ABC1234" in url
    assert "google.com" not in url


def test_oem_model_support_not_google() -> None:
    url = ba._oem_model_support_url(
        {
            "system_manufacturer": "Dell Inc.",
            "system_model": "Alienware m17 R5 AMD",
            "service_tag": "SVCTAG1",
        }
    )
    assert url is not None
    assert "google.com" not in url
    assert "SVCTAG1" in url


def test_driver_update_options_no_web_search() -> None:
    opts = ba.build_driver_update_options(
        "nvlddmkm.sys",
        [{"Name": "NVIDIA GeForce RTX", "DeviceID": "PCI\\VEN_10DE"}],
        {"system_manufacturer": "Alienware", "service_tag": "TAG12345"},
        {},
        [{"name": "NVIDIA GeForce RTX", "version": "1.0", "date": ""}],
    )
    assert not any(o.get("id") == "web_search" for o in opts)
    assert any("dell.com" in (o.get("url") or "") for o in opts if o.get("kind") == "url")


def test_service_tag_from_bios_for_oem_url() -> None:
    ctx = ba._system_ctx_with_service_tag(
        {"system_manufacturer": "Alienware"},
        {"bios": {"serial_number": "SVCTAG1"}},
    )
    assert ctx["service_tag"] == "SVCTAG1"
    url = ba._pc_support_drivers_url(ctx)
    assert url and "SVCTAG1" in url


if __name__ == "__main__":
    test_amd_chipset_link_uses_driver_portal()
    test_alienware_service_tag_drivers_url()
    test_oem_model_support_not_google()
    test_driver_update_options_no_web_search()
    test_service_tag_from_bios_for_oem_url()
    print("OK")
