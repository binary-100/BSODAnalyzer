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


def bundle_verification_probe_summary(comparison: dict | None) -> dict[str, Any]:
    """Compact bundle rollup block for live_machine_probe JSON."""
    from bundle_verification import (
        bundle_compare_rows_from_catalog_entry,
        stale_bundle_component_labels,
    )

    comp = comparison or {}
    wrapper = (comp.get("status") or "").strip().lower()
    rollup = (comp.get("bundle_status_rollup") or "").strip().lower()
    final = rollup if rollup == "newer" and wrapper in ("same", "none", "uncertain", "unknown") else wrapper
    compare = bundle_compare_rows_from_catalog_entry(comp)
    stale = stale_bundle_component_labels(compare)
    return {
        "wrapper_status": wrapper or "unknown",
        "rollup_status": rollup or "",
        "final_status": final or wrapper or "unknown",
        "stale_components": stale,
        "compare_count": len(compare),
        "bundle_compare_note": (comp.get("bundle_compare_note") or "").strip(),
        "components": [
            {
                "label": (row.get("label") or "?").strip(),
                "installed": (row.get("installed_version") or "?").strip(),
                "offer": (row.get("offer_version") or "?").strip(),
                "vs": (row.get("vs_offer") or "?").strip(),
            }
            for row in compare[:12]
        ],
    }


def probe_chipset_bundle_verification(
    system_ctx: dict | None,
    inventory: list | None,
) -> dict[str, Any]:
    """Live chipset platform comparison with bundle rollup (may use network for vendor offers)."""
    ctx = dict(system_ctx or {})
    out: dict[str, Any] = {}
    for dev_name, label in chipset_platform_targets(ctx):
        try:
            comparison = dc.build_chipset_platform_comparison(
                dev_name,
                ctx,
                inventory=inventory,
            )
        except Exception as exc:  # noqa: BLE001
            out[label] = {"error": str(exc)}
            continue
        status = comparison.get("status")
        if not status:
            from catalog_offer_status import summarize_offer_status

            status = summarize_offer_status(
                comparison.get("offers") or [],
                device_ctx=comparison.get("context"),
            )
        rollup = (comparison.get("bundle_status_rollup") or "").lower()
        if rollup == "newer" and (status or "").lower() in (
            "same",
            "none",
            "uncertain",
            "unknown",
        ):
            status = "newer"
        comparison["status"] = status
        block = bundle_verification_probe_summary(comparison)
        block["device_name"] = dev_name
        block["installed_version"] = comparison.get("installed_version") or ""
        block["offer_count"] = len(comparison.get("offers") or [])
        block["catalog_note"] = (comparison.get("catalog_note") or "").strip()
        out[label] = block
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
