"""
Driver catalog: compare installed vs Microsoft / OEM / vendor sources.
Download-only actions (no silent or automatic driver install).
Optional user-triggered restore point, driver backup, and System Restore enable.
Uses stdlib only (urllib, xml, subprocess).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import threading
import time
from collections import OrderedDict
from typing import Callable

import driver_version_identity as dvi
import oem_effective_version as oev
from catalog_scoring import (
    compare_firmware_versions,
    compare_driver_to_installed,
    compare_versions,
    driver_date_is_trustworthy,
    extract_version_from_text,
    parse_driver_package_date,
    parse_driver_version,
    _normalize_oem_date,
    _ctx_is_bluetooth_radio_device,
    _ctx_is_wifi_radio_device,
    _ctx_skip_amd_adrenalin_compare_gate,
    _intel_suite_vs_component_version_mismatch,
    _looks_like_amd_adrenalin_version,
    _looks_like_amd_chipset_package_version,
    _looks_like_amd_display_driver_version,
    _looks_like_intel_chipset_package_version,
    _looks_like_mediatek_uwd_version,
    _looks_like_nvidia_branch_version,
    _looks_like_nvidia_internal_version,
    _looks_like_realtek_apo_version,
    _looks_like_realtek_nic_driver_version,
    _looks_like_realtek_wdm_version,
    _looks_like_windows_inbox_driver_version,
    _load_amd_adrenalin_installed_version,
    _load_amd_chipset_suite_installed_version,
    _load_intel_chipset_suite_installed_version,
    _load_nvidia_branch_installed_version,
    _realtek_nic_cross_scheme_equivalent,
    _realtek_net_version_major,
    _version_schemes_compatible,
)

from catalog_mscatalog_session import (
    app_set_allows_persist,
    begin_batch_mscatalog_query_cache,
    catalog_include_preview_updates,
    clear_batch_mscatalog_query_cache,
    clear_install_probe_cache,
    clear_wu_driver_cache,
    configure_catalog,
    consume_mscatalog_startup_notice,
    ensure_mscatalog_module_ready,
    fetch_wu_driver_rows_deep,
    is_quick_check_mode,
    oem_offers_from_session_cache,
    oem_session_warmed_vendor_tags,
    peek_session_rows_truncated,
    persist_session_catalog_cache,
    set_gui_application_mode,
    set_gui_catalog_session,
    set_mscatalog_startup_notice,
    warm_batched_microsoft_online_store,
    warm_batched_mscatalog_queries,
    _allow_per_hwid_online_store,
    _BATCH_MSCATALOG_QUERY_CACHE,
    _cap_session_rows,
    _device_contexts_missing_hwid,
    _fetch_online_driver_store_for_hwid,
    _fetch_online_driver_store_for_hwids_batch,
    _fetch_online_driver_store_rows_uncached,
    _fetch_wu_driver_rows_uncached,
    _get_cached_online_driver_store_for_ctx,
    _get_cached_online_driver_store_rows,
    _get_cached_wu_driver_rows,
    _gui_application_mode_active,
    _gui_batched_online_store_enabled,
    _gui_batched_online_store_include_all,
    _gui_catalog_mode,
    _gui_catalog_parallel_workers,
    _gui_catalog_session_active,
    _gui_gap_catalog_fallback_enabled,
    _gui_mscatalog_batched_parallel_enabled,
    _gui_mscatalog_prewarm_enabled,
    _GUI_BATCH_INTER_PAUSE_SEC,
    _GUI_BATCH_MAX_WORKERS,
    _quick_check_mode,
    _GUI_DEVICE_SCAN_BATCH_SIZE,
    _GUI_ONLINE_HWID_WARM_BATCH_SIZE,
    _INSTALL_PROBE_CACHE,
    _WU_DRIVER_SEARCH_CRITERIA,
    _lazy_load_online_driver_store_all,
    _ONLINE_HWID_STORE_CACHE,
    _ONLINE_DRIVER_STORE_CLASS_BUCKETS,
    _online_store_hwid_candidates,
    _peek_online_driver_store_cache,
    _PNP_TO_STORE_CLASSES,
    _PNPSIGNED_DRIVER_CACHE,
    _PNPSIGNED_DRIVER_CACHE_AT,
    _PNPSIGNED_DRIVER_CACHE_TTL_SEC,
    _rebuild_online_store_class_buckets,
    _search_mscatalog_updates_cached,
    _SESSION_ROWS_CAP,
    _should_skip_online_driver_store,
    _unique_hwids_from_device_contexts,
    _unique_mscatalog_queries_from_device_contexts,
    _v6_catalog_enabled,
    _warm_mscatalog_parallel,
)
import catalog_mscatalog_session as _mscat_sess

from catalog_oem_live import (
    clear_oem_cache,
    fetch_acer_oem_offers,
    fetch_asus_oem_offers,
    fetch_dell_oem_offers,
    fetch_gigabyte_oem_offers,
    fetch_hp_oem_offers,
    fetch_lenovo_oem_offers,
    fetch_msi_oem_offers,
    fetch_oem_catalog_for_system,
    get_acer_bios_rows,
    get_acer_oem_rows,
    get_asus_oem_rows,
    get_dell_oem_rows,
    get_gigabyte_bios_rows,
    get_gigabyte_oem_rows,
    get_hp_oem_rows,
    get_lenovo_oem_rows,
    get_msi_oem_rows,
    parse_dell_software_manifest_root,
    system_has_oem_driver_catalog,
    _cached_oem_rows,
    _dell_service_tag,
    _slug_for_oem_api,
    _fetch_asus_oem_rows_live,
    _fetch_dell_oem_rows_live,
    _fetch_hp_oem_rows_live,
    _fetch_lenovo_oem_rows_live,
    _fetch_live_oem_offers,
    _fetch_msi_oem_rows_live,
    _get_dell_oem_rows_from_api,
    _get_dell_oem_rows_from_local_dup,
    _gigabyte_support_page_urls,
    _hp_fetch_wcc_driver_rows,
    _is_dell_driver_details_url,
    _is_generic_oem_support_row,
    _manufacturer_matches,
    _merge_dell_dup_inner_versions_into_rows,
    _merge_enterprise_oem_rows,
    _normalize_oem_driver_row_dict,
    _normalize_oem_driver_rows,
    _oem_live_row_warmers,
    _oem_model_candidates,
    _oem_model_slug_variants,
    _oem_offers_from_rows,
    _oem_row_cache_key,
    _oem_row_eligible_for_ctx,
    _oem_row_match_score,
    _oem_rows_to_catalog_offers,
    _oem_search_keywords,
    _parse_asus_driver_json,
    _parse_dell_dup_manifest,
    _parse_gigabyte_support_html,
    _parse_hp_wcc_driver_details,
    _resolve_dell_driver_download_url,
    _score_oem_row_for_ctx,
    _system_has_gigabyte_oem,
    _system_has_msi_oem,
    _warm_oem_session_cache,
    _windows_osid,
    _DELL_DRIVER_ID_RE,
    _DELL_DL_DIRECT_RE,
    _DELL_FILE_LOCATION_RE,
)

from catalog_device_profiles import (
    attach_all_dual_version_profiles,
    attach_chipset_platform_version_profile,
    attach_chipset_version_profile,
    attach_gpu_version_profile,
    attach_intel_me_version_profile,
    attach_network_version_profile,
    attach_realtek_audio_version_profile,
    build_chipset_platform_version_profile,
    build_chipset_version_profile,
    build_gpu_version_profile,
    build_intel_me_version_profile,
    build_network_version_profile,
    build_realtek_audio_version_profile,
    format_chipset_installed_table_cell,
    format_chipset_platform_installed_table_cell,
    format_chipset_platform_version_subtitle,
    format_chipset_version_subtitle,
    format_dual_version_installed_for_dev,
    format_dual_version_subtitle_for_dev,
    format_gpu_installed_table_cell,
    format_gpu_version_subtitle,
    format_intel_me_installed_table_cell,
    format_intel_me_version_subtitle,
    format_network_installed_table_cell,
    format_network_version_subtitle,
    format_realtek_audio_installed_table_cell,
    format_realtek_audio_version_subtitle,
    pick_dual_version_profile,
    # Re-exported for tests and stable driver_catalog.* patch targets.
    _collect_chipset_bundle_components,
    _load_broadcom_ethernet_installed_version,
    _load_intel_me_installed_version,
    _load_intel_wireless_installed_version,
    _load_killer_suite_installed_version,
    _load_qualcomm_wireless_installed_version,
    _load_realtek_ethernet_installed_version,
)
from catalog_offer_pipeline import (
    annotate_offer_source_conflicts,
    enrich_firmware_offers_with_comparison,
    enrich_offers_with_comparison,
    filter_offers_for_display,
    finalize_catalog_offers,
    offer_source_conflict_summary,
    offer_source_sort_tier,
    resolve_uncertain_catalog_offers,
    sort_catalog_offers,
    _append_compare_note,
    _finalize_catalog_offers,
    _installed_driver_date_from_ctx,
    _offer_installability_rank,
    _SAME_WITHOUT_VERSION_NOTE,
    _STATUS_RANK,
    _UNVERIFIED_NEWER_NOTE,
)
from catalog_http import (
    _HTTP_TIMEOUT,
    _amd_http_get_robust,
    _http_browser_headers,
    _http_get,
    _http_post_json,
    _looks_like_html_payload,
    _vendor_http_get_robust,
    catalog_user_agent,
)

from catalog_oem_filters import (
    _CATALOG_PACKAGE_BRAND_TOKENS,
    _DELL_OEM_INTERNAL_DRIVER_CLASSES,
    _OEM_AIRPLANE_MODE_HINTS,
    _OEM_PC_MAKER_UPDATE_APP_HINTS,
    _OEM_RADIO_CHIP_HINTS,
    _OEM_RADIO_CHIP_LABEL_TOKENS,
    _PC_OEM_BRAND_KEYS,
    _PLATFORM_SILICON_MANUFACTURER_HINTS,
    _STANDARD_PNP_MANUFACTURERS,
    _brand_identities_align,
    _ctx_label_has_radio_chip_hint,
    _device_brand_identities,
    _device_on_integrated_bus,
    _manufacturer_is_pc_system_oem,
    _manufacturer_is_platform_silicon_partner,
    _manufacturer_is_standard_or_ambiguous,
    _normalize_brand_token,
    _oem_package_title_is_bluetooth,
    _oem_package_title_is_wifi,
    _package_brand_identities,
    _pc_oem_catalog_may_target_device,
    _pnp_manufacturer_is_third_party,
    _reject_oem_airplane_mode_mismatch,
    _reject_oem_amd_chipset_on_component_inf,
    _reject_oem_application_on_driver_device,
    _reject_oem_audio_vendor_mismatch,
    _reject_oem_intel_chipset_on_component_inf,
    _reject_oem_package_brand_mismatch,
    _reject_oem_pc_maker_on_third_party_device,
    _reject_oem_pc_maker_update_application,
    _reject_oem_radio_chip_mismatch,
    _reject_oem_radio_wifi_bt_cross_mismatch,
    _reject_oem_realtek_hd_on_inbox_hd_controller,
)

from catalog_row_rejects import (
    _AMD_MEDIA_DRIVER_PHRASE,
    _AMD_SYSTEM_DRIVER_PHRASE,
    _FIRMWARE_CATALOG_TITLE_KEYWORDS,
    _GENERIC_PNP_DEVICE_LABELS,
    _PC_OEM_TITLE_PATTERNS,
    _PNP_CLASSES_BLOCK_AMD_SYSTEM,
    _SECURITY_AV_VENDOR_KEYWORDS,
    _catalog_hwid_mismatch_note,
    _catalog_row_hwid_blob,
    _catalog_row_hwid_matches_ctx,
    _catalog_row_hwid_strict_matches_ctx,
    _catalog_title_cross_oem_mismatch,
    _catalog_title_is_firmware_package,
    _catalog_title_is_security_software,
    _catalog_title_pc_oem_tags,
    _is_microsoft_catalog_row_source,
    _mscatalog_rows_hwid_first_keep,
    _normalize_catalog_row_for_reject,
    _prioritize_mscatalog_scored_rows,
    _realtek_catalog_row_is_companion_component,
    _realtek_catalog_row_is_wdm_codec,
    _realtek_device_component_role,
    _realtek_nic_mscatalog_trusted,
    _realtek_nic_public_build_suffix,
    _realtek_nic_same_oem_family,
    _realtek_nic_version_tail,
    _realtek_wdm_mscatalog_codec_rows_to_keep,
    _realtek_wdm_mscatalog_trusted,
    _reject_amd_bulk_catalog_row,
    _reject_mediatek_mscatalog_spurious,
    _reject_mscatalog_row_for_ctx,
    _reject_realtek_catalog_row,
    _reject_realtek_oem_net_family_mismatch,
    _reject_vendor_driver_class_mismatch,
    _shared_catalog_row_rejects,
    _system_pc_oem_tags,
)

from catalog_device_context import (
    _DRIVER_SCAN_EXCLUDED_PNP_CLASSES,
    _ctx_device_label,
    _ctx_is_amd_chipset_platform_row,
    _ctx_is_amd_device,
    _ctx_is_chipset_component_plumbing,
    _ctx_is_intel_chipset_platform_row,
    _ctx_is_intel_device,
    _device_is_amd_audio,
    _device_is_amd_chipset_plumbing,
    _device_is_amd_media,
    _device_is_chipset_plumbing,
    _device_is_intel_chipset_plumbing,
    _device_is_intel_me_device,
    _intel_driver_hint_from_ctx,
    _is_logitech_virtual_driver_noise,
    _nvidia_ctx_eligible,
    _nvidia_gpu_driver_lookup_applicable,
    _nvidia_is_audio_component,
    _nvidia_is_audio_or_usb_component,
    is_driver_scan_excluded_ctx,
    is_driver_scan_excluded_device,
    get_device_context,
    get_device_context_for_name,
    _apply_realtek_parent_hwid_ctx,
    _infer_pnp_class_for_device,
    _infer_vendor_from_device_name,
    _pci_tokens_from_id,
    _resolve_primary_installed_version,
)

from catalog_tier_policy import (
    _NETWORK_VENDOR_KEYS,
    _ctx_gpu_or_network_catalog,
    _ctx_is_chipset_catalog,
    _is_informational_catalog_offer,
    _is_manufacturer_catalog_offer,
    _manufacturer_confident_newer_offer,
    _manufacturer_gpu_lookup_uncertain,
    _oem_disk_offers_stale_vs_installed,
    _should_skip_oem_after_manufacturer_tier,
    has_actionable_versioned_manufacturer_offer,
    has_actionable_versioned_offer,
    should_defer_microsoft_catalog,
)

from catalog_offer_status import (
    _best_status_from_offers,
    _is_oem_support_link_offer,
    _microsoft_offer_status_eligible,
    _offer_contributes_to_status,
    _offer_is_intel_chipset_inf,
    _status_relevant_offers,
    _tier_has_actionable_offers,
    best_catalog_offer_version,
    best_authoritative_offer,
    best_versioned_offer,
    summarize_offer_status,
)

from catalog_none_reason import (
    classify_none_reason,
    format_device_check_progress,
    none_reason_display_label,
    possible_coverage_gap,
)

from catalog_realtek_queries import (
    _is_primary_realtek_wdm_oem_offer,
    _realtek_uad_catalog_queries,
    _soften_stale_realtek_wdm_oem_compare,
)

from catalog_offer_compare import (
    _alternate_installed_baselines,
    _apply_dual_baseline_gate,
    _apply_update_reporting_policy,
    _find_corroborating_offer,
    _inherit_verification_trust,
    _microsoft_hwid_verified_for_row,
    _offer_compare_version,
    _offer_has_installable_package,
    _offer_trusted_for_confident_newer,
    _probe_offer_install_path,
    _recompare_offer_row,
    _scheme_split_device_for_dual_baseline,
    _try_resolve_uncertain_offer,
)

from catalog_mscatalog_queries import (
    _batch_mscatalog_queries_for_ctx,
    _catalog_search_queries_for_ctx,
    _intel_mscatalog_queries,
    _is_hwid_query,
    _mediatek_mscatalog_queries,
)

from catalog_chipset_comparison import (
    _build_chipset_catalog_context,
    _chipset_platform_oem_offers,
    _load_chipset_suite_installed_version,
    _looks_like_chipset_package_version,
    _resolve_chipset_installed_version,
    build_chipset_platform_comparison,
    chipset_ms_catalog_limitation_note,
)

from catalog_lru_cache import _lru_cache_set, _lru_cache_touch

from catalog_vendor_cache import (
    _VENDOR_SCRAPE_CACHE,
    _VENDOR_SCRAPE_MAX_ENTRIES,
    _VENDOR_SCRAPE_TTL_SEC,
    _amd_vendor_cache_key,
    _nvidia_pnp_id_from_ctx,
    _nvidia_vendor_cache_key,
    _vendor_scrape_cache_get,
    _vendor_scrape_cache_set,
    _warm_vendor_scrapes_for_contexts,
    clear_vendor_scrape_cache,
)

from catalog_installed_packages import (
    clear_installed_package_versions_cache,
    _load_installed_package_versions,
    _load_installed_package_versions_winreg,
    _register_installed_package_from_name,
)

from catalog_wu_scoring import (
    _batch_prefilter_wu_rows,
    _filter_offers_for_device_ctx,
    _parse_wu_rows_for_scoring,
    _prefilter_wu_rows_for_ctx,
    _score_update_match,
)

from catalog_microsoft_scoring import (
    _iter_online_store_rows_for_ctx,
    _score_catalog_row_for_ctx,
    _score_online_driver_store_row,
    _version_plausible_for_ctx,
)

from catalog_microsoft_fetch import (
    _augment_gap_devices_with_verified_catalog,
    _gap_catalog_name_queries_for_ctx,
    _merge_wu_rows_by_update_id,
    _warm_gap_mscatalog_queries,
    fetch_microsoft_catalog_search_offers,
    fetch_microsoft_driver_offers,
    fetch_microsoft_driver_store_offers,
)

from catalog_intel_fetch import (
    _fetch_intel_page_html,
    _intel_attach_direct_download,
    _intel_best_version_from_html,
    _intel_dsa_utility_offer,
    _intel_fetch_dsa_chipset_page,
    _intel_fetch_dsa_graphics_page,
    _intel_fetch_product_page,
    _intel_page_needs_js_render,
    _intel_product_url,
    _intel_scrape_result_parts,
    _parse_intel_download_html,
    _parse_intel_version_from_embedded_json,
    _scrape_intel_download_page,
    _scrape_intel_driver_version,
    fetch_intel_driver_offers,
)
from catalog_intel_fetch import _INTEL_DSA_URL  # noqa: F401 — tests reference dc._INTEL_DSA_URL

from catalog_amd_fetch import (
    _amd_chipset_leaf_urls,
    _amd_drivers_download_url,
    _amd_fetch_chipset_from_hub_leaves,
    _amd_fetch_download_page_rendered,
    _amd_fetch_from_download_page,
    _amd_fetch_from_product_leaf,
    _amd_fetch_page_html,
    _amd_graphics_product_url,
    _amd_gpu_family_hint,
    _amd_vendor_version_lookup_applicable,
    _amd_version_from_html,
    _parse_amd_page_version,
    _scrape_amd_driver_version,
    _version_near_product_in_html,
    fetch_amd_driver_offers,
)

from catalog_nvidia_fetch import (
    _NVIDIA_RETIRED_API_MARKERS,  # noqa: F401 — audit_vendor_apis.py
    _nvidia_ajax_result_plausible,
    _nvidia_fetch_ajax_alternate_os,
    _nvidia_fetch_ajax_best_match,
    _nvidia_fetch_ajax_driver_lookup,
    _nvidia_fetch_processfind_lookup,
    _nvidia_gpu_within_support_floor,
    _nvidia_lookup_download_info,
    _nvidia_normalize_release_date,
    _nvidia_offer_from_ajax,
    _nvidia_parse_processfind_html,
    _nvidia_pci_dev_from_ctx,
    _nvidia_psid_pfid_candidates,
    _nvidia_psid_pfid_from_ctx,
    _nvidia_windows_os_id,
    fetch_nvidia_driver_offer,
)

from catalog_realtek_fetch import (
    _realtek_abs_url,
    _realtek_best_row_for_ctx,
    _realtek_cate_id_for_ctx,
    _realtek_normalize_date,
    _realtek_row_score,
    _realtek_rows_from_api_payload,
    _realtek_version_trustworthy,
    _realtek_windows_download_score,
    _scrape_realtek_category_rows,
    fetch_realtek_driver_offers,
)

from catalog_network_fetch import (
    _killer_component_version,
    _mediatek_product_slug,
    _network_vendor_cache_key,
    _qualcomm_chip_hint,
    _scrape_mediatek_product_rows,
    fetch_broadcom_driver_offers,
    fetch_killer_driver_offers,
    fetch_mediatek_driver_offers,
    fetch_network_vendor_offers,
    fetch_qualcomm_driver_offers,
)

from catalog_extended_fetch import (
    _EXTENDED_VENDOR_KEYS,
    _extended_vendor_cache_key,
    _marvell_product_kind,
    _peripheral_model_hint,
    _peripheral_support_url,
    _scrape_marvell_support_versions,
    fetch_elan_driver_offers,
    fetch_extended_vendor_offers,
    fetch_logitech_driver_offers,
    fetch_marvell_driver_offers,
    fetch_netgear_driver_offers,
    fetch_samsung_peripheral_offers,
    fetch_synaptics_driver_offers,
    fetch_tplink_driver_offers,
)

from catalog_multi_device import (
    _batch_check_worker_count,
    _build_multi_device_driver_comparison_body,
    _run_device_check_batch,
    build_multi_device_driver_comparison,
)

from catalog_download import (
    _DOWNLOAD_EXTENSIONS,
    _microsoft_catalog_url,
    _offer_download_kind,
    download_driver_offer,
    download_driver_package_for_install,
    download_file_to_folder,
    microsoft_catalog_view_url,
    resolve_vendor_package_download_url,
)

from catalog_system_actions import (
    backup_device_driver,
    create_system_restore_point,
    enable_system_restore,
    get_system_restore_status,
    open_device_manager,
    open_system_protection_settings,
)

from catalog_vendor_offers import (
    _catalog_system_ctx_from,
    _manufacturer_vendor_lookup_applicable,
    _offer_version_from_fields,
    _record_vendor_empty_extraction,
    _vendor_coverage_gap_offer,
    _vendor_fetch_get,
    _vendor_offer_row,
    fetch_generic_vendor_offer,
)

from catalog_oem_offers import (
    _oem_support_link_offers,
    _tag_offer_freshness,
    fetch_oem_driver_offers,
    fetch_oem_driver_offers_deep,
    oem_data_freshness_note,
)

from catalog_ps_context import (
    _build_pnpsigned_version_index,
    _CATALOG_CACHE_LOCK,
    _get_pnpsigned_driver_rows,
    _run_catalog_ps,
    catalog_powershell_available,
    consume_catalog_powershell_degraded,
    extend_system_ctx_for_catalog,
    mark_catalog_powershell_degraded,
)

from catalog_scan_summary import (
    build_summary_comparison_from_device_entries,
    build_uncertain_inspector_summary,
    catalog_scan_mode_summary,
)

from catalog_online_store import (
    ensure_online_driver_store_loaded,
    fetch_storage_driver_store_offers,
)

from catalog_device_comparison import (
    _build_device_comparison_from_ctx,
    _is_primary_gpu_display_manufacturer_authoritative,
    _manufacturer_catalog_tasks_for_ctx,
    _microsoft_catalog_task,
    _run_catalog_source_tasks,
    _skipped_firmware_driver_comparison,
    build_device_driver_comparison,
    catalog_device_source_path,
)



# Re-use project helpers when run as part of BSOD Analyzer
try:
    from bsod_crash_report import (
        DRIVER_TO_HARDWARE,
        _OEM_SUPPORT_URLS,
        _VENDOR_DRIVER_URLS,
        _find_pnp_entity_by_device_name,
        _infer_driver_vendor,
        _system_manufacturer_oem_url,
        find_culprit_devices,
        lookup_inventory_row,
    )
    from bsod_hardware_wmi import _extract_vendor_from_string
    from bsod_runtime import run_powershell
    from bsod_runtime import run_catalog_powershell
except ImportError:
    run_powershell = None  # type: ignore[assignment]
    run_catalog_powershell = None  # type: ignore[assignment,misc]

def _log_catalog_skip(context: str, exc: BaseException) -> None:
    """Best-effort session log when a non-fatal catalog path fails."""
    try:
        import session_log

        session_log.progress(
            "catalog",
            f"{context}: {type(exc).__name__}",
            extra={"status": "skip"},
        )
    except Exception:
        pass  # optional session_log; must not break catalog skip path


# Windows Update driver search is slow; reuse one result set per batch/session.
_oem_session_cache_enabled = True
_OEM_ROWS_CACHE: OrderedDict[str, tuple[list, float]] = OrderedDict()
_OEM_CACHE_TTL_SEC = 600.0
_OEM_CACHE_MAX_ENTRIES = 256
# GUI exe never loads Get-WindowsDriver -Online -All unless batched warm or CLI/tools opt in.
# Nested worker scopes (reference count — one worker finishing must not clear another's guard).

# Version/date scoring lives in catalog_scoring.py (re-exported at module level for tests/GUI).

