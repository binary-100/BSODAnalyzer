import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

pages = [
    "https://www.nvidia.com/en-us/geforce/drivers/",
    "https://www.nvidia.com/en-us/drivers/",
]
for url in pages:
    ok, html = dc._http_get(url)
    print(url, ok, len(html) if ok else html)
    if ok:
        for pat in (
            r"Game Ready Driver\s*(\d+\.\d+)",
            r"(\d{3}\.\d{2})",
            r"driverVersion[\"']:\s*[\"']([\d.]+)",
            r"(\d+\.\d+\.\d+\.\d+)",
        ):
            found = re.findall(pat, html[:120000], re.I)
            if found:
                print(" ", pat[:35], sorted(set(found))[-5:])
