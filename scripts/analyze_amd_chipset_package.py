"""Parse AMD Chipset Software installer metadata (Info.xml + DevID.xml)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from amd_chipset_manifest import (  # noqa: E402
    TAG_FRIENDLY,
    parse_devid_tags,
    parse_info_products,
)
import re


def scan_exe_strings(path: Path) -> tuple[list[str], list[str]]:
    data = path.read_bytes()
    infs = sorted(set(m.decode("ascii", "ignore") for m in re.findall(rb"[\w\\./-]{3,100}\.inf", data, re.I)))
    cabs = sorted(set(m.decode("ascii", "ignore") for m in re.findall(rb"[\w\\./-]{3,100}\.cab", data, re.I)))
    return infs, cabs


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"c:\Users\binar\OneDrive\Desktop\BSODAnalyzer\_tmp_chipset_full\Qt_Dependencies"
    )
    nested = base.parent / "AMD_Chipset_Drivers.exe"
    products = parse_info_products(base / "Info.xml", "Windows 11")
    tags = parse_devid_tags(base / "DevID.xml")

    print(f"Win11 component packages: {len(products)}")
    for row in products:
        print(f"  {row['version']:>12}  {row['name']}")

    print(f"\nDevID install groups: {len(tags)}")
    for t in tags:
        sample = ", ".join(t["devids"][:4])
        extra = len(t["devids"]) - 4
        suffix = f" (+{extra} more)" if extra > 0 else ""
        print(f"  {t['tag']:18}  {t['label']}  [{sample}{suffix}]")

    if nested.is_file():
        infs, cabs = scan_exe_strings(nested)
        print(f"\nNested exe: {nested.name} ({nested.stat().st_size} bytes)")
        print(f"  INF string refs: {len(infs)}")
        for s in infs[:30]:
            print(f"    {s}")
        if len(infs) > 30:
            print(f"    ... +{len(infs) - 30} more")
        print(f"  CAB string refs: {len(cabs)}")
        for s in cabs[:15]:
            print(f"    {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
