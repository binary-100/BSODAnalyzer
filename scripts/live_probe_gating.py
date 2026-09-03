"""Hardware-gated vendor/chipset probe helpers for live_machine_probe."""
from __future__ import annotations

from typing import Any, Callable

import bsod_hardware_wmi as hw
import driver_catalog as dc


def _skipped_probe(reason: str) -> dict[str, Any]:
    return {"skipped": True, "reason": reason, "ok": True}


def _hardware_context_confident(system_ctx: dict | None) -> bool:
    ctx = system_ctx or {}
    return bool(ctx.get("cpu_vendor") or ctx.get("gpu_vendor"))


def run_gated_vendor_probes(
    system_ctx: dict | None,
    *,
    run_probe: Callable[..., tuple[Any, str]],
    network_timeout_sec: float = 20.0,
) -> dict[str, Any]:
    """Run vendor probes only when this PC has matching hardware."""
    ctx = system_ctx or {}
    confident = _hardware_context_confident(ctx)
    probes: dict[str, Any] = {}

    if confident and not hw.nvidia_driver_lookup_applicable(ctx):
        probes["nvidia"] = _skipped_probe("No NVIDIA GPU on this PC")
    else:
        hit, err = run_probe(_nvidia_probe, network_timeout_sec)
        probes["nvidia"] = hit or {"ok": False, "error": err or "failed"}

    if confident and not hw.amd_driver_lookup_applicable(ctx):
        probes["amd"] = _skipped_probe("No AMD GPU or chipset on this PC")
    else:
        hit, err = run_probe(_amd_probe, network_timeout_sec)
        probes["amd"] = hit or {"ok": False, "error": err or "failed"}

    if confident and hw.intel_chipset_applicable(ctx):
        hit, err = run_probe(_intel_chipset_probe, network_timeout_sec)
        probes["intel_chipset"] = hit or {"ok": False, "error": err or "failed"}
    elif confident:
        probes["intel_chipset"] = _skipped_probe("No Intel chipset on this PC")
    else:
        probes["intel_chipset"] = _skipped_probe(
            "Platform not detected — Intel chipset check skipped"
        )

    return probes


def chipset_platform_targets(system_ctx: dict | None) -> list[tuple[str, str]]:
    """(device_key, label) pairs for chipset comparisons on this PC."""
    ctx = system_ctx or {}
    out: list[tuple[str, str]] = []
    if hw.amd_chipset_applicable(ctx):
        out.append((hw.CHIPSET_DEVICE_AMD, "amd"))
    if hw.intel_chipset_applicable(ctx):
        out.append((hw.CHIPSET_DEVICE_INTEL, "intel"))
    return out


def _nvidia_probe() -> dict[str, Any]:
    ctx_n = {
        "vendor_key": "nvidia",
        "pnp_class": "display",
        "device_label": "NVIDIA GeForce",
    }
    hit, method = dc._nvidia_lookup_download_info(ctx_n)
    return {
        "method": method or "",
        "version": (hit or {}).get("Version") or "",
        "ok": bool((hit or {}).get("Version")),
    }


def _amd_probe() -> dict[str, Any]:
    ver, _ = dc._scrape_amd_driver_version(
        {"hw_category": "graphics", "device_label": "AMD Radeon"}
    )
    return {"version": ver or "", "ok": bool(ver)}


def _intel_chipset_probe() -> dict[str, Any]:
    ver, date, url = dc._scrape_intel_driver_version("chipset")
    return {"version": ver, "date": date, "url": url, "ok": bool(ver)}
