"""One-shot live firmware scan — same pipeline as Firmware tab Search."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import driver_catalog as dc
import firmware_catalog as fwcat
from bsod_hardware_wmi import get_hardware_profile_wmi_bundle, get_ssd_firmware_inventory


def main() -> int:
    print("=" * 60)
    print("BSOD Analyzer — live firmware scan (catalog pipeline)")
    print("=" * 60)

    print("\n[1/3] Reading hardware profile (WMI)…")
    prof = get_hardware_profile_wmi_bundle()
    if not prof:
        print("ERROR: WMI hardware profile failed.")
        return 1

    bios_info = (prof.get("bios_driver_info") or {}).get("bios") or {}
    system_ctx = {
        k: prof.get(k)
        for k in (
            "pnp_list",
            "present_drivers",
            "system_manufacturer",
            "system_model",
            "system_product_uuid",
            "gpu_vendor",
            "gpu_vendors_present",
            "has_amd_chipset",
            "has_intel_chipset",
            "has_sata",
            "has_nvme",
            "disk_rows",
        )
        if prof.get(k) is not None
    }
    system_ctx["_gui_driver_catalog"] = True

    print(f"  PC: {system_ctx.get('system_manufacturer')} {system_ctx.get('system_model')}")
    print(
        f"  BIOS installed: {bios_info.get('manufacturer')} "
        f"{bios_info.get('version')} ({bios_info.get('date')})"
    )

    print("\n[2/3] Reading SSD firmware inventory…")
    ssd_list = get_ssd_firmware_inventory()
    for d in ssd_list:
        print(
            f"  SSD: {d.get('model')} — firmware {d.get('firmware_revision')} "
            f"({d.get('vendor_key')})"
        )
    if not ssd_list:
        print("  (no SSD rows from WMI)")

    print("\n[3/3] Running build_firmware_comparison (OEM + MSCatalog + WU + vendor)…")
    print("  (network calls — may take several minutes)\n")

    def progress(msg: str) -> None:
        print(f"  … {msg}")

    dc.set_gui_catalog_session(True)
    try:
        result = fwcat.build_firmware_comparison(
            bios_info,
            system_ctx,
            prof.get("pnp_list") or [],
            ssd_list,
            progress=progress,
            target_keys=None,
        )
    finally:
        dc.set_gui_catalog_session(False)

    offers = result.get("offers") or []
    print("\n" + "=" * 60)
    print(f"Scan complete at {result.get('fetched_at')} — {len(offers)} offer row(s)")
    print(f"Scan mode: {result.get('scan_mode')} — {result.get('scan_mode_detail')}")
    print("=" * 60)

    bios_offers = [o for o in offers if o.get("kind") == "bios"]
    ssd_offers = [o for o in offers if o.get("kind") == "ssd"]
    util_offers = [o for o in offers if fwcat.is_utility_or_link_offer(o)]
    versioned = [
        o
        for o in offers
        if (o.get("version") or "").strip() not in ("", "—")
        and not fwcat.is_utility_or_link_offer(o)
    ]

    bios_status = dc.summarize_offer_status(bios_offers)
    print(f"\nBIOS summary status: {bios_status}")
    print(f"  Versioned BIOS offers: {len([o for o in bios_offers if o.get('version')])}")
    for o in bios_offers[:6]:
        print(
            f"    [{o.get('vs_installed')}] {o.get('source_label')}: "
            f"{o.get('title')[:70]} — v{o.get('version') or '?'}"
        )

    print(f"\nSSD offer rows: {len(ssd_offers)}")
    models = {d.get("model") for d in ssd_list if d.get("model")}
    for model in sorted(models):
        related = [
            o
            for o in ssd_offers
            if (o.get("installed_model") or "").lower() == model.lower()
            or model.lower() in (o.get("title") or "").lower()
        ]
        st = dc.summarize_offer_status(related)
        print(f"  {model}: status={st}, offers={len(related)}")
        for o in related[:3]:
            flag = " [coverage_gap]" if o.get("coverage_check_failed") else ""
            print(
                f"    [{o.get('vs_installed')}] {o.get('source')} / "
                f"{o.get('source_label')}: v{o.get('version') or '?'}{flag}"
            )

    print(f"\nUtility/link-only rows: {len(util_offers)}")
    for o in util_offers[:8]:
        print(f"  {o.get('kind')}: {o.get('title')[:65]}")

    newer = [o for o in offers if o.get("vs_installed") == "newer"]
    uncertain = [o for o in offers if o.get("vs_installed") == "uncertain"]
    print(f"\nWould show 'Updates available' (vs_installed=newer): {len(newer)}")
    for o in newer:
        print(f"  + {o.get('kind')}: {o.get('title')[:60]} ({o.get('source_label')})")

    print(f"\nWould show 'Verify manually' (vs_installed=uncertain): {len(uncertain)}")
    for o in uncertain[:8]:
        print(f"  ? {o.get('kind')}: {o.get('title')[:60]}")

    out_path = ROOT / "live_firmware_scan_report.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\nFull JSON saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
