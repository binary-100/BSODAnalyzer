"""Simulate 6.0.8 MSCatalog rejections against a prior export."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import driver_catalog as dc


def main() -> None:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    print("Simulated rejections on prior newer rows:")
    for d in sorted(data["drivers"], key=lambda x: x["device_name"]):
        if d.get("status") != "newer":
            continue
        ctx = {
            "vendor_key": "",
            "pnp_class": (d.get("device_class") or "").lower(),
            "device_label": d["device_name"],
            "target_device_name": d["device_name"],
            "instance_id": "",
        }
        name_l = d["device_name"].lower()
        if "amd" in name_l:
            ctx["vendor_key"] = "amd"
        if "nvidia" in name_l:
            ctx["vendor_key"] = "nvidia"
        kept: list[str] = []
        rejected: list[tuple[str, str]] = []
        for o in d.get("offers") or []:
            if o.get("vs_installed") != "newer":
                continue
            row = {"title": o.get("title") or ""}
            reason = dc._reject_mscatalog_row_for_ctx(row, ctx, d["device_name"])
            title = (o.get("title") or "")[:55]
            if reason:
                rejected.append((title, reason))
            else:
                kept.append(title)
        print(f"\n{d['device_name'][:52]}")
        print("  KEEP:", kept or "(none — would drop from newer)")
        for title, reason in rejected:
            print(f"  REJECT ({reason}): {title}")


if __name__ == "__main__":
    main()
