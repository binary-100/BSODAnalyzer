"""Verify driver check returns installed + catalog versions after catalog fixes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

ctx = dc.extend_system_ctx_for_catalog({})
name = "NVIDIA GeForce RTX 3070 Ti Laptop GPU"
print("Checking", name, "...")
comp = dc.build_device_driver_comparison(
    name,
    [],
    [],
    ctx,
    progress=lambda m: print(" ", m),
)
print("installed:", comp.get("installed_version"))
print("status:", dc.summarize_offer_status(comp.get("offers")))
for o in (comp.get("offers") or [])[:10]:
    print(
        f"  [{o.get('source')}] vs={o.get('vs_installed')} "
        f"inst={o.get('installed_version')} ver={o.get('version')!r} "
        f"{(o.get('title') or '')[:45]}"
    )
