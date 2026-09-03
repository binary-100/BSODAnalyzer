"""Build bundled data/nvidia_gpu_psid_pfid.json from NVIDIA getMenuArrays JSON API."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gpu_vendor_maps as gvm

SERIES = gvm._NVIDIA_SERIES_PSIDS


def main() -> None:
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for psid, series_label in SERIES:
        products = gvm._fetch_nvidia_series_products(psid)
        for prod in products:
            key = (prod["psid"], prod["pfid"], prod["product"])
            if key in seen:
                continue
            seen.add(key)
            prod = dict(prod)
            prod["series"] = series_label
            rows.append(prod)
    out_path = Path(__file__).resolve().parents[1] / "data" / "nvidia_gpu_psid_pfid.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} NVIDIA products -> {out_path}")
    for row in rows[:15]:
        print(f"  psid={row['psid']} pfid={row['pfid']}  {row['product']}")


if __name__ == "__main__":
    main()
