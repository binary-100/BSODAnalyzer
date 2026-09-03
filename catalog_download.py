"""Driver package download and URL resolution (extracted from driver_catalog)."""

from __future__ import annotations

import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from catalog_http import _looks_like_html_payload, catalog_user_agent
from catalog_oem_live import (
    _DELL_DRIVER_ID_RE,
    _is_dell_driver_details_url,
    _resolve_dell_driver_download_url,
)


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


_CATALOG_BASE = "https://www.catalog.update.microsoft.com/Search.aspx?q="
_CATALOG_VIEW_BASE = (
    "https://www.catalog.update.microsoft.com/ScopedViewInline.aspx?updateid="
)
_DOWNLOAD_EXTENSIONS = (".exe", ".msi", ".cab", ".zip", ".inf", ".msu", ".7z")


def microsoft_catalog_view_url(offer: dict) -> str | None:
    """Browser URL for Microsoft Update Catalog package details."""
    uid = (offer.get("update_id") or "").strip()
    if uid:
        return f"{_CATALOG_VIEW_BASE}{uid}"
    url = (offer.get("url") or "").strip()
    if "catalog.update.microsoft.com" in url.lower():
        return url
    return None
def resolve_vendor_package_download_url(
    url: str,
    offer: dict | None = None,
) -> tuple[bool, str, str]:
    """Turn vendor/OEM web pages into direct package URLs when possible."""
    url = (url or "").strip()
    if not url:
        return False, "No download URL.", ""
    low_path = url.lower().split("?")[0]
    if any(low_path.endswith(ext) for ext in _DOWNLOAD_EXTENSIONS):
        return True, "", url
    if _is_dell_driver_details_url(url) or (
        "dell.com" in url.lower() and _DELL_DRIVER_ID_RE.search(url)
    ):
        return _resolve_dell_driver_download_url(url)
    try:
        import vendor_download_resolve as vdr

        ok, err, direct = vdr.resolve_vendor_package_download_url(url, offer)
        if ok and direct:
            return True, "", direct
        if err:
            return False, err, ""
    except ImportError:
        pass
    return False, "", ""
def _microsoft_catalog_url(title: str) -> str:
    q = urllib.parse.quote((title or "driver").strip()[:80])
    return f"{_CATALOG_BASE}{q}"
def _offer_download_kind(offer: dict) -> str:
    return (offer.get("download_kind") or offer.get("install_kind") or "url").strip()
def _filename_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    name = os.path.basename(path) or "driver_download"
    if not any(name.lower().endswith(ext) for ext in _DOWNLOAD_EXTENSIONS):
        name += ".exe"
    return re.sub(r'[<>:"/\\|?*]', "_", name)[:120]
def download_file_to_folder(url: str, folder: str | None = None) -> tuple[bool, str, str | None]:
    """Download a direct package URL into Downloads (or folder). Does not install."""
    folder = folder or os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, _filename_from_url(url))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": catalog_user_agent()})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        if _looks_like_html_payload(data):
            return (
                False,
                "Download returned a web page instead of a driver package. "
                "Open the vendor page in your browser and save the installer manually.",
                None,
            )
        with open(dest, "wb") as f:
            f.write(data)
        return (
            True,
            f"Saved to:\n{dest}",
            dest,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, f"Direct download failed: {e}", None
def download_driver_package_for_install(
    offer: dict,
    ctx: dict | None = None,
    *,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[bool, str, str | None]:
    """Download a driver package to disk for the unified Install driver flow."""
    del ctx  # reserved for future HWID-aware catalog picks

    def _progress(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    kind = _dc("_offer_download_kind")(offer)
    url = (offer.get("url") or "").strip()
    title = offer.get("title") or "driver"
    path = (offer.get("downloaded_path") or offer.get("local_package_path") or "").strip()
    if path and os.path.isfile(path):
        return True, f"Using downloaded package:\n{path}", path

    if kind == "catalog" or (
        kind == "url" and "catalog.update.microsoft.com" in url.lower()
    ):
        try:
            import catalog_ps_module as cps
        except ImportError:
            return False, "Microsoft Update Catalog module unavailable.", None
        _progress("Resolving Microsoft Update Catalog package…")
        update_id, err = cps.resolve_catalog_update_id(offer)
        if not update_id:
            return False, err or "Could not resolve catalog update ID.", None
        folder = os.path.join(
            os.path.expanduser("~"),
            "Downloads",
            "BSODAnalyzer_drivers",
            re.sub(r'[<>:"/\\|?*]', "_", title)[:50],
        )
        os.makedirs(folder, exist_ok=True)
        _progress("Downloading from Microsoft Update Catalog…")
        ok, msg, package = cps.download_mscatalog_package(update_id, folder)
        if ok and package:
            offer = dict(offer)
            offer["update_id"] = update_id
            return True, msg, package
        return False, msg or "Catalog download failed.", None

    if kind in ("optional_updates", "uri"):
        update_id = (offer.get("update_id") or "").strip()
        if update_id:
            return True, "Windows Update package ready (no file download needed).", None
        return (
            False,
            "No Windows Update package ID — open Optional updates in Settings.",
            None,
        )

    if kind == "url" and url:
        low = url.lower().split("?")[0]
        if any(low.endswith(ext) for ext in _DOWNLOAD_EXTENSIONS):
            _progress("Downloading driver package…")
            ok, msg, dest = download_file_to_folder(url)
            if ok and dest:
                return True, msg, dest
            return False, msg, None
        resolved_ok, resolved_err, direct_url = _dc("resolve_vendor_package_download_url")(
            url, offer
        )
        if resolved_ok and direct_url:
            _progress("Resolving vendor download link…")
            folder = os.path.join(
                os.path.expanduser("~"),
                "Downloads",
                "BSODAnalyzer_drivers",
                re.sub(r'[<>:"/\\|?*]', "_", title)[:50],
            )
            ok, msg, dest = download_file_to_folder(direct_url, folder=folder)
            if ok and dest:
                return True, msg, dest
            return False, msg or "Vendor download failed.", None
        return (
            False,
            resolved_err
            or "This link is a web page, not a direct download. "
            "Try Search for updates again or pick a row with a catalog package.",
            None,
        )

    return False, "No download link for this row.", None
def download_driver_offer(offer: dict, ctx: dict | None = None) -> tuple[bool, str, str | None]:
    """Open download page or save a direct package — never installs a driver."""
    kind = _dc("_offer_download_kind")(offer)
    url = (offer.get("url") or "").strip()
    title = offer.get("title") or "driver"

    if kind == "catalog":
        url = url or _microsoft_catalog_url(title)
        import webbrowser
        webbrowser.open(url)
        return True, (
            "Opened Microsoft Update Catalog in your browser.\n"
            "Download the package, then use Install from file… or Install selected package."
        ), None

    if kind in ("optional_updates", "uri"):
        target = url or "ms-settings:windowsupdate-optionalupdates"
        if sys.platform == "win32" and target.startswith("ms-"):
            os.startfile(target)  # type: ignore[attr-defined]
            return True, (
                "Opened Windows Update (optional updates).\n"
                "Select a row with a Windows Update package to use Install selected package, "
                "or download from the catalog first."
            ), None
        if target.startswith("http"):
            import webbrowser
            webbrowser.open(target)
            return True, "Opened the download page in your browser.", None
        return False, "No download link available.", None

    if kind == "url" and url:
        low = url.lower().split("?")[0]
        if any(low.endswith(ext) for ext in _DOWNLOAD_EXTENSIONS):
            ok, msg, path = download_file_to_folder(url)
            if ok:
                return True, msg, path
        import webbrowser
        webbrowser.open(url)
        return True, (
            f"Opened {offer.get('source_label', 'vendor')} download page in your browser.\n"
            "Save the package, then use Install from file… if you downloaded a .cab/.inf."
        ), None

    return False, "No download link for this row.", None
