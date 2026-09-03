import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

model = "Alienware m17 R5 AMD"
slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
print("slug guess", slug)
for code in (slug, "alienware-m17-r5-amd-laptop", "alienware-m17-r5", "m17-r5-amd"):
    api = "https://www.dell.com/support/driver/en-us/ips/api/driverlist/fetchdriversbyproduct"
    params = urllib.parse.urlencode(
        {
            "productcode": code,
            "oscode": "WT64A",
            "initialload": "true",
            "_": str(int(time.time() * 1000)),
        }
    )
    url = f"{api}?{params}"
    ok, body = dc._http_get(
        url,
        headers={"Accept": "application/json", "x-requested-with": "XMLHttpRequest"},
    )
    print(code, "ok", ok, "len", len(body) if ok else body[:80])
    if ok and body.strip().startswith("{"):
        data = json.loads(body)
        lst = data.get("DriverListData") or []
        print("  drivers", len(lst))
        for d in lst[:3]:
            if "video" in (d.get("DriverName") or "").lower() or "nvidia" in (d.get("DriverName") or "").lower():
                print("   ", d.get("DriverName"), d.get("DellVer"))
