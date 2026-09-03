import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

# From nvidia.com/en-us/geforce/drivers/ popularDownloadsDriverSettingsGrd_lcl
for psid, pfid in (("120", "942"), ("129", "1113"), ("129", "948")):
    url = (
        f"https://www.nvidia.com/Download/processDriver.aspx?"
        f"psid={psid}&pfid={pfid}&rpf=1&osid=135&lid=1&lang=en-us&ctk=0"
    )
    ok, body = dc._http_get(url)
    print(psid, pfid, ok, len(body) if ok else body[:80])
    if ok:
        for pat in (
            r"(\d+\.\d+\.\d+\.\d+)",
            r"Version\s*:\s*([\d.]+)",
            r"driverVersion\s*=\s*['\"]([\d.]+)",
        ):
            found = re.findall(pat, body)
            good = [v for v in found if v.startswith(("32.", "31.", "56."))]
            if good:
                print("  versions", good[:5])
