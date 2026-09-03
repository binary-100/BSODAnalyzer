"""Tests for hardware-gated chipset/vendor probe logic."""
from __future__ import annotations

import bsod_hardware_wmi as hw


def test_amd_system_skips_intel_chipset() -> None:
    ctx = {"cpu_vendor": "amd", "has_amd_chipset": True, "has_intel_chipset": False}
    assert hw.amd_chipset_applicable(ctx)
    assert not hw.intel_chipset_applicable(ctx)
    assert not hw.intel_driver_lookup_applicable(ctx)


def test_intel_cpu_includes_intel_chipset() -> None:
    ctx = {"cpu_vendor": "intel", "has_intel_chipset": True}
    assert hw.intel_chipset_applicable(ctx)
    assert hw.intel_driver_lookup_applicable(ctx)


def test_intel_wifi_without_chipset() -> None:
    ctx = {
        "cpu_vendor": "amd",
        "has_amd_chipset": True,
        "hardware_vendors": {"network": {"intel"}},
    }
    assert not hw.intel_chipset_applicable(ctx)
    assert hw.intel_driver_lookup_applicable(ctx)


def test_chipset_catalog_entries_match_hardware() -> None:
    amd_only = hw.chipset_driver_catalog_entries(
        {"cpu_vendor": "amd", "has_amd_chipset": True}
    )
    assert len(amd_only) == 1
    assert amd_only[0]["name"] == hw.CHIPSET_DEVICE_AMD


def test_gated_probes_skip_intel_on_amd_cpu() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from live_probe_gating import run_gated_vendor_probes

    ctx = {"cpu_vendor": "amd", "has_amd_chipset": True, "gpu_vendor": "nvidia"}
    probes = run_gated_vendor_probes(ctx, run_probe=lambda fn, _t: (fn(), ""))
    assert probes["intel_chipset"]["skipped"] is True
    assert "No Intel chipset" in probes["intel_chipset"]["reason"]


if __name__ == "__main__":
    test_amd_system_skips_intel_chipset()
    test_intel_cpu_includes_intel_chipset()
    test_intel_wifi_without_chipset()
    test_chipset_catalog_entries_match_hardware()
    test_gated_probes_skip_intel_on_amd_cpu()
    print("chipset gating tests OK")
