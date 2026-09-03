"""GPU vendor map — GTX 900+ floor and NVIDIA menu API ids."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import gpu_vendor_maps as gvm


def test_nvidia_gtx970_menu_ids() -> None:
    hit = gvm.nvidia_psid_pfid_from_label("NVIDIA GeForce GTX 970")
    assert hit == ("98", "756")


def test_nvidia_gtx1060_pci_dev() -> None:
    hit = gvm.nvidia_psid_pfid_from_pci_dev("1C60")
    assert hit == ("101", "817")


def test_nvidia_below_floor() -> None:
    assert not gvm.nvidia_gpu_supported("NVIDIA GeForce GTX 780 Ti", "11CB")


def test_amd_floor_rx_and_r9() -> None:
    assert gvm.amd_gpu_supported("AMD Radeon RX 580")
    assert gvm.amd_gpu_supported("AMD Radeon R9 290")
    assert not gvm.amd_gpu_supported("AMD Radeon HD 7970")


def test_intel_floor_hd530() -> None:
    assert gvm.intel_igpu_supported("Intel(R) HD Graphics 530")
    assert gvm.intel_igpu_supported("Intel(R) Iris Xe Graphics")
    assert not gvm.intel_igpu_supported("Intel(R) HD Graphics 4000")


def test_bundled_nvidia_catalog_nonempty() -> None:
    rows = gvm.nvidia_product_catalog()
    assert len(rows) >= 50
    assert any("GTX 970" in r["product"] for r in rows)


def test_bundled_amd_catalog_nonempty() -> None:
    rows = gvm.amd_product_catalog()
    assert len(rows) >= 100
    assert any("580" in (r.get("title") or "") for r in rows)


def test_amd_rx580_leaf_url() -> None:
    url = gvm.amd_product_url_from_label("AMD Radeon RX 580")
    assert url
    assert "/graphics/" in url
    assert "580" in url.lower()


def test_amd_notebook_prefers_mobility_url() -> None:
    desktop = gvm.amd_product_url_from_label("AMD Radeon RX 5500", notebook=False)
    mobile = gvm.amd_product_url_from_label("AMD Radeon RX 5500M", notebook=True)
    assert desktop and mobile
    assert desktop != mobile or "5500m" in mobile.lower()


def test_intel_hd530_legacy_bucket() -> None:
    assert gvm.intel_graphics_bucket_id("Intel(R) HD Graphics 530") == "legacy_dch"


def test_intel_arc_modern_bucket() -> None:
    assert gvm.intel_graphics_bucket_id("Intel(R) Arc A770 Graphics") == "arc_modern"


def test_intel_graphics_cache_key_per_bucket() -> None:
    assert gvm.intel_graphics_cache_key("legacy_dch") == "intel:graphics:legacy_dch"
    assert gvm.intel_graphics_cache_key("arc_modern") == "intel:graphics:arc_modern"


def test_intel_generation_mismatch_gates_arc_on_hd() -> None:
    ok = gvm.intel_graphics_version_applicable(
        device_label="Intel(R) HD Graphics 530",
        bucket_id="legacy_dch",
        installed_version="31.0.101.4502",
        scraped_version="32.0.101.6127",
    )
    assert not ok


if __name__ == "__main__":
    test_nvidia_gtx970_menu_ids()
    test_nvidia_gtx1060_pci_dev()
    test_nvidia_below_floor()
    test_amd_floor_rx_and_r9()
    test_intel_floor_hd530()
    test_bundled_nvidia_catalog_nonempty()
    print("gpu vendor map tests OK")
