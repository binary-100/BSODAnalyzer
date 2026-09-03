"""Live end-to-end validation of the driver catalog scan (GUI batch mode).

Confirms the fixes: (1) HWID queries no longer waste time, (2) the scan completes
without stalling, (3) 'Realtek Audio' surfaces the newer Microsoft offer.

    py -3 scripts/diag_full_scan_timing.py [max_devices]
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


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    settings = app_set.load_settings()
    dc.configure_catalog(
        quick_check=bool(settings.get("quick_check_mode"))
        and not app_set.is_full_install_mode(settings),
        oem_session_cache=settings.get("oem_session_cache"),
    )

    t0 = time.monotonic()
    prof = core.gather_hardware_profile(progress_cb=None)
    system_ctx = dict(prof.get("system_ctx") or {})
    bio = prof.get("bios_driver_info") or {}
    inv = core.device_inventory_for_matching(bio)
    pnp = system_ctx.get("pnp_list") or []
    print(f"hardware scan: {time.monotonic()-t0:.1f}s  inv={len(inv)} pnp={len(pnp)}")

    names = []
    seen = set()
    for d in inv:
        n = (d.get("name") or "").strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            names.append(n)
    if limit:
        names = names[:limit]
    print(f"scanning {len(names)} device(s) in GUI-batch mode\n")

    system_ctx["_gui_driver_catalog"] = True

    start = time.monotonic()
    last = [start]
    slow = []

    def prog(msg: str) -> None:
        now = time.monotonic()
        dt = now - last[0]
        last[0] = now
        if dt > 8.0:
            slow.append((dt, msg))
        print(f"[{now-start:7.1f}s (+{dt:5.1f})] {msg[:100]}")

    result = dc.build_multi_device_driver_comparison(
        names, pnp, inv, system_ctx, progress=prog
    )
    total = time.monotonic() - start
    devices = result.get("devices") or []
    print(f"\n=== scan complete in {total:.1f}s; "
          f"{len(devices)} device(s); checked={result.get('checked_count')} "
          f"updates={result.get('update_count')} ===")

    if slow:
        print("\nslowest progress gaps (>8s):")
        for dt, msg in sorted(slow, reverse=True)[:10]:
            print(f"  +{dt:6.1f}s  {msg[:80]}")

    for d in devices:
        n = (d.get("device_name") or "")
        if "realtek audio" == n.lower():
            print(f"\nREALTEK AUDIO -> status={d.get('status')} "
                  f"installed={d.get('installed_version')}")
            for o in d.get("offers") or []:
                print(f"    [{o.get('source')}] {o.get('vs_installed')} "
                      f"cand={o.get('version')!r} {(o.get('title') or '')[:55]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
