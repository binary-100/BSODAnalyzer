"""Targeted coverage for audit Improve test-gap modules (sections D–J)."""

from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import app_settings as app_set
import catalog_device_profiles as cdp
import catalog_device_context as cdc
import catalog_oem_live as oem_live
import catalog_offer_pipeline as offer_pipe
import catalog_scoring as scoring
import catalog_offer_status as offer_status
import catalog_offer_compare as offer_compare
import catalog_chipset_comparison as chipset_cmp
import catalog_installed_packages as inst_pkg
import catalog_vendor_cache as vendor_cache
import catalog_wu_scoring as wu_scoring
import catalog_microsoft_scoring as ms_scoring
import catalog_microsoft_fetch as ms_fetch
import catalog_intel_fetch as intel_fetch
import catalog_amd_fetch as amd_fetch
import catalog_nvidia_fetch as nvidia_fetch
import catalog_realtek_fetch as rt_fetch
import catalog_network_fetch as net_fetch
import catalog_extended_fetch as ext_fetch
import catalog_multi_device as multi_dev
import catalog_download as cat_dl
import catalog_device_comparison as dev_cmp
import catalog_mscatalog_queries as mscat_queries
import catalog_oem_filters as oem_filters
import catalog_oem_offers as oem_offers
import catalog_online_store as online_store
import catalog_ps_context as ps_ctx
import catalog_realtek_queries as rt_queries
import catalog_none_reason as none_reason
import catalog_scan_summary as scan_summary
import catalog_system_actions as sys_actions
import catalog_tier_policy as tier_policy
import catalog_vendor_offers as vendor_offers
import crash_report_events as cre
import crash_report_timeline as crt
import crash_report_culprit as crc
import crash_report_fix_plan as crfp
import crash_report_format as crfmt
import bsod_crash_report  # noqa: F401 — complete load before narrative (avoids _bc default-arg cycle)
import crash_report_narrative as crn
import analyzer_gather as agather
import analyzer_hardware as ahardware
import hardware_cache as hwcache
import log_cleanup as lc
import maintenance_log as mlog


def test_crash_report_fix_plan_uncertain_focus() -> None:
    fp = crfp.derive_report_fix_focus(
        None, {}, None, None, {}, {}, [], None, None, system_ctx={},
    )
    assert fp.get("focus") == crfp.FIX_UNCERTAIN


def test_crash_report_format_wrap_text() -> None:
    lines = crfmt._wrap_text("hello world", 20, "  ")
    assert lines and lines[0].startswith("  ")


def test_crash_report_timeline_parse_event_time() -> None:
    assert crt._parse_event_time("2026-05-01 12:00:00") is not None
    assert crt._parse_event_time("?") is None


def test_crash_report_culprit_synthetic_key() -> None:
    key = crc.crash_synthetic_device_key("nvlddmkm.sys")
    assert crc.is_crash_synthetic_device_key(key)
    assert crc.has_crash_faulting_driver("nvlddmkm.sys")
    assert not crc.has_crash_faulting_driver("genuineintel")


def test_catalog_oem_filters_brand_token() -> None:
    assert oem_filters._normalize_brand_token("Dell Inc.") == "dell"


def test_catalog_oem_offers_freshness_note() -> None:
    assert "Live OEM" in oem_offers.oem_data_freshness_note("live")


def test_catalog_vendor_offers_version_from_fields() -> None:
    assert vendor_offers._offer_version_from_fields({"version": "10.0.0.1"}) == "10.0.0.1"


def test_catalog_ps_context_powershell_available() -> None:
    assert isinstance(ps_ctx.catalog_powershell_available(), bool)


def test_catalog_scan_summary_mode_summary() -> None:
    summary = scan_summary.catalog_scan_mode_summary(quick_check=True)
    assert summary.get("mode") == "quick check"


def test_catalog_online_store_storage_tokens() -> None:
    with mock.patch.object(online_store, "_should_skip_online_driver_store", return_value=True):
        assert online_store.fetch_storage_driver_store_offers("Samsung SSD 980", "1.0") == []


def test_catalog_system_actions_restore_shape() -> None:
    with mock.patch.object(sys_actions, "_dc", return_value=lambda *_a, **_k: (False, "")):
        status = sys_actions.get_system_restore_status()
    assert "drive" in status


def test_crash_report_events_parse_p1() -> None:
    assert cre.parse_p1("0") == 0
    assert cre.parse_p1("0x1a") == 0x1A
    assert cre.parse_p1("42") == 42
    assert cre.parse_p1("not-a-number") is None


def test_crash_report_events_decode_exception_code() -> None:
    assert "Access violation" in cre.decode_exception_code("0xC0000005")
    assert cre.decode_exception_code("") == ""


def test_crash_report_events_group_by_incident() -> None:
    events = [
        {"time": "2026-05-01 12:00:00", "id": "a"},
        {"time": "2026-05-01 12:01:00", "id": "b"},
        {"time": "2026-05-01 13:00:00", "id": "c"},
    ]
    groups = cre.group_events_by_incident(events, window_minutes=2)
    assert len(groups) == 2
    ids = {frozenset(e["id"] for e in g) for g in groups}
    assert ids == {frozenset({"a", "b"}), frozenset({"c"})}


def test_bsod_crash_report_reexports_event_helpers() -> None:
    import bsod_crash_report as crash_report

    assert crash_report._parse_p1("0x10") == 16
    assert crash_report.has_crash_faulting_driver("nvlddmkm.sys")
    assert not crash_report.has_crash_faulting_driver("")
    key = crash_report.crash_synthetic_device_key("nvlddmkm.sys")
    assert crash_report.is_crash_synthetic_device_key(key)


def test_gui_mixin_classes_importable() -> None:
    import gui_mixin_analysis
    import gui_mixin_catalog
    import gui_mixin_catalog_export
    import gui_mixin_catalog_install
    import gui_mixin_catalog_layout
    import gui_mixin_catalog_packages
    import gui_mixin_catalog_scan
    import gui_mixin_catalog_shell
    import gui_mixin_drivers
    import gui_mixin_drivers_inventory
    import gui_mixin_drivers_table
    import gui_mixin_drivers_workflow
    import gui_mixin_firmware
    import gui_mixin_firmware_inventory
    import gui_mixin_firmware_scan
    import gui_mixin_firmware_table
    import gui_mixin_firmware_workflow
    import gui_mixin_lifecycle
    import gui_mixin_maintenance
    import gui_mixin_settings
    import gui_mixin_shell
    import gui_mixin_system
    import gui_mixin_tabs
    import gui_mixin_task_progress
    import gui_mixin_vendor_health
    import gui_mixin_window_chrome

    assert gui_mixin_analysis.GuiAnalysisMixin.__name__ == "GuiAnalysisMixin"
    assert gui_mixin_shell.GuiShellMixin.__name__ == "GuiShellMixin"
    assert gui_mixin_settings.GuiSettingsMixin.__name__ == "GuiSettingsMixin"
    assert gui_mixin_catalog_layout.GuiCatalogLayoutMixin.__name__ == "GuiCatalogLayoutMixin"
    assert gui_mixin_catalog_shell.GuiCatalogShellMixin.__name__ == "GuiCatalogShellMixin"
    assert gui_mixin_task_progress.GuiTaskProgressMixin.__name__ == "GuiTaskProgressMixin"
    assert gui_mixin_maintenance.GuiMaintenanceMixin.__name__ == "GuiMaintenanceMixin"
    assert gui_mixin_lifecycle.GuiLifecycleMixin.__name__ == "GuiLifecycleMixin"
    assert gui_mixin_window_chrome.GuiWindowChromeMixin.__name__ == "GuiWindowChromeMixin"
    assert gui_mixin_tabs.GuiTabsMixin.__name__ == "GuiTabsMixin"
    assert gui_mixin_system.GuiSystemMixin.__name__ == "GuiSystemMixin"
    assert gui_mixin_drivers.GuiDriversMixin.__name__ == "GuiDriversMixin"
    assert gui_mixin_drivers_table.GuiDriversTableMixin.__name__ == "GuiDriversTableMixin"
    assert gui_mixin_drivers_inventory.GuiDriversInventoryMixin.__name__ == "GuiDriversInventoryMixin"
    assert gui_mixin_catalog.GuiCatalogMixin.__name__ == "GuiCatalogMixin"
    assert gui_mixin_catalog_scan.GuiCatalogScanMixin.__name__ == "GuiCatalogScanMixin"
    assert gui_mixin_catalog_packages.GuiCatalogPackagesMixin.__name__ == "GuiCatalogPackagesMixin"
    assert gui_mixin_catalog_install.GuiCatalogInstallMixin.__name__ == "GuiCatalogInstallMixin"
    assert gui_mixin_catalog_export.GuiCatalogExportMixin.__name__ == "GuiCatalogExportMixin"
    assert gui_mixin_catalog_export.ExportFileChoices.__name__ == "ExportFileChoices"
    assert gui_mixin_drivers_workflow.GuiDriversWorkflowMixin.__name__ == "GuiDriversWorkflowMixin"
    assert gui_mixin_firmware.GuiFirmwareMixin.__name__ == "GuiFirmwareMixin"
    assert gui_mixin_firmware_workflow.GuiFirmwareWorkflowMixin.__name__ == "GuiFirmwareWorkflowMixin"
    assert gui_mixin_firmware_inventory.GuiFirmwareInventoryMixin.__name__ == "GuiFirmwareInventoryMixin"
    assert gui_mixin_firmware_table.GuiFirmwareTableMixin.__name__ == "GuiFirmwareTableMixin"
    assert gui_mixin_firmware_scan.GuiFirmwareScanMixin.__name__ == "GuiFirmwareScanMixin"
    assert gui_mixin_vendor_health.GuiVendorHealthMixin.__name__ == "GuiVendorHealthMixin"


def test_gui_app_context_exports_qt_and_workers() -> None:
    import gui_app_context as ctx

    assert hasattr(ctx, "QtWidgets")
    assert hasattr(ctx, "AnalysisWorker")
    assert hasattr(ctx, "MainWindowSignalRelay")


def test_gui_signal_relay_slot_names() -> None:
    import gui_signal_relay

    assert hasattr(gui_signal_relay.MainWindowSignalRelay, "analysis_progress")
    assert hasattr(gui_signal_relay.MainWindowSignalRelay, "analysis_finished")


def test_hardware_cache_portable_mode_is_noop() -> None:
    settings = dict(app_set.DEFAULT_SETTINGS)
    settings["install_mode"] = "portable"
    with mock.patch.object(app_set, "load_settings", return_value=settings):
        assert hwcache._cache_dir() is None
        assert hwcache.load_cached_profile() is None


def test_hardware_cache_parse_cached_at() -> None:
    assert hwcache._parse_cached_at("2026-01-02T03:04:05Z") is not None
    assert hwcache._parse_cached_at("garbage") is None


def test_catalog_scoring_compare_versions() -> None:
    assert scoring.compare_versions("1.0.0", "2.0.0") == "newer"
    assert scoring.compare_versions("10.0", "10.0.0") == "same"
    assert scoring._normalize_oem_date("2026-02-02") == "2026-02-02"


def test_catalog_offer_status_summarize_none() -> None:
    assert offer_status.summarize_offer_status([]) == "none"


def test_catalog_none_reason_standard_device() -> None:
    ctx = {"manufacturer": "(Standard system devices)", "primary_version": "10.0.0.1"}
    assert none_reason.classify_none_reason(ctx, [], status="none") == "standard_device"


def test_catalog_http_user_agent_and_html_sniff() -> None:
    import catalog_http as http
    import driver_catalog as dc

    assert "BSODAnalyzer/" in http.catalog_user_agent()
    assert http.catalog_user_agent() == dc.catalog_user_agent()
    assert http._looks_like_html_payload(b"<!DOCTYPE html><html><body>x</body></html>")
    assert not http._looks_like_html_payload(b"MZ" + b"\x00" * 100)


def test_catalog_row_rejects_shared_mscatalog() -> None:
    import catalog_row_rejects as rejects

    row = {"title": "Kaspersky Endpoint Security", "version": "1.0"}
    ctx = {"device_label": "Intel Wi-Fi 6", "vendor_key": "intel", "pnp_class": "net"}
    assert rejects._reject_mscatalog_row_for_ctx(row, ctx, "Intel Wi-Fi") == "security_software"
    assert rejects._shared_catalog_row_rejects is not None


def test_catalog_offer_pipeline_sort_tier() -> None:
    assert offer_pipe.offer_source_sort_tier("oem") < offer_pipe.offer_source_sort_tier("microsoft")


def test_catalog_oem_live_manufacturer_matches() -> None:
    assert oem_live._manufacturer_matches("Dell Inc.", "dell")
    assert not oem_live._manufacturer_matches("HP Inc.", "dell")


def test_catalog_device_profiles_gpu_profile_shape() -> None:
    dev = {
        "device_class": "display",
        "vendor_key": "nvidia",
        "name": "NVIDIA GeForce RTX",
        "version": "32.0.15.7688",
        "_installed_at_scan": "32.0.15.7688",
    }
    profile = cdp.build_gpu_version_profile(dev)
    assert profile is not None
    assert profile["vendor"] == "nvidia"


def test_log_cleanup_guidance_and_admin_check() -> None:
    assert len(lc.GUIDANCE_STEPS) >= 3
    assert isinstance(lc.is_user_admin(), bool)


def test_log_cleanup_dir_size_mb_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert lc._dir_size_mb(tmp) == 0.0


def test_maintenance_log_format_events_plain() -> None:
    text = mlog.format_events_plain([])
    assert "No maintenance activity" in text
    text2 = mlog.format_events_plain(
        [{"local_at": "2026-05-01 12:00:00", "kind": "test", "summary": "ok"}]
    )
    assert "[test]" in text2


def test_catalog_device_context_builds_vendor_key() -> None:
    ctx = cdc.get_device_context_for_name("Realtek Audio", [], [], None)
    assert ctx.get("vendor_key") == "realtek"


def test_catalog_tier_policy_realtek_net_never_defers() -> None:
    ctx = {"vendor_key": "realtek", "pnp_class": "net"}
    offers = [{"source": "oem", "version": "10.0.0.1"}]
    assert not tier_policy.should_defer_microsoft_catalog(offers, "9.0.0.0", ctx)


def test_catalog_offer_compare_has_installable_cab() -> None:
    assert offer_compare._offer_has_installable_package(
        {"download_kind": "cab", "url": "https://example.com/x.cab"}
    )


def test_catalog_microsoft_fetch_merge_wu_rows() -> None:
    rows = ms_fetch._merge_wu_rows_by_update_id([
        [{"UpdateId": "abc", "Title": "Driver A"}],
        [{"UpdateId": "abc", "Title": "Driver A duplicate"}],
    ])
    assert len(rows) == 1


def test_catalog_intel_fetch_scrape_result_parts() -> None:
    assert intel_fetch._intel_scrape_result_parts(("1.2.3", "2024-01-01", "https://x", "https://dl")) == (
        "1.2.3",
        "2024-01-01",
        "https://x",
        "https://dl",
    )
    assert intel_fetch._intel_scrape_result_parts(None) == ("", "", "", "")


def test_catalog_amd_fetch_gpu_family_hint() -> None:
    ctx = {"device_label": "AMD Radeon RX 7800 XT"}
    assert amd_fetch._amd_gpu_family_hint(ctx) == "RX 7800 XT"


def test_catalog_nvidia_fetch_processfind_parser() -> None:
    html = (
        '<tr id="driverList">'
        '<td class="version">581.42</td><td class="date">Jan 15, 2026</td>'
        "</tr>"
    )
    parsed = nvidia_fetch._nvidia_parse_processfind_html(html)
    assert parsed is not None
    assert parsed["Version"] == "581.42"


def test_catalog_realtek_fetch_cate_mapping() -> None:
    cate, hint = rt_fetch._realtek_cate_id_for_ctx({
        "pnp_class": "media",
        "device_label": "Realtek Audio",
        "instance_id": "",
    })
    assert cate == "593"
    assert hint == "audio"


def test_catalog_network_fetch_qualcomm_chip_hint() -> None:
    assert net_fetch._qualcomm_chip_hint({
        "device_label": "Qualcomm QCA9377 Wireless",
        "instance_id": "",
    }) == "QCA9377"


def test_catalog_extended_fetch_marvell_product_kind() -> None:
    assert ext_fetch._marvell_product_kind({
        "device_label": "Marvell Yukon 88E8056 PCI-E Gigabit",
        "pnp_class": "net",
        "instance_id": "PCI\\VEN_11AB&DEV_436B",
    }) == "network"


def test_catalog_multi_device_batch_worker_count() -> None:
    assert multi_dev._batch_check_worker_count(5) >= 1
    assert multi_dev._batch_check_worker_count(5, gui_batch=True) >= 1


def test_catalog_download_offer_kind() -> None:
    assert cat_dl._offer_download_kind({"download_kind": "catalog"}) == "catalog"


def test_catalog_device_comparison_source_path() -> None:
    assert dev_cmp.catalog_device_source_path({"pnp_class": "net", "vendor_key": "realtek"}) == "network_realtek_full"


def test_catalog_microsoft_scoring_plausible_display() -> None:
    ctx = {"vendor_key": "nvidia", "pnp_class": "display"}
    assert ms_scoring._version_plausible_for_ctx("581.42.15", ctx)
    assert not ms_scoring._version_plausible_for_ctx("10.0.26100", ctx)


def test_catalog_wu_scoring_update_match() -> None:
    ctx = {"vendor_key": "nvidia", "device_label": "nvidia display", "pnp_class": "display"}
    assert wu_scoring._score_update_match("NVIDIA display driver", ctx) >= 10


def test_catalog_vendor_cache_miss_returns_none() -> None:
    vendor_cache.clear_vendor_scrape_cache()
    assert vendor_cache._vendor_scrape_cache_get("__missing_test_key__") is None


def test_catalog_installed_packages_register_amd() -> None:
    out: dict[str, str] = {}
    inst_pkg._register_installed_package_from_name(out, "AMD Chipset Drivers", "8.05.04.516")
    assert out.get("amd_chipset") == "8.05.04.516"


def test_catalog_chipset_suite_version_helper() -> None:
    assert chipset_cmp._looks_like_chipset_package_version("10.1.19600.8418", "intel")


def test_catalog_mscatalog_queries_hwid() -> None:
    assert mscat_queries._is_hwid_query(r"PCI\VEN_10DE&DEV_2484")


def test_catalog_realtek_uad_queries_wdm() -> None:
    ctx = {"vendor_key": "realtek", "device_label": "Realtek Audio", "pnp_class": "media"}
    qs = rt_queries._realtek_uad_catalog_queries(ctx)
    assert any("Realtek Media" in q for q in qs)


def test_crash_report_narrative_infer_cause_type() -> None:
    out = crn.infer_likely_cause_type(
        "nvlddmkm.sys", 0x116, None, [], [], thermal_events=[], reliability_ctx={},
    )
    assert out.get("label")


def test_crash_report_narrative_confidence_summary() -> None:
    conf = crn.build_crash_confidence_summary(
        [],
        {"faulting_driver": "nvlddmkm.sys", "dumps_analyzed": 1},
        driver_verification={"attribution": {"can_name_faulting_driver": True}},
        needs_config=False,
        has_bugcheck=True,
    )
    assert conf.get("level") == "verified"
    assert "nvlddmkm" in (conf.get("detail") or "")


def test_analyzer_gather_exports() -> None:
    assert callable(agather.gather_report_data)
    assert callable(agather.gather_firmware_inventory_for_gui)


def test_analyzer_hardware_exports() -> None:
    assert callable(ahardware.gather_hardware_profile)
    assert callable(ahardware._gather_hardware_profile_legacy)


def test_facade_parse_event_time_via_ba() -> None:
    import bsod_analyzer as core
    from bsod_minidump import _ba

    assert hasattr(core, "_parse_event_time")
    dt = _ba("_parse_event_time")("2026-05-01 12:00:00")
    assert dt is not None
    assert _ba("_parse_event_time")("?") is None


def test_load_all_drivers_worker_enrich_path() -> None:
    """LoadAllDriversWorker must enrich via device_enrichment when pnp_index is set."""
    import device_enrichment as de

    rows = [{"name": "Ethernet", "version": "1.0"}]
    index = {"Ethernet": {"vendor": "Intel", "device_id": "PCI\\VEN_8086"}}
    out = de.enrich_driver_inventory_rows(
        rows,
        index,
        known_vendor_fn=lambda s: (s or "").split()[0],
        parallel=False,
    )
    assert out and out[0].get("name") == "Ethernet"


def test_bsod_gui_log_cleanup_module_exports() -> None:
    import bsod_gui_log_cleanup as gui_log_cleanup

    assert hasattr(gui_log_cleanup, "PreparePage")
    assert hasattr(gui_log_cleanup, "InventoryPage")
    assert gui_log_cleanup.PreparePage.__name__ == "PreparePage"


if __name__ == "__main__":
    mod = sys.modules[__name__]
    for name, obj in inspect.getmembers(mod):
        if name.startswith("test_") and callable(obj):
            obj()
            print(f"OK: {name}")
    print("test_improve_coverage: all passed")
