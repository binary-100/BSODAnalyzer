"""Regression tests for AMD driver-source reliability hardening.

Covers three fixes made after discovering AMD's site sits behind Akamai Bot
Manager (intermittently serving a challenge shell instead of the real page):

  Part 1  Static AMD fetch retries past bot-challenge shells and never treats a
          challenge interstitial as real content.
  Part 2  AMD dual version schemes compare like-for-like: installed Windows INF
          (32.0.x) vs scraped Adrenalin marketing (26.x) is mapped to the
          installed Adrenalin version, not compared numerically across schemes.
  Part 3  When the AMD version cannot be verified (fetch blocked), the device
          degrades to an honest "uncertain / couldn't verify" row instead of a
          silent no-offer state that looks like "confirmed current".
"""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driver_catalog as dc
import catalog_http as http
import vendor_page_render as vpr


_CHALLENGE_HTML = (
    "<html><head><title>Pardon Our Interruption</title></head><body>"
    "<script>window.bmak={};</script>_abck=xyz; please enable javascript and cookies"
    "</body></html>"
)
_REAL_HTML = "<html><body>" + ("AMD Software: Adrenalin Edition 26.6.4 " * 500) + "</body></html>"

_GPU_CTX = {
    "instance_id": "PCI\\VEN_1002&DEV_1681&SUBSYS_0B5B1028&REV_C7",
    "device_label": "AMD Radeon RX 580",
    "vendor_key": "amd",
    "pnp_class": "Display",
    "hw_category": "gpu",
}


# ---------------------------------------------------------------- Part 1
def test_challenge_detector_flags_interstitial_not_content() -> None:
    assert vpr.looks_like_bot_challenge(_CHALLENGE_HTML) is True
    assert vpr.looks_like_bot_challenge(_REAL_HTML) is False
    assert vpr.looks_like_bot_challenge("") is False


def test_fallback_never_returns_challenge_shell() -> None:
    # allow_js False so we exercise only the plain-HTTP branch.
    ok, body, method = vpr.fetch_html_with_js_fallback(
        "https://www.amd.com/x", lambda u: (True, _CHALLENGE_HTML),
        allow_js=False,
    )
    assert ok is False and body == "", (ok, body)


def test_amd_robust_get_retries_past_challenge() -> None:
    calls = {"n": 0}

    def fake_http_get(url, headers=None, **kw):
        calls["n"] += 1
        return (True, _CHALLENGE_HTML) if calls["n"] == 1 else (True, _REAL_HTML)

    with mock.patch.object(http, "_http_get", side_effect=fake_http_get), \
         mock.patch.object(http.time, "sleep"):
        ok, body = dc._amd_http_get_robust("https://www.amd.com/x")
    assert ok is True and "26.6.4" in body
    assert calls["n"] == 2, "should have retried once past the challenge"


def test_amd_robust_get_fails_when_all_challenged() -> None:
    with mock.patch.object(http, "_http_get", return_value=(True, _CHALLENGE_HTML)), \
         mock.patch.object(http.time, "sleep"):
        ok, body = dc._amd_http_get_robust("https://www.amd.com/x", attempts=3)
    assert ok is False, "a body that is always a challenge shell is not success"


# ---------------------------------------------------------------- Part 2
def test_amd_marketing_vs_inf_maps_to_adrenalin() -> None:
    with mock.patch.object(dc, "_load_amd_adrenalin_installed_version", return_value="26.6.4"):
        status, note = dc.compare_driver_to_installed("32.0.21043.19003", "26.6.4")
    assert status == "same", (status, note)
    assert "adrenalin" in note.lower()


def test_amd_marketing_vs_inf_detects_newer() -> None:
    with mock.patch.object(dc, "_load_amd_adrenalin_installed_version", return_value="26.5.1"):
        status, _ = dc.compare_driver_to_installed("32.0.21043.19003", "26.6.4")
    assert status == "newer", status


# ---------------------------------------------------------------- Part 3
def test_failed_amd_fetch_degrades_to_uncertain() -> None:
    with mock.patch.object(dc, "_manufacturer_vendor_lookup_applicable", return_value=True), \
         mock.patch.object(dc, "_amd_vendor_version_lookup_applicable", return_value=True), \
         mock.patch.object(dc, "is_quick_check_mode", return_value=False), \
         mock.patch.object(dc, "_vendor_scrape_cache_get", return_value=None), \
         mock.patch.object(dc, "_vendor_scrape_cache_set"), \
         mock.patch.object(dc, "_scrape_amd_driver_version", return_value=("", "")):
        offers = dc.fetch_amd_driver_offers(dict(_GPU_CTX))
    assert len(offers) == 1
    o = offers[0]
    assert o["vs_installed"] == "uncertain", o
    assert o.get("coverage_check_failed") is True
    assert "couldn't verify" in o["notes"].lower()
    assert dc.summarize_offer_status(offers) == "uncertain"


def test_successful_amd_fetch_stays_actionable() -> None:
    with mock.patch.object(dc, "_manufacturer_vendor_lookup_applicable", return_value=True), \
         mock.patch.object(dc, "_amd_vendor_version_lookup_applicable", return_value=True), \
         mock.patch.object(dc, "is_quick_check_mode", return_value=False), \
         mock.patch.object(dc, "_vendor_scrape_cache_get", return_value=None), \
         mock.patch.object(dc, "_vendor_scrape_cache_set"), \
         mock.patch.object(dc, "_scrape_amd_driver_version", return_value=("26.6.4", "")):
        offers = dc.fetch_amd_driver_offers(dict(_GPU_CTX))
    assert len(offers) == 1
    assert offers[0]["version"] == "26.6.4"
    assert offers[0].get("coverage_check_failed") is not True


if __name__ == "__main__":
    test_challenge_detector_flags_interstitial_not_content()
    test_fallback_never_returns_challenge_shell()
    test_amd_robust_get_retries_past_challenge()
    test_amd_robust_get_fails_when_all_challenged()
    test_amd_marketing_vs_inf_maps_to_adrenalin()
    test_amd_marketing_vs_inf_detects_newer()
    test_failed_amd_fetch_degrades_to_uncertain()
    test_successful_amd_fetch_stays_actionable()
    print("amd source hardening tests OK")
