"""AMD Chipset Software installer metadata (Info.xml / DevID.xml)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from bundle_verification import component_label_from_text

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


def parse_info_products(
    info_xml: str | bytes | Path,
    *,
    os_filter: str = "Windows 11",
) -> list[dict]:
    """Parse AMD Chipset Software Info.xml product rows."""
    if isinstance(info_xml, Path):
        root = ET.parse(info_xml).getroot()
    elif isinstance(info_xml, bytes):
        root = ET.fromstring(info_xml)
    else:
        root = ET.fromstring(str(info_xml))
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


def amd_info_products_to_bundle_components(products: list[dict]) -> list[dict]:
    """Convert Info.xml products to normalized bundle component rows."""
    out: list[dict] = []
    seen: set[str] = set()
    for row in products or []:
        name = (row.get("name") or "").strip()
        ver = (row.get("version") or "").strip()
        if not name or not ver:
            continue
        label = component_label_from_text(name)
        if label == "Other":
            continue
        if label in seen:
            continue
        seen.add(label)
        out.append({"label": label, "device_name": name, "version": ver})
    return out


def parse_devid_tags(devid_xml: str | bytes | Path) -> list[dict]:
    if isinstance(devid_xml, Path):
        root = ET.parse(devid_xml).getroot()
    elif isinstance(devid_xml, bytes):
        root = ET.fromstring(devid_xml)
    else:
        root = ET.fromstring(str(devid_xml))
    rows: list[dict] = []
    for p in root.findall("Product"):
        tag = (p.findtext("Tag") or "").strip()
        devids = [x.strip() for x in (p.findtext("DevID") or "").split(",") if x.strip()]
        rows.append(
            {
                "tag": tag,
                "devids": devids,
                "label": TAG_FRIENDLY.get(tag, tag),
            }
        )
    return rows
