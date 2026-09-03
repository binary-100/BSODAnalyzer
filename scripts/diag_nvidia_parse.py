import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

ok, body = dc._http_get("https://www.nvidia.com/Download/API/lookupValue/lookupValue/24E0")
print("ok", ok, "len", len(body) if ok else 0)
if not ok:
    print(body)
    raise SystemExit(1)
for pat in (
    r"psid['\"]?\s*[:=]\s*['\"]?(\d+)",
    r"pfid['\"]?\s*[:=]\s*['\"]?(\d+)",
    r"driverVersion['\"]?\s*[:=]\s*['\"]?([\d.]+)",
):
    m = re.findall(pat, body[:80000], re.I)
    if m:
        print(pat, m[:5])
vers = re.findall(r"(32\.\d+\.\d+\.\d+)", body)
print("32.x versions found:", sorted(set(vers))[-5:])
