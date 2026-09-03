"""Tests for catalog device roles and WU batch assignment."""

from __future__ import annotations

import catalog_device_roles as cdr
import driver_catalog as dc


def test_apply_catalog_roles_marks_lg_monitor_and_child() -> None:
    rows = [
        {
            "name": "LG ULTRAGEAR(DisplayPort)",
            "device_class": "MONITOR",
            "pnp_class": "Monitor",
            "version": "1.0.0.0",
            "device_id": "DISPLAY\\GSM5BD3\\5&C6A2E9C&1&UID261",
        },
        {
            "name": "LG Monitor Support Application",
            "device_class": "SOFTWARECOMPONENT",
            "pnp_class": "SoftwareComponent",
            "version": "1.1.2023.1102",
            "parent_device_name": "LG ULTRAGEAR(DisplayPort)",
            "device_id": "SWD\\DRIVERENUM\\{3846AD8C-DD27-433D-AB89-453654CD542A}#LGMONITORAPP&6&D5F2B4A&0",
        },
    ]
    out = cdr.apply_catalog_roles_to_inventory(rows)
    by_name = {r["name"]: r for r in out}
    assert by_name["LG ULTRAGEAR(DisplayPort)"]["catalog_role"] == "monitor_edid"
    assert by_name["LG ULTRAGEAR(DisplayPort)"]["catalog_has_swc_child"] is True
    assert by_name["LG ULTRAGEAR(DisplayPort)"]["catalog_skip_mscatalog"] is True
    assert by_name["LG Monitor Support Application"]["catalog_role"] == "softwarecomponent"


def test_batch_wu_update_id_dedup_prefers_swc_child() -> None:
    wu_row = {
        "Title": "LG Electronics Inc. SoftwareComponent Driver Update (2.0.2026.810)",
        "Version": "2.0.2026.810",
        "UpdateId": "2d7714ef-c5fd-4eb7-8a7b-d11e7d12b07b",
        "HardwareIds": [],
    }
    monitor_ctx = {
        "device_label": "LG ULTRAGEAR(DisplayPort)",
        "target_device_name": "LG ULTRAGEAR(DisplayPort)",
        "pnp_class": "MONITOR",
        "pnp_manufacturer": "LG",
        "vendor_key": "lg",
        "catalog_role": "monitor_edid",
        "catalog_has_swc_child": True,
    }
    swc_ctx = {
        "device_label": "LG Monitor Support Application",
        "target_device_name": "LG Monitor Support Application",
        "pnp_class": "SOFTWARECOMPONENT",
        "pnp_manufacturer": "LG Electronics Inc.",
        "vendor_key": "lg",
        "catalog_role": "softwarecomponent",
        "parent_device_name": "LG ULTRAGEAR(DisplayPort)",
    }
    contexts = {
        "LG ULTRAGEAR(DisplayPort)": monitor_ctx,
        "LG Monitor Support Application": swc_ctx,
    }
    assigned = dc._batch_prefilter_wu_rows([wu_row], contexts)
    assert assigned["LG Monitor Support Application"]
    assert not assigned["LG ULTRAGEAR(DisplayPort)"]


def test_monitor_with_swc_child_skips_mscatalog_queries() -> None:
    ctx = {
        "catalog_skip_mscatalog": True,
        "device_label": "LG ULTRAGEAR(DisplayPort)",
        "instance_id": "DISPLAY\\GSM5BD3\\5&C6A2E9C&1&UID261",
        "vendor_key": "lg",
    }
    assert dc._catalog_search_queries_for_ctx(ctx) == []
