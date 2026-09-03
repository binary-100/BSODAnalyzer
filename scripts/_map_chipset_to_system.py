"""Map AMD Chipset Software bundle components to this machine's installed drivers."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "_tmp_chipset_full" / "Qt_Dependencies"

# Component name keywords -> Info.xml product name fragments
COMPONENT_KEYWORDS = {
    "gpio": "GPIO",
    "i2c": "I2C",
    "uart": "UART",
    "smbus": "SMBUS",
    "psp": "PSP",
    "pci device": "PCI Device",
    "iommu": "IOV",
    "iov": "IOV",
    "micro pep": "MicroPEP",
    "micropep": "MicroPEP",
    "interface": "Interface",
    "provisioning package": "PPM Provisioning",
    "provisioning for oem": "Provisioning for OEM",
    "sensor fusion": "SFH Driver",
    "sfh": "SFH",
    "wireless button": "Wireless Button",
    "application compatibility": "Application Compatibility",
    "mailbox": "AMS Mailbox",
    "s0i3": "S0i3",
    "v-cache": "V-Cache",
    "hsmp": "HSMP",
    "pluton": "Pluton",
    "pmf": "PMF",
    "usb 3.1": "USB 3.1",
    "usb filter": "USB Filter",
    "usb4": "USB4",
    "sata": "SATA",
    "cir": "CIR",
    "power plan": "Ryzen Power Plan",
    "10gbe": "10GbE",
}


def load_products(os_filter: str) -> dict[str, str]:
    root = ET.parse(EXTRACT / "Info.xml").getroot()
    out: dict[str, str] = {}
    for p in root.findall("Product"):
        os_name = (p.findtext("OS") or "").strip()
        if os_filter not in os_name:
            continue
        name = (p.findtext("Name") or "").strip()
        ver = (p.findtext("Version") or "").strip()
        out[name.lower()] = ver
    return out


def match_bundle_version(device_name: str, products: dict[str, str]) -> tuple[str, str]:
    blob = device_name.lower()
    for kw, frag in COMPONENT_KEYWORDS.items():
        if kw in blob:
            for pname, ver in products.items():
                if frag.lower() in pname:
                    return ver, frag
    return "", ""


def suite_version() -> str:
    try:
        import winreg
    except ImportError:
        return "?"
    for hive, sub in (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ):
        try:
            with winreg.OpenKey(hive, sub) as parent:
                for i in range(winreg.QueryInfoKey(parent)[0]):
                    try:
                        with winreg.OpenKey(parent, winreg.EnumKey(parent, i)) as sk:
                            name = str(winreg.QueryValueEx(sk, "DisplayName")[0] or "")
                            ver = str(winreg.QueryValueEx(sk, "DisplayVersion")[0] or "")
                            if re.search(r"amd.*chipset|chipset.*amd", name, re.I):
                                return ver
                    except OSError:
                        continue
        except OSError:
            continue
    return "?"


def query_devices() -> list[dict]:
    ps = r"""
$ErrorActionPreference='SilentlyContinue'
Get-CimInstance Win32_PnPSignedDriver |
  Where-Object {
    $_.DeviceName -match 'AMD' -and (
      $_.DeviceClass -eq 'System' -or
      $_.DeviceName -match 'GPIO|I2C|SMBUS|PSP|Provisioning|Micro|Interface|USB 3|USB4|IOV|IOMMU|UART|Sensor|PMF|Mailbox|Filter|PCI Device|Platform Security|CoProcessor|Software Component|Power|Pluton|HSMP|V-Cache|CIR|Wireless Button|Application Compatibility'
    )
  } |
  Select-Object DeviceName, DriverVersion, DeviceClass, InfName |
  Sort-Object DeviceName |
  ConvertTo-Json -Compress
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(r.stderr or "WMI query failed")
    data = json.loads(r.stdout)
    return [data] if isinstance(data, dict) else data


def main() -> int:
    products = load_products("Windows 11")
    suite = suite_version()
    print(f"AMD Chipset suite (Add/Remove Programs): {suite}")
    print(f"Bundle lists {len(products)} Win11 component packages in Info.xml\n")

    devices = query_devices()
    in_bundle: list[tuple] = []
    unknown: list[tuple] = []
    for d in devices:
        name = (d.get("DeviceName") or "").strip()
        win_ver = (d.get("DriverVersion") or "?").strip()
        cls = (d.get("DeviceClass") or "").strip()
        comp_ver, frag = match_bundle_version(name, products)
        row = (name, win_ver, cls, comp_ver, frag)
        if comp_ver:
            in_bundle.append(row)
        else:
            unknown.append(row)

    print(f"=== In chipset bundle ({len(in_bundle)}) ===")
    for name, win_ver, cls, comp_ver, frag in in_bundle:
        flag = " *" if win_ver != comp_ver else ""
        print(f"  Win {win_ver:>14}  Bundle {comp_ver:>12} ({frag}){flag}")
        print(f"    [{cls}] {name}")

    print(f"\n=== AMD system devices NOT mapped to bundle ({len(unknown)}) ===")
    for name, win_ver, cls, _c, _f in unknown:
        print(f"  Win {win_ver:>14}  [{cls}] {name}")

    not_in_bundle = [
        "AMD Radeon / Display GPU (Adrenalin — separate installer)",
        "AMD Audio / Streaming Audio / HDMI Audio",
        "AMD SoftwareComponent (GPU companion metadata)",
        "Third-party NIC/Wi-Fi/Bluetooth",
        "Storage/NVMe (unless AMD SATA controller present)",
        "Monitor/DisplayPort OEM panels",
    ]
    print("\n=== Never in AMD Chipset Software (by design) ===")
    for line in not_in_bundle:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
