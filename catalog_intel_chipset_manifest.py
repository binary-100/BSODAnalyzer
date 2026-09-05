"""Fetch and cache Intel Chipset INF package manifests for bundle_components on vendor offers."""

from __future__ import annotations

import json
import re
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from intel_chipset_manifest import intel_infs_to_bundle_components, read_infs_from_zip

_CACHE_SUBDIR = "intel_chipset_manifest"
_INTEL_REFERER = "https://www.intel.com/content/www/us/en/download-center/home.html"


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


def bundle_components_from_package_path(path: str | Path) -> list[dict]:
    pkg = Path(path)
    entries = read_infs_from_zip(pkg)
    if not entries:
        entries = _read_infs_from_archive(pkg)
    return intel_infs_to_bundle_components(entries)


def _read_infs_from_archive(path: Path) -> list[tuple[str, str]]:
    """Extract INF files via 7-Zip when the package is not a plain zip."""
    try:
        import bsod_runtime as rt
    except ImportError:
        return []
    if not rt.seven_zip_exe():
        return []
    import subprocess

    with tempfile.TemporaryDirectory(prefix="bsod_intel_manifest_") as tmp:
        exe = rt.seven_zip_exe()
        proc = subprocess.run(
            [exe, "x", str(path.resolve()), f"-o{tmp}", "-y"],
            capture_output=True,
            text=True,
            timeout=240,
        )
        if proc.returncode != 0:
            return []
        out: list[tuple[str, str]] = []
        for inf in Path(tmp).rglob("*.inf"):
            if not inf.is_file():
                continue
            try:
                out.append((str(inf.relative_to(tmp)), inf.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
        return out


def _download_package(url: str, dest: Path, *, referer: str = _INTEL_REFERER) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    try:
        import vendor_download_resolve as vdr
    except ImportError:
        vdr = None
    direct = url
    if vdr and not vdr._path_is_package(url):
        ok, _, resolved = vdr.resolve_intel_download_url(url)
        if ok and resolved:
            direct = resolved
    try:
        from catalog_http import _http_browser_headers, _looks_like_html_payload
    except ImportError:
        _http_browser_headers = lambda: {"User-Agent": "Mozilla/5.0"}  # noqa: E731
        _looks_like_html_payload = lambda _b: False  # noqa: E731
    headers = _http_browser_headers()
    headers["Referer"] = referer
    req = urllib.request.Request(direct, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = resp.read()
        if _looks_like_html_payload(data):
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest.is_file() and dest.stat().st_size > 4096
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _resolve_chipset_package_url(ctx: dict | None) -> tuple[str, str]:
    """Return (page_url, direct_package_url) for Intel chipset INF utility."""
    import catalog_intel_fetch as cif

    ver, _date, page_url, direct_url = cif._scrape_intel_driver_version("chipset", ctx=ctx)
    if not page_url and not direct_url:
        page_url = cif._intel_product_url("chipset", ctx=ctx)
    pkg_url = (direct_url or "").strip()
    if not pkg_url and page_url:
        ok, html, _method = cif._fetch_intel_page_html(page_url, hint="chipset")
        if ok and html:
            _ver, _date_s, installer = cif._parse_intel_download_html(html, hint="chipset")
            pkg_url, _verified = cif._intel_attach_direct_download(page_url, html, installer)
    return page_url or "", pkg_url


def fetch_intel_chipset_bundle_components(
    suite_version: str,
    ctx: dict | None = None,
    *,
    system_ctx: dict | None = None,
    force_refresh: bool = False,
) -> list[dict]:
    """
    Load or fetch Intel chipset bundle_components for a suite version.

    Returns [] when unavailable (quick-check mode, download blocked, etc.).
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
    ctx.setdefault("vendor_key", "intel")
    page_url, pkg_url = _resolve_chipset_package_url(ctx)
    if not pkg_url:
        return []
    cache_dir = manifest_cache_file(ver, system_ctx=system_ctx)
    if not cache_dir:
        return []
    ext = ".zip" if pkg_url.lower().split("?")[0].endswith(".zip") else ".exe"
    pkg_path = cache_dir.parent / f"pkg_{_version_cache_key(ver)}{ext}"
    if not pkg_path.is_file() or force_refresh:
        if not _download_package(pkg_url, pkg_path, referer=page_url or _INTEL_REFERER):
            return []
    components = bundle_components_from_package_path(pkg_path)
    if components:
        save_cached_bundle_components(ver, components, source_url=pkg_url, system_ctx=system_ctx)
    return components


__all__ = [
    "bundle_components_from_package_path",
    "fetch_intel_chipset_bundle_components",
    "load_cached_bundle_components",
    "manifest_cache_file",
    "save_cached_bundle_components",
]
