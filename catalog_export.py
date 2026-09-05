"""Export driver/firmware catalog scan results for offline review or sharing."""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import driver_catalog as drvcat
from bundle_verification import format_bundle_compare_export_lines

EXPORT_SCHEMA_VERSION = 3

_OFFER_KEYS = (
    "source",
    "source_label",
    "title",
    "version",
    "date",
    "url",
    "vs_installed",
    "compare_note",
    "notes",
    "kind",
    "confidence",
    "source_conflict",
    "data_freshness",
    "catalog_tier",
    "installed_model",
    "installed_firmware",
    "update_id",
    "hwid_matched",
    "oem_match_score",
)


def pick_offer(offer: dict | None) -> dict[str, Any]:
    if not offer:
        return {}
    out: dict[str, Any] = {}
    for key in _OFFER_KEYS:
        val = offer.get(key)
        if val is None or val == "":
            continue
        if key == "source_conflict":
            out[key] = bool(val)
        elif key in ("hwid_matched",):
            out[key] = bool(val)
        elif key == "oem_match_score":
            if val is not None and val != "":
                out[key] = val
        else:
            out[key] = val
    return out


def format_elapsed_ms(elapsed_ms: int | None) -> str:
    """Human-readable duration for export summaries."""
    if elapsed_ms is None:
        return ""
    ms = max(0, int(elapsed_ms))
    sec = ms / 1000.0
    if ms >= 60_000:
        return f"{sec / 60:.1f} min ({sec:.0f} s)"
    if ms >= 1000:
        return f"{sec:.1f} s"
    return f"{ms} ms"


def scan_timing_fields(elapsed_ms: int | None) -> dict[str, Any]:
    """JSON/text summary fields for a catalog scan duration."""
    if elapsed_ms is None:
        return {}
    ms = max(0, int(elapsed_ms))
    out: dict[str, Any] = {"elapsed_ms": ms, "elapsed_human": format_elapsed_ms(ms)}
    return out


def count_statuses(rows: list[dict], *, key: str = "status") -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        st = (row.get(key) or "none").strip().lower() or "none"
        counts[st] = counts.get(st, 0) + 1
    return dict(sorted(counts.items()))


def merge_export_row_lists(*sources: list[dict]) -> list[dict]:
    """Merge export rows; earlier sources win for the same device_name."""
    rows: list[dict] = []
    seen: set[str] = set()
    for source in sources:
        for row in source:
            name = (row.get("device_name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            rows.append(dict(row))
    return rows


def build_windows_environment_summary() -> dict[str, Any]:
    """Windows build/caption for cross-machine export comparison (no extra WMI)."""
    out: dict[str, Any] = {}
    if sys.platform != "win32":
        return out
    try:
        wv = sys.getwindowsversion()
        out["windows_major_minor"] = f"{wv.major}.{wv.minor}"
        out["windows_build"] = wv.build
    except (AttributeError, OSError, ValueError):
        pass
    try:
        win_ver = platform.win32_ver()
        if win_ver[0]:
            out["windows_caption"] = win_ver[0]
        if win_ver[1]:
            out["windows_release_id"] = win_ver[1]
    except (AttributeError, OSError, ValueError):
        pass
    try:
        out["windows_architecture"] = platform.machine()
    except (AttributeError, OSError, ValueError):
        pass
    return out


def device_catalog_diagnostics(
    ctx: dict | None,
    *,
    system_ctx: dict | None = None,
    offers: list[dict] | None = None,
) -> dict[str, Any]:
    """Per-device fields for export debugging (HWID, class, catalog path)."""
    c = ctx or {}
    out: dict[str, Any] = {}
    for key in ("vendor_key", "pnp_class", "hw_category"):
        val = (c.get(key) or "").strip()
        if val:
            out[key] = val
    inst = (c.get("instance_id") or "").strip()
    if inst:
        out["instance_id"] = inst
    path = drvcat.catalog_device_source_path(c, system_ctx)
    if path:
        out["catalog_source_path"] = path
    if offers:
        out["offer_count"] = len(offers)
        out["installable_offers"] = sum(
            1 for o in offers if drvcat._offer_installability_rank(o) <= 2
        )
        out["status_driving_offers"] = len([
            o for o in offers
            if drvcat._offer_contributes_to_status(o, c)
        ])
        resolved = sum(1 for o in offers if o.get("verification_method"))
        if resolved:
            out["verification_resolved_offers"] = resolved
    return out


def build_hardware_summary(
    hardware_profile: dict | None,
    *,
    bios_driver_info: dict | None = None,
    full_driver_count: int | None = None,
    device_counts: dict | None = None,
    system_ctx: dict | None = None,
) -> dict[str, Any]:
    """Manufacturer/model for exports using the same enrichment as driver catalog."""
    prof = hardware_profile or {}
    bio = bios_driver_info if bios_driver_info is not None else (prof.get("bios_driver_info") or {})
    system = bio.get("system") or {}
    ctx: dict[str, Any] = {
        "system_manufacturer": (
            prof.get("system_manufacturer")
            or system.get("manufacturer")
            or ""
        ).strip(),
        "system_model": (
            prof.get("system_model")
            or system.get("model")
            or ""
        ).strip(),
        "baseboard_manufacturer": (prof.get("baseboard_manufacturer") or "").strip(),
        "baseboard_product": (prof.get("baseboard_product") or "").strip(),
        "service_tag": (prof.get("service_tag") or bio.get("service_tag") or "").strip(),
        "machine_type": (prof.get("machine_type") or "").strip(),
    }
    ctx = drvcat.extend_system_ctx_for_catalog(ctx)
    inv = bio.get("all_drivers") or bio.get("device_inventory") or bio.get("drivers") or []
    inventory_n = len(inv)
    if full_driver_count is not None and full_driver_count > inventory_n:
        inventory_n = full_driver_count
    elif bio.get("all_drivers_count"):
        try:
            inventory_n = max(inventory_n, int(bio.get("all_drivers_count") or 0))
        except (TypeError, ValueError):
            pass
    out = {
        "manufacturer": ctx.get("system_manufacturer") or "",
        "model": ctx.get("system_model") or "",
        "service_tag": ctx.get("service_tag") or "",
        "system_sku": ctx.get("system_sku") or "",
        "baseboard": (
            f"{ctx.get('baseboard_manufacturer') or ''} {ctx.get('baseboard_product') or ''}".strip()
        ),
        "oem_catalog_supported": drvcat.system_has_oem_driver_catalog(ctx),
        "device_list_count": inventory_n,
        "pnp_device_count": len(prof.get("pnp_list") or []),
    }
    if device_counts:
        out["device_counts"] = dict(device_counts)
    ctx = system_ctx or prof.get("system_ctx") or {}
    if ctx:
        try:
            import catalog_cache as ccat

            fp = ccat.machine_fingerprint(ctx)
            if fp and fp != "unknown":
                out["machine_fingerprint"] = fp
        except ImportError:
            pass
        gpu_vendors = ctx.get("gpu_vendors_present") or []
        if gpu_vendors:
            out["gpu_vendors"] = list(gpu_vendors)
        cpu_vendor = (ctx.get("cpu_vendor") or "").strip()
        if cpu_vendor:
            out["cpu_vendor"] = cpu_vendor
    out.update(build_windows_environment_summary())
    return out


def apply_redaction(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove service tag and full PnP device IDs for safer sharing."""
    import copy

    out = copy.deepcopy(payload)
    out["redacted_sensitive_fields"] = True
    hw = dict(out.get("hardware_summary") or {})
    for key in ("service_tag", "system_sku"):
        hw.pop(key, None)
    out["hardware_summary"] = hw
    crash = dict(out.get("crash_context") or {})
    crash.pop("culprit_device_names", None)
    out["crash_context"] = crash
    for row in out.get("drivers") or []:
        if row.get("device_name"):
            row["device_name"] = "(redacted device id)"
        row.pop("driver_file", None)
        diag = row.get("device_diagnostics")
        if isinstance(diag, dict):
            diag.pop("instance_id", None)
    return out


def build_payload(
    *,
    app_version: str,
    install_mode: str,
    scan_mode: dict[str, str],
    exported_at: str | None = None,
    crash_context: dict | None = None,
    hardware_summary: dict | None = None,
    driver_rows: list[dict],
    firmware_rows: list[dict],
    driver_batch_fetched_at: str = "",
    firmware_fetched_at: str = "",
    driver_batch_elapsed_ms: int | None = None,
    firmware_elapsed_ms: int | None = None,
    data_sources: list[str] | None = None,
    lookup_health: dict | None = None,
    export_index: dict | None = None,
    export_options: dict | None = None,
    redact_sensitive: bool = False,
) -> dict[str, Any]:
    """Assemble a JSON-serializable export document."""
    drivers = [dict(r) for r in driver_rows]
    firmware = [dict(r) for r in firmware_rows]
    for row in drivers:
        row["offers"] = [pick_offer(o) for o in (row.get("offers") or [])]
    for row in firmware:
        row["offers"] = [pick_offer(o) for o in (row.get("offers") or [])]

    payload = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "app_version": app_version,
        "exported_at": exported_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "install_mode": install_mode,
        "scan_mode": dict(scan_mode or {}),
        "data_sources": list(data_sources or []),
        "crash_context": dict(crash_context or {}),
        "hardware_summary": dict(hardware_summary or {}),
        "summary": {
            "drivers": {
                "device_count": len(drivers),
                "export_universe_count": (hardware_summary or {}).get("device_counts", {}).get(
                    "full_inventory_count"
                ),
                "fetched_at": driver_batch_fetched_at,
                **scan_timing_fields(driver_batch_elapsed_ms),
                "by_status": count_statuses(drivers),
                "crash_linked": sum(1 for d in drivers if d.get("crash_linked")),
                "with_offers": sum(1 for d in drivers if d.get("offers")),
                "coverage_gaps": sum(1 for d in drivers if d.get("possible_coverage_gap")),
                "none_by_reason": count_statuses(
                    [
                        {"status": (d.get("none_reason") or "none").strip() or "none"}
                        for d in drivers
                        if (d.get("status") or "") == "none"
                    ],
                ),
            },
            "firmware": {
                "component_count": len(firmware),
                "fetched_at": firmware_fetched_at,
                **scan_timing_fields(firmware_elapsed_ms),
                "by_status": count_statuses(firmware),
                "with_offers": sum(1 for f in firmware if f.get("offers")),
            },
        },
        "drivers": drivers,
        "firmware": firmware,
        "lookup_health": dict(lookup_health or {}),
    }
    if export_index:
        payload["export_index"] = dict(export_index)
    if export_options:
        payload["export_options"] = dict(export_options)
    if redact_sensitive:
        payload = apply_redaction(payload)
    return payload


def format_text_summary(payload: dict[str, Any]) -> str:
    """Human-readable export for quick review or chat paste."""
    lines: list[str] = [
        "BSOD Analyzer — Catalog scan export",
        "=" * 60,
        f"App version: {payload.get('app_version', '?')}",
        f"Exported: {payload.get('exported_at', '?')}",
        f"Install mode: {payload.get('install_mode', '?')}",
    ]
    sources = payload.get("data_sources") or []
    if sources:
        lines.append(f"Data sources: {', '.join(sources)}")

    scan = payload.get("scan_mode") or {}
    if scan.get("mode"):
        lines.append(f"Scan mode: {scan['mode']}")
    if scan.get("detail"):
        lines.append("")
        lines.append("Scan sources:")
        lines.extend(f"  {ln}" for ln in str(scan["detail"]).splitlines())

    crash = payload.get("crash_context") or {}
    if any(crash.values()):
        lines.extend(["", "Crash context", "-" * 40])
        if crash.get("faulting_driver"):
            lines.append(f"Faulting module: {crash['faulting_driver']}")
        if crash.get("stop_code"):
            lines.append(f"Stop code: {crash['stop_code']}")
        names = crash.get("culprit_device_names") or []
        if names:
            lines.append(f"Culprit device(s): {', '.join(names[:12])}")
            if len(names) > 12:
                lines.append(f"  … and {len(names) - 12} more")

    hw = payload.get("hardware_summary") or {}
    if hw:
        lines.extend(["", "Hardware", "-" * 40])
        priority = (
            "manufacturer",
            "model",
            "machine_fingerprint",
            "service_tag",
            "windows_caption",
            "windows_build",
            "windows_major_minor",
            "windows_architecture",
            "cpu_vendor",
            "gpu_vendors",
            "baseboard",
            "oem_catalog_supported",
            "device_list_count",
            "pnp_device_count",
        )
        shown: set[str] = set()
        for label in priority:
            val = hw.get(label)
            if val is None or val == "":
                continue
            if label == "gpu_vendors" and isinstance(val, list):
                lines.append(f"{label}: {', '.join(str(v) for v in val)}")
            elif label in ("oem_catalog_supported",):
                lines.append(f"{label}: {val}")
            else:
                lines.append(f"{label}: {val}")
            shown.add(label)
        for label, val in hw.items():
            if label in shown or label == "device_counts" or not val:
                continue
            lines.append(f"{label}: {val}")
        counts = hw.get("device_counts") or {}
        if counts:
            lines.append(f"device_counts: {counts}")

    summary = payload.get("summary") or {}
    drv_sum = summary.get("drivers") or {}
    fw_sum = summary.get("firmware") or {}
    lines.extend(
        [
            "",
            "Summary",
            "-" * 40,
            (
                f"Drivers: {drv_sum.get('device_count', 0)} exported"
                + (f" (scan at {drv_sum.get('fetched_at')})" if drv_sum.get("fetched_at") else "")
                + (
                    f" — duration {drv_sum.get('elapsed_human')}"
                    if drv_sum.get("elapsed_human")
                    else ""
                )
            ),
        ]
    )
    for st, n in (drv_sum.get("by_status") or {}).items():
        lines.append(f"  {st}: {n}")
    lines.append(
        f"Firmware: {fw_sum.get('component_count', 0)} exported"
        + (f" (scan at {fw_sum.get('fetched_at')})" if fw_sum.get("fetched_at") else "")
        + (
            f" — duration {fw_sum.get('elapsed_human')}"
            if fw_sum.get("elapsed_human")
            else ""
        )
    )
    for st, n in (fw_sum.get("by_status") or {}).items():
        lines.append(f"  {st}: {n}")

    lookup = payload.get("lookup_health") or {}
    if lookup:
        lines.extend(["", "Lookup sources & API health", "-" * 40])
        note = (lookup.get("note") or "").strip()
        if note:
            lines.append(note)
        cat = lookup.get("catalog_scan") or {}
        if cat.get("mode"):
            lines.append(f"Catalog scan mode: {cat['mode']}")
        active = cat.get("active_sources") or []
        skipped = cat.get("skipped_sources") or []
        if active:
            lines.append("Active catalog sources:")
            lines.extend(f"  • {s}" for s in active)
        if skipped:
            lines.append("Skipped in this mode:")
            lines.extend(f"  • {s}" for s in skipped)
        seen = lookup.get("offer_sources_in_export") or []
        if seen:
            lines.append(f"Package sources in this export: {', '.join(seen)}")
        for row in lookup.get("vendor_lookups") or []:
            label = row.get("label") or row.get("vendor") or "?"
            if not row.get("applicable_to_this_pc"):
                lines.append(f"{label}: not applicable to this PC")
                continue
            status = row.get("session_status") or "unknown"
            status_label = {
                "ok": "OK (last search)",
                "failed": "FAILED (last search)",
                "not_checked": "not checked this session",
            }.get(status, status)
            lines.append(f"{label}: {status_label}")
            method = (row.get("working_method") or "").strip()
            if method:
                lines.append(f"  Method: {method}")
            failures = row.get("failed_steps") or []
            if failures and status != "ok":
                lines.append(f"  Failed steps: {'; '.join(failures[:4])}")
            endpoints = row.get("configured_endpoints") or {}
            if endpoints:
                lines.append("  Configured lookup URLs:")
                for key, url in sorted(endpoints.items()):
                    lines.append(f"    {key}: {url}")
        manifest = lookup.get("endpoint_manifest") or {}
        if manifest.get("updated_at"):
            lines.append(
                f"Lookup settings file: {manifest.get('source') or 'bundled'} "
                f"(updated {manifest['updated_at']})"
            )

    export_index = payload.get("export_index") or {}
    if export_index:
        lines.extend(["", "Driver index (SQLite)", "-" * 40])
        if export_index.get("enabled") is False:
            lines.append("Driver index disabled for this install mode.")
        else:
            err = (export_index.get("read_error") or "").strip()
            if err:
                lines.append(f"Read error: {err[:240]}")
            skipped = export_index.get("skipped_devices") or []
            if skipped:
                lines.append(
                    f"Devices not loaded from index ({len(skipped)}): "
                    + ", ".join(skipped[:20])
                )
                if len(skipped) > 20:
                    lines.append(f"  … and {len(skipped) - 20} more")
            if not err and not skipped:
                lines.append("Index read OK for this export.")

    drivers = payload.get("drivers") or []
    if drivers:
        lines.extend(["", "Drivers", "-" * 40])
        rank = drvcat._STATUS_RANK
        ordered = sorted(
            drivers,
            key=lambda d: (
                rank.get((d.get("status") or "none").lower(), 99),
                not d.get("crash_linked"),
                (d.get("device_name") or "").lower(),
            ),
        )
        for dev in ordered:
            _append_driver_text(lines, dev)

    firmware = payload.get("firmware") or []
    if firmware:
        lines.extend(["", "Firmware", "-" * 40])
        for ent in firmware:
            _append_firmware_text(lines, ent)

    lines.extend(
        [
            "",
            "Tip: share the .json export for full package detail (all catalog offers).",
            f"Generated by BSOD Analyzer v{payload.get('app_version', '?')}.",
        ]
    )
    return "\n".join(lines)


def _append_driver_text(lines: list[str], dev: dict) -> None:
    name = (dev.get("display_name") or dev.get("device_name") or "?").strip()
    pnp = (dev.get("device_name") or "").strip()
    status = (dev.get("status") or "none").strip()
    inst = (dev.get("installed_version") or "?").strip()
    flags: list[str] = []
    if dev.get("crash_linked"):
        flags.append("crash-linked")
    tier = (dev.get("tier") or "").strip()
    if tier and tier not in ("normal", ""):
        flags.append(f"tier={tier}")
    flag_s = f" [{', '.join(flags)}]" if flags else ""
    lines.append(f"\n{name}{flag_s}")
    if pnp and pnp != name:
        lines.append(f"  PnP name: {pnp}")
    mfr = (dev.get("manufacturer") or "").strip()
    if mfr:
        lines.append(f"  Manufacturer: {mfr}")
    cls = (dev.get("device_class") or "").strip()
    if cls:
        lines.append(f"  Class: {cls}")
    diag = dev.get("device_diagnostics") or {}
    if isinstance(diag, dict):
        if diag.get("vendor_key"):
            lines.append(f"  Vendor key: {diag['vendor_key']}")
        if diag.get("pnp_class"):
            lines.append(f"  PnP class: {diag['pnp_class']}")
        if diag.get("instance_id"):
            lines.append(f"  Instance ID: {diag['instance_id']}")
        if diag.get("catalog_source_path"):
            lines.append(f"  Catalog path: {diag['catalog_source_path']}")
    parent_name = (dev.get("parent_device_name") or "").strip()
    if parent_name:
        lines.append(f"  PnP parent (Windows): {parent_name}")
    lines.append(f"  Installed: {inst}  |  Status: {status}")
    bundle_lines = format_bundle_compare_export_lines(dev)
    if bundle_lines:
        lines.extend(bundle_lines)
    elif dev.get("chipset_bundle_components"):
        bundle = dev.get("chipset_bundle_components") or []
        lines.append(f"  Chipset bundle ({len(bundle)} component INF version(s)):")
        for comp in bundle[:12]:
            if not isinstance(comp, dict):
                continue
            dn = (comp.get("device_name") or comp.get("label") or "?").strip()
            cv = (comp.get("version") or "?").strip()
            lines.append(f"    • {dn}: {cv}")
        if len(bundle) > 12:
            lines.append(f"    … and {len(bundle) - 12} more")
    _append_offers_text(lines, dev.get("offers") or [])


def _append_firmware_text(lines: list[str], ent: dict) -> None:
    label = (ent.get("component") or ent.get("target_key") or "?").strip()
    status = (ent.get("status") or "none").strip()
    inst = (ent.get("installed_version") or "?").strip()
    tier = (ent.get("tier") or "").strip()
    tier_s = f" [{tier}]" if tier and tier not in ("normal", "") else ""
    lines.append(f"\n{label}{tier_s}")
    lines.append(f"  Installed: {inst}  |  Status: {status}")
    _append_offers_text(lines, ent.get("offers") or [])


def _append_offers_text(lines: list[str], offers: list[dict]) -> None:
    if not offers:
        lines.append("  Packages: (none saved)")
        return
    lines.append(f"  Packages ({len(offers)}):")
    for i, offer in enumerate(offers[:20], 1):
        src = offer.get("source_label") or offer.get("source") or "?"
        ver = offer.get("version") or "—"
        vs = offer.get("vs_installed") or "?"
        title = (offer.get("title") or "")[:100]
        conflict = " [source conflict]" if offer.get("source_conflict") else ""
        hwid = " [HWID verified]" if offer.get("hwid_matched") else ""
        score = offer.get("oem_match_score")
        score_note = f" [oem score {score}]" if score not in (None, "") else ""
        lines.append(f"    {i}. {src}: v{ver} → {vs}{conflict}{hwid}{score_note}")
        if title:
            lines.append(f"       {title}")
        note = (offer.get("compare_note") or offer.get("notes") or "").strip()
        if note:
            lines.append(f"       {note[:200]}")
    if len(offers) > 20:
        lines.append(f"    … and {len(offers) - 20} more package(s)")


def _export_driver_map(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in payload.get("drivers") or []:
        key = (row.get("display_name") or row.get("device_name") or "").strip()
        if key:
            out[key] = row
    return out


def _export_header_line(label: str, payload: dict) -> str:
    hw = payload.get("hardware_summary") or {}
    ver = payload.get("app_version") or "?"
    fp = hw.get("machine_fingerprint") or hw.get("model") or "?"
    win = hw.get("windows_caption") or ""
    build = hw.get("windows_build") or ""
    os_bit = f" ({win} build {build})" if win or build else ""
    return f"{label}: v{ver} | {fp}{os_bit} | exported {payload.get('exported_at', '?')}"


def compare_catalog_exports(a: dict, b: dict) -> str:
    """Human-readable diff between two catalog scan JSON exports."""
    lines = [
        "BSOD Analyzer — catalog export comparison",
        "=" * 72,
        _export_header_line("A", a),
        _export_header_line("B", b),
        "",
    ]
    sa = (a.get("summary") or {}).get("drivers") or {}
    sb = (b.get("summary") or {}).get("drivers") or {}
    lines.append("Scan summary:")
    lines.append(
        f"  A: {sa.get('device_count', 0)} devices, "
        f"elapsed {sa.get('elapsed_human') or sa.get('elapsed_ms') or '?'}, "
        f"statuses {sa.get('by_status') or {}}"
    )
    lines.append(
        f"  B: {sb.get('device_count', 0)} devices, "
        f"elapsed {sb.get('elapsed_human') or sb.get('elapsed_ms') or '?'}, "
        f"statuses {sb.get('by_status') or {}}"
    )
    crash_a = ((a.get("crash_context") or {}).get("culprit_devices") or [])
    crash_b = ((b.get("crash_context") or {}).get("culprit_devices") or [])
    if crash_a or crash_b:
        lines.append(f"  Crash-linked A: {', '.join(crash_a) or '(none)'}")
        lines.append(f"  Crash-linked B: {', '.join(crash_b) or '(none)'}")
    lines.append("")

    va = {
        v.get("vendor"): v.get("session_status")
        for v in (a.get("lookup_health") or {}).get("vendor_lookups") or []
    }
    vb = {
        v.get("vendor"): v.get("session_status")
        for v in (b.get("lookup_health") or {}).get("vendor_lookups") or []
    }
    vendors = sorted(set(va) | set(vb))
    if vendors:
        lines.append("Manufacturer lookup session status:")
        for vk in vendors:
            lines.append(f"  {vk}: {va.get(vk, '-')} -> {vb.get(vk, '-')}")
        lines.append("")

    da = _export_driver_map(a)
    db = _export_driver_map(b)
    all_names = sorted(set(da) | set(db))
    status_changes: list[str] = []
    version_changes: list[str] = []
    gap_changes: list[str] = []
    for name in all_names:
        ra = da.get(name) or {}
        rb = db.get(name) or {}
        sa_st = (ra.get("status") or "none").strip()
        sb_st = (rb.get("status") or "none").strip()
        if sa_st != sb_st:
            status_changes.append(f"  {name}: {sa_st} -> {sb_st}")
        ia = (ra.get("installed_version") or "").strip()
        ib = (rb.get("installed_version") or "").strip()
        if ia and ib and ia != ib:
            version_changes.append(f"  {name}: {ia} -> {ib}")
        ga = bool(ra.get("possible_coverage_gap"))
        gb = bool(rb.get("possible_coverage_gap"))
        if ga != gb:
            gap_changes.append(f"  {name}: gap {ga} -> {gb}")

    if status_changes:
        lines.append(f"Status changes ({len(status_changes)}):")
        lines.extend(status_changes[:40])
        if len(status_changes) > 40:
            lines.append(f"  … and {len(status_changes) - 40} more")
        lines.append("")
    else:
        lines.append("No driver status changes between exports (matched device names).")
        lines.append("")

    if version_changes:
        lines.append(f"Installed version changes ({len(version_changes)}):")
        lines.extend(version_changes[:20])
        lines.append("")

    if gap_changes:
        lines.append(f"Coverage gap flag changes ({len(gap_changes)}):")
        lines.extend(gap_changes[:20])
        lines.append("")

    only_a = sorted(set(da) - set(db))
    only_b = sorted(set(db) - set(da))
    if only_a:
        lines.append(f"Devices only in A ({len(only_a)}): " + ", ".join(only_a[:15]))
        if len(only_a) > 15:
            lines.append(f"  … and {len(only_a) - 15} more")
        lines.append("")
    if only_b:
        lines.append(f"Devices only in B ({len(only_b)}): " + ", ".join(only_b[:15]))
        if len(only_b) > 15:
            lines.append(f"  … and {len(only_b) - 15} more")
        lines.append("")

    return "\n".join(lines)


def write_export_file(path: Path | str, payload: dict[str, Any]) -> None:
    """Write JSON or plain-text summary based on file extension."""
    import bsod_runtime as rt

    p = Path(path)
    if p.suffix.lower() == ".txt":
        rt.write_text_file_sync(p, format_text_summary(payload))
    else:
        rt.write_text_file_sync(
            p,
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        )
