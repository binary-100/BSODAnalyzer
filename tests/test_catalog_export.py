"""Catalog scan export — JSON payload and text summary."""

from __future__ import annotations

import catalog_export as cexp


def test_build_payload_and_text_summary() -> None:
    payload = cexp.build_payload(
        app_version="6.0.6",
        export_options={"quick_check_mode": False},
        install_mode="full_install",
        scan_mode={"mode": "full scan", "detail": "Scan mode: full scan"},
        crash_context={"faulting_driver": "nvlddmkm.sys", "culprit_device_names": ["GPU"]},
        hardware_summary={"manufacturer": "Dell Inc.", "model": "XPS"},
        driver_rows=[
            {
                "device_name": "PCI\\VEN_10DE",
                "display_name": "NVIDIA GPU",
                "installed_version": "31.0.15.0",
                "status": "newer",
                "crash_linked": True,
                "tier": "culprit",
                "offers": [
                    {
                        "source": "oem",
                        "source_label": "OEM (Dell)",
                        "title": "NVIDIA Graphics Driver",
                        "version": "31.0.15.512",
                        "vs_installed": "newer",
                    }
                ],
            }
        ],
        firmware_rows=[
            {
                "target_key": "bios",
                "component": "System BIOS",
                "installed_version": "1.18.0",
                "status": "unknown",
                "tier": "normal",
                "offers": [],
            }
        ],
        data_sources=["session_driver_batch"],
        driver_batch_fetched_at="2026-07-25 21:09",
        firmware_fetched_at="2026-07-25 21:11",
        driver_batch_elapsed_ms=450_419,
        firmware_elapsed_ms=27_000,
    )
    assert payload["summary"]["drivers"]["device_count"] == 1
    assert payload["summary"]["drivers"]["by_status"]["newer"] == 1
    assert payload["summary"]["drivers"]["elapsed_ms"] == 450_419
    assert payload["summary"]["drivers"]["elapsed_human"] == "7.5 min (450 s)"
    assert payload["summary"]["firmware"]["elapsed_ms"] == 27_000
    assert payload["summary"]["firmware"]["elapsed_human"] == "27.0 s"
    text = cexp.format_text_summary(payload)
    assert "NVIDIA GPU" in text
    assert "nvlddmkm.sys" in text
    assert "System BIOS" in text
    assert "duration 7.5 min (450 s)" in text
    assert "duration 27.0 s" in text


def test_format_elapsed_ms() -> None:
    assert cexp.format_elapsed_ms(None) == ""
    assert cexp.format_elapsed_ms(450_419) == "7.5 min (450 s)"
    assert cexp.format_elapsed_ms(4_500) == "4.5 s"
    assert cexp.format_elapsed_ms(250) == "250 ms"


def test_export_index_section_in_text_summary() -> None:
    payload = cexp.build_payload(
        app_version="6.2.32",
        install_mode="portable",
        scan_mode={"mode": "full scan"},
        driver_rows=[],
        firmware_rows=[],
        export_index={
            "enabled": True,
            "read_error": "disk I/O error",
            "skipped_devices": ["Realtek Audio", "NVIDIA GPU"],
        },
    )
    text = cexp.format_text_summary(payload)
    assert "Driver index (SQLite)" in text
    assert "disk I/O error" in text
    assert "Realtek Audio" in text


def test_pick_offer_includes_match_debug_fields() -> None:
    offer = cexp.pick_offer(
        {
            "source": "oem",
            "source_label": "OEM (Dell)",
            "title": "Realtek LAN",
            "version": "2.0",
            "vs_installed": "newer",
            "hwid_matched": True,
            "oem_match_score": 8,
        }
    )
    assert offer["hwid_matched"] is True
    assert offer["oem_match_score"] == 8


def test_merge_export_row_lists() -> None:
    merged = cexp.merge_export_row_lists(
        [{"device_name": "A", "status": "newer"}],
        [{"device_name": "A", "status": "same"}, {"device_name": "B", "status": "none"}],
    )
    assert len(merged) == 2
    assert merged[0]["status"] == "newer"


def test_pick_offer_strips_empty_fields() -> None:
    offer = cexp.pick_offer(
        {
            "source": "microsoft",
            "source_label": "Microsoft Update Catalog",
            "title": "Driver",
            "version": "1.2.3",
            "vs_installed": "newer",
            "notes": "",
            "source_conflict": True,
        }
    )
    assert offer["version"] == "1.2.3"
    assert offer["source_conflict"] is True
    assert "notes" not in offer


def test_build_hardware_summary_enriched() -> None:
    hw = cexp.build_hardware_summary(
        {
            "system_manufacturer": "Alienware",
            "system_model": "m17 R5 AMD",
            "service_tag": "ABC1234",
            "baseboard_manufacturer": "Alienware",
            "baseboard_product": "0KWCC8",
            "pnp_list": [{"name": "x"}],
            "bios_driver_info": {"all_drivers": [{"name": "a"}], "system": {}},
        }
    )
    assert hw["manufacturer"] == "Alienware"
    assert hw["model"] == "m17 R5 AMD"
    assert hw["service_tag"] == "ABC1234"
    assert hw["oem_catalog_supported"] is True
    assert hw["device_list_count"] == 1


def test_build_payload_includes_lookup_health() -> None:
    import vendor_endpoint_health as veh

    lookup = veh.build_export_lookup_health(
        {},
        {"mode": "full scan", "active_list": ["OEM catalog"], "skipped_list": ["Quick WU"]},
        driver_rows=[
            {
                "offers": [{"source_label": "Microsoft Update Catalog", "source": "microsoft"}]
            }
        ],
    )
    payload = cexp.build_payload(
        app_version="6.1.0",
        export_options={},
        install_mode="portable",
        scan_mode={"mode": "full scan", "active_list": ["OEM catalog"]},
        driver_rows=[],
        firmware_rows=[],
        lookup_health=lookup,
    )
    assert payload["export_schema_version"] == 3
    assert payload["lookup_health"]["catalog_scan"]["active_sources"] == ["OEM catalog"]
    assert "Microsoft Update Catalog" in payload["lookup_health"]["offer_sources_in_export"]
    text = cexp.format_text_summary(payload)
    assert "Lookup sources & API health" in text
    assert "OEM catalog" in text


def test_build_hardware_summary_includes_fingerprint_and_windows() -> None:
    hw = cexp.build_hardware_summary(
        {
            "system_manufacturer": "HP",
            "system_model": "Pavilion",
            "pnp_list": [],
            "bios_driver_info": {},
        },
        system_ctx={
            "system_manufacturer": "HP",
            "system_model": "Pavilion",
            "service_tag": "ABC1234",
            "gpu_vendors_present": ["nvidia"],
            "cpu_vendor": "amd",
        },
    )
    assert hw["machine_fingerprint"]
    assert hw["gpu_vendors"] == ["nvidia"]
    assert hw["cpu_vendor"] == "amd"
    assert "windows_major_minor" in hw or "windows_build" in hw


def test_device_catalog_diagnostics_gpu_path() -> None:
    import driver_catalog as dc

    ctx = {
        "pnp_class": "display",
        "vendor_key": "nvidia",
        "device_label": "NVIDIA GeForce RTX",
        "instance_id": "PCI\\VEN_10DE&DEV_2484",
    }
    diag = cexp.device_catalog_diagnostics(ctx, system_ctx={})
    assert diag["vendor_key"] == "nvidia"
    assert diag["instance_id"].startswith("PCI\\")
    assert diag["catalog_source_path"] == dc.catalog_device_source_path(ctx, {})


def test_apply_redaction_strips_sensitive_fields() -> None:
    payload = cexp.build_payload(
        app_version="6.1.0",
        install_mode="full_install",
        scan_mode={"mode": "full scan"},
        crash_context={
            "faulting_driver": "nvlddmkm.sys",
            "culprit_device_names": ["PCI\\VEN_10DE"],
        },
        hardware_summary={
            "manufacturer": "Dell Inc.",
            "model": "XPS",
            "service_tag": "ABC1234",
            "system_sku": "0ABCD",
        },
        driver_rows=[
            {
                "device_name": "PCI\\VEN_10DE",
                "display_name": "NVIDIA GPU",
                "driver_file": "nvlddmkm.sys",
                "installed_version": "1.0",
                "status": "newer",
                "offers": [],
                "device_diagnostics": {
                    "instance_id": "PCI\\VEN_10DE&DEV_2484",
                    "catalog_source_path": "gpu_manufacturer_authoritative",
                },
            }
        ],
        firmware_rows=[],
        redact_sensitive=True,
    )
    assert payload.get("redacted_sensitive_fields") is True
    assert payload["hardware_summary"].get("service_tag") is None
    assert payload["drivers"][0]["device_name"] == "(redacted device id)"
    assert "driver_file" not in payload["drivers"][0]
    assert "instance_id" not in (payload["drivers"][0].get("device_diagnostics") or {})
    assert payload["drivers"][0]["device_diagnostics"]["catalog_source_path"]
    assert "culprit_device_names" not in payload["crash_context"]


if __name__ == "__main__":
    test_build_payload_and_text_summary()
    test_format_elapsed_ms()
    test_export_index_section_in_text_summary()
    test_build_payload_includes_lookup_health()
    test_apply_redaction_strips_sensitive_fields()
    test_pick_offer_includes_match_debug_fields()
    test_merge_export_row_lists()
    test_pick_offer_strips_empty_fields()
    test_build_hardware_summary_enriched()
    test_build_hardware_summary_includes_fingerprint_and_windows()
    test_device_catalog_diagnostics_gpu_path()
    print("Catalog export tests OK")
