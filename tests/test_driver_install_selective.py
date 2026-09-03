"""Tests for selective INF discovery inside extracted driver packages."""

from __future__ import annotations

import tempfile
from pathlib import Path

import driver_install as di


def test_find_inf_dirs_for_hwid_tokens() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        display = root / "Display.Driver"
        display.mkdir()
        (display / "nv_dispi.inf").write_text(
            "[Manufacturer]\n"
            "%NVIDIA% = NVIDIA_Devices, NTamd64\n\n"
            "[NVIDIA_Devices.NTamd64]\n"
            "%NVIDIA.NPCF% = NPCF_Install, ACPI\\NVDA0820\n",
            encoding="utf-8",
        )
        hits = di.find_inf_dirs_for_hwid_tokens(str(root), ["ACPI\\NVDA0820"])
        assert hits
        assert any("Display.Driver" in h for h in hits)


def test_hwid_ranking_prefers_npcf_over_display_substring() -> None:
    """RmDisableACPI in display INF must not outrank a real ACPI\\NVDA0820 HWID line."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        display = root / "Display.Driver"
        npcf = root / "NVPCF"
        display.mkdir()
        npcf.mkdir()
        (display / "nvdmegpu.inf").write_text(
            "[Strings]\nHKR,,RmDisableACPI\n",
            encoding="utf-8",
        )
        (npcf / "nvpcf.inf").write_text(
            "[Manufacturer]\n"
            "%NVIDIA% = NVIDIA_Devices, NTamd64\n\n"
            "[NVIDIA_Devices.NTamd64]\n"
            "%NVIDIA.NPCF% = NPCF_Install, ACPI\\NVDA0820\n",
            encoding="utf-8",
        )
        ctx = {"instance_id": "ACPI\\NVDA0820\\NPCF"}
        tokens = di._hwid_tokens_from_device_ctx(ctx)
        assert "ACPI" not in tokens
        assert "ACPI\\NVDA0820" in tokens
        hits = di.find_inf_dirs_for_hwid_tokens(str(root), tokens)
        assert hits
        assert "NVPCF" in hits[0].replace("\\", "/")


def test_collect_pnputil_targets_no_fallthrough_on_component_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bogus = root / "package.txt"
        bogus.write_text("not a driver", encoding="utf-8")
        ctx = {
            "instance_id": "ACPI\\NVDA0820\\NPCF",
            "target_device_name": "NVIDIA Platform Controllers",
            "catalog_role": "gpu_companion",
        }
        ok, err, targets = di._collect_pnputil_targets(str(bogus), device_ctx=ctx)
        assert not ok
        assert not targets
        assert "component" in err.lower() or "matching" in err.lower() or "extract" in err.lower()


def test_component_install_gate_blocks_downgrade_not_wrapper() -> None:
    offer = {
        "source": "oem",
        "title": "NVIDIA GeForce Driver",
        "version": "32.0.16.1060",
        "inner_versions": [
            {
                "version": "32.0.16.1060",
                "pci": [{"instance_id_prefix": "ACPI\\NVDA0820"}],
            },
        ],
        "installed_version": "32.0.16.1088",
    }
    ctx = {
        "instance_id": "ACPI\\NVDA0820\\NPCF",
        "target_device_name": "NVIDIA Platform Controllers",
        "catalog_role": "gpu_companion",
    }
    ok, msg = di.component_install_version_gate(offer, ctx)
    assert not ok
    assert "1088" in msg
    assert "downgrade" in msg.lower()

    offer_newer = dict(offer, installed_version="32.0.16.1051")
    ok2, _ = di.component_install_version_gate(offer_newer, ctx)
    assert ok2


def test_component_install_confirm_note_gpu_companion() -> None:
    offer = {
        "source": "oem",
        "title": "NVIDIA GeForce RTX Graphics Driver",
        "version": "32.0.16.1060",
        "url": "https://downloads.dell.com/example.exe",
    }
    ctx = {
        "catalog_role": "gpu_companion",
        "instance_id": "ACPI\\NVDA0820\\NPCF",
    }
    note = di.component_install_confirm_note(offer, ctx)
    assert "Component-only" in note
    assert "multi-driver" in note.lower()


def test_gpu_companion_graphics_bundle_compare_note_without_inner_versions() -> None:
    import catalog_offer_compare as coc

    offer = {
        "source": "oem",
        "title": "NVIDIA GeForce RTX 3080 Graphics Driver",
        "version": "32.0.16.1060",
    }
    ctx = {
        "catalog_role": "gpu_companion",
        "video_controllers": [
            {"name": "NVIDIA GeForce RTX 3080", "driver_version": "32.0.16.1088"},
        ],
    }
    note = coc._append_oem_bundle_component_note(
        offer, "newer", "Version is newer.", device_ctx=ctx
    )
    assert "component only" in note.lower()
    assert "display-driver portion is older" in note.lower()
