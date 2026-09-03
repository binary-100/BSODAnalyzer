import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

ok, html = dc._http_get("https://www.nvidia.com/en-us/geforce/drivers/")
for m in re.finditer(r"var\s+(\w+)\s*=\s*(\{[\s\S]*?\});", html):
    name, blob = m.group(1), m.group(2)
    if "driver" in name.lower() or "download" in name.lower():
        print("var", name, blob[:200])
for m in re.finditer(r'"driverVersion"\s*:\s*"([^"]+)"', html):
    print("driverVersion", m.group(1))
for m in re.finditer(r'"version"\s*:\s*"([\d.]+)"', html):
    print("version", m.group(1))
    if m.start() > 500000:
        break
