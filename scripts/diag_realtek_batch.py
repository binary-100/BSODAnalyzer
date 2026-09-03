"""Validate that the Realtek MEDIA codec surfaces its newer MS offer in BATCH mode."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app_settings as app_set
import driver_catalog as dc
import bsod_analyzer as core


def main() -> int:
    s = app_set.load_settings()
    dc.configure_catalog(
        quick_check=bool(s.get("quick_check_mode")) and not app_set.is_full_install_mode(s),
        oem_session_cache=s.get("oem_session_cache"),
    )
    prof = core.gather_hardware_profile(progress_cb=None)
    sc = dict(prof.get("system_ctx") or {})
    bio = prof.get("bios_driver_info") or {}
    inv = core.device_inventory_for_matching(bio)
    pnp = sc.get("pnp_list") or []
    name = next(
        (d.get("name") for d in inv if "realtek audio" == (d.get("name") or "").strip().lower()),
        None,
    )
    print("device:", name)

    dctx = dc.get_device_context_for_name(name, pnp, inv, dc.extend_system_ctx_for_catalog(dict(sc)))
    dctx["_batch_driver_check"] = True
    dctx["_gui_driver_catalog"] = True
    dctx["_catalog_system_ctx"] = dc.extend_system_ctx_for_catalog(dict(sc))
    print("batch queries:", dc._catalog_search_queries_for_ctx(dctx))

    sc["_gui_driver_catalog"] = True
    t = time.monotonic()
    res = dc.build_multi_device_driver_comparison([name], pnp, inv, sc, progress=lambda m: None)
    print(f"batch comparison took {time.monotonic()-t:.1f}s")
    for d in res.get("devices") or []:
        print("STATUS", d.get("status"), "installed", d.get("installed_version"))
        for o in d.get("offers") or []:
            title = (o.get("title") or "")[:55]
            print(f"   [{o.get('source')}] {o.get('vs_installed')} cand={o.get('version')!r} {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
