"""Resolve vendor download pages to direct package URLs (Realtek, Intel, …)."""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request

_REALTEK_TODOWNLOAD_RE = re.compile(
    r"realtek\.com/download/todownload\?",
    re.I,
)
_INTEL_MIRROR_RE = re.compile(
    r"https?://(?:downloadmirror\.intel\.com|intel\.com/content/dam)[^\s\"'<>]+\.(?:exe|zip)",
    re.I,
)
_INTEL_DETAILS_DL_RE = re.compile(
    r"https?://[^\s\"'<>]+\.(?:exe|zip)(?:\?[^\s\"'<>]*)?",
    re.I,
)
_PACKAGE_EXT = (".exe", ".zip", ".msi", ".7z", ".cab")


def _browser_headers() -> dict[str, str]:
    try:
        import driver_catalog as dc

        return dc._http_browser_headers()
    except ImportError:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }


def _path_is_package(url: str) -> bool:
    low = (url or "").lower().split("?")[0]
    return any(low.endswith(ext) for ext in _PACKAGE_EXT)


def _extract_package_url_from_html(html: str, base_url: str) -> str:
    for pat in (_INTEL_MIRROR_RE, _INTEL_DETAILS_DL_RE):
        m = pat.search(html or "")
        if m and _path_is_package(m.group(0)):
            return m.group(0).rstrip("'\"")
    m = re.search(r'href=["\']([^"\']+\.(?:exe|zip|msi))["\']', html or "", re.I)
    if m:
        href = urllib.parse.urljoin(base_url, m.group(1))
        if _path_is_package(href):
            return href
    return ""


def resolve_http_redirect_url(
    url: str,
    *,
    referer: str | None = None,
) -> tuple[bool, str]:
    """Follow redirects; return final URL if it looks like a downloadable package."""
    current = (url or "").strip()
    if not current:
        return False, ""
    if _path_is_package(current):
        return True, current
    headers = _browser_headers()
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(current, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            final = resp.geturl() or current
            ctype = (resp.getheader("Content-Type") or "").lower()
            if _path_is_package(final):
                return True, final
            if "application/zip" in ctype or "octet-stream" in ctype:
                return True, final
            if "text/html" not in ctype and "application/json" not in ctype:
                return True, final
            body = resp.read(131072).decode("utf-8", errors="replace")
            pkg = _extract_package_url_from_html(body, final)
            if pkg:
                return True, pkg
            return False, ""
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            loc = e.headers.get("Location") or e.headers.get("location") or ""
            if loc:
                return resolve_http_redirect_url(
                    urllib.parse.urljoin(current, loc),
                    referer=referer,
                )
        return False, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, ""


def resolve_realtek_download_url(url: str) -> tuple[bool, str, str]:
    """Resolve Realtek ToDownload or relative DownloadUrl to a direct package."""
    u = (url or "").strip()
    if not u:
        return False, "No download URL.", ""
    if _path_is_package(u):
        return True, "", u
    if u.startswith("/"):
        u = "https://www.realtek.com" + u
    if _REALTEK_TODOWNLOAD_RE.search(u) or "realtek.com/download" in u.lower():
        ok, final = resolve_http_redirect_url(
            u,
            referer="https://www.realtek.com/Download",
        )
        if ok and final:
            return True, "", final
        return False, "Realtek download page did not resolve to a direct package.", ""
    return False, "", ""


def extract_intel_direct_download_url(
    html: str,
    page_url: str = "",
    installer_filename: str = "",
) -> str:
    """Pull a direct Intel mirror/package URL from a product download page."""
    body = html or ""
    base = (page_url or "").strip()
    inst = (installer_filename or "").strip()
    if inst:
        pat = re.compile(
            rf'href=["\']([^"\']*{re.escape(inst)})["\']',
            re.I,
        )
        m = pat.search(body)
        if m:
            href = urllib.parse.urljoin(base, m.group(1))
            if _path_is_package(href):
                return href
        mirror = re.search(
            rf"(https?://downloadmirror\.intel\.com/[^\s\"'<>]*{re.escape(inst)})",
            body,
            re.I,
        )
        if mirror:
            return mirror.group(1).rstrip("'\"")
    return _extract_package_url_from_html(body, base)


def resolve_intel_download_url(url: str, *, html: str = "") -> tuple[bool, str, str]:
    """Extract direct Intel installer link from a product download page."""
    u = (url or "").strip()
    if not u:
        return False, "No download URL.", ""
    if _path_is_package(u):
        return True, "", u
    if html:
        pkg = extract_intel_direct_download_url(html, u)
        if pkg:
            return True, "", pkg
    if "intel.com" not in u.lower() and "downloadmirror.intel.com" not in u.lower():
        return False, "", ""
    ok, final = resolve_http_redirect_url(
        u,
        referer="https://www.intel.com/content/www/us/en/download-center/home.html",
    )
    if ok and final:
        return True, "", final
    return False, "Intel download page did not expose a direct installer link.", ""


def resolve_vendor_package_download_url(
    url: str,
    offer: dict | None = None,
) -> tuple[bool, str, str]:
    """Vendor resolver entry — Realtek and Intel (Dell stays in driver_catalog)."""
    u = (url or "").strip()
    if not u:
        return False, "No download URL.", ""
    if _path_is_package(u):
        return True, "", u
    label = ((offer or {}).get("source_label") or "").lower()
    title = ((offer or {}).get("title") or "").lower()
    if "realtek" in u.lower() or "realtek" in label or "realtek" in title:
        hit = resolve_realtek_download_url(u)
        if hit[0]:
            return hit
    if "intel" in u.lower() or "intel" in label:
        hit = resolve_intel_download_url(u)
        if hit[0]:
            return hit
    return False, "", ""
