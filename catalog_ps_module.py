"""
MSCatalogLTS portable bundling: local copy, PyInstaller bundle, and online update.

Mirrors the DebuggingTools/CDB pattern:
  1) Writable copy next to BSODAnalyzer.exe (USB-friendly)
  2) Read-only copy in _internal/ from PyInstaller
  3) Optional online update via PowerShell Gallery .nupkg (no winget)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import OrderedDict
from typing import Callable

try:
    from bsod_runtime import get_tool_dir, run_powershell, run_catalog_powershell
except ImportError:
    get_tool_dir = None  # type: ignore[assignment,misc]
    run_powershell = None  # type: ignore[assignment]
    run_catalog_powershell = None  # type: ignore[assignment,misc]


def _catalog_ps(script: str, timeout: int = 30) -> tuple[bool, str]:
    if run_catalog_powershell is not None:
        return run_catalog_powershell(script, timeout=timeout)
    if run_powershell is not None:
        return run_powershell(script, timeout=timeout)
    return False, "PowerShell unavailable"


# The Microsoft Update Catalog web search (Search.aspx?q=…) is a TITLE/TEXT search:
# raw hardware-ID strings (PCI\VEN_…, HDAUDIO\FUNC_…, …&DEV_…) never match a result
# ("WARNING: We did not find any results for …"). Firing them anyway costs a
# PowerShell spawn + HTTP round-trip (and a failed HTML fallback) per query — the
# dominant cost of a full driver scan. Detect and skip them so the scan finishes.
#
# This is the CANONICAL predicate: the single-search path here, the batch path in
# catalog_ps_batch, and the query builder in driver_catalog all import it so the
# HWID definition lives in exactly one place.
HWID_QUERY_PREFIXES = ("PCI\\", "HDAUDIO\\", "USB\\", "ACPI\\", "SWC\\", "HID\\", "SW\\")


def is_hwid_search(query: str) -> bool:
    """True for raw hardware-ID search strings (PCI\\…, HDAUDIO\\…, VEN_…/DEV_…)."""
    u = (query or "").strip().upper()
    if not u:
        return False
    if "VEN_" in u or "DEV_" in u:
        return True
    return u.startswith(HWID_QUERY_PREFIXES)


# Backwards-compatible private aliases (older internal references / patched tests).
_HWID_QUERY_PREFIXES = HWID_QUERY_PREFIXES
_is_hwid_search = is_hwid_search


def _extract_json_payload(text: str) -> str:
    """Isolate the JSON array/object from catalog output.

    MSCatalogLTS can emit a leading ``WARNING:``/``VERBOSE:`` line (its "no results"
    notice) on the warning stream, which ``-Command`` merges into stdout ahead of the
    ``[]`` payload. Strip anything before the first ``[``/``{`` so json.loads works
    even when the warning stream is not fully suppressed.
    """
    s = (text or "").strip()
    if not s:
        return ""
    if s[0] in "[{":
        return s
    for i, ch in enumerate(s):
        if ch in "[{":
            return s[i:].strip()
    return s

MSCATALOG_MODULE_NAME = "MSCatalogLTS"
MSCATALOG_PINNED_VERSION = "2.1.0.2"
MSCATALOG_GALLERY_ID = "MSCatalogLTS"
MSCATALOG_NUPKG_URL = (
    f"https://www.powershellgallery.com/api/v2/package/{MSCATALOG_GALLERY_ID}/"
    f"{MSCATALOG_PINNED_VERSION}"
)
MSCATALOG_FIND_URL = (
    "https://www.powershellgallery.com/api/v2/FindPackagesById()"
    f"?id='{MSCATALOG_GALLERY_ID}'"
)
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_DC_NS = "{http://purl.org/dc/elements/1.1/}"
_HTTP_TIMEOUT = 45
_GALLERY_CHECK_TTL_SEC = 86400.0
_SEARCH_CACHE_TTL_SEC = 900.0
_SEARCH_CACHE_MAX = 128
_ONLINE_CACHE_TTL_SEC = 60.0
_SESSION_LOCK = threading.Lock()
_online_cache_lock = threading.Lock()
_online_cache_result: bool | None = None
_online_cache_at: float = 0.0
_mscatalog_prepared = False
_mscatalog_gallery_checked_at = 0.0
_search_cache: OrderedDict[str, tuple[list[dict], float]] = OrderedDict()


def _probe_is_online() -> bool:
    """Uncached TCP reachability probe (up to 3 s)."""
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(("8.8.8.8", 53))
        sock.close()
        return True
    except (OSError, socket.error):
        return False


def _is_online() -> bool:
    """Quick network check; result cached ~60 s to avoid repeated 3 s socket probes."""
    global _online_cache_result, _online_cache_at
    now = time.monotonic()
    with _online_cache_lock:
        if (
            _online_cache_result is not None
            and (now - _online_cache_at) < _ONLINE_CACHE_TTL_SEC
        ):
            return _online_cache_result
        result = _probe_is_online()
        _online_cache_result = result
        _online_cache_at = time.monotonic()
        return result


def _tool_dir() -> str:
    if get_tool_dir is not None:
        return get_tool_dir()
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _repo_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _module_version_dir(version: str) -> str:
    return os.path.join(MSCATALOG_MODULE_NAME, version)


def _local_module_root() -> str:
    return os.path.join(_tool_dir(), "PowerShellModules")


def _local_module_dir(version: str = MSCATALOG_PINNED_VERSION) -> str:
    return os.path.join(_local_module_root(), _module_version_dir(version))


def _newest_local_module_dir() -> str | None:
    """Highest-version MSCatalogLTS folder beside the exe (may be newer than bundled)."""
    base = os.path.join(_local_module_root(), MSCATALOG_MODULE_NAME)
    if not os.path.isdir(base):
        return None
    best_ver = ""
    best_path: str | None = None
    try:
        names = os.listdir(base)
    except OSError:
        return None
    for name in names:
        path = os.path.join(base, name)
        psd1 = os.path.join(path, f"{MSCATALOG_MODULE_NAME}.psd1")
        if not os.path.isfile(psd1):
            continue
        ver = read_module_version(path) or name
        if not best_path or _version_gt(ver, best_ver):
            best_ver = ver
            best_path = path
    return best_path


def _prune_old_local_modules(keep_version: str) -> None:
    """Drop stale local module folders after a successful online upgrade."""
    base = os.path.join(_local_module_root(), MSCATALOG_MODULE_NAME)
    if not os.path.isdir(base):
        return
    try:
        names = os.listdir(base)
    except OSError:
        return
    for name in names:
        if name == keep_version:
            continue
        path = os.path.join(base, name)
        psd1 = os.path.join(path, f"{MSCATALOG_MODULE_NAME}.psd1")
        if not os.path.isfile(psd1):
            continue
        ver = read_module_version(path) or name
        if _version_gt(keep_version, ver):
            try:
                shutil.rmtree(path)
            except OSError:
                pass


def _bundled_module_candidates(version: str = MSCATALOG_PINNED_VERSION) -> list[str]:
    rel = os.path.join("PowerShellModules", _module_version_dir(version))
    candidates: list[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, rel))
    internal = os.path.join(_tool_dir(), "_internal", rel)
    candidates.append(internal)
    candidates.append(os.path.join(_repo_root(), rel))
    out: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        psd1 = os.path.join(path, f"{MSCATALOG_MODULE_NAME}.psd1")
        if os.path.isfile(psd1):
            out.append(path)
    return out


def read_module_version(module_dir: str) -> str:
    psd1 = os.path.join(module_dir, f"{MSCATALOG_MODULE_NAME}.psd1")
    if not os.path.isfile(psd1):
        return ""
    try:
        with open(psd1, encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read(4096)
    except OSError:
        return ""
    m = re.search(r"ModuleVersion\s*=\s*['\"]([^'\"]+)['\"]", text)
    return (m.group(1) if m else "").strip()


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for seg in (version or "").split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            break
    return tuple(parts)


def _version_gt(a: str, b: str) -> bool:
    ta = _parse_version_tuple(a)
    tb = _parse_version_tuple(b)
    n = max(len(ta), len(tb))
    ta = ta + (0,) * (n - len(ta))
    tb = tb + (0,) * (n - len(tb))
    return ta > tb


def resolve_active_module_dir() -> str | None:
    """Prefer newest writable local copy, then bundled/_internal/repo."""
    local = _newest_local_module_dir()
    if local:
        return local
    bundled = _bundled_module_candidates()
    return bundled[0] if bundled else None


def _copy_module_tree(src: str, dest: str) -> bool:
    if not os.path.isdir(src):
        return False
    try:
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns("_rels", "package", "*.nuspec", "[Content_Types].xml"),
        )
        return os.path.isfile(os.path.join(dest, f"{MSCATALOG_MODULE_NAME}.psd1"))
    except OSError:
        return False


def ensure_local_mscatalog_module() -> tuple[bool, str]:
    """Seed a writable local copy from the bundled module when none exists yet."""
    local = _newest_local_module_dir()
    if local:
        return True, local

    bundled_dirs = _bundled_module_candidates()
    if not bundled_dirs:
        return False, "MSCatalogLTS module not found (bundled or local)."

    dest = _local_module_dir(MSCATALOG_PINNED_VERSION)
    if _copy_module_tree(bundled_dirs[0], dest):
        return True, dest
    return True, bundled_dirs[0]


def prepare_mscatalog_module(
    *,
    check_online: bool = True,
    force_gallery_check: bool = False,
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Ensure MSCatalogLTS is ready; prefer a newer gallery build when online.

    Order:
      1) Seed local copy from bundle (offline-safe — never blocks on network)
      2) When online, download a newer PowerShell Gallery release if available
      3) Use the highest-version local folder for catalog searches
    """
    global _mscatalog_prepared, _mscatalog_gallery_checked_at

    with _SESSION_LOCK:
        ok, _seed = ensure_local_mscatalog_module()
        if not ok:
            bundled = _bundled_module_candidates()
            if not bundled:
                return False, "MSCatalogLTS not found"
            ok = True

        active = resolve_active_module_dir()
        if not active:
            return False, "MSCatalogLTS not found"

        now = time.monotonic()
        should_check = bool(
            check_online
            and _is_online()
            and _mscatalog_auto_update_enabled()
            and (
                force_gallery_check
                or not _mscatalog_prepared
                or (now - _mscatalog_gallery_checked_at) >= _GALLERY_CHECK_TTL_SEC
            )
        )
        if should_check:
            _mscatalog_gallery_checked_at = now
            upd_ok, _msg = update_mscatalog_module_if_online(progress=progress)
            if upd_ok:
                active = resolve_active_module_dir() or active

        _mscatalog_prepared = True
        return True, active


def reset_mscatalog_session() -> None:
    """Test helper — allow a fresh gallery check in the same process."""
    global _mscatalog_prepared, _mscatalog_gallery_checked_at
    global _online_cache_result, _online_cache_at
    with _SESSION_LOCK:
        _mscatalog_prepared = False
        _mscatalog_gallery_checked_at = 0.0
    with _online_cache_lock:
        _online_cache_result = None
        _online_cache_at = 0.0
    _search_cache.clear()


def _gallery_latest_version() -> str | None:
    req = urllib.request.Request(
        MSCATALOG_FIND_URL,
        headers={"User-Agent": "BSODAnalyzer/catalog-module-update"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            data = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    versions: list[str] = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        for child in entry:
            if child.tag == f"{_DC_NS}version":
                ver = (child.text or "").strip()
                if ver:
                    versions.append(ver)
    if not versions:
        return None
    return max(versions, key=lambda v: _parse_version_tuple(v) or (0,))


def _extract_nupkg(nupkg_path: str, dest_dir: str) -> bool:
    try:
        if os.path.isdir(dest_dir):
            shutil.rmtree(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)
        with zipfile.ZipFile(nupkg_path, "r") as zf:
            zf.extractall(dest_dir)
        for junk in ("_rels", "package", "[Content_Types].xml", f"{MSCATALOG_MODULE_NAME}.nuspec"):
            jp = os.path.join(dest_dir, junk)
            if os.path.isdir(jp):
                shutil.rmtree(jp, ignore_errors=True)
            elif os.path.isfile(jp):
                os.remove(jp)
        return os.path.isfile(os.path.join(dest_dir, f"{MSCATALOG_MODULE_NAME}.psd1"))
    except (OSError, zipfile.BadZipFile):
        return False


def _download_nupkg(version: str, dest_path: str) -> bool:
    url = (
        f"https://www.powershellgallery.com/api/v2/package/"
        f"{MSCATALOG_GALLERY_ID}/{version}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "BSODAnalyzer/catalog-module-update"})
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            data = resp.read()
        with open(dest_path, "wb") as fh:
            fh.write(data)
        return os.path.getsize(dest_path) > 1024
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def update_mscatalog_module_if_online(
    *,
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Download a newer MSCatalogLTS .nupkg when PowerShell Gallery has one."""
    if run_powershell is None:
        return False, "PowerShell unavailable."

    def say(msg: str) -> None:
        if progress:
            progress(msg)

    ok, _active = ensure_local_mscatalog_module()
    if not ok:
        return False, "MSCatalogLTS is not installed locally or bundled."
    current = read_module_version(resolve_active_module_dir() or "") or MSCATALOG_PINNED_VERSION

    say("Checking PowerShell Gallery for MSCatalogLTS updates…")
    latest = _gallery_latest_version()
    if not latest:
        return True, f"Could not query gallery; using MSCatalogLTS {current}."
    if not _version_gt(latest, current):
        return True, f"MSCatalogLTS is up to date ({current})."

    say(f"Downloading MSCatalogLTS {latest}…")
    import tempfile

    nupkg = os.path.join(tempfile.gettempdir(), f"{MSCATALOG_MODULE_NAME}.{latest}.nupkg")
    dest = _local_module_dir(latest)
    if not _download_nupkg(latest, nupkg):
        return False, f"Download failed; still using MSCatalogLTS {current}."
    if not _extract_nupkg(nupkg, dest):
        return False, f"Extract failed; still using MSCatalogLTS {current}."
    try:
        os.remove(nupkg)
    except OSError:
        pass
    _prune_old_local_modules(latest)
    return True, f"Updated MSCatalogLTS: {current} → {latest}."


def get_mscatalog_module_status() -> dict:
    ok, path = prepare_mscatalog_module(check_online=False)
    bundled = _bundled_module_candidates()
    gallery_latest = _gallery_latest_version() if _is_online() else None
    return {
        "available": bool(ok and path),
        "active_path": path or "",
        "version": read_module_version(path or "") if path else "",
        "pinned_version": MSCATALOG_PINNED_VERSION,
        "gallery_latest": gallery_latest or "",
        "online": _is_online(),
        "local_path": _local_module_root(),
        "local_exists": _newest_local_module_dir() is not None,
        "bundled_path": bundled[0] if bundled else "",
        "bundled_exists": bool(bundled),
        "auto_update_enabled": _mscatalog_auto_update_enabled(),
    }


def _ps_module_path_prefix(module_dir: str) -> str:
    parent = os.path.dirname(module_dir)
    return parent.replace("'", "''")


def probe_mscatalog_module() -> tuple[bool, str]:
    """Verify Import-Module and Get-MSCatalogUpdate work."""
    ok, path = prepare_mscatalog_module(check_online=False)
    if not ok or not path or run_powershell is None:
        return False, "MSCatalogLTS not available"
    prefix = _ps_module_path_prefix(path)
    ps = f"""
$ErrorActionPreference = 'Stop'
$env:PSModulePath = '{prefix}' + [IO.Path]::PathSeparator + $env:PSModulePath
Import-Module '{path.replace("'", "''")}\\{MSCATALOG_MODULE_NAME}.psd1' -Force
(Get-Command Get-MSCatalogUpdate).Source
"""
    ok2, out = _catalog_ps(ps, timeout=60)
    if ok2 and out.strip():
        return True, path
    return False, (out or "Import failed")[:200]


def _search_cache_get(key: str) -> list[dict] | None:
    hit = _search_cache.get(key)
    if not hit:
        return None
    rows, at = hit
    if (time.monotonic() - at) > _SEARCH_CACHE_TTL_SEC:
        _search_cache.pop(key, None)
        return None
    _search_cache.move_to_end(key)
    return list(rows)


def _search_cache_set(key: str, rows: list[dict]) -> None:
    _search_cache[key] = (list(rows), time.monotonic())
    while len(_search_cache) > _SEARCH_CACHE_MAX:
        _search_cache.popitem(last=False)


def _mscatalog_auto_update_enabled() -> bool:
    try:
        import app_settings as app_set

        return bool(app_set.load_settings().get("mscatalog_auto_update", True))
    except ImportError:
        return True


_CATALOG_SEARCH_BASE = "https://www.catalog.update.microsoft.com/Search.aspx?q="
_CATALOG_GOTODETAILS_RE = re.compile(
    r"goToDetails\s*\(\s*['\"]([0-9a-fA-F-]{36})['\"]",
    re.I,
)
_CATALOG_INLINE_ID_RE = re.compile(
    r"ScopedViewInline\.aspx\?updateid=([0-9a-fA-F-]{36})",
    re.I,
)


def parse_catalog_search_html(html: str, *, limit: int = 8) -> list[dict]:
    """Parse Microsoft Update Catalog search results without MSCatalogLTS."""
    if not html:
        return []
    rows: list[dict] = []
    seen: set[str] = set()

    def _append(uid: str, window: str) -> None:
        uid_l = uid.lower()
        if uid_l in seen:
            return
        seen.add(uid_l)
        title = "Catalog update"
        for pat in (
            r">([^<>]{10,220})<",
            r'title="([^"]{10,220})"',
        ):
            title_m = re.search(pat, window, re.I | re.S)
            if title_m:
                candidate = re.sub(r"\s+", " ", title_m.group(1)).strip()
                if len(candidate) >= 8 and not candidate.lower().startswith("javascript"):
                    title = candidate
                    break
        date_m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", window)
        rows.append({
            "title": title[:240],
            "version": _resolve_catalog_row_version({"Title": title}, title),
            "date": _normalize_catalog_date(date_m.group(1) if date_m else ""),
            "update_id": uid_l,
            "products": "",
            "classification": "",
            "size": "",
            "description": "",
            "file_names": [],
            "catalog_tier": _catalog_tier_from_title(title),
            "source": "microsoft_catalog_html",
        })

    for m in _CATALOG_GOTODETAILS_RE.finditer(html):
        _append(m.group(1), html[max(0, m.start() - 80): min(len(html), m.end() + 520)])
        if len(rows) >= limit:
            return rows[:limit]

    if len(rows) < limit:
        for m in _CATALOG_INLINE_ID_RE.finditer(html):
            _append(m.group(1), html[max(0, m.start() - 120): min(len(html), m.end() + 420)])
            if len(rows) >= limit:
                break

    return rows[:limit]


def search_catalog_html_fallback(
    search: str,
    *,
    limit: int = 8,
) -> tuple[list[dict], str]:
    """HTTP GET + Python HTML parse when MSCatalogLTS is unavailable."""
    from urllib.parse import quote_plus

    query = (search or "").strip()
    if not query:
        return [], "Empty search query"
    url = _CATALOG_SEARCH_BASE + quote_plus(query)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "BSODAnalyzer/catalog-html-search"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [], str(exc)[:200]
    rows = parse_catalog_search_html(html, limit=limit)
    return rows, "" if rows else "No catalog rows parsed from HTML"


def search_mscatalog_updates(
    search: str,
    *,
    limit: int = 8,
    timeout: int = 90,
    include_preview: bool = False,
    include_file_names: bool = True,
) -> tuple[list[dict], str]:
    """Search Microsoft Update Catalog via bundled MSCatalogLTS."""
    if run_powershell is None:
        return [], "PowerShell unavailable"
    query = (search or "").strip()
    if not query:
        return [], "Empty search query"

    # Hardware-ID strings never match the catalog web search — skip the network.
    if is_hwid_search(query):
        return [], ""

    cache_key = f"{query.lower()}:{int(limit)}"
    cached = _search_cache_get(cache_key)
    if cached is not None:
        return cached, ""

    ok, path = prepare_mscatalog_module(check_online=False)
    if not ok or not path:
        return [], "MSCatalogLTS module not available"

    safe_query = query.replace("'", "''")
    prefix = _ps_module_path_prefix(path)
    preview_flag = "$true" if include_preview else "$false"
    file_flag = "$true" if include_file_names else "$false"
    ps = f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$InformationPreference = 'SilentlyContinue'
$env:PSModulePath = '{prefix}' + [IO.Path]::PathSeparator + $env:PSModulePath
Import-Module '{path.replace("'", "''")}\\{MSCATALOG_MODULE_NAME}.psd1' -Force -WarningAction SilentlyContinue
$params = @{{
  Search = '{safe_query}'
  IncludePreview = {preview_flag}
  WarningAction = 'SilentlyContinue'
}}
if ({file_flag}) {{ $params['IncludeFileNames'] = $true }}
$rows = @(Get-MSCatalogUpdate @params | Select-Object -First {int(limit)} Title, LastUpdated, Guid, UpdateID, Products, Classification, Size, Description, Version, FileNames)
if (-not $rows) {{ '[]' }} else {{ $rows | ConvertTo-Json -Compress -Depth 5 }}
"""
    ok2, out = _catalog_ps(ps, timeout=timeout)
    if not ok2:
        html_rows, _html_err = search_catalog_html_fallback(query, limit=limit)
        if html_rows:
            _search_cache_set(cache_key, html_rows)
            return html_rows, ""
        return [], (out or "Catalog search failed.")[:300]
    text = _extract_json_payload(out)
    if not text or text.lower() == "null":
        html_rows, _html_err = search_catalog_html_fallback(query, limit=limit)
        if html_rows:
            _search_cache_set(cache_key, html_rows)
            return html_rows, ""
        return [], ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        html_rows, _html_err = search_catalog_html_fallback(query, limit=limit)
        if html_rows:
            _search_cache_set(cache_key, html_rows)
            return html_rows, ""
        return [], "Could not parse MSCatalogLTS output."
    if isinstance(data, dict):
        data = [data]
    rows: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        title = (row.get("Title") or "").strip()
        if not title:
            continue
        last = row.get("LastUpdated") or ""
        if hasattr(last, "isoformat"):
            last = last.isoformat()
        rows.append({
            "title": title[:240],
            "version": _resolve_catalog_row_version(row, title),
            "date": _normalize_catalog_date(str(last)),
            "update_id": catalog_update_id_from_row(row),
            "products": row.get("Products") or "",
            "classification": (row.get("Classification") or "").strip(),
            "size": (row.get("Size") or "").strip(),
            "description": (row.get("Description") or "").strip()[:400],
            "file_names": _normalize_catalog_file_names(row.get("FileNames")),
            "catalog_tier": _catalog_tier_from_title(title),
            "source": "microsoft_catalog",
        })
    _search_cache_set(cache_key, rows)
    return rows, ""


def _extract_version_from_catalog_title(title: str) -> str:
    t = title or ""
    for pat in (
        r"(\d+\.\d+\.\d+\.\d+)",
        r"(\d+\.\d+\.\d+)",
        r"(\d{4}\.\d+\.\d+\.\d{4})",
        r"(\d+\.\d+\.\d+\.\d{4})",
    ):
        m = re.search(pat, t)
        if m:
            return m.group(1)
    return ""


def _normalize_catalog_file_names(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _extract_version_from_catalog_description(description: str) -> str:
    text = description or ""
    for pat in (
        r"DriverVer(?:sion)?\s*[=:]\s*([\d.]+)",
        r"Version\s*[=:]\s*([\d.]+)",
        r"(\d+\.\d+\.\d+\.\d+)",
    ):
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return ""


def _extract_version_from_catalog_filenames(filenames: list[str]) -> str:
    for name in filenames:
        for pat in (
            r"(\d+\.\d+\.\d+\.\d+)",
            r"(\d+\.\d+\.\d+)",
            r"(\d{4}\.\d+\.\d+\.\d{4})",
        ):
            m = re.search(pat, name)
            if m:
                return m.group(1)
    return ""


def _catalog_tier_from_title(title: str) -> str:
    t = (title or "").lower()
    if re.search(r"\bpreview\b", t):
        return "preview"
    if re.search(r"\bwhql\b", t):
        return "whql"
    return "standard"


def _resolve_catalog_row_version(row: dict, title: str) -> str:
    for key in ("Version", "version"):
        ver = str(row.get(key) or "").strip()
        if ver and re.search(r"\d", ver):
            return ver
    ver = _extract_version_from_catalog_title(title)
    if ver:
        return ver
    ver = _extract_version_from_catalog_description(str(row.get("Description") or ""))
    if ver:
        return ver
    return _extract_version_from_catalog_filenames(
        _normalize_catalog_file_names(row.get("FileNames"))
    )


def _normalize_catalog_date(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    m_dotnet = re.search(r"/Date\((\d+)\)/?", s)
    if m_dotnet:
        try:
            ms = int(m_dotnet.group(1))
            if ms < 1_000_000_000_000:
                ms *= 1000
            from datetime import datetime, timezone

            return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )
        except (ValueError, OSError):
            pass
    try:
        from bsod_hardware_wmi import _parse_json_date
    except ImportError:
        _parse_json_date = lambda x: x or ""  # type: ignore[assignment, misc]
    parsed = (_parse_json_date(s) or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", parsed):
        return parsed[:10]
    m = re.match(r"(\d{1,2}/\d{1,2}/\d{4})", s)
    if m:
        parts = m.group(1).split("/")
        if len(parts) == 3:
            return f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"
    m2 = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m2:
        return m2.group(1)
    return ""


_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def is_catalog_update_guid(value: str) -> bool:
    s = (value or "").strip().strip("{}")
    return bool(_GUID_RE.match(s))


def catalog_update_id_from_row(row: dict) -> str:
    """Extract a catalog update GUID from MSCatalogLTS JSON or normalized rows."""
    for key in ("UpdateID", "UpdateId", "Guid", "update_id", "updateId"):
        raw = row.get(key)
        if raw is None:
            continue
        s = str(raw).strip().strip("{}")
        if is_catalog_update_guid(s):
            return s
    return ""


def catalog_update_id_from_url(url: str) -> str:
    m = re.search(
        r"[?&]updateid=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        (url or ""),
        re.I,
    )
    return m.group(1) if m else ""


def _pick_catalog_row_for_offer(rows: list[dict], offer: dict) -> dict | None:
    """Choose the best catalog row when several share the same search title."""
    title = (offer.get("title") or "").strip().lower()
    ver = (offer.get("version") or "").strip()
    best: dict | None = None
    best_score = -1
    for row in rows:
        uid = (row.get("update_id") or "").strip()
        if not is_catalog_update_guid(uid):
            continue
        row_title = (row.get("title") or "").strip().lower()
        row_ver = (row.get("version") or "").strip()
        score = 0
        if title and (title == row_title or title in row_title or row_title in title):
            score += 12
        if ver and row_ver == ver:
            score += 24
        elif ver and ver in row_title:
            score += 16
        products = (row.get("products") or "").lower()
        files = " ".join(row.get("file_names") or []).lower()
        blob = f"{products} {files} {row_title}"
        if "amd64" in blob or "x64" in blob or "64-bit" in blob:
            score += 6
        if "arm64" in blob and "amd64" not in blob and "x64" not in blob:
            score -= 8
        if offer.get("hwid_matched"):
            score += 4
        if score > best_score:
            best_score = score
            best = row
    if best:
        return best
    for row in rows:
        uid = (row.get("update_id") or "").strip()
        if is_catalog_update_guid(uid):
            return row
    return None


def resolve_catalog_update_id(offer: dict) -> tuple[str, str]:
    """Return (update_id, error). Resolves missing IDs via catalog search."""
    uid = catalog_update_id_from_row(offer) or catalog_update_id_from_url(
        (offer.get("url") or "").strip()
    )
    if is_catalog_update_guid(uid):
        return uid, ""
    title = (offer.get("title") or "").strip()
    if not title:
        return "", "No Microsoft Update Catalog ID or package title to download."
    rows, err = search_mscatalog_updates(title, limit=12)
    if not rows:
        html_rows, _html_err = search_catalog_html_fallback(title, limit=12)
        rows = html_rows
    if not rows:
        return "", err or "Microsoft Update Catalog search returned no packages."
    picked = _pick_catalog_row_for_offer(rows, offer)
    if not picked:
        return "", "Could not resolve a catalog package ID for this row."
    resolved = (picked.get("update_id") or "").strip()
    if not is_catalog_update_guid(resolved):
        return "", "Catalog search did not return a usable update ID."
    return resolved, ""


def download_mscatalog_package(
    update_id: str,
    dest_folder: str,
    *,
    timeout: int = 600,
) -> tuple[bool, str, str | None]:
    """Download one catalog update (.cab/.msu/.exe) into dest_folder."""
    uid = (update_id or "").strip()
    if not is_catalog_update_guid(uid):
        return False, "Invalid Microsoft Update Catalog ID.", None
    if run_powershell is None:
        return False, "PowerShell not available.", None
    ok, path = prepare_mscatalog_module(check_online=False)
    if not ok or not path:
        return False, "MSCatalogLTS module not available.", None
    os.makedirs(dest_folder, exist_ok=True)
    prefix = _ps_module_path_prefix(path)
    uid_esc = uid.replace("'", "''")
    dest_esc = dest_folder.replace("'", "''")
    ps = f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$env:PSModulePath = '{prefix}' + [IO.Path]::PathSeparator + $env:PSModulePath
Import-Module '{path.replace("'", "''")}\\{MSCATALOG_MODULE_NAME}.psd1' -Force -WarningAction SilentlyContinue
Save-MSCatalogUpdate -Guid '{uid_esc}' -Destination '{dest_esc}' -Force | Out-String
$files = @(Get-ChildItem -Path '{dest_esc}' -File -Recurse |
  Where-Object {{ $_.Extension -match '\\.(cab|msu|exe|msi|zip|inf)$' }} |
  Sort-Object LastWriteTime -Descending)
if (-not $files) {{ throw 'Catalog download finished but no driver package was found.' }}
$files[0].FullName
"""
    ok2, out = _catalog_ps(ps, timeout=timeout)
    if not ok2:
        return False, (out or "Catalog download failed.")[:500], None
    package = (out or "").strip().splitlines()
    package_path = ""
    for line in reversed(package):
        line = line.strip().strip('"')
        if line and os.path.isfile(line):
            package_path = line
            break
    if not package_path:
        return False, "Catalog download finished but no package file was found.", None
    return True, f"Downloaded catalog package:\n{package_path}", package_path
