"""Regression tests for the generalized vendor-source reliability hardening.

After confirming AMD, Dell, Lenovo, Intel, Marvell, MediaTek, MSI and Gigabyte
all sit behind bot managers / WAFs, the AMD-specific hardening was generalized:

  * ``_vendor_http_get_robust`` — shared static GET that rejects bot-challenge
    shells and retries them + transient errors, but FAST-FAILS on a hard client
    block (403/401/404) so a permanently gated host never inflates scan time.
  * ``_vendor_coverage_gap_offer`` — shared honest "couldn't verify" row so any
    blocked version-applicable device degrades to ``uncertain`` instead of a
    silent no-offer that would read as "confirmed current".
"""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driver_catalog as dc
import catalog_http as http


_CHALLENGE = (
    "<html><head><title>Pardon Our Interruption</title></head><body>"
    "<script>window.bmak={};</script>_abck=xyz; please enable javascript and cookies"
    "</body></html>"
)
_REAL = "<html><body>" + ("Realtek Media 6.0.9578.1 " * 200) + "</body></html>"


# ---------------------------------------------------------------- robust GET
def test_robust_get_retries_past_challenge_then_succeeds() -> None:
    calls = {"n": 0}

    def fake(url, headers=None, **kw):
        calls["n"] += 1
        return (True, _CHALLENGE) if calls["n"] == 1 else (True, _REAL)

    with mock.patch.object(http, "_http_get", side_effect=fake), \
         mock.patch.object(http.time, "sleep"):
        ok, body = dc._vendor_http_get_robust("https://vendor.example/x")
    assert ok is True and "6.0.9578.1" in body
    assert calls["n"] == 2


def test_robust_get_fast_fails_on_hard_403_without_retry() -> None:
    """A hard 403 never changes on retry — must stop after the first attempt."""
    calls = {"n": 0}

    def fake(url, headers=None, **kw):
        calls["n"] += 1
        return (False, "HTTP Error 403: Forbidden")

    with mock.patch.object(http, "_http_get", side_effect=fake), \
         mock.patch.object(http.time, "sleep") as slept:
        ok, _ = dc._vendor_http_get_robust("https://intel.example/x", attempts=3)
    assert ok is False
    assert calls["n"] == 1, "must not hammer a permanently gated host"
    assert slept.call_count == 0, "no backoff sleep on a fast-fail"


def test_robust_get_retries_transient_then_fails() -> None:
    calls = {"n": 0}

    def fake(url, headers=None, **kw):
        calls["n"] += 1
        return (False, "timed out")

    with mock.patch.object(http, "_http_get", side_effect=fake), \
         mock.patch.object(http.time, "sleep"):
        ok, _ = dc._vendor_http_get_robust("https://vendor.example/x", attempts=3)
    assert ok is False
    assert calls["n"] == 3, "transient errors are worth retrying"


def test_robust_get_fails_when_all_challenged() -> None:
    with mock.patch.object(http, "_http_get", return_value=(True, _CHALLENGE)), \
         mock.patch.object(http.time, "sleep"):
        ok, _ = dc._vendor_http_get_robust("https://vendor.example/x", attempts=3)
    assert ok is False


# ----------------------------------------------------------- coverage-gap row
def test_coverage_gap_offer_is_honest_uncertain() -> None:
    o = dc._vendor_coverage_gap_offer(
        source_label="Manufacturer (Intel)", vendor_disp="Intel",
        title="Intel Graphics", url="https://intel.example",
    )
    assert o["vs_installed"] == "uncertain"
    assert o["coverage_check_failed"] is True
    assert o["version"] == ""
    assert "couldn't verify" in o["notes"].lower()
    assert "intel" in o["notes"].lower()


# --------------------------------------------------- per-vendor degradation
def test_blocked_intel_graphics_degrades_to_uncertain() -> None:
    ctx = {"vendor_key": "intel", "pnp_class": "display", "hw_category": "gpu",
           "device_label": "Intel Iris Xe Graphics", "instance_id": "PCI\\VEN_8086&DEV_9A49"}
    with mock.patch.object(dc, "_manufacturer_vendor_lookup_applicable", return_value=True), \
         mock.patch.object(dc, "_vendor_scrape_cache_get", return_value=None), \
         mock.patch.object(dc, "_vendor_scrape_cache_set"), \
         mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), \
         mock.patch.object(dc, "_scrape_intel_driver_version", return_value=("", "", "https://intel.example", "")):
        offers = dc.fetch_intel_driver_offers(ctx)
    assert any(o.get("coverage_check_failed") and o.get("vs_installed") == "uncertain"
               for o in offers), offers


def test_blocked_killer_degrades_to_uncertain() -> None:
    ctx = {"vendor_key": "killer", "device_label": "Killer Wi-Fi 6E AX1675"}
    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), \
         mock.patch.object(dc, "_vendor_scrape_cache_get", return_value=None), \
         mock.patch.object(dc, "_vendor_http_get_robust", return_value=(False, "")):
        offers = dc.fetch_killer_driver_offers(ctx)
    assert len(offers) == 1
    assert offers[0].get("coverage_check_failed") is True
    assert offers[0]["vs_installed"] == "uncertain"


if __name__ == "__main__":
    test_robust_get_retries_past_challenge_then_succeeds()
    test_robust_get_fast_fails_on_hard_403_without_retry()
    test_robust_get_retries_transient_then_fails()
    test_robust_get_fails_when_all_challenged()
    test_coverage_gap_offer_is_honest_uncertain()
    test_blocked_intel_graphics_degrades_to_uncertain()
    test_blocked_killer_degrades_to_uncertain()
    print("vendor source hardening tests OK")
