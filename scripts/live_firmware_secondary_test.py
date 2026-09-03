"""Live test — secondary firmware discovery + Razer support search + BIOS/SSD."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import driver_catalog as dc
import firmware_catalog as fwcat
import firmware_peripheral_discovery as fpdisc
import firmware_peripheral_vendors as fpv
from bsod_hardware_wmi import get_hardware_profile_wmi_bundle, get_ssd_firmware_inventory


def main() -> int:
    issues: list[str] = []
    print("=" * 70)
    print("Live firmware test — secondary + primary pipeline")
    print("=" * 70)

    prof = get_hardware_profile_wmi_bundle()
    if not prof:
        print("FAIL: WMI profile")
        return 1

    pnp = prof.get("pnp_list") or []
    drivers = prof.get("drivers") or []
    secondary = fpdisc.discover_secondary_firmware_devices(
        pnp, drivers, query_pnp_firmware=True
    )
    print(f"\nSecondary devices: {len(secondary)}")
    razer = None
    for d in secondary:
        print(
            f"  [{d.get('key')}] {d.get('resolved_name') or d.get('component')} "
            f"installed={d.get('installed')} source={d.get('installed_source')}"
        )
        if d.get("key") == "peripheral:1532:0277":
            razer = d

    if not razer:
        issues.append("Razer Pro Type Ultra (1532:0277) not in secondary discovery")

    if razer:
        ctx = {
            "device_id": razer.get("device_id"),
            "device_label": razer.get("resolved_name"),
            "subcategory": razer.get("subcategory"),
        }
        row = fpv.fetch_vendor_peripheral_firmware("razer", ctx)
        print("\nRazer support-site lookup:")
        print(f"  title:   {row.get('title') if row else None}")
        print(f"  version: {row.get('version') if row else None}")
        print(f"  url:     {row.get('url') if row else None}")
        if not row or not row.get("version"):
            issues.append("Razer article parse failed or no version")
        elif row.get("version") != "1.03.00_r3":
            issues.append(f"Unexpected Razer version: {row.get('version')}")
        if row and "6217" not in (row.get("url") or ""):
            issues.append("Razer URL missing article 6217")

    ssd = get_ssd_firmware_inventory()
    print(f"\nSSD inventory: {len(ssd)}")
    for d in ssd:
        print(f"  {d.get('model')} — {d.get('firmware_revision')}")

    target_keys = ["bios"]
    if ssd:
        target_keys.append(f"ssd:{ssd[0].get('model')}")
    if razer:
        target_keys.append("peripheral:1532:0277")

    print(f"\nbuild_firmware_comparison targets: {target_keys}")
    dc.set_gui_catalog_session(True)
    try:
        result = fwcat.build_firmware_comparison(
            (prof.get("bios_driver_info") or {}).get("bios"),
            prof,
            pnp,
            ssd,
            progress=lambda m: print(f"  … {m}"),
            target_keys=target_keys,
        )
    finally:
        dc.set_gui_catalog_session(False)

    offers = result.get("offers") or []
    print(f"\nOffers returned: {len(offers)}")
    for kind in ("bios", "ssd", "peripheral"):
        rows = [o for o in offers if o.get("kind") == kind]
        print(f"  {kind}: {len(rows)}")
        for o in rows[:3]:
            print(
                f"    vs={o.get('vs_installed')} ver={o.get('version')} "
                f"{(o.get('title') or '')[:60]}"
            )

    bios_rows = [o for o in offers if o.get("kind") == "bios"]
    ssd_rows = [o for o in offers if o.get("kind") == "ssd"]
    razer_rows = [
        o for o in offers if o.get("target_key") == "peripheral:1532:0277"
        or (
            o.get("kind") == "peripheral"
            and "pro type" in (o.get("title") or "").lower()
        )
    ]

    if not bios_rows:
        issues.append("No BIOS offers")
    elif any(o.get("vs_installed") == "newer" for o in bios_rows):
        false_newer = [o for o in bios_rows if o.get("vs_installed") == "newer"]
        if len(false_newer) > 2:
            issues.append(f"Suspicious BIOS 'newer' count: {len(false_newer)}")

    if ssd:
        if not ssd_rows:
            issues.append("No SSD offers for installed drive")
        elif all(o.get("vs_installed") == "newer" for o in ssd_rows if o.get("version") not in ("", "—")):
            issues.append("All SSD offers marked newer — possible false positive")

    if razer and not razer_rows:
        issues.append("No peripheral offer for Razer in build_firmware_comparison")

    out = ROOT / "live_firmware_secondary_test.json"
    out.write_text(
        json.dumps(
            {
                "issues": issues,
                "secondary": secondary,
                "target_keys": target_keys,
                "offer_summary": [
                    {
                        "kind": o.get("kind"),
                        "title": o.get("title"),
                        "version": o.get("version"),
                        "vs_installed": o.get("vs_installed"),
                        "target_key": o.get("target_key"),
                    }
                    for o in offers
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nJSON: {out}")

    if issues:
        print("\nISSUES:")
        for i in issues:
            print(f"  - {i}")
        return 1

    print("\nPASS — no blocking issues found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
