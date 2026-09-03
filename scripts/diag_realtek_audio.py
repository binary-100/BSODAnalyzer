"""Live probe: why 'Realtek Audio' (MEDIA) gets no Microsoft Update Catalog offer.

Runs on the real machine. Prints:
  * the MSCatalog search queries generated for the Realtek Audio device,
  * raw MSCatalog rows returned per query,
  * the final comparison offers and (if any) why non-OEM offers were dropped.

    py -3 scripts/diag_realtek_audio.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_settings as app_set
import driver_catalog as dc
import bsod_analyzer as core


def _find_realtek_audio(inv, pnp):
    cands = []
    for d in inv:
        name = (d.get("name") or d.get("display_name") or "")
        cls = (d.get("device_class") or "").upper()
        if "realtek" in name.lower() and cls == "MEDIA":
            cands.append(d)
    return cands


def main() -> int:
    settings = app_set.load_settings()
    dc.configure_catalog(
        quick_check=bool(settings.get("quick_check_mode"))
        and not app_set.is_full_install_mode(settings),
        oem_session_cache=settings.get("oem_session_cache"),
    )
    print("=== Realtek Audio MSCatalog probe ===")
    print(f"full_install={app_set.is_full_install_mode(settings)} "
          f"quick_check_active={dc.is_quick_check_mode()}")

    t0 = time.monotonic()
    prof = core.gather_hardware_profile(progress_cb=None)
    print(f"hardware scan: {time.monotonic()-t0:.1f}s")
    system_ctx = prof.get("system_ctx") or {}
    bio = prof.get("bios_driver_info") or {}
    inv = core.device_inventory_for_matching(bio)
    pnp = system_ctx.get("pnp_list") or []
    ctx_ext = dc.extend_system_ctx_for_catalog(dict(system_ctx))

    cands = _find_realtek_audio(inv, pnp)
    print(f"\nRealtek MEDIA devices found: {[c.get('name') for c in cands]}")
    if not cands:
        print("No Realtek MEDIA device in inventory — nothing to probe.")
        return 0

    for dev in cands:
        name = (dev.get("name") or "").strip()
        print("\n" + "=" * 60)
        print(f"DEVICE: {name}  installed={dev.get('version')!r}")
        dctx = dc.get_device_context_for_name(name, pnp, inv, ctx_ext)
        dctx["_catalog_system_ctx"] = ctx_ext
        print(f"  vendor_key={dctx.get('vendor_key')!r} pnp_class={dctx.get('pnp_class')!r}")
        print(f"  instance_id={(dctx.get('instance_id') or '')[:70]!r}")

        queries = dc._catalog_search_queries_for_ctx(dctx)
        print(f"\n  MSCatalog queries ({len(queries)}):")
        for q in queries:
            print(f"    - {q!r}")

        include_preview = dc.catalog_include_preview_updates()
        for q in queries:
            t = time.monotonic()
            rows, err = dc._search_mscatalog_updates_cached(
                q, limit=8, include_preview=include_preview
            )
            print(f"\n  QUERY {q!r} -> {len(rows)} row(s) in {time.monotonic()-t:.1f}s "
                  f"err={err[:80]!r}")
            for r in rows[:8]:
                print(f"      title={ (r.get('Title') or '')[:70]!r} "
                      f"ver={r.get('Version')!r} "
                      f"hw={len(r.get('HardwareIds') or r.get('hardware_ids') or [])}ids")

        print(f"\n  --- full comparison for {name} ---")
        t = time.monotonic()
        comp = dc.build_device_driver_comparison(
            name, pnp, inv, ctx_ext, progress=lambda m: None
        )
        offers = comp.get("offers") or []
        print(f"  comparison took {time.monotonic()-t:.1f}s; status="
              f"{dc.summarize_offer_status(offers)}; {len(offers)} offer(s)")
        for o in offers:
            print(f"    [{o.get('source')}] vs={o.get('vs_installed')} "
                  f"cand={o.get('version')!r} {(o.get('title') or '')[:55]}")

    print("\n=== done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
