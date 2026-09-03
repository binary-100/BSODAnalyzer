"""Driver catalog GUI stability (v5.2.31+): serial batch checks, no online store in GUI."""

from __future__ import annotations

from unittest import mock

import catalog_mscatalog_session as mscat
import driver_catalog as dc


def test_gui_session_blocks_online_fetch() -> None:
    dc.set_gui_catalog_session(True)
    try:
        assert dc._should_skip_online_driver_store() is True
        rows, err = dc._get_cached_online_driver_store_rows()
        assert rows == [] and err == ""
    finally:
        dc.set_gui_catalog_session(False)


def test_gui_application_mode_blocks_online_fetch() -> None:
    dc.set_gui_application_mode(True)
    try:
        assert dc._should_skip_online_driver_store() is True
        assert dc._should_skip_online_driver_store({"_gui_driver_catalog": False}) is True
        messages: list[str] = []
        rows, err = dc.ensure_online_driver_store_loaded(progress=messages.append)
        assert rows == [] and err == "" and messages == []
    finally:
        dc.set_gui_application_mode(False)


def test_gui_session_refcount() -> None:
    dc.set_gui_catalog_session(True)
    dc.set_gui_catalog_session(True)
    assert dc._should_skip_online_driver_store() is True
    dc.set_gui_catalog_session(False)
    assert dc._should_skip_online_driver_store() is True
    dc.set_gui_catalog_session(False)
    assert dc._should_skip_online_driver_store() is False


def test_gui_skips_online_driver_store() -> None:
    assert dc._should_skip_online_driver_store({"_gui_driver_catalog": True}) is True
    assert dc._should_skip_online_driver_store({"_gui_driver_catalog": False}) is False


def test_gui_batch_uses_parallel_workers() -> None:
    assert dc._batch_check_worker_count(5) > 1
    assert dc._batch_check_worker_count(5, gui_batch=True) > 1
    assert dc._batch_check_worker_count(5, gui_batch=True) <= dc._GUI_BATCH_MAX_WORKERS


def test_batch_wu_prefilter_parses_hardware_once() -> None:
    rows = [
        {
            "Title": "AMD Chipset Driver",
            "Version": "5.11.0.0",
            "HardwareIds": ["PCI\\VEN_1022&DEV_790B"],
        },
        {
            "Title": "Intel Wi-Fi Driver",
            "Version": "23.0.0.0",
            "HardwareIds": ["PCI\\VEN_8086&DEV_2725"],
        },
    ]
    ctx_amd = {
        "vendor_key": "amd",
        "device_label": "AMD Chipset",
        "pci_tokens": ["VEN_1022", "DEV_790B"],
        "pnp_class": "system",
    }
    ctx_intel = {
        "vendor_key": "intel",
        "device_label": "Intel Wi-Fi",
        "pci_tokens": ["VEN_8086", "DEV_2725"],
        "pnp_class": "net",
    }
    mapped = dc._batch_prefilter_wu_rows(
        rows,
        {"amd": ctx_amd, "intel": ctx_intel},
    )
    assert mapped["amd"] and mapped["amd"][0]["Title"].startswith("AMD")
    assert mapped["intel"] and "Intel" in mapped["intel"][0]["Title"]


def test_live_oem_fetch_uses_session_cache() -> None:
    from unittest import mock

    dc.clear_oem_cache()
    dc.configure_catalog(oem_session_cache=True)
    calls: list[str] = []

    def fake_live(_sys):
        calls.append("dell")
        return ([{"title": "Dell pkg", "version": "1.0", "url": "https://example.test"}], "https://dell.com")

    system_ctx = {"system_manufacturer": "Dell Inc.", "system_model": "XPS"}
    ctx_a = {"vendor_key": "dell", "pnp_class": "system", "device_label": "Dell device A"}
    ctx_b = {"vendor_key": "dell", "pnp_class": "system", "device_label": "Dell device B"}
    with mock.patch.object(dc, "_fetch_dell_oem_rows_live", side_effect=fake_live):
        first = dc.fetch_dell_oem_offers(ctx_a, system_ctx)
        second = dc.fetch_dell_oem_offers(ctx_b, system_ctx)
    assert first and second
    assert len(calls) == 1


def test_ensure_online_reports_ready_via_progress() -> None:
    messages: list[str] = []

    def prog(msg: str) -> None:
        messages.append(msg)

    dc.clear_wu_driver_cache()
    mscat._ONLINE_DRIVER_STORE_CACHE = None
    mscat._ONLINE_DRIVER_STORE_CACHE_AT = 0.0
    fake_rows = [{"Version": "1.0.0.1", "ClassName": "net"}]
    with mock.patch.object(
        dc,
        "_fetch_online_driver_store_rows_uncached",
        return_value=(fake_rows, ""),
    ):
        rows, err = dc.ensure_online_driver_store_loaded(progress=prog)
        dc.ensure_online_driver_store_loaded(progress=prog)
    assert rows == fake_rows and not err
    assert messages == [] or "catalog" in messages[0].lower()
    mscat._ONLINE_DRIVER_STORE_CACHE = None
    mscat._ONLINE_DRIVER_STORE_CACHE_AT = 0.0


if __name__ == "__main__":
    test_gui_session_blocks_online_fetch()
    test_gui_application_mode_blocks_online_fetch()
    test_gui_session_refcount()
    test_gui_skips_online_driver_store()
    test_gui_batch_uses_parallel_workers()
    test_batch_wu_prefilter_parses_hardware_once()
    test_live_oem_fetch_uses_session_cache()
    test_ensure_online_reports_ready_via_progress()
    print("OK")
