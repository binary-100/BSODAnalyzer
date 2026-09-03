"""Batched Microsoft online driver store warm (GUI stability + coverage)."""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driver_catalog as dc
import catalog_mscatalog_session as mscat


def test_unique_hwids_from_contexts_dedupes() -> None:
    contexts = {
        "a": {"instance_id": "PCI\\VEN_10DE&DEV_2484&SUBSYS_11111111&REV_A1"},
        "b": {"instance_id": "PCI\\VEN_10DE&DEV_2484&SUBSYS_22222222&REV_A1"},
        "c": {"instance_id": ""},
    }
    hwids = dc._unique_hwids_from_device_contexts(contexts)
    assert len(hwids) >= 2
    assert all("VEN_10DE" in h.upper() for h in hwids)


def test_peek_online_store_cache_without_fetch() -> None:
    dc.set_gui_application_mode(True)
    try:
        mscat._ONLINE_DRIVER_STORE_CACHE = [{"Version": "1.2.3.4", "ClassName": "net"}]
        mscat._ONLINE_DRIVER_STORE_CACHE_AT = __import__("time").monotonic()
        assert dc._peek_online_driver_store_cache()
        rows, err = dc._get_cached_online_driver_store_rows()
        assert rows and not err
    finally:
        dc.set_gui_application_mode(False)
        mscat._ONLINE_DRIVER_STORE_CACHE = None
        mscat._ONLINE_DRIVER_STORE_CACHE_AT = 0.0


def test_warm_batched_hwids_in_batches() -> None:
    batch_calls: list[list[str]] = []

    def fake_batch_fetch(hwids: list[str]) -> dict[str, tuple[list[dict], str]]:
        batch_calls.append(list(hwids))
        row = [{"Version": "1.0.0.1", "ClassName": "net", "HardwareDescription": "Net"}]
        return {h.upper(): (row, "") for h in hwids}

    contexts = {
        f"d{i}": {"instance_id": f"PCI\\VEN_8086&DEV_{1000 + i:04d}&SUBSYS_00000000&REV_00"}
        for i in range(7)
    }
    dc.set_gui_application_mode(True)
    dc.configure_catalog(quick_check=False)
    mscat._ONLINE_HWID_STORE_CACHE.clear()
    all_calls: list[str] = []

    def fake_all_fetch() -> tuple[list[dict], str]:
        all_calls.append("all")
        return [{"Version": "9.9.9.9", "ClassName": "net"}], ""

    try:
        with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), mock.patch.object(
            dc, "_fetch_online_driver_store_for_hwids_batch", side_effect=fake_batch_fetch
        ), mock.patch.object(
            dc, "_fetch_online_driver_store_rows_uncached", side_effect=fake_all_fetch
        ), mock.patch.object(
            dc, "_gui_batched_online_store_include_all", return_value=True
        ), mock.patch.object(
            mscat, "_GUI_BATCH_INTER_PAUSE_SEC", 0
        ):
            orig_batch = mscat._GUI_ONLINE_HWID_WARM_BATCH_SIZE
            mscat._GUI_ONLINE_HWID_WARM_BATCH_SIZE = 3
            try:
                dc.warm_batched_microsoft_online_store(
                    contexts,
                    {"_gui_driver_catalog": True},
                    progress=lambda _m: None,
                )
            finally:
                mscat._GUI_ONLINE_HWID_WARM_BATCH_SIZE = orig_batch
        expected = len(dc._unique_hwids_from_device_contexts(contexts))
        warmed = sum(len(b) for b in batch_calls)
        assert warmed == expected
        assert expected >= 7
        assert len(batch_calls) == (expected + 2) // 3
        assert all_calls == []
    finally:
        dc.set_gui_application_mode(False)
        mscat._ONLINE_HWID_STORE_CACHE.clear()


def test_batch_mscatalog_query_cap() -> None:
    ctx = {
        "_batch_driver_check": True,
        "instance_id": "PCI\\VEN_10DE&DEV_2484&SUBSYS_11111111&REV_A1",
        "device_label": "NVIDIA GeForce RTX",
        "vendor_key": "nvidia",
        "pnp_class": "display",
    }
    full = dc._catalog_search_queries_for_ctx({**ctx, "_batch_driver_check": False})
    batch = dc._catalog_search_queries_for_ctx(ctx)
    assert len(full) >= 2
    assert batch == ["PCI\\VEN_10DE&DEV_2484"]


def test_mscatalog_prewarm_off_by_default() -> None:
    calls: list[str] = []

    def fake_search(query: str, **kwargs) -> tuple[list[dict], str]:
        calls.append(query)
        return [], ""

    contexts = {
        "a": {
            "instance_id": "PCI\\VEN_10DE&DEV_2484&SUBSYS_11111111&REV_A1",
            "device_label": "NVIDIA GeForce RTX",
            "vendor_key": "nvidia",
            "pnp_class": "display",
            "pci_tokens": ["VEN_10DE", "DEV_2484"],
        },
    }
    dc.begin_batch_mscatalog_query_cache()
    try:
        with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), mock.patch.object(
            dc, "_gui_mscatalog_prewarm_enabled", return_value=False
        ), mock.patch.object(
            dc, "_gui_mscatalog_batched_parallel_enabled", return_value=False
        ), mock.patch(
            "catalog_ps_module.search_mscatalog_updates", side_effect=fake_search
        ):
            dc.warm_batched_mscatalog_queries(contexts, progress=lambda _m: None)
        assert calls == []
    finally:
        dc.clear_batch_mscatalog_query_cache()


def test_mscatalog_batch_prewarm_dedupes() -> None:
    calls: list[str] = []

    def fake_search(query: str, **kwargs) -> tuple[list[dict], str]:
        calls.append(query)
        return [{
            "title": f"Driver for {query[:20]}",
            "version": "1.0.0.1",
            "update_id": f"uid-{len(calls)}",
            "catalog_tier": "standard",
        }], ""

    contexts = {
        "a": {
            "instance_id": "PCI\\VEN_10EC&DEV_8125&SUBSYS_11111111&REV_A1",
            "device_label": "Realtek PCIe 2.5GbE",
            "vendor_key": "realtek",
            "pnp_class": "net",
            "pci_tokens": ["VEN_10EC", "DEV_8125"],
        },
        "b": {
            "instance_id": "PCI\\VEN_10EC&DEV_8125&SUBSYS_22222222&REV_A1",
            "device_label": "Realtek PCIe 2.5GbE",
            "vendor_key": "realtek",
            "pnp_class": "net",
            "pci_tokens": ["VEN_10EC", "DEV_8125"],
        },
    }
    dc.begin_batch_mscatalog_query_cache()
    try:
        with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), mock.patch.object(
            dc, "_gui_mscatalog_prewarm_enabled", return_value=True
        ), mock.patch.object(
            dc, "_gui_mscatalog_batched_parallel_enabled", return_value=False
        ), mock.patch.object(
            dc, "ensure_mscatalog_module_ready", return_value=True
        ), mock.patch(
            "catalog_ps_module.search_mscatalog_updates", side_effect=fake_search
        ):
            dc.warm_batched_mscatalog_queries(contexts, progress=lambda _m: None)
            unique = len(dc._unique_mscatalog_queries_from_device_contexts(contexts))
            assert len(calls) == unique
            dc.warm_batched_mscatalog_queries(contexts, progress=lambda _m: None)
            assert len(calls) == unique
    finally:
        dc.clear_batch_mscatalog_query_cache()


def test_mscatalog_batch_prewarm_parallel_seeds_cache() -> None:
    """Batched-parallel warm runs one batch call and seeds the query cache."""
    batch_calls: list[list[str]] = []

    def fake_batch(queries, **kwargs) -> dict[str, list[dict]]:
        batch_calls.append(list(queries))
        return {
            q: [{
                "title": f"Driver for {q[:20]}",
                "version": "1.0.0.1",
                "update_id": f"uid-{i}",
                "catalog_tier": "standard",
                "source": "microsoft_catalog",
            }]
            for i, q in enumerate(queries)
        }

    contexts = {
        "a": {
            "instance_id": "PCI\\VEN_10EC&DEV_8125&SUBSYS_11111111&REV_A1",
            "device_label": "Realtek PCIe 2.5GbE",
            "vendor_key": "realtek",
            "pnp_class": "net",
            "pci_tokens": ["VEN_10EC", "DEV_8125"],
        },
        "b": {
            "instance_id": "PCI\\VEN_10EC&DEV_8125&SUBSYS_22222222&REV_A1",
            "device_label": "Realtek PCIe 2.5GbE",
            "vendor_key": "realtek",
            "pnp_class": "net",
            "pci_tokens": ["VEN_10EC", "DEV_8125"],
        },
    }
    dc.begin_batch_mscatalog_query_cache()
    try:
        # warm_batched_mscatalog_queries and these three gates all live in
        # catalog_mscatalog_session; patching the driver_catalog facade never
        # intercepts the module-internal lookups.
        import catalog_mscatalog_session as cms

        with mock.patch.object(cms, "_v6_catalog_enabled", return_value=True), mock.patch.object(
            cms, "_gui_mscatalog_batched_parallel_enabled", return_value=True
        ), mock.patch.object(
            cms, "_gui_mscatalog_parallel_throttle", return_value=5
        ), mock.patch(
            "catalog_ps_batch.search_mscatalog_batch", side_effect=fake_batch
        ):
            unique = dc._unique_mscatalog_queries_from_device_contexts(contexts)
            dc.warm_batched_mscatalog_queries(contexts, progress=lambda _m: None)
            # Exactly one batch call, carrying every unique query.
            assert len(batch_calls) == 1
            assert sorted(batch_calls[0]) == sorted(unique)
            # Cache seeded for each unique query.
            for q in unique:
                assert q.strip().lower() in dc._BATCH_MSCATALOG_QUERY_CACHE
            # Second warm is a no-op (already cached) — no new batch call.
            dc.warm_batched_mscatalog_queries(contexts, progress=lambda _m: None)
            assert len(batch_calls) == 1
    finally:
        dc.clear_batch_mscatalog_query_cache()


def test_device_comparison_parallel_oem_microsoft_wu_only_first() -> None:
    order: list[str] = []

    def fake_oem(_ctx, _sys):
        order.append("oem")
        return [{"source": "oem", "title": "OEM pkg", "version": "9.9.9.9"}]

    def fake_ms(_ctx, **kwargs):
        order.append("microsoft")
        assert kwargs.get("allow_catalog_search") is False
        return [{"source": "microsoft", "title": "WU pkg", "version": "1.0.0.1"}]

    ctx = {
        "instance_id": "PCI\\VEN_8086&DEV_2725&SUBSYS_00000000&REV_00",
        "device_label": "Intel Wi-Fi",
        "vendor_key": "intel",
        "pnp_class": "net",
        "pci_tokens": ["VEN_8086", "DEV_2725"],
        "_prefiltered_wu_rows": [],
        "installed_rows": [{"version": "1.0.0.0"}],
    }
    with mock.patch.object(dc, "fetch_oem_driver_offers", side_effect=fake_oem), mock.patch.object(
        dc, "fetch_microsoft_driver_offers", side_effect=fake_ms
    ), mock.patch.object(
        dc, "fetch_microsoft_catalog_search_offers", return_value=[]
    ), mock.patch.object(
        dc, "_manufacturer_catalog_tasks_for_ctx", return_value={}
    ), mock.patch.object(
        dc, "_resolve_primary_installed_version", return_value="1.0.0.0"
    ):
        dc._build_device_comparison_from_ctx(ctx, {"system_manufacturer": "Dell Inc."})
    assert "oem" in order
    assert "microsoft" in order


def test_lazy_all_blocked_during_gui_catalog_session() -> None:
    dc.set_gui_application_mode(True)
    dc.set_gui_catalog_session(True)
    all_calls: list[str] = []

    def fake_all() -> tuple[list[dict], str]:
        all_calls.append("all")
        return [{"Version": "1.0.0.1", "ClassName": "net"}], ""

    ctx = {
        "instance_id": "",
        "pnp_class": "net",
        "vendor_key": "realtek",
        "device_label": "Realtek PCIe GbE",
    }
    try:
        with mock.patch.object(
            dc, "_fetch_online_driver_store_rows_uncached", side_effect=fake_all
        ):
            offers = dc.fetch_microsoft_driver_store_offers(ctx)
        assert all_calls == []
        assert offers
        assert offers[0].get("title") == "Online catalog scan skipped in GUI"
    finally:
        dc.set_gui_catalog_session(False)
        dc.set_gui_application_mode(False)


def test_lazy_all_loads_outside_gui_session() -> None:
    mscat._ONLINE_DRIVER_STORE_CACHE = None
    mscat._ONLINE_DRIVER_STORE_CACHE_AT = 0.0
    all_calls: list[str] = []

    def fake_all() -> tuple[list[dict], str]:
        all_calls.append("all")
        return [{
            "Version": "1125.29.50.2026",
            "ClassName": "net",
            "HardwareDescription": "Realtek PCIe GbE Family Controller",
            "HardwareID": "",
            "ProviderName": "Realtek",
        }], ""

    try:
        with mock.patch.object(
            dc, "_fetch_online_driver_store_rows_uncached", side_effect=fake_all
        ), mock.patch.object(
            dc, "_gui_batched_online_store_include_all", return_value=True
        ), mock.patch.object(
            dc, "_should_skip_online_driver_store", return_value=False
        ), mock.patch.object(
            dc, "_gui_catalog_session_active", return_value=False
        ):
            rows, err = dc._lazy_load_online_driver_store_all()
        assert all_calls == ["all"]
        assert rows and not err
    finally:
        mscat._ONLINE_DRIVER_STORE_CACHE = None
        mscat._ONLINE_DRIVER_STORE_CACHE_AT = 0.0
        mscat._ONLINE_DRIVER_STORE_CLASS_BUCKETS = None


def test_fetch_store_uses_warmed_bulk_cache_in_gui() -> None:
    dc.set_gui_application_mode(True)
    try:
        mscat._ONLINE_DRIVER_STORE_CACHE = [{
            "Version": "1125.29.50.2026",
            "ClassName": "net",
            "HardwareDescription": "Realtek PCIe GbE Family Controller",
            "HardwareID": "",
            "ProviderName": "Realtek",
        }]
        mscat._ONLINE_DRIVER_STORE_CACHE_AT = __import__("time").monotonic()
        mscat._rebuild_online_store_class_buckets(mscat._ONLINE_DRIVER_STORE_CACHE)
        ctx = {"instance_id": "", "pnp_class": "net", "vendor_key": "realtek", "device_label": "Realtek PCIe GbE"}
        offers = dc.fetch_microsoft_driver_store_offers(ctx)
        assert offers
        assert not any(o.get("title") == "Online catalog scan skipped in GUI" for o in offers)
    finally:
        dc.set_gui_application_mode(False)
        mscat._ONLINE_DRIVER_STORE_CACHE = None
        mscat._ONLINE_DRIVER_STORE_CACHE_AT = 0.0
        mscat._ONLINE_DRIVER_STORE_CLASS_BUCKETS = None


def test_mscatalog_query_dedup_within_batch() -> None:
    calls: list[str] = []

    def fake_search(query: str, **kwargs) -> tuple[list[dict], str]:
        calls.append(query)
        return [{
            "title": f"Driver for {query[:20]}",
            "version": "1.0.0.1",
            "update_id": f"uid-{len(calls)}",
            "catalog_tier": "standard",
        }], ""

    ctx = {
        "instance_id": "PCI\\VEN_10DE&DEV_2484&SUBSYS_11111111&REV_A1",
        "device_label": "NVIDIA GeForce RTX",
        "vendor_key": "nvidia",
        "pnp_class": "display",
        "pci_tokens": ["VEN_10DE", "DEV_2484"],
    }
    dc.begin_batch_mscatalog_query_cache()
    try:
        with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), mock.patch.object(
            dc, "ensure_mscatalog_module_ready", return_value=True
        ), mock.patch(
            "catalog_ps_module.search_mscatalog_updates", side_effect=fake_search
        ):
            first = dc.fetch_microsoft_catalog_search_offers(ctx, max_results=2)
            second = dc.fetch_microsoft_catalog_search_offers(ctx, max_results=2)
        assert first
        assert second
        expected_queries = len(dc._catalog_search_queries_for_ctx(ctx))
        assert len(calls) == expected_queries
        assert expected_queries >= 1
    finally:
        dc.clear_batch_mscatalog_query_cache()


if __name__ == "__main__":
    test_unique_hwids_from_contexts_dedupes()
    test_peek_online_store_cache_without_fetch()
    test_warm_batched_hwids_in_batches()
    test_batch_mscatalog_query_cap()
    test_mscatalog_prewarm_off_by_default()
    test_mscatalog_batch_prewarm_dedupes()
    test_device_comparison_parallel_oem_microsoft_wu_only_first()
    test_lazy_all_blocked_during_gui_catalog_session()
    test_lazy_all_loads_outside_gui_session()
    test_fetch_store_uses_warmed_bulk_cache_in_gui()
    test_mscatalog_query_dedup_within_batch()
    print("batched online store tests OK")
