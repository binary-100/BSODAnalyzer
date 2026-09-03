"""S10: unified culprit resolution across Summary, System, and Drivers tabs."""

from __future__ import annotations

import bsod_analyzer as core
import driver_list_build as drvlist


def _sample_inventory() -> tuple[list[dict], list[dict]]:
    thin = [
        {
            "name": "USB Root Hub",
            "driver": "usbhub.sys",
            "device_class": "USB",
            "version": "10.0.0.0",
        },
    ]
    full = thin + [
        {
            "name": "NVIDIA GeForce RTX 4070",
            "driver": "nvlddmkm.sys",
            "device_class": "DISPLAY",
            "version": "31.0.15.4601",
            "date": "2024-01-01",
        },
    ]
    return thin, full


def test_resolve_names_match_driver_info_after_full_inventory() -> None:
    driver = "nvlddmkm.sys"
    thin, full = _sample_inventory()
    thin_ctx = core.resolve_crash_culprit_context(
        driver, {"drivers": thin}, code_val=0x116, has_crash_context=True
    )
    full_ctx = core.resolve_crash_culprit_context(
        driver, {"all_drivers": full}, code_val=0x116, has_crash_context=True
    )
    assert core._culprit_info_row_is_placeholder(thin_ctx["culprit_driver_info"][0])
    assert "nvidia geforce rtx 4070" in full_ctx["culprit_device_names"]
    assert full_ctx["culprit_driver_info"][0]["name"] == "NVIDIA GeForce RTX 4070"
    assert full_ctx["culprit_driver_info"][0]["version"] == "31.0.15.4601"


def test_refresh_model_syncs_all_culprit_fields() -> None:
    driver = "nvlddmkm.sys"
    thin, full = _sample_inventory()
    model = {
        "driver": driver,
        "stop_code_val": 0x116,
        "cause_type": {"driver_actionable": True, "label": "Driver / software"},
        "fix_plan": {"focus": core.FIX_NAMED_DRIVER},
        "system_ctx": {"pnp_list": []},
        "culprit_driver_info": core.get_culprit_device_driver_info(driver, thin),
        "culprit_callout": None,
    }
    changed = core.refresh_model_culprit_fields(model, {"all_drivers": full})
    assert changed
    assert model["culprit_driver_info"][0]["name"] == "NVIDIA GeForce RTX 4070"
    assert "nvidia geforce rtx 4070" in {
        n.lower() for n in model.get("culprit_device_names") or []
    }


def test_driver_list_build_uses_same_name_keys() -> None:
    driver = "nvlddmkm.sys"
    _thin, full = _sample_inventory()
    model = core.build_display_model(
        (
            [], [], None, [], {"faulting_driver": driver, "bugcheck_code": "0x116"},
            [], [], "Automatic memory dump", 7, False, "", "", [], {"all_drivers": full},
            {}, [], [], None,
        )
    )
    prof = {"bios_driver_info": {"all_drivers": full}, "system_ctx": {}}
    names = drvlist.culprit_device_names(prof, last_model=model, last_fmt_args=(1,))
    assert "nvidia geforce rtx 4070" in names
    assert set(model.get("culprit_device_names") or []) == names


def test_lookup_inventory_row_case_insensitive() -> None:
    inv = [{"name": "Realtek Audio", "version": "6.0.1.0"}]
    row = core.lookup_inventory_row(inv, "realtek audio")
    assert row is not None
    assert row["version"] == "6.0.1.0"


if __name__ == "__main__":
    test_resolve_names_match_driver_info_after_full_inventory()
    test_refresh_model_syncs_all_culprit_fields()
    test_driver_list_build_uses_same_name_keys()
    test_lookup_inventory_row_case_insensitive()
    print("S10 culprit resolution tests OK")
