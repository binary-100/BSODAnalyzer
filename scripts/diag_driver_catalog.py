"""Live diagnostic: why driver update versions may not populate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_settings as app_set
import driver_catalog as dc
import bsod_analyzer as core


def main() -> int:
    settings = app_set.load_settings()
    print("=== BSOD Analyzer driver catalog diagnostic ===\n")
    print(f"full_install: {app_set.is_full_install_mode(settings)}")
    print(f"quick_check_mode (settings): {settings.get('quick_check_mode')}")
    dc.configure_catalog(
        quick_check=bool(settings.get("quick_check_mode"))
        and not app_set.is_full_install_mode(settings),
        oem_session_cache=settings.get("oem_session_cache"),
    )
    print(f"catalog quick_check active: {dc.is_quick_check_mode()}\n")

    print("--- Windows Update optional drivers (COM) ---")
    rows, err = dc.fetch_wu_driver_rows_deep()
    print(f"row_count: {len(rows)}")
    print(f"error: {err[:300] if err else '(none)'}")
    for r in rows[:5]:
        print(
            f"  - {(r.get('Title') or '')[:70]!r} "
            f"ver={r.get('Version')!r} hw={len(r.get('HardwareIds') or [])} ids"
        )

    print("\n--- Video controllers (installed) ---")
    ok, out = core.run_powershell(
        r"Get-CimInstance Win32_VideoController -EA 0 | "
        r"Select-Object Name, DriverVersion, PNPDeviceID | ConvertTo-Json -Compress"
    )
    vcs = []
    if ok and out:
        try:
            data = json.loads(out)
            vcs = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            print(out[:400])
    for vc in vcs[:4]:
        print(
            f"  {vc.get('Name')}: driver={vc.get('DriverVersion')} "
            f"pnp={(vc.get('PNPDeviceID') or '')[:60]}"
        )

    system_ctx = {}
    try:
        import bsod_hardware_wmi as hw
        prof = hw.scan_hardware_profile(progress=None)
        system_ctx = prof.get("system_ctx") or {}
        bio = prof.get("bios_driver_info") or {}
        inv = core.device_inventory_for_matching(bio)
        pnp = system_ctx.get("pnp_list") or []
        print(f"\n--- Hardware scan: {len(inv)} inventory, {len(pnp)} PnP ---")
        display = [
            d for d in inv
            if (d.get("device_class") or "").upper() == "DISPLAY"
            or "nvidia" in (d.get("name") or "").lower()
            or "geforce" in (d.get("name") or "").lower()
        ][:3]
        if not display:
            display = inv[:3]
        ctx_ext = dc.extend_system_ctx_for_catalog(dict(system_ctx))
        for d in display:
            name = (d.get("name") or "").strip()
            print(f"\n--- Device check: {name} ---")
            print(f"  installed inventory version: {d.get('version')!r}")
            comp = dc.build_device_driver_comparison(
                name, pnp, inv, ctx_ext, progress=lambda m: None
            )
            inst = comp.get("installed_version")
            offers = comp.get("offers") or []
            status = dc.summarize_offer_status(offers)
            print(f"  comparison installed: {inst!r} status: {status}")
            for o in offers[:8]:
                print(
                    f"    [{o.get('source')}] {o.get('vs_installed')} "
                    f"inst={o.get('installed_version')} cand={o.get('version')!r} "
                    f"{(o.get('title') or '')[:50]}"
                )
    except Exception as e:
        print(f"\nHardware scan skipped: {e}")
        if vcs:
            fake_name = vcs[0].get("Name") or "GPU"
            ctx_ext = dc.extend_system_ctx_for_catalog(
                {"video_controllers": [
                    {
                        "name": fake_name,
                        "pnp_device_id": vcs[0].get("PNPDeviceID"),
                        "driver_version": vcs[0].get("DriverVersion"),
                    }
                ]}
            )
            comp = dc.build_device_driver_comparison(
                fake_name, [], [], ctx_ext
            )
            print(f"\n--- Fallback GPU check: {fake_name} ---")
            print(f"  status: {dc.summarize_offer_status(comp.get('offers') or [])}")
            for o in (comp.get("offers") or [])[:6]:
                print(
                    f"    [{o.get('source')}] {o.get('vs_installed')} "
                    f"cand={o.get('version')!r}"
                )

    print("\n=== done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
