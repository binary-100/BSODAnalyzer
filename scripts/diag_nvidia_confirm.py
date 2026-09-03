import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

url = "https://www.nvidia.com/content/DriverDownloads/confirmation.php?lang=en-us&ctk=0&confirm=yes&devid=0x24E0"
ok, html = dc._http_get(url)
print("ok", ok, len(html))
if not ok:
    print(html)
    raise SystemExit(1)
for pat in (
    r"driverVersion['\"]?\s*[:=]\s*['\"]?([\d.]+)",
    r"Version\s*:\s*([\d.]+)",
    r"(\d{3,5}\.\d{2,5}\.\d{2,5}\.\d{4,5})",
    r"(\d+\.\d+\.\d+\.\d+)",
):
    found = re.findall(pat, html)
    if found:
        uniq = sorted(set(found), key=lambda v: dc.parse_driver_version(v) or ())
        print(pat[:40], "count", len(uniq), "max", uniq[-3:])
# __NEXT_DATA__ style
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>', html, re.S)
if m:
    print("has __NEXT_DATA__", len(m.group(1)))
