"""Regression tests for v5.2.28 backlog: PnP lookup, find_cdb cache, OEM LRU."""

from __future__ import annotations

import device_enrichment as de
import driver_catalog as drvcat


def test_pnp_enrichment_lookup_exact_and_substring():
    index = {
        "Intel(R) Ethernet Connection": {
            "display_name": "Intel Ethernet I219-V",
            "vendor_key": "intel",
        },
        "NVIDIA GeForce RTX 4070": {
            "display_name": "NVIDIA GeForce RTX 4070",
            "vendor_key": "nvidia",
        },
    }
    lu = de.PnpEnrichmentLookup(index)
    hit = lu.match("Intel(R) Ethernet Connection")
    assert hit and hit.get("vendor_key") == "intel"
    hit2 = lu.match("intel ethernet i219-v")
    assert hit2 and hit2.get("vendor_key") == "intel"
    hit3 = lu.match("GeForce RTX 4070")
    assert hit3 and hit3.get("vendor_key") == "nvidia"


def test_pnp_lookup_from_ctx_caches_on_system_ctx():
    ctx = {
        "pnp_enrichment": {
            "USB Root Hub": {"display_name": "USB Root Hub (USB 3.0)", "vendor_key": ""},
        },
    }
    lu1 = de.pnp_lookup_from_ctx(ctx)
    lu2 = de.pnp_lookup_from_ctx(ctx)
    assert lu1 is lu2
    assert ctx["_pnp_enrichment_lu"] is lu1


def test_find_cdb_memoization(monkeypatch):
    import bsod_analyzer as core
    import bsod_minidump

    core.clear_cdb_path_cache()
    calls = {"n": 0}

    def fake_paths():
        calls["n"] += 1
        return ["/no/such/cdb.exe"]

    # find_cdb() calls _get_cdb_search_paths within bsod_minidump, so the facade
    # attribute is not the one that gets looked up.
    monkeypatch.setattr(bsod_minidump, "_get_cdb_search_paths", fake_paths)
    assert core.find_cdb() is None
    assert core.find_cdb() is None
    assert calls["n"] == 1
    core.clear_cdb_path_cache()
    assert core.find_cdb() is None
    assert calls["n"] == 2


def test_oem_cache_lru_eviction():
    drvcat.clear_oem_cache()
    drvcat.configure_catalog(oem_session_cache=True)
    seen = []

    def fetch_rows(_sys):
        seen.append(1)
        return ([{"title": "pkg", "version": "1.0", "url": "https://example.test"}], "https://example.test")

    for i in range(drvcat._OEM_CACHE_MAX_ENTRIES + 5):
        drvcat._cached_oem_rows(f"tag{i}", fetch_rows, {"system_manufacturer": f"mfr{i}", "system_model": "x"})
    assert len(seen) == drvcat._OEM_CACHE_MAX_ENTRIES + 5
    assert len(drvcat._OEM_ROWS_CACHE) == drvcat._OEM_CACHE_MAX_ENTRIES
    drvcat._cached_oem_rows("tag0", fetch_rows, {"system_manufacturer": "mfr0", "system_model": "x"})
    assert len(seen) == drvcat._OEM_CACHE_MAX_ENTRIES + 6
