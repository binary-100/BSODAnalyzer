import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

ok, html = dc._http_get("https://www.nvidia.com/en-us/geforce/drivers/")
text = html if ok else ""
for needle in ("Game Ready", "Studio Driver", "32.0.", "581.", "572.", "WHQL", "download"):
    idx = text.lower().find(needle.lower())
    if idx >= 0:
        print(needle, "->", repr(text[idx : idx + 120]))

# JSON-LD
for m in re.finditer(r'<script type="application/ld\+json">(.+?)</script>', text, re.S):
    blob = m.group(1)[:500]
    if "driver" in blob.lower() or "version" in blob.lower():
        print("ld+json snippet", blob[:200])
