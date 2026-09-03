"""
Vendor-branded icons for device/driver rows (monogram badges + optional SVG assets).

Uses recognizable brand colors and initials when official logo files are not bundled.
Drop SVG/PNG files into assets/vendor_icons/{vendor_key}.svg to override monograms.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:  # pragma: no cover
    QSvgRenderer = None  # type: ignore[misc, assignment]

import device_enrichment as de

# Text tokens -> vendor_key (display names, synthetic crash rows, etc.)
_NAME_VENDOR_TOKENS: tuple[tuple[str, str], ...] = (
    ("advanced micro devices", "amd"),
    ("amd", "amd"),
    ("nvidia", "nvidia"),
    ("geforce", "nvidia"),
    ("intel", "intel"),
    ("realtek", "realtek"),
    ("microsoft", "microsoft"),
    ("dell", "dell"),
    ("alienware", "alienware"),
    ("hp ", "hp"),
    ("hewlett", "hp"),
    ("lenovo", "lenovo"),
    ("asus", "asus"),
    ("acer", "acer"),
    ("msi", "msi"),
    ("gigabyte", "gigabyte"),
    ("samsung", "samsung"),
    ("qualcomm", "qualcomm"),
    ("broadcom", "broadcom"),
    ("marvell", "marvell"),
    ("mediatek", "mediatek"),
    ("synaptics", "synaptics"),
    ("logitech", "logitech"),
    ("corsair", "corsair"),
    ("razer", "razer"),
    ("apple", "apple"),
    ("western digital", "western_digital"),
    ("seagate", "seagate"),
    ("crucial", "crucial"),
    ("sandisk", "sandisk"),
    ("kingston", "kingston"),
    ("sk hynix", "sk_hynix"),
    ("hynix", "sk_hynix"),
)

# Brand colors (approximate; monogram badges, not official trademark artwork).
VENDOR_BRANDS: dict[str, tuple[str, str, str]] = {
    # key -> (bg_hex, fg_hex, monogram)
    "amd": ("#ED1C24", "#FFFFFF", "AMD"),
    "nvidia": ("#76B900", "#111111", "NV"),
    "intel": ("#0071C5", "#FFFFFF", "IN"),
    "realtek": ("#0066CC", "#FFFFFF", "RT"),
    "qualcomm": ("#3253DC", "#FFFFFF", "QC"),
    "broadcom": ("#E31837", "#FFFFFF", "BC"),
    "microsoft": ("#0078D4", "#FFFFFF", "MS"),
    "dell": ("#007DB8", "#FFFFFF", "DL"),
    "alienware": ("#0C3866", "#00AEEF", "AW"),
    "hp": ("#0096D6", "#FFFFFF", "HP"),
    "lenovo": ("#E2231A", "#FFFFFF", "LV"),
    "asus": ("#000000", "#FFFFFF", "AS"),
    "acer": ("#83B81A", "#FFFFFF", "AC"),
    "msi": ("#FF0000", "#FFFFFF", "MSI"),
    "gigabyte": ("#F47920", "#FFFFFF", "GB"),
    "samsung": ("#1428A0", "#FFFFFF", "SS"),
    "lg": ("#A50034", "#FFFFFF", "LG"),
    "logitech": ("#00B8FC", "#111111", "LOGI"),
    "corsair": ("#F9E900", "#111111", "CR"),
    "razer": ("#44D62C", "#111111", "RZ"),
    "marvell": ("#002855", "#FFFFFF", "MV"),
    "mediatek": ("#EC008C", "#FFFFFF", "MT"),
    "killer": ("#0078D4", "#FFFFFF", "KL"),
    "synaptics": ("#005CB9", "#FFFFFF", "SY"),
    "apple": ("#555555", "#FFFFFF", "AP"),
    "vmware": ("#607078", "#FFFFFF", "VM"),
    "virtualbox": ("#183A61", "#FFFFFF", "VB"),
    "western_digital": ("#005195", "#FFFFFF", "WD"),
    "seagate": ("#6EBE44", "#111111", "SG"),
    "crucial": ("#0066CC", "#FFFFFF", "CR"),
    "sandisk": ("#E31837", "#FFFFFF", "SD"),
    "kingston": ("#CC0000", "#FFFFFF", "KN"),
    "sk_hynix": ("#E60012", "#FFFFFF", "HX"),
    "firmware": ("#1a3a5c", "#FFFFFF", "FW"),
    "storage": ("#4a5568", "#FFFFFF", "SSD"),
}

_ICON_DIR_NAMES = (
    "assets/vendor_icons",
    "vendor_icons",
)


def _repo_vendor_icon_dir() -> Path | None:
    here = Path(__file__).resolve().parent
    for name in _ICON_DIR_NAMES:
        d = here / name
        if d.is_dir():
            return d
    return None


def _bundled_vendor_icon_dir() -> Path | None:
    meipass = getattr(__import__("sys"), "frozen", False) and getattr(
        __import__("sys"), "_MEIPASS", None
    )
    if not meipass:
        return None
    base = Path(str(meipass))
    for name in _ICON_DIR_NAMES:
        d = base / name
        if d.is_dir():
            return d
    return None


def vendor_icon_dir() -> Path | None:
    return _bundled_vendor_icon_dir() or _repo_vendor_icon_dir()


def _infer_vendor_from_text(*parts: str) -> str:
    for text in parts:
        low = (text or "").strip().lower()
        if not low:
            continue
        for token, key in _NAME_VENDOR_TOKENS:
            if token in low:
                return key
    return ""


def vendor_key_for_device(dev: dict) -> str:
    vk = (dev.get("vendor_key") or "").strip().lower()
    if vk:
        return vk
    name = (dev.get("display_name") or dev.get("name") or "").strip()
    pnp = (dev.get("device_class") or dev.get("pnp_class") or "").strip()
    mfr = (dev.get("manufacturer") or "").strip()
    device_id = (dev.get("device_id") or "").strip()
    from_name = _infer_vendor_from_text(name, mfr, dev.get("driver") or "")
    if from_name:
        return from_name
    inferred = de.infer_vendor_key(
        name,
        pnp,
        mfr,
        device_id,
        disk_model=(dev.get("disk_model") or "").strip(),
    )
    if inferred:
        return inferred.lower()
    driver = (dev.get("driver") or "").lower()
    for token, key in (
        ("amdkmdag", "amd"),
        ("amdfendr", "amd"),
        ("amdkmpfd", "amd"),
        ("nvlddmkm", "nvidia"),
        ("igdkmd", "intel"),
        ("rt640", "realtek"),
        ("rtwlane", "realtek"),
        ("rt68", "realtek"),
        ("bcm", "broadcom"),
        ("qca", "qualcomm"),
        ("mt792", "mediatek"),
    ):
        if token in driver:
            return key
    return ""


def _monogram_for_key(key: str) -> tuple[str, str, str]:
    if key in VENDOR_BRANDS:
        return VENDOR_BRANDS[key]
    if not key:
        return ("#4a4a55", "#ccccd4", "?")
    label = key.replace("_", " ").title()
    letters = "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", label)[:3]).upper()
    if len(letters) < 2:
        letters = (label[:2] or "?").upper()
    return ("#3a3a44", "#c8c8d0", letters[:3])


@lru_cache(maxsize=128)
def _monogram_pixmap(key: str, size: int) -> QtGui.QPixmap:
    bg, fg, mono = _monogram_for_key(key)
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setBrush(QtGui.QColor(bg))
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    r = size - 2
    p.drawRoundedRect(1, 1, r, r, size // 4, size // 4)
    font = QtGui.QFont("Segoe UI", max(7, size // 3))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QtGui.QColor(fg))
    p.drawText(pm.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, mono)
    p.end()
    return pm


def _icon_from_svg_bytes(data: bytes, size: int, *, pad_ratio: float = 0.1) -> QtGui.QIcon | None:
    if not data or QSvgRenderer is None:
        return None
    renderer = QSvgRenderer(QtCore.QByteArray(data))
    if not renderer.isValid():
        return None
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    pad = max(1, int(size * pad_ratio))
    target = QtCore.QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    vb = renderer.viewBoxF()
    if vb.isValid() and not vb.isEmpty():
        renderer.render(p, target)
    else:
        renderer.render(p, QtCore.QRectF(0, 0, size, size))
    p.end()
    if pm.isNull():
        return None
    return QtGui.QIcon(pm)


def _amd_strip_black_matte(pm: QtGui.QPixmap) -> QtGui.QPixmap:
    """Make the approved black-background AMD PNG blend into dark table rows.

    The committed asset keeps an opaque black matte (user-approved Jul 2026). Strip
    it at paint time so only the red mark and the square hole show through.
    """
    img = pm.toImage().convertToFormat(QtGui.QImage.Format.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0 and c.red() < 32 and c.green() < 32 and c.blue() < 32:
                c.setAlpha(0)
                img.setPixelColor(x, y, c)
    return QtGui.QPixmap.fromImage(img)


def _icon_from_png_path(
    path: Path,
    size: int,
    *,
    key: str,
    pad_ratio: float = 0.1,
) -> QtGui.QIcon | None:
    pm = QtGui.QPixmap(str(path))
    if pm.isNull():
        return None
    if key == "amd":
        pm = _amd_strip_black_matte(pm)
        pad_ratio = 0.04
    out = QtGui.QPixmap(size, size)
    out.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(out)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    pad = max(1, int(size * pad_ratio))
    inner = max(1, size - 2 * pad)
    scaled = pm.scaled(
        inner,
        inner,
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    p.drawPixmap(x, y, scaled)
    p.end()
    if out.isNull():
        return None
    return QtGui.QIcon(out)


def _load_file_icon(key: str, size: int) -> QtGui.QIcon | None:
    if not key:
        return None
    base = vendor_icon_dir()
    if not base:
        return None
    for ext in (".svg", ".png", ".ico"):
        path = base / f"{key}{ext}"
        if path.is_file():
            if ext == ".svg":
                svg_bytes = path.read_bytes()
                pad_ratio = 0.04 if key == "amd" else (0.06 if key == "microsoft" else 0.1)
                icon = _icon_from_svg_bytes(svg_bytes, size, pad_ratio=pad_ratio)
                if icon is not None:
                    return icon
            if ext == ".png":
                icon = _icon_from_png_path(path, size, key=key)
                if icon is not None:
                    return icon
            icon = QtGui.QIcon(str(path))
            if not icon.isNull():
                pm = icon.pixmap(size, size)
                if not pm.isNull():
                    return QtGui.QIcon(pm)
    return None


def icon_for_vendor_key(key: str, *, size: int = 24) -> QtGui.QIcon:
    key = (key or "").strip().lower()
    file_icon = _load_file_icon(key, size)
    if file_icon is not None:
        return file_icon
    pm = _monogram_pixmap(key, size)
    return QtGui.QIcon(pm)


def icon_for_device(dev: dict, *, size: int = 24) -> QtGui.QIcon:
    return icon_for_vendor_key(vendor_key_for_device(dev), size=size)


def set_vendor_icon_label(label: QtWidgets.QLabel, icon: QtGui.QIcon, *, size: int) -> None:
    """Show a vendor icon at the label's fixed size without stretching."""
    label.setPixmap(icon.pixmap(size, size))


def large_icon_for_device(dev: dict, *, size: int = 44) -> QtGui.QIcon:
    return icon_for_device(dev, size=size)


def vendor_key_for_firmware(ent: dict) -> str:
    vk = (ent.get("vendor_key") or "").strip().lower()
    if vk:
        return vk
    key = (ent.get("key") or "").strip().lower()
    component = (ent.get("component") or "").strip()
    mfr = (ent.get("manufacturer") or "").strip()
    model = (ent.get("model") or "").strip()
    device_id = (ent.get("device_id") or "").strip()

    from_name = _infer_vendor_from_text(component, mfr, model)
    if from_name:
        return from_name

    if key.startswith("peripheral:"):
        parts = key.split(":")
        if len(parts) >= 2:
            vid = parts[1].upper()
            if vid in de._USB_VID_VENDORS:
                return (de._USB_VID_VENDORS[vid] or "").lower()
        if device_id:
            try:
                import firmware_peripheral_vendors as fpv

                hint = fpv.product_hint(device_id, component)
                if hint and hint.vendor_key:
                    return hint.vendor_key.lower()
            except ImportError:
                pass

    if key == "bios":
        inferred = de.infer_vendor_key(component, "", mfr)
        return (inferred or "firmware").lower()
    if key == "ssd:loading":
        return "storage"
    if key == "ssd:none":
        return "storage"
    if key.startswith("ssd:"):
        disk = model or key[4:].strip()
        inferred = de.infer_vendor_key(disk, "", mfr, disk_model=disk)
        if inferred:
            return inferred.lower()
        low = disk.lower()
        for token, vkey in (
            ("samsung", "samsung"),
            ("western digital", "western_digital"),
            ("wd ", "western_digital"),
            ("seagate", "seagate"),
            ("crucial", "crucial"),
            ("sandisk", "sandisk"),
            ("intel", "intel"),
            ("kingston", "kingston"),
            ("sk hynix", "sk_hynix"),
            ("hynix", "sk_hynix"),
        ):
            if token in low:
                return vkey
        return "storage"
    inferred = de.infer_vendor_key(component, "", mfr, device_id)
    return (inferred or "").lower()


def icon_for_firmware_entry(ent: dict, *, size: int = 24) -> QtGui.QIcon:
    return icon_for_vendor_key(vendor_key_for_firmware(ent), size=size)


def large_icon_for_firmware_entry(ent: dict, *, size: int = 44) -> QtGui.QIcon:
    return icon_for_firmware_entry(ent, size=size)
