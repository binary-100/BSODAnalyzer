"""Parse AMD Chipset Software installer metadata (Info.xml + DevID.xml)."""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TAG_FRIENDLY = {
    "/SETSMBUS": "AMD SMBUS Driver",
    "/SETPCI": "AMD PCI Device Driver",
    "/SETI2C": "AMD I2C Driver",
    "/SETPSP": "AMD PSP Driver",
    "/SETGPIO2": "AMD GPIO2 Driver",
    "/SETUART": "AMD UART Driver",
    "/SETGPIO3": "PT GPIO Driver (Promontory)",
    "/SETSFHI2C": "AMD SFH I2C Driver",
    "/SETSFH1.1": "AMD SFH1.1 Driver",
    "/SETSFHDRVR": "AMD SFH Driver",
    "/SETUPEP": "AMD MicroPEP Driver",
    "/SETIOV_WT": "AMD IOV Driver (IOMMU)",
    "/SETAS4ACPI": "AMD AS4 ACPI Driver",
    "/SETUSBCNTRL": "AMD USB Controller",
    "/SETUSBCNTRL_HD": "AMD USB Controller (Hudson)",
    "/SETUSBCNTRL_PT": "AMD USB Controller (Promontory)",
    "/SETSATA": "AMD SATA Driver",
    "/SETFILTERUSB": "AMD USB Filter Driver",
    "/SETCIR": "AMD CIR Driver",
    "/SETEMBCCP": "AMD Embedded CCP",
    "/SETUSB31": "AMD USB 3.1 Driver",
    "/SETWBD": "AMD Wireless Button Driver",
    "/SETSERIAL": "AMD Serial Driver",
    "/SETEMBFLASH": "AMD Embedded Flash",
    "/SETPPM": "AMD Ryzen Power Plan",
    "/SETUSB4CM": "AMD USB4 CM Driver",
    "/SETCVAC": "AMD 3D V-Cache Performance Optimizer",
    "/SETMAIL": "AMD AMS Mailbox Driver",
    "/SETS0I3": "AMD S0i3 Filter Driver",
    "/SETINTERFACE": "AMD Interface Driver",
    "/SETOEMPF": "AMD Provisioning for OEM",
    "/SETNAIPMF300": "AMD PMF Ryzen AI 300 Series",
    "/SETTAIPMF300": "AMD PMF Ryzen AI 300 Series-2",
    "/SETAIPMFMAX300": "AMD PMF Ryzen AI MAX 300 Series",
    "/SETAPPCOMPATDB": "AMD Application Compatibility Database",
    "/SETMSFT1": "AMD NULL Driver (Microsoft Pluton 1)",
    "/SETMSFT2": "AMD NULL Driver (Microsoft Pluton 2)",
    "/SETHSMP": "AMD HSMP Driver",
    "/SETXGBE": "AMD 10GbE Driver",
}


def parse_info(path: Path, os_filter: str = "Windows 11") -> list[dict]:
    root = ET.parse(path).getroot()
    rows: list[dict] = []
    for p in root.findall("Product"):
        os_name = (p.findtext("OS") or "").strip()
        if os_filter and os_filter not in os_name:
            continue
        rows.append(
            {
                "name": (p.findtext("Name") or "").strip(),
                "version": (p.findtext("Version") or "").strip(),
                "installer": (p.findtext("Installer") or "").strip(),
            }
        )
    return rows


def parse_devid(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    rows: list[dict] = []
    for p in root.findall("Product"):
        tag = (p.findtext("Tag") or "").strip()
        devids = [x.strip() for x in (p.findtext("DevID") or "").split(",") if x.strip()]
        rows.append({"tag": tag, "devids": devids, "label": TAG_FRIENDLY.get(tag, tag)})
    return rows


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
    products = parse_info(base / "Info.xml", "Windows 11")
    tags = parse_devid(base / "DevID.xml")

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
