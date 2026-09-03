"""Catalog row rejection, HWID matching, and MSCatalog row filters (extracted from driver_catalog)."""

from __future__ import annotations

import re

import driver_version_identity as dvi
from catalog_oem_filters import (
    _row_is_oem_sourced,
    _reject_oem_airplane_mode_mismatch,
    _reject_oem_amd_chipset_on_component_inf,
    _reject_oem_application_on_driver_device,
    _reject_oem_audio_vendor_mismatch,
    _reject_oem_intel_chipset_on_component_inf,
    _reject_oem_pc_maker_on_third_party_device,
    _reject_oem_pc_maker_update_application,
    _reject_oem_radio_chip_mismatch,
    _reject_oem_realtek_hd_on_inbox_hd_controller,
)
from catalog_scoring import (
    compare_versions,
    parse_driver_version,
    _realtek_nic_same_oem_family,
    _realtek_nic_version_tail,
    _looks_like_amd_adrenalin_version,
    _looks_like_mediatek_uwd_version,
    _looks_like_realtek_nic_driver_version,
    _looks_like_realtek_wdm_version,
    _realtek_net_version_major,
)
from catalog_device_context import (
    _DRIVER_SCAN_EXCLUDED_PNP_CLASSES,
    _ctx_device_label,
    _ctx_is_amd_device,
    _device_is_amd_chipset_plumbing,
    _device_is_amd_media,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


# _DRIVER_SCAN_EXCLUDED_PNP_CLASSES lives in catalog_device_context (imported above)

# Generic Windows PnP names that produce false MSCatalog matches without HWID proof.
_GENERIC_PNP_DEVICE_LABELS = frozenset({
    "device firmware",
    "audio endpoint",
    "high precision event timer",
    "system timer",
    "programmable interrupt controller",
    "composite bus enumerator",
    "um bus root bus enumerator",
    "microsoft gs wavetable synth",
    "microsoft streaming service proxy",
    "microsoft bluetooth enumerator",
    "microsoft device association root enumerator",
})
# Title substring → required device vendor_key for branded SoftwareComponent WU rows.
_SWC_BRANDED_VENDOR_MARKERS: tuple[tuple[str, str], ...] = (
    ("lg electronics", "lg"),
    ("logitech", "logitech"),
    ("razer", "razer"),
    ("corsair", "corsair"),
    ("steelseries", "steelseries"),
)
_PC_OEM_TITLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "dell": ("dell ", "dell,", "alienware"),
    "hp": ("hp inc", "hewlett-packard", "hewlett packard", " hp "),
    "lenovo": ("lenovo", "thinkpad", "ideapad"),
    "asus": ("asus", "rog "),
    "acer": ("acer",),
    "msi": ("msi ", "micro-star"),
    "gigabyte": ("gigabyte",),
}

_SECURITY_AV_VENDOR_KEYWORDS = (
    "kaspersky",
    "norton",
    "symantec",
    "mcafee",
    "avast",
    "avg antivirus",
    "bitdefender",
    "eset ",
    "trend micro",
    "sophos",
    "malwarebytes",
    "crowdstrike",
    "sentinelone",
    "webroot",
    "comodo",
    "avira",
    "panda security",
)

_FIRMWARE_CATALOG_TITLE_KEYWORDS = (
    "firmware driver",
    " device firmware",
    " system firmware",
    " uefi firmware",
    " bios update",
    "embedded controller firmware",
    "ec firmware",
    "capsule firmware",
)

_AMD_SYSTEM_DRIVER_PHRASE = "amd system driver update"
_AMD_MEDIA_DRIVER_PHRASE = "amd media driver update"
_PNP_CLASSES_BLOCK_AMD_SYSTEM = frozenset({
    "monitor",
    "display",
    "media",
    "softwarecomponent",
    "audio",
    "audioendpoint",
    "audioprocessingobject",
    "bluetooth",
    "net",
    "camera",
    "image",
    "hidclass",
})
def _reject_amd_bulk_catalog_row(row: dict, ctx: dict) -> str | None:
    """Block generic AMD System/Media catalog bundles unless HWID or device role matches."""
    if not _ctx_is_amd_device(ctx):
        return None
    if _catalog_row_hwid_matches_ctx(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx)

    if _AMD_SYSTEM_DRIVER_PHRASE in title_l:
        if pnp in _PNP_CLASSES_BLOCK_AMD_SYSTEM:
            return "amd_system_driver_wrong_class"
        if _device_is_amd_media(ctx):
            return "amd_system_driver_wrong_class"
        if "monitor" in label or "displayport" in label or " lg " in f" {label} ":
            return "amd_system_driver_wrong_class"
        if not _device_is_amd_chipset_plumbing(ctx):
            return "amd_system_driver_not_chipset"
        return None

    if _AMD_MEDIA_DRIVER_PHRASE in title_l:
        if not _device_is_amd_media(ctx) and pnp not in ("media", "audio", "audioendpoint"):
            return "amd_media_driver_wrong_class"
        return None

    return None


def _reject_vendor_driver_class_mismatch(row: dict, ctx: dict) -> str | None:
    """Reject catalog packages whose implied device class does not match (without HWID proof)."""
    if _catalog_row_hwid_matches_ctx(row, ctx):
        return None
    title_l = (row.get("title") or "").lower()
    cat_l = (row.get("category") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx)
    vk = (ctx.get("vendor_key") or "").lower()

    gpu_title = any(
        k in title_l
        for k in (
            "radeon",
            "geforce",
            "graphics driver",
            "display driver",
            "video driver",
            "nvidia driver",
        )
    )
    if gpu_title:
        if ctx.get("hw_category") == "chipset":
            if not any(k in title_l or k in cat_l for k in ("chipset", "platform")):
                return "gpu_on_chipset"
        if pnp == "display":
            if vk == "nvidia" and any(k in title_l for k in ("radeon", "amd ", "amd/")):
                return "cross_vendor_gpu_offer"
            if vk == "amd" and any(k in title_l for k in ("geforce", "nvidia")):
                return "cross_vendor_gpu_offer"
        gpu_device = (
            pnp == "display"
            or any(
                k in label
                for k in (
                    "radeon",
                    "geforce",
                    "graphics",
                    "nvidia",
                    "arc ",
                    "iris",
                    "uhd graphics",
                )
            )
        )
        if not gpu_device:
            return "gpu_driver_wrong_device"

    if pnp in ("monitor", "keyboard", "mouse", "battery", "hidclass"):
        if any(
            k in title_l
            for k in (
                "radeon",
                "geforce",
                "graphics driver",
                "chipset driver",
                "chipset inf",
                " nvidia ",
            )
        ):
            return "driver_package_wrong_device_class"
        if any(
            k in title_l or k in cat_l
            for k in (
                " bios",
                "uefi",
                "firmware",
                "application",
                "on-screen display",
                "update application",
                "supportassist",
                "alienware update",
            )
        ):
            return "oem_app_on_peripheral"

    if pnp in ("media", "audio", "audioendpoint") or "audio" in label:
        if any(
            k in title_l
            for k in (
                "radeon",
                "geforce",
                "graphics driver",
                "chipset driver",
                "chipset inf",
                " nvidia ",
            )
        ):
            return "gpu_chipset_on_audio"

    if "nvidia" in title_l and (
        "display driver" in title_l or title_l.startswith("nvidia driver update")
    ):
        if pnp in ("media", "audio", "audioendpoint") or "virtual audio" in label:
            return "display_driver_on_audio_device"

    if ("display driver" in title_l or "graphics driver" in title_l) and pnp == "monitor":
        if any(tag in title_l for tag in ("nvidia", "geforce", "radeon", "amd radeon")):
            return "gpu_driver_on_monitor"

    if "audioprocessingobject" in title_l or "softwarecomponent driver update" in title_l:
        if pnp == "monitor":
            return "swc_driver_update_on_monitor"
        if "battery" in label or "control method battery" in label:
            return "component_driver_on_battery"
        # Vendor-branded SWC packages (LG monitor app, Logitech, …) must not land on
        # unrelated SoftwareComponent rows (e.g. AMD OpenCL) without HWID proof.
        if not _catalog_row_hwid_matches_ctx(row, ctx):
            for marker, expected_vk in _SWC_BRANDED_VENDOR_MARKERS:
                if marker in title_l and vk != expected_vk:
                    return "swc_branded_vendor_mismatch"

    if pnp == "bluetooth" and " net driver" in title_l:
        return "net_driver_on_bluetooth"

    if pnp == "usb" or any(k in label for k in ("xhci", "host controller", "usb controller")):
        if any(
            k in title_l
            for k in (
                "ethernet",
                "wi-fi",
                "wifi",
                "wireless",
                "network driver",
                "gbe",
                "2.5g",
                "bluetooth driver",
            )
        ):
            return "oem_net_on_usb"

    peripheral_label = any(
        k in label
        for k in (
            "battery",
            "control method battery",
            "keyboard",
            "mouse",
            "touchpad",
            "pointing device",
            "usb root hub",
            "usb composite",
            "usb host controller",
            "volume manager",
            "disk drive",
            "system timer",
            "programmable interrupt",
        )
    )
    if peripheral_label or pnp in ("keyboard", "battery"):
        if gpu_title or any(
            k in title_l
            for k in ("ethernet controller", "network driver", "wireless driver", "audio driver")
        ):
            return "oem_package_wrong_device_class"

    return None
def _is_microsoft_catalog_row_source(source: str) -> bool:
    """True for MSCatalogLTS raw rows, assembled offers, and pre-offer cache rows."""
    src = (source or "").strip().lower()
    if not src:
        return True
    return src in (
        "microsoft",
        "microsoft_catalog",
        "microsoft_catalog_html",
    )


def _reject_mediatek_mscatalog_spurious(row: dict, ctx: dict) -> str | None:
    """Drop MSCatalog rows that mismatch MediaTek UWD version families without HWID proof."""
    if not _is_microsoft_catalog_row_source(row.get("source") or ""):
        return None
    if (ctx.get("vendor_key") or "").lower() != "mediatek":
        return None
    if (ctx.get("pnp_class") or "").lower() != "net":
        return None
    if _catalog_row_hwid_matches_ctx(row, ctx):
        return None
    ver = (row.get("version") or "").strip()
    title_l = (row.get("title") or "").lower()
    if "mediatek" not in title_l and "mt792" not in title_l:
        return "mediatek_ms_unrelated"
    if ver and _looks_like_amd_adrenalin_version(ver) and not _looks_like_mediatek_uwd_version(ver):
        return "mediatek_ms_version_mismatch"
    inst = (ctx.get("primary_version") or "").strip()
    if (
        inst
        and _looks_like_mediatek_uwd_version(inst)
        and ver
        and not _looks_like_mediatek_uwd_version(ver)
    ):
        return "mediatek_ms_version_mismatch"
    if (
        inst
        and ver
        and _looks_like_mediatek_uwd_version(inst)
        and _looks_like_mediatek_uwd_version(ver)
        and compare_versions(inst, ver) == "older"
    ):
        return "mediatek_ms_stale_unverified"
    return None
def _realtek_device_component_role(ctx: dict) -> str:
    """Realtek UAD stack role for Microsoft Catalog matching."""
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx)
    primary = (ctx.get("primary_version") or "").strip()
    if pnp == "net" or any(k in label for k in ("ethernet", "2.5gbe", "gbe", "gaming 2.5")):
        return "net"
    if pnp == "audioprocessingobject" or (
        "effects component" in label and not _looks_like_realtek_wdm_version(primary)
    ):
        return "apo"
    if pnp == "softwarecomponent" or any(
        k in label for k in ("universal service", "hardware support", "asio component")
    ):
        return "swc"
    if pnp in ("media", "audio") or "realtek audio" in label:
        return "wdm"
    return "generic"


def _realtek_catalog_row_is_wdm_codec(row: dict) -> bool:
    title_l = (row.get("title") or "").lower()
    ver = (row.get("version") or "").strip()
    if "audioprocessingobject" in title_l:
        return False
    if _looks_like_realtek_wdm_version(ver):
        return True
    return any(
        k in title_l
        for k in (
            "realtek media",
            "high definition audio",
            "semiconductor corp media",
            "universal audio driver",
        )
    )


def _realtek_nic_mscatalog_trusted(row: dict, ctx: dict) -> bool:
    """
    Realtek PCIe NIC rows from MSCatalog title/version search — same OEM family
    prefix as installed (e.g. 1125.x) without INF HWID text in the catalog row.
    """
    if (ctx.get("vendor_key") or "").lower() != "realtek":
        return False
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx).lower()
    if pnp != "net" and not any(k in label for k in ("ethernet", "gbe", "2.5g")):
        return False
    title_l = (row.get("title") or "").lower()
    if "realtek" not in title_l:
        return False
    if any(k in title_l for k in ("audio", "high definition audio", "hdaudio")):
        return False
    inst = (ctx.get("primary_version") or "").strip()
    for inv in ctx.get("installed_rows") or []:
        inst = inst or (inv.get("version") or "").strip()
    cand = _dc("_offer_version_from_fields")(row) or (row.get("version") or "").strip()
    if not inst or not cand:
        return False
    if not _looks_like_realtek_nic_driver_version(inst):
        return False
    if not _looks_like_realtek_nic_driver_version(cand):
        return False
    if _realtek_net_version_major(inst) != _realtek_net_version_major(cand):
        return False
    return compare_versions(inst, cand) in ("newer", "same")


def _realtek_wdm_mscatalog_trusted(row: dict, ctx: dict) -> bool:
    """Realtek audio codec rows require strict DEV_ confirmation in catalog metadata."""
    if (ctx.get("vendor_key") or "").lower() != "realtek":
        return False
    if _realtek_device_component_role(ctx) != "wdm":
        return False
    return _catalog_row_hwid_strict_matches_ctx(row, ctx)


def _realtek_catalog_row_is_companion_component(row: dict) -> bool:
    title_l = (row.get("title") or "").lower()
    return (
        "audioprocessingobject" in title_l
        or ("softwarecomponent" in title_l and "realtek" in title_l)
        or "multifunction" in title_l
    )


def _reject_realtek_catalog_row(row: dict, ctx: dict) -> str | None:
    """Keep Realtek UAD catalog rows aligned with the device component role."""
    vk = (ctx.get("vendor_key") or "").lower()
    title_l = (row.get("title") or "").lower()
    if vk != "realtek" and "realtek" not in title_l:
        return None
    role = _realtek_device_component_role(ctx)
    # UAD stack nodes share HWID text — reject companion rows before HWID bypass.
    if role == "wdm":
        if _realtek_catalog_row_is_companion_component(row) and not _realtek_catalog_row_is_wdm_codec(row):
            return "realtek_companion_on_wdm_device"
    if _catalog_row_hwid_matches_ctx(row, ctx):
        return None
    if role == "wdm":
        if any(
            k in title_l
            for k in ("ethernet", "gbe", "2.5g", "pcie ethernet", "network driver")
        ):
            return "realtek_net_on_wdm_device"
    elif role == "apo":
        if "high definition audio" in title_l and "audioprocessingobject" not in title_l:
            return "realtek_wdm_on_apo_device"
        if any(
            k in title_l
            for k in ("ethernet", "gbe", "2.5g", "pcie ethernet", "network driver")
        ):
            return "realtek_net_on_apo_device"
    elif role == "swc":
        label = _ctx_device_label(ctx).lower()
        if "asio" in label and any(
            k in title_l
            for k in (
                "console application",
                "universal service",
                "hardware support application",
            )
        ):
            return "realtek_swc_role_mismatch"
        if "universal service" in label and "console application" in title_l:
            return "realtek_swc_role_mismatch"
        if "high definition audio" in title_l or "realtek media" in title_l:
            return "realtek_wdm_on_swc_device"
        if any(
            k in title_l
            for k in ("ethernet", "gbe", "2.5g", "pcie ethernet", "network driver")
        ):
            return "realtek_net_on_swc_device"
    elif role == "net":
        if any(k in title_l for k in ("audio", "audioprocessingobject", "high definition audio")):
            return "realtek_audio_on_nic"
    return None




def _realtek_nic_public_build_suffix(version: str) -> tuple[int, ...]:
    """Realtek.com PCIe package numbering (e.g. 11.030.50 → build 30.50)."""
    return dvi._realtek_nic_public_build_suffix(version)




def _mscatalog_rows_hwid_first_keep(
    pool: list[tuple[int, dict, bool]],
    ctx: dict,
) -> list[tuple[int, dict, bool]]:
    """Prefer HWID-strict catalog rows over higher-version wrong-HWID packages (P1)."""
    if not pool:
        return pool
    strict = [
        item for item in pool
        if _catalog_row_hwid_strict_matches_ctx(item[1], ctx)
    ]
    loose = [item for item in pool if item[2]]
    pick_from = strict or loose or pool
    newest = max(
        pick_from,
        key=lambda x: parse_driver_version(x[1].get("version") or "") or (),
    )
    keep: list[tuple[int, dict, bool]] = [newest]
    keep_ids = {(newest[1].get("update_id") or "").lower()}

    if strict and newest not in strict:
        best_strict = max(
            strict,
            key=lambda x: parse_driver_version(x[1].get("version") or "") or (),
        )
        sid = (best_strict[1].get("update_id") or "").lower()
        if sid and sid not in keep_ids:
            keep.insert(0, best_strict)
            keep_ids.add(sid)

    inst = (ctx.get("primary_version") or "").strip()
    for inv in ctx.get("installed_rows") or []:
        inst = inst or (inv.get("version") or "").strip()
    if inst:
        for item in pool:
            uid = (item[1].get("update_id") or "").lower()
            if not uid or uid in keep_ids:
                continue
            cand_ver = (item[1].get("version") or "").strip()
            if cand_ver and compare_versions(inst, cand_ver) == "same":
                keep.append(item)
                keep_ids.add(uid)
            elif cand_ver and dvi.catalog_offer_matches_installed(
                inst,
                cand_ver,
                device_ctx=ctx,
            ):
                keep.append(item)
                keep_ids.add(uid)
    return keep


def _prioritize_mscatalog_scored_rows(
    scored: list[tuple[int, dict, bool]],
    ctx: dict,
) -> list[tuple[int, dict, bool]]:
    """Reorder MSCatalog hits so HWID-verified rows are not dropped by version sorting."""
    if not scored or not (ctx.get("instance_id") or "").strip():
        return scored
    strict = [
        item for item in scored
        if _catalog_row_hwid_strict_matches_ctx(item[1], ctx)
    ]
    if not strict:
        return scored
    kept = _mscatalog_rows_hwid_first_keep(scored, ctx)
    kept_ids = {
        (item[1].get("update_id") or "").lower()
        for item in kept
    }
    return kept + [
        item for item in scored
        if (item[1].get("update_id") or "").lower() not in kept_ids
    ]


def _realtek_wdm_mscatalog_codec_rows_to_keep(
    wdm_codec: list[tuple[int, dict, bool]],
    ctx: dict,
) -> list[tuple[int, dict, bool]]:
    """Select Realtek WDM codec catalog hits without hiding HWID-verified builds."""
    return _mscatalog_rows_hwid_first_keep(wdm_codec, ctx)


def _reject_realtek_oem_net_family_mismatch(row: dict, ctx: dict) -> str | None:
    """Drop Realtek NIC OEM rows that target a different Realtek driver family."""
    src = (row.get("source") or "").lower()
    if src and src != "oem":
        return None
    if _catalog_row_hwid_matches_ctx(row, ctx):
        return None
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx)
    if pnp != "net" and not any(k in label for k in ("ethernet", "gbe", "2.5g")):
        return None
    title_l = (row.get("title") or "").lower()
    if "realtek" not in title_l or "ethernet" not in title_l:
        return None
    inst = (ctx.get("primary_version") or "").strip()
    for inv in ctx.get("installed_rows") or []:
        inst = inst or (inv.get("version") or "").strip()
    cand = (row.get("version") or "").strip()
    im = _realtek_net_version_major(inst)
    cm = _realtek_net_version_major(cand)
    if im and cm and im != cm:
        if _realtek_nic_same_oem_family(inst, cand):
            return None
        if (
            "realtek" in title_l
            and "ethernet" in title_l
            and _looks_like_realtek_nic_driver_version(cand)
            and _looks_like_realtek_nic_driver_version(inst)
        ):
            return None
        return "realtek_nic_version_family_mismatch"
    return None
def _system_pc_oem_tags(ctx: dict) -> set[str]:
    mfr = (ctx.get("system_manufacturer") or "").lower()
    tags: set[str] = set()
    if "dell" in mfr or "alienware" in mfr:
        tags.add("dell")
    if "hp" in mfr or "hewlett" in mfr:
        tags.add("hp")
    if "lenovo" in mfr or "thinkpad" in mfr or "ideapad" in mfr:
        tags.add("lenovo")
    if "asus" in mfr or "rog" in mfr:
        tags.add("asus")
    if "acer" in mfr:
        tags.add("acer")
    if "msi" in mfr or "micro-star" in mfr:
        tags.add("msi")
    if "gigabyte" in mfr:
        tags.add("gigabyte")
    return tags


def _catalog_title_pc_oem_tags(title_l: str) -> set[str]:
    tags: set[str] = set()
    for tag, patterns in _PC_OEM_TITLE_PATTERNS.items():
        if any(p in title_l for p in patterns):
            tags.add(tag)
    return tags


def _catalog_title_cross_oem_mismatch(title_l: str, ctx: dict) -> bool:
    """Reject HP firmware on Dell, etc."""
    title_tags = _catalog_title_pc_oem_tags(title_l)
    if not title_tags:
        return False
    system_tags = _system_pc_oem_tags(ctx)
    if not system_tags:
        return False
    return not title_tags.intersection(system_tags)


def _catalog_title_is_firmware_package(title_l: str) -> bool:
    if any(kw in title_l for kw in _FIRMWARE_CATALOG_TITLE_KEYWORDS):
        return True
    return bool(re.search(r"\b(bios|uefi)\b", title_l))


def _catalog_title_is_security_software(title_l: str, ctx: dict) -> bool:
    for av in _SECURITY_AV_VENDOR_KEYWORDS:
        if av not in title_l:
            continue
        vk = (ctx.get("vendor_key") or "").lower()
        label = (ctx.get("device_label") or ctx.get("target_device_name") or "").lower()
        if av in vk or av in label:
            return False
        return True
    return False


def _catalog_row_hwid_blob(row: dict) -> str:
    blob_parts = [
        row.get("title") or "",
        row.get("products") or "",
        row.get("description") or "",
        " ".join(row.get("file_names") or []),
    ]
    return " ".join(blob_parts).upper().replace("/", "\\")


def _catalog_row_hwid_matches_ctx(row: dict, ctx: dict) -> bool:
    inst = (ctx.get("instance_id") or "").upper()
    if not inst or "VEN_" not in inst:
        return False
    blob = _catalog_row_hwid_blob(row)
    ven = re.search(r"VEN_([0-9A-F]{4})", inst)
    dev = re.search(r"DEV_([0-9A-F]{4})", inst)
    sub = re.search(r"SUBSYS_([0-9A-F]{8})", inst)
    if ven and f"VEN_{ven.group(1)}" in blob:
        if dev and f"DEV_{dev.group(1)}" in blob:
            return True
        if sub and f"SUBSYS_{sub.group(1)}" in blob:
            return True
    inst_norm = inst.replace("\\\\", "\\")
    if len(inst_norm) >= 20 and inst_norm[:32] in blob:
        return True
    for token in ctx.get("pci_tokens") or []:
        tok = str(token).upper()
        if tok and tok in blob:
            if dev and f"DEV_{dev.group(1)}" in blob:
                return True
    return False


def _catalog_row_hwid_strict_matches_ctx(row: dict, ctx: dict) -> bool:
    """Require DEV_ match when the catalog blob lists device IDs (avoids VEN-only false positives)."""
    if not _catalog_row_hwid_matches_ctx(row, ctx):
        return False
    inst = (ctx.get("instance_id") or "").upper()
    dev_m = re.search(r"DEV_([0-9A-F]{4})", inst)
    if not dev_m:
        return True
    blob = _catalog_row_hwid_blob(row)
    dev_tokens = set(re.findall(r"DEV_([0-9A-F]{4})", blob))
    if not dev_tokens:
        return False
    return dev_m.group(1) in dev_tokens


def _catalog_hwid_mismatch_note(row: dict, ctx: dict) -> str:
    """Explain when a catalog row mentions different DEV_ IDs than the selected device."""
    inst = (ctx.get("instance_id") or "").upper()
    dev_m = re.search(r"DEV_([0-9A-F]{4})", inst)
    if not dev_m:
        return ""
    blob = _catalog_row_hwid_blob(row)
    dev_tokens = sorted(set(re.findall(r"DEV_([0-9A-F]{4})", blob)))
    if not dev_tokens or dev_m.group(1) in dev_tokens:
        return ""
    yours = dev_m.group(1)
    listed = ", ".join(f"DEV_{t}" for t in dev_tokens[:4])
    extra = f" (+{len(dev_tokens) - 4} more)" if len(dev_tokens) > 4 else ""
    return (
        f"Catalog Package Details list {listed}{extra}, but this device is DEV_{yours} — "
        "verify hardware IDs in Update Catalog before installing."
    )


def _normalize_catalog_row_for_reject(row: dict) -> dict:
    """Normalize WU / online-store / OEM row shapes for shared reject helpers."""
    if row.get("title"):
        return row
    title = (
        row.get("Title")
        or row.get("HardwareDescription")
        or row.get("ProviderName")
        or ""
    )
    if not title:
        return row
    out = dict(row)
    out["title"] = str(title).strip()
    if not out.get("category"):
        out["category"] = str(row.get("ClassName") or row.get("category") or "").strip()
    return out


def _shared_catalog_row_rejects(
    row: dict,
    ctx: dict,
    *,
    query: str = "",
    include_oem_net_family: bool = True,
) -> str | None:
    """Unified rejection for OEM bulk, WU, online driver store, and MSCatalog rows."""
    r = _normalize_catalog_row_for_reject(row)
    title_l = (r.get("title") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    if _catalog_title_is_security_software(title_l, ctx):
        return "security_software"
    if _catalog_title_cross_oem_mismatch(title_l, ctx):
        return "cross_oem"
    if pnp not in _DRIVER_SCAN_EXCLUDED_PNP_CLASSES and _catalog_title_is_firmware_package(title_l):
        return "firmware_package"
    label = _ctx_device_label(ctx) or (ctx.get("target_device_name") or "").strip().lower()
    if label in _GENERIC_PNP_DEVICE_LABELS and not _catalog_row_hwid_matches_ctx(r, ctx):
        return "generic_device"
    if query.strip().lower() in _GENERIC_PNP_DEVICE_LABELS and not _catalog_row_hwid_matches_ctx(r, ctx):
        return "generic_query"
    # Applies to every catalog source: device-class and vendor-family sanity.
    for helper in (
        _reject_amd_bulk_catalog_row,
        _reject_vendor_driver_class_mismatch,
        _reject_realtek_catalog_row,
        _reject_mediatek_mscatalog_spurious,
    ):
        reason = helper(r, ctx)
        if reason:
            return reason
    # PC-maker/OEM support-catalog rules only — see _row_is_oem_sourced.
    if _row_is_oem_sourced(r):
        for helper in (
            _reject_oem_pc_maker_on_third_party_device,
            _reject_oem_pc_maker_update_application,
            _reject_oem_amd_chipset_on_component_inf,
            _reject_oem_intel_chipset_on_component_inf,
            _reject_oem_audio_vendor_mismatch,
            _reject_oem_application_on_driver_device,
            _reject_oem_airplane_mode_mismatch,
            _reject_oem_realtek_hd_on_inbox_hd_controller,
            _reject_oem_radio_chip_mismatch,
        ):
            reason = helper(r, ctx)
            if reason:
                return reason
    if include_oem_net_family:
        reason = _reject_realtek_oem_net_family_mismatch(r, ctx)
        if reason:
            return reason
    return None


def _reject_mscatalog_row_for_ctx(row: dict, ctx: dict, query: str) -> str | None:
    return _shared_catalog_row_rejects(row, ctx, query=query, include_oem_net_family=False)
