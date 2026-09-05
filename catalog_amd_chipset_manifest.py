"""Fetch and cache AMD Chipset Software Info.xml for bundle_components on vendor offers."""

from __future__ import annotations

import json
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from amd_chipset_manifest import amd_info_products_to_bundle_components, parse_info_products

_CACHE_SUBDIR = "amd_chipset_manifest"
_INFO_XML_RE = re.compile(rb"<Products\b[\s\S]*?</Products>", re.I)
_PKG_URL_RE = re.compile(
    r"https?://[^\s\"'<>]+(?:\.exe|\.zip)(?:\?[^\s\"'<>]*)?",
    re.I,
)


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


def _version_cache_key(suite_version: str) -> str:
    safe = re.sub(r"[^\w.+-]", "_", (suite_version or "").strip()) or "unknown"
    return f"manifest_{safe}.json"


def manifest_cache_file(suite_version: str, *, system_ctx: dict | None = None) -> Path | None:
    try:
        import catalog_cache as ccat
    except ImportError:
        return None
    base = ccat._cache_dir(system_ctx=system_ctx)
    if not base:
        return None
    return base / _CACHE_SUBDIR / _version_cache_key(suite_version)


def load_cached_bundle_components(
    suite_version: str,
    *,
    system_ctx: dict | None = None,
) -> list[dict] | None:
    path = manifest_cache_file(suite_version, system_ctx=system_ctx)
    if not path or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    rows = data.get("bundle_components")
    return list(rows) if isinstance(rows, list) and rows else None


def save_cached_bundle_components(
    suite_version: str,
    components: list[dict],
    *,
    source_url: str = "",
    system_ctx: dict | None = None,
) -> None:
    path = manifest_cache_file(suite_version, system_ctx=system_ctx)
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "suite_version": suite_version,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": source_url,
        "bundle_components": components,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def extract_amd_chipset_download_url(html: str, page_url: str = "") -> str:
    """Best-effort direct package URL from an AMD chipset product page."""
    if not html:
        return ""
    import html as htmlmod

    text = htmlmod.unescape(html)
    candidates: list[str] = []
    for m in _PKG_URL_RE.finditer(text):
        url = m.group(0).rstrip("'\"")
        if "amd.com" in url.lower() or url.lower().startswith("http"):
            candidates.append(url)
    for pat in (
        r'"downloadUrl"\s*:\s*"([^"]+)"',
        r'"fileUrl"\s*:\s*"([^"]+)"',
        r'"href"\s*:\s*"([^"]+\.exe[^"]*)"',
    ):
        for m in re.finditer(pat, text, re.I):
            href = m.group(1).replace("\\/", "/")
            candidates.append(urllib.parse.urljoin(page_url or "", href))
    if not candidates:
        return ""
    seen: set[str] = set()
    ranked: list[tuple[int, str]] = []
    for url in candidates:
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        low = url.lower()
        score = 0
        if low.endswith(".exe"):
            score += 4
        if "chipset" in low:
            score += 3
        if "driver" in low or "download" in low:
            score += 2
        ranked.append((score, url))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return ranked[0][1] if ranked else ""


def _info_xml_bytes_from_archive(path: Path) -> bytes | None:
    data = path.read_bytes()
    m = _INFO_XML_RE.search(data)
    if m:
        return m.group(0)
    try:
        import bsod_runtime as rt
    except ImportError:
        rt = None
    if rt and rt.seven_zip_exe():
        with tempfile.TemporaryDirectory(prefix="bsod_amd_manifest_") as tmp:
            exe = rt.seven_zip_exe()
            import subprocess

            proc = subprocess.run(
                [exe, "x", str(path.resolve()), f"-o{tmp}", "-y"],
                capture_output=True,
                text=True,
                timeout=240,
            )
            if proc.returncode == 0:
                for info in Path(tmp).rglob("Info.xml"):
                    if info.is_file():
                        return info.read_bytes()
    return None


def bundle_components_from_package_path(path: str | Path) -> list[dict]:
    raw = _info_xml_bytes_from_archive(Path(path))
    if not raw:
        return []
    products = parse_info_products(raw, os_filter="Windows 11")
    return amd_info_products_to_bundle_components(products)


def _download_package(url: str, dest: Path, *, referer: str = "") -> bool:
    url = (url or "").strip()
    if not url:
        return False
    try:
        import vendor_download_resolve as vdr
    except ImportError:
        vdr = None
    direct = url
    if vdr and not vdr._path_is_package(url):
        ok, _, resolved = vdr.resolve_vendor_package_download_url(url)
        if ok and resolved:
            direct = resolved
    try:
        from catalog_http import _http_browser_headers, _looks_like_html_payload
    except ImportError:
        _http_browser_headers = lambda: {"User-Agent": "Mozilla/5.0"}  # noqa: E731
        _looks_like_html_payload = lambda _b: False  # noqa: E731
    headers = _http_browser_headers()
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(direct, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = resp.read()
        if _looks_like_html_payload(data):
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest.is_file() and dest.stat().st_size > 65536
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _best_chipset_leaf(ctx: dict) -> tuple[str, str, str] | None:
    """Return (suite_version, leaf_url, html) from AMD chipset hub leaves."""
    import catalog_amd_fetch as caf

    ok, html = _dc("_amd_http_get_robust")(caf._amd_drivers_download_url())
    if not ok or not html:
        ok, html = caf._amd_fetch_page_html(caf._amd_drivers_download_url())
    if not ok or not html:
        return None
    urls = caf._amd_chipset_leaf_urls(html)
    if not urls:
        return None
    urls.sort(key=caf._amd_chipset_leaf_priority, reverse=True)
    best_ver = ""
    best_url = ""
    best_html = ""
    for url in urls[:4]:
        ok_leaf, leaf_html = caf._amd_fetch_page_html(url)
        if not ok_leaf or not leaf_html:
            continue
        hit = _dc("_amd_version_from_html")(leaf_html, ctx)
        ver = (hit[0] or "").strip() if hit else ""
        if ver and (not best_ver or _dc("compare_versions")(best_ver, ver) in ("newer", "unknown")):
            best_ver = ver
            best_url = url
            best_html = leaf_html
    if best_ver and best_html:
        return best_ver, best_url, best_html
    return None


def fetch_amd_chipset_bundle_components(
    suite_version: str,
    ctx: dict | None = None,
    *,
    system_ctx: dict | None = None,
    force_refresh: bool = False,
) -> list[dict]:
    """
    Load or fetch AMD chipset bundle_components for a suite version.

    Uses on-disk cache under the catalog cache dir. Returns [] when unavailable
    (no 7-Zip, download blocked, quick-check mode, etc.).
    """
    ver = (suite_version or "").strip()
    if not ver:
        return []
    try:
        from catalog_mscatalog_session import is_quick_check_mode

        if is_quick_check_mode():
            return []
    except ImportError:
        pass
    if not force_refresh:
        cached = load_cached_bundle_components(ver, system_ctx=system_ctx)
        if cached:
            return cached
    ctx = dict(ctx or {})
    ctx.setdefault("hw_category", "chipset")
    ctx.setdefault("vendor_key", "amd")
    leaf = _best_chipset_leaf(ctx)
    if not leaf:
        return []
    _leaf_ver, leaf_url, leaf_html = leaf
    pkg_url = extract_amd_chipset_download_url(leaf_html, leaf_url)
    if not pkg_url:
        return []
    cache_dir = manifest_cache_file(ver, system_ctx=system_ctx)
    if not cache_dir:
        return []
    pkg_path = cache_dir.parent / f"pkg_{_version_cache_key(ver)}.exe"
    if not pkg_path.is_file() or force_refresh:
        if not _download_package(pkg_url, pkg_path, referer=leaf_url):
            return []
    components = bundle_components_from_package_path(pkg_path)
    if components:
        save_cached_bundle_components(ver, components, source_url=pkg_url, system_ctx=system_ctx)
    return components


__all__ = [
    "bundle_components_from_package_path",
    "extract_amd_chipset_download_url",
    "fetch_amd_chipset_bundle_components",
    "load_cached_bundle_components",
    "manifest_cache_file",
    "save_cached_bundle_components",
]
