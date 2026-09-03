"""Settings defaults and orphaned-key regression tests."""

from __future__ import annotations

import app_settings as app_set


def test_last_maintenance_at_default() -> None:
    s = dict(app_set.DEFAULT_SETTINGS)
    assert "last_maintenance_at" in s
    assert not (s.get("last_maintenance_at") or "").strip()


def test_auto_load_all_drivers_default_on() -> None:
    s = dict(app_set.DEFAULT_SETTINGS)
    assert s.get("auto_load_all_drivers_on_scan") is True
    portable = app_set.apply_portable_defaults({})
    assert portable.get("auto_load_all_drivers_on_scan") is True


def test_orphan_prompt_keys_removed_from_defaults() -> None:
    s = dict(app_set.DEFAULT_SETTINGS)
    assert "last_hardware_driver_scan_scope" not in s
    assert "last_cache_refresh_prompt_at" not in s
    assert "auto_hardware_scan_on_launch" not in s


if __name__ == "__main__":
    test_last_maintenance_at_default()
    test_orphan_prompt_keys_removed_from_defaults()
    print("Settings defaults tests OK")
