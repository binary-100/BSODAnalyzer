"""OEM brand alignment and reject filters (extracted from driver_catalog)."""

from __future__ import annotations

import re

from catalog_oem_live import _is_generic_oem_support_row
from catalog_scoring import (
    _ctx_is_bluetooth_radio_device,
    _ctx_is_wifi_radio_device,
    _looks_like_amd_chipset_package_version,
    _looks_like_intel_chipset_package_version,
    _looks_like_windows_inbox_driver_version,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


def _row_is_oem_sourced(row: dict) -> bool:
    """
    Whether the PC-maker OEM reject rules may judge this row.

    The `_reject_oem_*` helpers encode assumptions that only hold for vendor/OEM support
    catalogs — most importantly that a versioned package aimed at a non-integrated device
    is wrong. Windows Update and Microsoft Catalog rows are versioned for *every* device,
    so running those rules against them suppressed every WU offer for attached hardware
    (external monitor SoftwareComponent children, USB audio, peripherals, docks).

    An empty source stays permissive: OEM rows assembled without an explicit `source` are
    still filtered. Matches `_reject_realtek_oem_net_family_mismatch`.
    """
    src = (row.get("source") or "").strip().lower()
    return not src or src == "oem"


_STANDARD_PNP_MANUFACTURERS = frozenset({
    "microsoft",
    "(standard system devices)",
    "(standard usb hubs)",
    "(standard usb hub)",
    "(standard disk drives)",
    "(standard monitor types)",
    "(standard keyboards)",
    "(standard mice)",
    "(generic usb hub)",
    "standard sata ahci controller",
})

_PC_OEM_BRAND_KEYS = frozenset({
    "dell",
    "alienware",
    "hp",
    "hewlett",
    "lenovo",
    "thinkpad",
    "ideapad",
    "asus",
    "rog",
    "acer",
    "msi",
    "micro-star",
    "gigabyte",
    "aorus",
})

# Silicon / component vendors whose drivers PC OEMs redistribute on factory-integrated hardware.
_PLATFORM_SILICON_MANUFACTURER_HINTS = (
    "realtek",
    "intel",
    "amd",
    "advanced micro",
    "nvidia",
    "qualcomm",
    "mediatek",
    "killer",
    "broadcom",
    "marvell",
    "synaptics",
    "elan",
    "conexant",
    "cirrus",
    "idt",
    "sigma",
    "texas instruments",
    "wacom",
)

# Tokens that may appear in OEM catalog package titles (for device↔package brand alignment).
_CATALOG_PACKAGE_BRAND_TOKENS = (
    "realtek",
    "intel",
    "amd",
    "nvidia",
    "qualcomm",
    "mediatek",
    "killer",
    "broadcom",
    "marvell",
    "synaptics",
    "elan",
    "conexant",
    "cirrus",
    "dolby",
    "waves",
    "intelligo",
    "nahimic",
    "logitech",
    "razer",
    "corsair",
    "microsoft",
    "dell",
    "alienware",
    "hp",
    "lenovo",
    "asus",
    "realtek",
)
def _normalize_brand_token(value: str) -> str:
    s = (value or "").strip().lower()
    for suffix in (
        " inc.",
        " inc",
        " ltd.",
        " ltd",
        " corp.",
        " corp",
        " co.",
        " co",
        " technologies",
        " technology",
    ):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s


def _manufacturer_is_standard_or_ambiguous(mfr: str) -> bool:
    m = (mfr or "").strip().lower()
    if not m:
        return True
    if m in _STANDARD_PNP_MANUFACTURERS:
        return True
    return m.startswith("(standard")


def _manufacturer_is_pc_system_oem(mfr: str, ctx: dict) -> bool:
    m = _normalize_brand_token(mfr)
    if not m:
        return False
    for tag in _dc("_system_pc_oem_tags")(ctx):
        if tag == "dell" and ("dell" in m or "alienware" in m):
            return True
        if tag in m:
            return True
    return False


def _manufacturer_is_platform_silicon_partner(mfr: str) -> bool:
    m = _normalize_brand_token(mfr)
    if not m:
        return False
    return any(hint in m for hint in _PLATFORM_SILICON_MANUFACTURER_HINTS)


def _device_brand_identities(ctx: dict) -> set[str]:
    """Distinct brands Windows reports for this device (WMI + enrichment)."""
    brands: set[str] = set()
    mfr = (ctx.get("pnp_manufacturer") or "").strip()
    if mfr and not _manufacturer_is_standard_or_ambiguous(mfr):
        brands.add(_normalize_brand_token(mfr))
    vk = _normalize_brand_token(ctx.get("vendor_key") or "")
    if vk and len(vk) >= 2:
        brands.add(vk)
    label = _dc("_ctx_device_label")(ctx)
    if " — " in label:
        prefix = _normalize_brand_token(label.split(" — ", 1)[0])
        if prefix and not _manufacturer_is_standard_or_ambiguous(prefix):
            brands.add(prefix)
    return brands


def _package_brand_identities(title_l: str) -> set[str]:
    """Vendor names explicitly referenced in a catalog package title."""
    brands: set[str] = set()
    for token in _CATALOG_PACKAGE_BRAND_TOKENS:
        if token in title_l:
            brands.add(token)
    return brands


def _brand_identities_align(device_brands: set[str], package_brands: set[str]) -> bool:
    if not device_brands or not package_brands:
        return True
    for dev in device_brands:
        for pkg in package_brands:
            if dev == pkg or dev in pkg or pkg in dev:
                return True
    return False


def _device_on_integrated_bus(ctx: dict) -> bool:
    inst = (ctx.get("instance_id") or "").strip().upper()
    return inst.startswith(
        ("PCI\\", "ACPI\\", "ROOT\\", "HDAUDIO\\", "INTELAUDIO\\")
    )


def _pc_oem_catalog_may_target_device(ctx: dict) -> bool:
    """
    Whether this device's identity allows PC-maker OEM catalog packages at all.

    Rule: OEM catalog is for factory-integrated hardware (PCI/ACPI/on-board silicon)
    or devices whose WMI manufacturer is the same PC brand. External USB gear with
    its own manufacturer (iFi, Logitech, …) is out of scope — not a whitelist of
    brands, but a bus + manufacturer identity check.
    """
    vk = _normalize_brand_token(ctx.get("vendor_key") or "")
    label = _dc("_ctx_device_label")(ctx)
    if vk in _PC_OEM_BRAND_KEYS and vk in label:
        return True
    mfr = (ctx.get("pnp_manufacturer") or "").strip()
    if _manufacturer_is_standard_or_ambiguous(mfr):
        if _device_on_integrated_bus(ctx):
            return True
        brands = _device_brand_identities(ctx)
        if brands and any(
            _manufacturer_is_platform_silicon_partner(b) for b in brands
        ):
            return True
        if vk and _manufacturer_is_pc_system_oem(vk, ctx):
            return True
        if vk and _manufacturer_is_platform_silicon_partner(vk):
            return True
        return False
    if _manufacturer_is_pc_system_oem(mfr, ctx):
        return True
    if _manufacturer_is_platform_silicon_partner(mfr):
        return True
    if _device_on_integrated_bus(ctx):
        return True
    return False


def _reject_oem_package_brand_mismatch(row: dict, ctx: dict) -> str | None:
    """Package title names vendor A; device reports manufacturer B — reject."""
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    dev = _device_brand_identities(ctx)
    pkg = _package_brand_identities(title_l)
    if not dev or not pkg:
        return None
    if dev <= {"microsoft"}:
        return None
    if _brand_identities_align(dev, pkg):
        return None
    return "oem_package_brand_mismatch"


def _pnp_manufacturer_is_third_party(ctx: dict) -> bool:
    """True when the device is not eligible for PC-OEM catalog matching."""
    return not _pc_oem_catalog_may_target_device(ctx)


def _reject_oem_pc_maker_on_third_party_device(row: dict, ctx: dict) -> str | None:
    """
    Block PC-maker catalog packages on foreign / attached devices.

    Uses bus + WMI manufacturer identity, then package↔device brand alignment —
    not a hardcoded list of peripheral companies.
    """
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    mismatch = _reject_oem_package_brand_mismatch(row, ctx)
    if mismatch:
        return mismatch
    if _pc_oem_catalog_may_target_device(ctx):
        return None
    brands = _device_brand_identities(ctx) - {"microsoft"}
    if not brands:
        return None
    title_l = (row.get("title") or "").lower()
    if _is_generic_oem_support_row(row):
        return "oem_generic_support_on_third_party"
    if (row.get("version") or "").strip():
        return "oem_pc_maker_on_third_party_device"
    if any(tag in title_l for tag in ("dell", "alienware", "hp ", "lenovo", "support —")):
        return "oem_pc_maker_on_third_party_device"
    return None


def _reject_oem_amd_chipset_on_component_inf(row: dict, ctx: dict) -> str | None:
    """Dell/AMD 'Chipset Driver' OEM rows must not compare suite version to GPIO/I2C INF versions."""
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    if "chipset" not in title_l or "amd" not in title_l:
        return None
    if not _dc("_device_is_amd_chipset_plumbing")(ctx):
        return None
    inst = (ctx.get("primary_version") or "").strip()
    cand = (row.get("version") or "").strip()
    if not inst or not cand:
        return None
    if _looks_like_amd_chipset_package_version(inst):
        return None
    if _looks_like_amd_chipset_package_version(cand) and not _looks_like_amd_chipset_package_version(
        inst
    ):
        return "oem_chipset_package_on_component_inf"
    if not _looks_like_amd_chipset_package_version(inst) and any(
        phrase in title_l for phrase in ("chipset driver", "chipset drivers")
    ):
        return "oem_chipset_package_on_component_inf"
    return None


def _reject_oem_intel_chipset_on_component_inf(row: dict, ctx: dict) -> str | None:
    """OEM Intel Chipset INF rows must not compare suite version to Serial IO / ME INF versions."""
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    if "chipset" not in title_l or "intel" not in title_l:
        return None
    if not _dc("_device_is_intel_chipset_plumbing")(ctx):
        return None
    inst = (ctx.get("primary_version") or "").strip()
    cand = (row.get("version") or "").strip()
    if not inst or not cand:
        return None
    if _looks_like_intel_chipset_package_version(inst):
        return None
    if _looks_like_intel_chipset_package_version(cand) and not _looks_like_intel_chipset_package_version(
        inst
    ):
        return "oem_chipset_package_on_component_inf"
    if not _looks_like_intel_chipset_package_version(inst) and any(
        phrase in title_l for phrase in ("chipset driver", "chipset drivers", "chipset inf")
    ):
        return "oem_chipset_package_on_component_inf"
    return None


def _reject_oem_audio_vendor_mismatch(row: dict, ctx: dict) -> str | None:
    """Block Realtek/Dolby OEM audio rows on NVIDIA/AMD audio devices (and vice versa)."""
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    label = _dc("_ctx_device_label")(ctx)
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    pc_oem_audio_vendors = ("realtek", "dolby", "waves", "sound blaster", "nahimic", "intelligo")
    if _pnp_manufacturer_is_third_party(ctx) and (
        pnp in ("media", "audio", "audioendpoint") or "audio" in label
    ):
        if any(v in title_l for v in pc_oem_audio_vendors):
            return "oem_audio_vendor_mismatch"
    if not (
        pnp in ("media", "audio", "audioendpoint", "system")
        or "audio" in label
        or _dc("_nvidia_is_audio_component")(ctx)
        or _dc("_device_is_amd_audio")(ctx)
    ):
        return None
    third_party_audio = ("realtek", "dolby", "waves", "sound blaster", "nahimic")
    if _dc("_nvidia_is_audio_component")(ctx):
        if any(v in title_l for v in third_party_audio) and "nvidia" not in title_l:
            return "oem_audio_vendor_mismatch"
    elif _dc("_device_is_amd_audio")(ctx) or (
        _dc("_ctx_is_amd_device")(ctx)
        and "coprocessor" in label
        and pnp == "system"
    ):
        if any(v in title_l for v in third_party_audio) and "amd" not in title_l:
            return "oem_audio_vendor_mismatch"
    elif vk == "realtek" or "realtek" in label:
        if "nvidia" in title_l and "realtek" not in title_l:
            return "oem_audio_vendor_mismatch"
        if any(k in title_l for k in ("ethernet", "gbe", "2.5g", "pcie ethernet")):
            return "oem_audio_vendor_mismatch"
    return None


def _reject_oem_application_on_driver_device(row: dict, ctx: dict) -> str | None:
    """Dell lists companion apps separately — not kernel driver updates for audio/NIC/GPU rows."""
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    if " application" not in title_l and " console application" not in title_l:
        return None
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _dc("_ctx_device_label")(ctx)
    if pnp == "softwarecomponent" or any(k in label for k in ("application", " console")):
        if "asio" in label.lower() and "console application" in title_l:
            return "oem_application_role_mismatch"
        if "universal service" in label.lower() and "console application" in title_l:
            return "oem_application_role_mismatch"
        return None
    if pnp in ("media", "audio", "audioendpoint", "net", "display", "bluetooth"):
        return "oem_application_on_driver_device"
    return None


_OEM_PC_MAKER_UPDATE_APP_HINTS = (
    "dell update",
    "alienware update",
    "supportassist os recovery plugin",
    "supportassist",
    "command center",
)

_DELL_OEM_INTERNAL_DRIVER_CLASSES = (
    "dellutils",
    "dellinstrumentation",
)


def _reject_oem_pc_maker_update_application(row: dict, ctx: dict) -> str | None:
    """
    Dell/Alienware Update, SupportAssist, and Command Center suite installers
    are apps — not kernel driver updates for arbitrary factory nodes
    (DBUtilDrv2, DellInstrumentation, …).
    """
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    if not any(h in title_l for h in _OEM_PC_MAKER_UPDATE_APP_HINTS):
        if not (
            " update/" in title_l
            or " update application" in title_l
            or " universal application" in title_l
        ):
            return None
    label = _dc("_ctx_device_label")(ctx).lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    if any(
        k in label
        for k in ("dell update", "alienware update", "supportassist", "dell supportassist")
    ):
        return None
    if pnp in _DELL_OEM_INTERNAL_DRIVER_CLASSES:
        return "oem_update_app_on_dell_internal_driver"
    return "oem_update_app_mismatch"


_OEM_AIRPLANE_MODE_HINTS = ("airplane mode", "air plane mode")


def _reject_oem_airplane_mode_mismatch(row: dict, ctx: dict) -> str | None:
    """Airplane Mode Switch drivers belong on radio/switch nodes — not monitors or unrelated PnP."""
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    if not any(h in title_l for h in _OEM_AIRPLANE_MODE_HINTS):
        return None
    label = _dc("_ctx_device_label")(ctx).lower()
    if any(h in label for h in _OEM_AIRPLANE_MODE_HINTS):
        return None
    pnp = (ctx.get("pnp_class") or "").lower()
    if pnp == "radio":
        return None
    return "oem_airplane_mode_wrong_device"


def _reject_oem_realtek_hd_on_inbox_hd_controller(row: dict, ctx: dict) -> str | None:
    """
    Realtek HD audio OEM packages target the codec stack — not the Microsoft inbox
    High Definition Audio Controller bus driver (10.0.x).
    """
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    if "realtek" not in title_l or "high definition audio" not in title_l:
        return None
    label = _dc("_ctx_device_label")(ctx).lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    inst = (ctx.get("primary_version") or "").strip()
    if "high definition audio controller" not in label:
        return None
    if not _looks_like_windows_inbox_driver_version(inst):
        return None
    if pnp == "system" or (ctx.get("vendor_key") or "").lower() in ("", "microsoft"):
        return "oem_realtek_hd_on_inbox_hd_controller"
    return None

_OEM_RADIO_CHIP_HINTS = (
    "mediatek mt",
    "qualcomm wcn",
    "intel ax",
    "intel wi-fi",
    "killer ",
    "realtek rtl",
    "broadcom ",
)

# Device labels like "MediaTek Wi-Fi 6 MT7921…" omit the literal "mediatek mt" substring.
_OEM_RADIO_CHIP_LABEL_TOKENS = (
    "mt7921",
    "mt7922",
    "mt7925",
    "mt7920",
    "mt7902",
    "mt7630",
    "mt7612",
    "mt792",
    "rz616",
    "rz608",
    "ax201",
    "ax210",
    "ax200",
    "ax1650",
    "ax411",
    "qca",
    "wcn",
    "ar9",
    "802.11ax",
)


def _ctx_label_has_radio_chip_hint(ctx: dict) -> bool:
    """True when the device label/HWID identifies a specific radio chip (not generic MS stack)."""
    label = _dc("_ctx_device_label")(ctx).lower()
    if any(h in label for h in _OEM_RADIO_CHIP_HINTS):
        return True
    if any(tok in label for tok in _OEM_RADIO_CHIP_LABEL_TOKENS):
        return True
    vk = (ctx.get("vendor_key") or "").lower()
    if vk in ("mediatek", "qualcomm", "killer", "broadcom", "intel") and any(
        k in label for k in ("wi-fi", "wifi", "wireless", "wlan", "bluetooth", "802.11")
    ):
        return True
    inst = (ctx.get("instance_id") or "").upper()
    if re.search(r"DEV_(7961|7922|7920|7925|7902|0616|0608|7630|7612)\b", inst):
        return True
    return False


def _oem_package_title_is_wifi(title_l: str) -> bool:
    return any(
        k in title_l
        for k in ("wi-fi", "wifi", "wireless lan", " wlan", "802.11", "wireless uwd")
    )


def _oem_package_title_is_bluetooth(title_l: str) -> bool:
    return "bluetooth" in title_l






def _reject_oem_radio_wifi_bt_cross_mismatch(title_l: str, ctx: dict) -> str | None:
    """Wi-Fi OEM packages must not attach to Bluetooth devices (and vice versa)."""
    if _oem_package_title_is_wifi(title_l) and _ctx_is_bluetooth_radio_device(ctx):
        return "oem_radio_wifi_bt_mismatch"
    if _oem_package_title_is_bluetooth(title_l) and _ctx_is_wifi_radio_device(ctx):
        return "oem_radio_wifi_bt_mismatch"
    return None






def _reject_oem_radio_chip_mismatch(row: dict, ctx: dict) -> str | None:
    """Generic Microsoft BT/net stack rows must not inherit unrelated Wi-Fi/BT OEM packages."""
    if _dc("_catalog_row_hwid_matches_ctx")(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    cross = _reject_oem_radio_wifi_bt_cross_mismatch(title_l, ctx)
    if cross:
        return cross
    if not any(h in title_l for h in _OEM_RADIO_CHIP_HINTS):
        return None
    label = _dc("_ctx_device_label")(ctx)
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    label_has_chip = _ctx_label_has_radio_chip_hint(ctx)
    title_has_chip = any(h in title_l for h in _OEM_RADIO_CHIP_HINTS)
    if label_has_chip:
        return None
    generic_ms = vk in ("", "microsoft") or label.startswith("microsoft") or "microsoft —" in label
    if not generic_ms and pnp not in ("net", "bluetooth"):
        return None
    if pnp in ("net", "bluetooth") or "bluetooth" in label or "miniport" in label:
        if title_has_chip:
            return "oem_radio_chip_mismatch"
    return None
