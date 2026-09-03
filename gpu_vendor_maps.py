"""GPU vendor identity maps — API-first lookups, minimal HTML scraping.

Policy floor (supported for manufacturer GPU driver checks):
  NVIDIA: GeForce GTX 900 series and newer
  AMD:    R9 200 / R7 300 / RX 400 series and newer (GCN 1.1+)
  Intel:  HD Graphics 530 (Skylake) / Iris 540+ and newer
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from functools import lru_cache
from pathlib import Path

# Series psid values from NVIDIA getMenuArrays (GeForce product lines at/above 900).
_NVIDIA_SERIES_PSIDS: tuple[tuple[str, str], ...] = (
    ("98", "GeForce 900 Series"),
    ("99", "GeForce 900M Series (Notebooks)"),
    ("101", "GeForce 10 Series"),
    ("102", "GeForce 10 Series (Notebooks)"),
    ("112", "GeForce 16 Series"),
    ("115", "GeForce GTX 16 Series (Notebooks)"),
    ("107", "GeForce RTX 20 Series"),
    ("111", "GeForce RTX 20 Series (Notebooks)"),
    ("120", "GeForce RTX 30 Series"),
    ("123", "GeForce RTX 30 Series (Notebooks)"),
    ("127", "GeForce RTX 40 Series"),
    ("129", "GeForce RTX 40 Series (Notebooks)"),
    ("131", "GeForce RTX 50 Series"),
    ("133", "GeForce RTX 50 Series (Notebooks)"),
)

# PCI DEV id (uppercase) -> (psid, pfid). Augments menu-API name matching.
_NVIDIA_PCI_DEV_PSID_PFID: dict[str, tuple[str, str]] = {
    # Maxwell (900)
    "13C0": ("98", "756"),
    "13C2": ("98", "756"),  # GTX 970
    "13C3": ("99", "757"),  # GTX 980M (notebook; pfid from 900M series)
    "1401": ("98", "764"),  # GTX 960
    "1402": ("98", "782"),  # GTX 950
    "1406": ("98", "764"),
    "1617": ("99", "757"),
    "1618": ("99", "760"),  # GTX 970M
    "17C2": ("98", "761"),  # Titan X
    "17C8": ("98", "755"),  # GTX 980
    "17FD": ("99", "757"),
    # Pascal (10)
    "1B80": ("101", "815"),  # GTX 1080
    "1B81": ("101", "815"),
    "1B82": ("101", "815"),
    "1C02": ("101", "816"),  # GTX 1070
    "1C03": ("101", "816"),
    "1C20": ("101", "816"),
    "1C60": ("101", "817"),  # GTX 1060 6GB
    "1C61": ("101", "818"),  # GTX 1060 3GB — verify against menu map
    "1C62": ("101", "817"),
    "1C82": ("101", "825"),  # GTX 1050 Ti
    "1C83": ("101", "826"),  # GTX 1050
    # Turing / Ampere / Ada (partial — name match preferred)
    "1F02": ("112", "879"),
    "2184": ("112", "885"),
    "2206": ("120", "929"),
    "2484": ("127", "942"),
    "2684": ("131", "942"),
}

# AMD: label patterns for supported floor (GCN 1.1+ / Polaris+).
_AMD_GPU_FLOOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bRX\s*(4[6-9]\d|5\d{2}|6\d{2}|7\d{2}|9\d{2})\b", re.I),
    re.compile(r"\bR9\s*(2\d{2}|3\d{2}|Fury)\b", re.I),
    re.compile(r"\bR7\s*(3[6-9]\d|370)\b", re.I),
    re.compile(r"\bVega\s*\d+", re.I),
    re.compile(r"\bRadeon\s*(Pro\s*)?(W\d{3,4}|VII)\b", re.I),
)

# Intel iGPU floor: Skylake HD 5xx / Iris 5xx and newer.
_INTEL_IGPU_FLOOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bArc\s", re.I),
    re.compile(r"\bIris\s*(Xe|Plus|Pro|Graphics)\b", re.I),
    re.compile(r"\bUHD\s*Graphics\s*(6[0-9]{2}|7[0-9]{2}|770)\b", re.I),
    re.compile(r"\bHD\s*Graphics\s*(5[3-9]\d|6[0-9]{2}|630)\b", re.I),
    re.compile(r"\bIris\s*(540|550|650)\b", re.I),
)


def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        for candidate in (base / "data", base / "_internal" / "data"):
            if candidate.is_dir():
                return candidate
    return Path(__file__).resolve().parent / "data"


def _http_get(url: str) -> tuple[bool, str]:
    try:
        import driver_catalog as dc

        return dc._http_get(url)
    except ImportError:
        return False, ""


@lru_cache(maxsize=1)
def _load_bundled_nvidia_products() -> list[dict]:
    path = _data_dir() / "nvidia_gpu_psid_pfid.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _fetch_nvidia_series_products(psid: str) -> list[dict]:
    """One JSON API call per series — not HTML, not bot-walled."""
    params = json.dumps(
        {"pt": 1, "pst": int(psid), "d4": 135, "d5": 1033, "driverType": "all"},
        separators=(",", ":"),
    )
    url = (
        "https://gfwsl.geforce.com/nvidia_web_services/controller.php?"
        "com.nvidia.services.Drivers.getMenuArrays/"
        + urllib.parse.quote(params)
    )
    ok, body = _http_get(url)
    if not ok or not body.strip():
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list) or len(data) < 3:
        return []
    products = data[2]
    if not isinstance(products, list):
        return []
    out: list[dict] = []
    for item in products:
        if not isinstance(item, dict):
            continue
        pfid = str(item.get("id") or "").strip()
        name = (item.get("menutext") or "").strip()
        if pfid and name:
            out.append({"psid": psid, "pfid": pfid, "product": name})
    return out


@lru_cache(maxsize=1)
def nvidia_product_catalog() -> list[dict]:
    """All supported NVIDIA GPU products (bundled JSON or live menu API)."""
    bundled = _load_bundled_nvidia_products()
    if bundled:
        return bundled
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for psid, _label in _NVIDIA_SERIES_PSIDS:
        for prod in _fetch_nvidia_series_products(psid):
            key = (prod["psid"], prod["pfid"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(prod)
    return rows


def _normalize_gpu_label(label: str) -> str:
    s = re.sub(r"\s+", " ", (label or "").strip().lower())
    s = re.sub(r"nvidia\s+", "", s)
    s = re.sub(r"\([^)]*\)", "", s).strip()
    return s


def _label_implies_notebook(label: str) -> bool:
    low = (label or "").lower()
    if re.search(r"\d+m(?:x|ax)?\b", low):
        return True
    return any(
        k in low
        for k in ("mobile", "notebook", " laptop", "laptop ", " max-q", " max q")
    )


def label_implies_notebook(label: str) -> bool:
    """Public wrapper for notebook/desktop GPU product disambiguation."""
    return _label_implies_notebook(label)


def nvidia_psid_pfid_from_label(label: str) -> tuple[str, str] | None:
    """Match device label to NVIDIA menu product (longest win)."""
    norm = _normalize_gpu_label(label)
    if not norm:
        return None
    notebook = _label_implies_notebook(label)
    best: tuple[int, str, str] | None = None
    for prod in nvidia_product_catalog():
        pname = _normalize_gpu_label(prod["product"])
        if not pname:
            continue
        is_notebook_prod = prod["psid"] in ("99", "102", "111", "115", "123", "129", "133") or any(
            k in pname for k in ("notebook", "mobile", " max-q")
        )
        if is_notebook_prod and not notebook:
            continue
        if notebook and not is_notebook_prod and pname.endswith("m"):
            continue
        if not notebook and re.search(r"\d+m\b", pname) and not re.search(
            rf"{re.escape(pname)}\b", norm
        ):
            continue
        if pname in norm or norm in pname:
            score = len(pname)
            if best is None or score > best[0]:
                best = (score, prod["psid"], prod["pfid"])
    return (best[1], best[2]) if best else None


def nvidia_psid_pfid_from_pci_dev(dev: str) -> tuple[str, str] | None:
    d = (dev or "").upper().strip()
    if not d:
        return None
    return _NVIDIA_PCI_DEV_PSID_PFID.get(d)


def nvidia_psid_pfid_candidates(
    *,
    device_label: str = "",
    pci_dev: str = "",
) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []

    def add(psid: str, pfid: str) -> None:
        pair = (psid, pfid)
        if pair not in seen:
            seen.add(pair)
            out.append(pair)

    hit = nvidia_psid_pfid_from_pci_dev(pci_dev)
    if hit:
        add(*hit)
    hit = nvidia_psid_pfid_from_label(device_label)
    if hit:
        add(*hit)
    # Legacy regex fallbacks (bundled map may be empty on first run)
    label = device_label or ""
    for pat, psid, pfid in _label_fallbacks():
        if pat.search(label):
            add(psid, pfid)
    add("131", "942")  # last-resort current GRD series
    return out


def _label_fallbacks() -> list[tuple[re.Pattern[str], str, str]]:
    return [
        (re.compile(r"\bgtx\s*980\b", re.I), "98", "755"),
        (re.compile(r"\bgtx\s*970\b", re.I), "98", "756"),
        (re.compile(r"\bgtx\s*960\b", re.I), "98", "764"),
        (re.compile(r"\bgtx\s*950\b", re.I), "98", "782"),
        (re.compile(r"\bgtx\s*1060\b", re.I), "101", "817"),
        (re.compile(r"\bgtx\s*1070\b", re.I), "101", "816"),
        (re.compile(r"\bgtx\s*1080\b", re.I), "101", "815"),
        (re.compile(r"\bgtx\s*1050\b", re.I), "101", "826"),
        (re.compile(r"\bgtx\s*16\d{2}\b", re.I), "112", "879"),
        (re.compile(r"\brtx\s*20\d{2}\b", re.I), "107", "948"),
        (re.compile(r"\brtx\s*30\d{2}\b", re.I), "120", "929"),
        (re.compile(r"\brtx\s*40\d{2}\b", re.I), "127", "942"),
        (re.compile(r"\brtx\s*50\d{2}\b", re.I), "131", "942"),
    ]


def nvidia_gpu_supported(device_label: str, pci_dev: str = "") -> bool:
    if nvidia_psid_pfid_from_pci_dev(pci_dev) or nvidia_psid_pfid_from_label(device_label):
        return True
    label = device_label or ""
    return any(pat.search(label) for pat, _, _ in _label_fallbacks())


def amd_gpu_supported(device_label: str) -> bool:
    label = device_label or ""
    return any(pat.search(label) for pat in _AMD_GPU_FLOOR_PATTERNS)


def intel_igpu_supported(device_label: str) -> bool:
    label = device_label or ""
    return any(pat.search(label) for pat in _INTEL_IGPU_FLOOR_PATTERNS)


def gpu_support_policy_summary() -> str:
    return (
        "Manufacturer GPU checks: NVIDIA GTX 900+, AMD R9/RX (GCN 1.1+), "
        "Intel HD 530 / Iris 540+."
    )


# ---------------------------------------------------------------------------
# AMD graphics — bundled product leaf URLs (P1)
# ---------------------------------------------------------------------------

_AMD_RX_FAMILY_RE = re.compile(
    r"\b(RX\s*\d{4}(?:\s*XTX|\s*XT|\s*GRE|\s*XL)?|R[79]\s*\d{3}|Vega\s*\d+)\b",
    re.I,
)


def _pci_dev_from_instance(instance_id: str) -> str:
    m = re.search(r"DEV_([0-9A-F]{4})", (instance_id or "").upper())
    return m.group(1) if m else ""


def _normalize_amd_title(title: str) -> str:
    s = re.sub(r"\s+", " ", (title or "").replace("\ufffd", "")).strip().lower()
    s = re.sub(r"amd\s+radeon\s*", "", s)
    s = re.sub(r"radeon\s*", "", s)
    return s


@lru_cache(maxsize=1)
def _load_bundled_amd_products() -> list[dict]:
    path = _data_dir() / "amd_gpu_product_urls.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        products = data.get("products") if isinstance(data, dict) else data
        return products if isinstance(products, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def amd_product_catalog() -> list[dict]:
    return _load_bundled_amd_products()


def amd_product_url_from_label(
    device_label: str,
    *,
    notebook: bool | None = None,
) -> str | None:
    """Best AMD graphics product leaf URL for a device label."""
    label = device_label or ""
    if notebook is None:
        notebook = _label_implies_notebook(label)
    norm = _normalize_gpu_label(label)
    amd_norm = _normalize_amd_title(label)
    family_m = _AMD_RX_FAMILY_RE.search(label)
    family = re.sub(r"\s+", " ", family_m.group(1)).strip().lower() if family_m else ""

    best: tuple[int, str] | None = None
    for prod in amd_product_catalog():
        url = (prod.get("url") or "").strip()
        title = prod.get("title") or ""
        if not url or not title:
            continue
        is_nb = bool(prod.get("notebook"))
        if notebook and not is_nb:
            continue
        if not notebook and is_nb and not _label_implies_notebook(title):
            continue
        title_norm = _normalize_amd_title(title)
        score = 0
        if family and family.replace(" ", "") in title_norm.replace(" ", ""):
            score = 100 + len(title_norm)
        elif amd_norm and (amd_norm in title_norm or title_norm in amd_norm):
            score = 80 + len(title_norm)
        elif norm and any(tok in title_norm for tok in norm.split() if len(tok) > 3):
            score = 40 + len(title_norm)
        if score <= 0:
            continue
        depth = int(prod.get("depth") or 0)
        score += depth * 5
        if best is None or score > best[0]:
            best = (score, url)
    return best[1] if best else None


def amd_product_url_for_ctx(
    *,
    device_label: str = "",
    instance_id: str = "",
    notebook: bool | None = None,
) -> str | None:
    """Resolve AMD graphics leaf URL from label (PCI DEV reserved for future map)."""
    _ = _pci_dev_from_instance(instance_id)
    return amd_product_url_from_label(device_label, notebook=notebook)


# ---------------------------------------------------------------------------
# Intel graphics — generation buckets (P1)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_intel_graphics_buckets() -> list[dict]:
    path = _data_dir() / "intel_graphics_products.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        buckets = data.get("buckets") if isinstance(data, dict) else data
        return buckets if isinstance(buckets, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def intel_graphics_buckets() -> list[dict]:
    return _load_intel_graphics_buckets()


def intel_graphics_bucket_id(
    device_label: str,
    *,
    pci_dev: str = "",
    instance_id: str = "",
) -> str:
    """Pick Intel graphics download bucket for this iGPU."""
    dev = (pci_dev or _pci_dev_from_instance(instance_id)).upper()
    label = device_label or ""
    label_l = label.lower()

    # Arc Pro before generic Arc
    if re.search(r"\barc\s*pro\b", label_l):
        return "arc_pro"

    for bucket in intel_graphics_buckets():
        bid = bucket.get("id") or ""
        for d in bucket.get("pci_dev") or []:
            if dev and str(d).upper() == dev:
                return bid

    for bucket in intel_graphics_buckets():
        bid = bucket.get("id") or ""
        for pat in bucket.get("label_patterns") or []:
            try:
                if re.search(pat, label, re.I):
                    return bid
            except re.error:
                continue

    # Default modern unified page for supported floor devices we couldn't classify
    if intel_igpu_supported(label):
        if re.search(r"\bArc\b", label, re.I):
            return "arc_modern"
        if re.search(r"\bUHD\s*Graphics\s*7", label, re.I):
            return "xe_11_14"
        return "legacy_dch"
    return "legacy_dch"


def intel_graphics_product_url(bucket_id: str) -> str:
    for bucket in intel_graphics_buckets():
        if bucket.get("id") == bucket_id:
            return (bucket.get("url") or "").strip()
    # Fallback to legacy DCH
    for bucket in intel_graphics_buckets():
        if bucket.get("id") == "legacy_dch":
            return (bucket.get("url") or "").strip()
    return (
        "https://www.intel.com/content/www/us/en/download/19344/"
        "intel-graphics-windows-dch-drivers.html"
    )


def intel_graphics_bucket_title(bucket_id: str) -> str:
    for bucket in intel_graphics_buckets():
        if bucket.get("id") == bucket_id:
            return (bucket.get("title") or bucket_id).strip()
    return bucket_id


def intel_graphics_cache_key(bucket_id: str) -> str:
    return f"intel:graphics:{bucket_id or 'legacy_dch'}"


def intel_graphics_version_applicable(
    *,
    device_label: str,
    bucket_id: str,
    installed_version: str,
    scraped_version: str,
) -> bool:
    """P3: gate 'newer' when scraped page targets a different Intel generation."""
    if not scraped_version:
        return False
    if not installed_version:
        return True
    inst = installed_version.strip()
    scraped = scraped_version.strip()
    label_l = (device_label or "").lower()

    # Arc unified 32.x must not upgrade legacy HD 6xx rows
    if bucket_id == "legacy_dch" and scraped.startswith("32."):
        if re.search(r"\bhd\s*graphics\s*[56]", label_l) or re.search(
            r"\buhd\s*graphics\s*6", label_l
        ):
            return False
    if bucket_id == "legacy_dch" and inst.startswith("31."):
        if scraped.startswith("32.") and not re.search(r"\barc\b", label_l):
            return False

    # Arc Pro bucket vs consumer label mismatch
    if bucket_id == "arc_pro" and not re.search(r"\barc\s*pro\b", label_l):
        return False
    if bucket_id != "arc_pro" and re.search(r"\barc\s*pro\b", label_l):
        return False

    return True
