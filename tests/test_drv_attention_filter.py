"""Drivers tab Needs attention / Updates available filter rules."""

from __future__ import annotations


def dev_needs_analysis_attention(dev: dict) -> bool:
    """Mirror MainWindow._dev_needs_analysis_attention (no Qt)."""
    return bool(dev.get("_crash_linked"))


def drv_passes_log_attention(dev: dict, *, has_faulting_driver: bool) -> bool:
    if not has_faulting_driver:
        return False
    return dev_needs_analysis_attention(dev)


def drv_passes_updates(dev: dict) -> bool:
    return bool(dev.get("_scan_verified")) and (dev.get("_check_status") or "") == "newer"


def drv_passes_uncertain(dev: dict) -> bool:
    """Mirror MainWindow._drv_passes_view_filter mode == 'uncertain'."""
    return bool(dev.get("_scan_verified")) and (dev.get("_check_status") or "") == "uncertain"


def test_log_attention_includes_crash_linked() -> None:
    dev = {"_crash_linked": True, "_tier": "culprit"}
    assert drv_passes_log_attention(dev, has_faulting_driver=True)


def test_log_attention_excludes_generic_flagged() -> None:
    dev = {"_analysis_attention": True, "_tier": "attention", "_reasons": ["Generic driver"]}
    assert not drv_passes_log_attention(dev, has_faulting_driver=True)


def test_log_attention_excludes_culprit_tier_without_link() -> None:
    dev = {"_tier": "culprit"}
    assert not drv_passes_log_attention(dev, has_faulting_driver=True)


def test_log_attention_excludes_normal_without_analysis() -> None:
    dev = {"_tier": "normal"}
    assert not drv_passes_log_attention(dev, has_faulting_driver=True)


def test_log_attention_requires_faulting_driver() -> None:
    dev = {"_crash_linked": True, "_tier": "culprit"}
    assert not drv_passes_log_attention(dev, has_faulting_driver=False)


def test_updates_requires_verified_newer() -> None:
    assert drv_passes_updates({"_scan_verified": True, "_check_status": "newer"})
    assert not drv_passes_updates({"_scan_verified": True, "_check_status": "same"})
    assert not drv_passes_updates({"_check_status": "newer"})


def test_uncertain_filter_matches_verify_manually_devices() -> None:
    # "Verify manually" view: only verified devices whose status is uncertain.
    assert drv_passes_uncertain({"_scan_verified": True, "_check_status": "uncertain"})
    assert not drv_passes_uncertain({"_scan_verified": True, "_check_status": "newer"})
    assert not drv_passes_uncertain({"_scan_verified": True, "_check_status": "same"})
    assert not drv_passes_uncertain({"_scan_verified": True, "_check_status": "none"})
    # Not yet scanned → excluded even if a stale status lingers.
    assert not drv_passes_uncertain({"_check_status": "uncertain"})


if __name__ == "__main__":
    test_log_attention_includes_crash_linked()
    test_log_attention_excludes_generic_flagged()
    test_log_attention_excludes_culprit_tier_without_link()
    test_log_attention_excludes_normal_without_analysis()
    test_log_attention_requires_faulting_driver()
    test_updates_requires_verified_newer()
    test_uncertain_filter_matches_verify_manually_devices()
    print("OK")
