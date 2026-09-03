"""Tests for crash-linked driver verification pipeline."""

from __future__ import annotations

from unittest import mock

import driver_verification as dv


def test_build_suspect_list_from_minidump() -> None:
    events = [{"type": "BugCheck", "code": "0x0A", "time": "2026-08-09 12:00:00"}]
    windbg = {
        "faulting_driver": "nvlddmkm.sys",
        "dump_time": "2026-08-09 12:00:00",
    }
    suspects = dv.build_crash_suspect_list(
        events,
        windbg,
        code_val=0x0A,
        stop_name="IRQL_NOT_LESS_OR_EQUAL",
        stop_code_verified=True,
    )
    modules = [s["module"] for s in suspects]
    assert "nvlddmkm" in modules
    top = suspects[0]
    assert top["confidence"] == dv.CONFIDENCE_CONFIRMED


def test_wer_module_hint_when_dump_missing_on_disk() -> None:
    events = [
        {
            "type": "BugCheck",
            "code_source": "wer1001",
            "time": "2026-08-09 20:59:46",
            "dump": r"C:\Windows\Minidump\missing.dmp",
        }
    ]
    system_ctx = {
        "wer_dump_recovery": {
            "module_hints": [
                {
                    "module": "storport.sys",
                    "event_time": "2026-08-09 20:59:46",
                    "source": "wer_archive",
                }
            ]
        }
    }
    suspects = dv.build_crash_suspect_list(events, None, system_ctx=system_ctx)
    modules = [s["module"] for s in suspects]
    assert "storport" in modules
    srcs = suspects[modules.index("storport")]["sources"]
    assert any("WER archived" in s for s in srcs)


def test_suspect_list_ignores_stale_dump_module() -> None:
    events = [{"type": "KernelPower", "time": "2026-08-09 20:59:35", "code": "N/A"}]
    windbg = {
        "faulting_driver": "nvlddmkm.sys",
        "dump_time": "2026-08-04 12:00:00",
    }
    suspects = dv.build_crash_suspect_list(events, windbg)
    modules = [s["module"] for s in suspects]
    assert "nvlddmkm" not in modules


def test_map_unmapped_includes_manual_hint() -> None:
    suspects = [{"module": "unknownmod", "confidence": dv.CONFIDENCE_LIKELY, "sources": ["test"]}]
    mapped = dv.map_suspects_to_devices(suspects, [])
    assert mapped[0]["map_status"] == "unmapped"
    assert "Device Manager" in (mapped[0].get("manual_hint") or "")


def test_verify_flags_generic_driver() -> None:
    mapped = [{
        "module": "nvlddmkm",
        "confidence": dv.CONFIDENCE_CONFIRMED,
        "sources": ["test"],
        "map_status": "mapped",
        "devices": [{"name": "NVIDIA GPU", "version": "1.0"}],
    }]
    pnp = [{
        "Name": "NVIDIA GPU",
        "DeviceID": "PCI\\VEN_10DE&DEV_1234",
        "ConfigManagerErrorCode": 0,
        "Manufacturer": "NVIDIA",
    }]
    generic = [{"name": "NVIDIA GPU"}]
    with mock.patch.object(dv, "_fetch_signed_driver_device_ids", return_value={"nvidia gpu": "PCI\\VEN_10DE&DEV_1234"}):
        out = dv.verify_suspect_drivers_locally(
            mapped,
            pnp_list=pnp,
            inventory=[{"name": "NVIDIA GPU", "version": "1.0"}],
            problem_devices=[],
            generic_devices=generic,
        )
    assert out[0]["local"]["assessment"] == "generic_driver"


def test_catalog_gate_unmapped_is_no() -> None:
    verified = [{
        "module": "foo",
        "map_status": "unmapped",
        "confidence": dv.CONFIDENCE_LIKELY,
        "local": {"assessment": "uncertain"},
    }]
    gated = dv.gate_catalog_for_suspects(verified)
    assert gated[0]["catalog_gate"] == dv._CATALOG_NO


def test_catalog_gate_confirmed_mapped_is_yes() -> None:
    verified = [{
        "module": "nvlddmkm",
        "map_status": "mapped",
        "confidence": dv.CONFIDENCE_CONFIRMED,
        "local": {"assessment": "ok"},
    }]
    gated = dv.gate_catalog_for_suspects(verified)
    assert gated[0]["catalog_gate"] == dv._CATALOG_YES


def test_suspect_list_platform_chipset_not_storport_on_shutdown() -> None:
    events = [{"type": "KernelPower", "time": "2026-08-09 20:59:35", "code": "N/A"}]
    windbg = {
        "faulting_driver": "storport.sys",
        "dump_time": "2026-08-04 12:00:00",
    }
    culprits = {"__chipset_amd_platform__"}
    suspects = dv.build_crash_suspect_list(
        events,
        windbg,
        boot_recovery=[{"subtype": "Wininit", "time": "2026-08-10", "message": "boot device"}],
        culprit_device_names=culprits,
        system_ctx={"has_amd_chipset": True},
    )
    modules = [s["module"] for s in suspects]
    assert "storport" not in modules
    assert "platform_chipset" in modules or "__chipset_amd_platform__" in modules


def test_attribution_shutdown_without_dump_names_chipset() -> None:
    events = [{"type": "KernelPower", "time": "2026-08-09 20:59:35", "code": "N/A"}]
    windbg = {"faulting_driver": "nvlddmkm.sys", "dump_time": "2026-08-04 12:00:00"}
    attr = dv.build_crash_driver_attribution(
        events,
        windbg,
        boot_recovery=[{"subtype": "Wininit", "time": "2026-08-10"}],
        culprit_device_names={"__chipset_amd_platform__"},
        system_ctx={"has_amd_chipset": True},
    )
    text = "\n".join(attr["lines"])
    assert "cannot be named" in text.lower()
    assert "AMD Chipset" in text
    assert attr["action_plan_steps"]
    assert "Chipset" in attr["action_plan_steps"][0]


def test_pipeline_produces_report_lines() -> None:
    events = []
    windbg = None
    bio = {"all_drivers": [{"name": "Realtek Audio", "version": "6.0", "device_class": "MEDIA"}]}
    pnp = [{"Name": "Realtek Audio", "DeviceID": "PCI\\VEN_10EC", "ConfigManagerErrorCode": 0, "Manufacturer": "Realtek"}]
    with mock.patch.object(dv, "_fetch_signed_driver_device_ids", return_value={"realtek audio": "PCI\\VEN_10EC"}):
        report = dv.run_driver_verification_pipeline(
            events,
            windbg,
            bio,
            pnp_list=pnp,
            problem_devices=[],
            generic_devices=[],
            boot_recovery=[{"subtype": "StartupRepair", "time": "2026-08-09", "message": "boot failure"}],
        )
    assert isinstance(report.get("lines"), list)


def test_crash_linked_catalog_device_names_chipset() -> None:
    import bsod_analyzer as core

    names = dv.crash_linked_catalog_device_names(
        {
            "suspects": [{
                "catalog_gate": dv._CATALOG_YES,
                "module": "__chipset_amd_platform__",
                "devices": [{"name": "AMD Chipset / Platform drivers"}],
            }],
        },
        {core.CHIPSET_DEVICE_AMD},
    )
    assert names
    assert any("chipset" in n.lower() or "amd" in n.lower() for n in names)


def test_build_crash_confidence_focus_without_dump() -> None:
    import bsod_analyzer as core

    events = [{"type": "KernelPower", "time": "2026-08-09 20:59:35", "code": "N/A"}]
    windbg = {"faulting_driver": "nvlddmkm.sys", "dump_time": "2026-08-04 12:00:00"}
    conf = core.build_crash_confidence_summary(
        events,
        windbg,
        driver_verification={
            "attribution": {
                "platform_chipset_focus": True,
                "can_name_faulting_driver": False,
                "dump_matches_latest": False,
            },
        },
        needs_config=False,
    )
    assert conf["level"] == "focus"
    assert conf["what_would_change"]


if __name__ == "__main__":
    test_build_suspect_list_from_minidump()
    test_suspect_list_ignores_stale_dump_module()
    test_map_unmapped_includes_manual_hint()
    test_verify_flags_generic_driver()
    test_catalog_gate_unmapped_is_no()
    test_catalog_gate_confirmed_mapped_is_yes()
    test_suspect_list_platform_chipset_not_storport_on_shutdown()
    test_attribution_shutdown_without_dump_names_chipset()
    test_crash_linked_catalog_device_names_chipset()
    test_pipeline_produces_report_lines()
    print("driver verification tests OK")
