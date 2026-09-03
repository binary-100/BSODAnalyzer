"""Probe NVIDIA AjaxDriverService psid/pfid for PCI DEV ids (build map data)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

# Maxwell + Pascal + selected RTX — canonical DEV ids (uppercase hex)
DEV_IDS = {
    # Maxwell (900 series) — target floor
    "13C0": "GTX 970",
    "13C2": "GTX 970",
    "13C3": "GTX 980M",
    "1401": "GTX 960",
    "1402": "GTX 950",
    "1406": "GTX 960",
    "1617": "GTX 980M",
    "1618": "GTX 970M",
    "17C2": "GTX Titan X",
    "17C8": "GTX 980",
    "17FD": "GTX 980M",
    # Pascal (already partially mapped)
    "1B80": "GTX 1080",
    "1C02": "GTX 1070",
    "1C60": "GTX 1060",
    # Polaris / Turing sample
    "1F02": "GTX 1650",
    "2206": "RTX 3080",
    "2484": "RTX 4070",
}

# psid candidates by generation (from NVIDIA download site series ids)
PSID_SERIES = {
    "100": "GeForce 900 Series",
    "101": "GeForce 10 Series",
    "129": "GeForce RTX 20/16 Series",
    "120": "GeForce RTX 40/50",
}


def ajax(psid: str, pfid: str, os_id: str = "135") -> dict | None:
    url = (
        "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/"
        f"AjaxDriverService.php?func=DriverManualLookup&psid={psid}&pfid={pfid}"
        f"&osID={os_id}&languageCode=1033&isWHQL=1&dch=1&sort1=0&numberOfResults=1"
    )
    ok, body = dc._http_get(url)
    if not ok or not body.strip():
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    ids = data.get("IDS") or []
    if not ids:
        return None
    return (ids[0] or {}).get("downloadInfo") or {}


def main() -> None:
    # Scan pfid range for psid 100 (900 series) and 101 (10 series)
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["100", "101"]
    for psid in targets:
        print(f"\n=== psid={psid} ({PSID_SERIES.get(psid, '?')}) ===")
        hits: list[tuple[str, str, str]] = []
        for pfid in range(780, 870):
            di = ajax(psid, str(pfid))
            if not di or not di.get("Version"):
                continue
            ver = di.get("Version", "")
            name = (di.get("NameLocalized") or di.get("Name") or "")[:50]
            hits.append((str(pfid), ver, name))
        # dedupe by version
        seen: set[str] = set()
        for pfid, ver, name in hits:
            key = f"{ver}|{name}"
            if key in seen:
                continue
            seen.add(key)
            print(f"  pfid={pfid:>4}  ver={ver:<8}  {name}")


if __name__ == "__main__":
    main()
