"""Driver scan scope: no silent device caps on Include searches."""

from __future__ import annotations

import inspect

import driver_catalog as drvcat


def test_max_batch_driver_devices_removed() -> None:
    assert not hasattr(drvcat, "max_batch_driver_devices")


def test_build_multi_device_does_not_truncate_names() -> None:
    src = inspect.getsource(drvcat.build_multi_device_driver_comparison)
    assert "max_batch_driver_devices" not in src
    assert "[:max_batch" not in src


def test_build_multi_device_batch_loads_wu_rows() -> None:
    """Regression: batch scan must define wu_rows before prefilter (GUI all-devices search)."""
    from contextlib import ExitStack
    from unittest import mock

    patches = [
        mock.patch.object(
            drvcat,
            "_get_cached_wu_driver_rows",
            return_value=([{"Title": "Intel Wi-Fi Driver", "HardwareIds": []}], ""),
        ),
        mock.patch.object(
            drvcat,
            "get_device_context_for_name",
            return_value={"device_label": "Wi-Fi", "vendor_key": "intel"},
        ),
        mock.patch.object(drvcat, "_build_pnpsigned_version_index", return_value={}),
        mock.patch.object(drvcat, "_warm_oem_session_cache"),
        mock.patch.object(drvcat, "_warm_vendor_scrapes_for_contexts"),
        mock.patch.object(
            drvcat,
            "_build_device_comparison_from_ctx",
            return_value={
                "installed_version": "1.0",
                "offers": [],
                "context": {},
            },
        ),
        mock.patch.object(drvcat, "ensure_mscatalog_module_ready", return_value=(True, "")),
    ]
    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        vendor_warm = mocks[3]
        out = drvcat.build_multi_device_driver_comparison(
            ["Wi-Fi Device"],
            pnp_list=[],
            inventory=[],
            system_ctx={"_gui_driver_catalog": True},
        )
    assert len(out["devices"]) == 1
    vendor_warm.assert_called_once()


if __name__ == "__main__":
    test_max_batch_driver_devices_removed()
    test_build_multi_device_does_not_truncate_names()
    print("Driver scan scope tests OK")
