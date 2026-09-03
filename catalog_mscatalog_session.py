"""GUI catalog session flags, MSCatalog batch cache, and online/WU store warm (extracted)."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from collections import OrderedDict
from typing import Callable


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_WU_DRIVER_ROWS_CACHE: list[dict] | None = None

_WU_DRIVER_CACHE_AT: float = 0.0

_WU_DRIVER_CACHE_TTL_SEC = 300.0

_SESSION_ROWS_CAP = 8000

_last_session_rows_truncated = False

_last_session_rows_original_count = 0

_ONLINE_DRIVER_STORE_CACHE: list[dict] | None = None

_ONLINE_DRIVER_STORE_CACHE_AT: float = 0.0

_ONLINE_DRIVER_STORE_CACHE_TTL_SEC = 3600.0

_ONLINE_DRIVER_STORE_LOCK = threading.Lock()

_ONLINE_DRIVER_STORE_CLASS_BUCKETS: dict[str, list[dict]] | None = None

_PNP_TO_STORE_CLASSES = {
    "display": ("display",),
    "net": ("net", "netclient", "nettrans", "netservice"),
    "media": ("media", "audio", "sound"),
    "bluetooth": ("bluetooth",),
    "camera": ("camera", "image"),
    "usb": ("usb", "usbcontroller"),
    "scsiadapter": ("scsiadapter", "hdc", "diskdrive"),
}

_PNPSIGNED_DRIVER_CACHE: list[dict] | None = None

_PNPSIGNED_DRIVER_CACHE_AT: float = 0.0

_PNPSIGNED_DRIVER_CACHE_TTL_SEC = 600.0

_quick_check_mode = False

_GUI_BATCH_MAX_WORKERS = 6

_GUI_DEVICE_SCAN_BATCH_SIZE = 12

_GUI_ONLINE_HWID_WARM_BATCH_SIZE = 10

_GUI_BATCH_INTER_PAUSE_SEC = 0.1

_GUI_APPLICATION_MODE = False

_GUI_ONLINE_WARM_DEPTH = 0

_GUI_ONLINE_WARM_LOCK = threading.Lock()

_catalog_include_preview = False

_ONLINE_HWID_STORE_CACHE: OrderedDict[str, tuple[list[dict], float]] = OrderedDict()

_ONLINE_HWID_STORE_CACHE_TTL_SEC = 900.0

_ONLINE_HWID_STORE_CACHE_MAX = 96

_ONLINE_STORE_ALL_TIMEOUT_SEC = 180

_ONLINE_STORE_ALL_LOAD_LOCK = threading.Lock()

_BATCH_MSCATALOG_QUERY_CACHE: dict[str, tuple[list[dict], str]] = {}

_BATCH_MSCATALOG_LOCK = threading.Lock()

_INSTALL_PROBE_CACHE: dict[str, dict[str, object]] = {}

_GUI_CATALOG_SESSION_DEPTH = 0

_GUI_CATALOG_SESSION_LOCK = threading.Lock()

def _cap_session_rows(rows: list[dict]) -> list[dict]:
    global _last_session_rows_truncated, _last_session_rows_original_count
    n = len(rows)
    if n <= _SESSION_ROWS_CAP:
        _last_session_rows_truncated = False
        _last_session_rows_original_count = n
        return rows
    _last_session_rows_truncated = True
    _last_session_rows_original_count = n
    return rows[:_SESSION_ROWS_CAP]

def peek_session_rows_truncated() -> tuple[bool, int]:
    """Return (was_truncated, original_row_count) from the last cap application."""
    return _last_session_rows_truncated, _last_session_rows_original_count

def set_gui_application_mode(active: bool) -> None:
    """BSODAnalyzer.exe — skip Get-WindowsDriver -Online -All for process lifetime."""
    global _GUI_APPLICATION_MODE
    _GUI_APPLICATION_MODE = bool(active)

def set_gui_catalog_session(active: bool) -> None:
    """Enter/leave GUI worker scope — blocks Get-WindowsDriver -Online -All."""
    global _GUI_CATALOG_SESSION_DEPTH
    with _GUI_CATALOG_SESSION_LOCK:
        if active:
            _GUI_CATALOG_SESSION_DEPTH += 1
        else:
            _GUI_CATALOG_SESSION_DEPTH = max(0, _GUI_CATALOG_SESSION_DEPTH - 1)

def _gui_catalog_session_active() -> bool:
    with _GUI_CATALOG_SESSION_LOCK:
        return _GUI_CATALOG_SESSION_DEPTH > 0

def _gui_catalog_mode(system_ctx: dict | None) -> bool:
    return bool((system_ctx or {}).get("_gui_driver_catalog"))

def _gui_online_store_warm_active() -> bool:
    with _GUI_ONLINE_WARM_LOCK:
        return _GUI_ONLINE_WARM_DEPTH > 0

def _gui_catalog_parallel_workers() -> int:
    """Cap parallel device workers in GUI scans (lower = more stable under heavy catalog I/O)."""
    try:
        import app_settings as app_set

        raw = app_set.load_settings().get("gui_catalog_parallel_workers", 6)
        n = int(raw)
    except (ImportError, ValueError, TypeError):
        n = 6
    return max(1, min(_GUI_BATCH_MAX_WORKERS, n))

def _gui_batched_online_store_enabled() -> bool:
    try:
        import app_settings as app_set

        return bool(app_set.load_settings().get("gui_batched_online_store", True))
    except ImportError:
        return True

def _gui_batched_online_store_include_all() -> bool:
    try:
        import app_settings as app_set

        return bool(
            app_set.load_settings().get("gui_batched_online_store_include_all", True)
        )
    except ImportError:
        return True

def _gui_mscatalog_prewarm_enabled() -> bool:
    """Upfront MSCatalog query warm — off by default (417+ sequential PS calls ≈ 1 hr)."""
    try:
        import app_settings as app_set

        return bool(app_set.load_settings().get("gui_mscatalog_prewarm", False))
    except ImportError:
        return False

def _gui_mscatalog_batched_parallel_enabled() -> bool:
    """Run the batch's unique MSCatalog searches in ONE PowerShell process with
    bounded internal parallelism (pwsh 7) instead of one serialized subprocess
    per query. On by default — main catalog-scan speed-up (parallel batch warm)."""
    try:
        import app_settings as app_set

        return bool(app_set.load_settings().get("gui_mscatalog_batched_parallel", True))
    except ImportError:
        return True

def _gui_mscatalog_parallel_throttle() -> int:
    """Concurrent catalog queries inside the single batched process (4-6 is safe)."""
    try:
        import app_settings as app_set

        n = int(app_set.load_settings().get("gui_mscatalog_parallel_throttle", 6))
    except (ImportError, ValueError, TypeError):
        n = 6
    return max(1, min(12, n))

def _gui_mscatalog_parallel_chunk() -> int:
    """Queries per parallel sub-batch. Smaller chunks keep the progress bar and
    status field moving (each chunk emits a `searched N/total` update) instead of
    freezing on one message for the whole multi-minute run, and let partial
    results seed the cache if a later chunk fails."""
    try:
        import app_settings as app_set

        n = int(app_set.load_settings().get("gui_mscatalog_parallel_chunk", 24))
    except (ImportError, ValueError, TypeError):
        n = 24
    try:
        import bsod_runtime as rt

        if rt.system_on_battery_power():
            # Smaller batches finish inside the timeout budget on slower battery links.
            n = min(n, 12)
    except ImportError:
        pass
    return max(4, min(60, n))

def _peek_online_driver_store_cache() -> list[dict]:
    """Return warmed full online store rows without triggering a fetch."""
    now = time.monotonic()
    if (
        _ONLINE_DRIVER_STORE_CACHE is not None
        and (now - _ONLINE_DRIVER_STORE_CACHE_AT) < _ONLINE_DRIVER_STORE_CACHE_TTL_SEC
    ):
        return list(_ONLINE_DRIVER_STORE_CACHE)
    return []

def _unique_hwids_from_device_contexts(contexts: dict[str, dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ctx in contexts.values():
        if _dc('_is_primary_gpu_display_manufacturer_authoritative')(ctx):
            continue
        for hwid in _online_store_hwid_candidates(ctx):
            key = hwid.upper()
            if key in seen:
                continue
            seen.add(key)
            out.append(hwid)
    return out

def _device_contexts_missing_hwid(contexts: dict[str, dict]) -> bool:
    return any(not _online_store_hwid_candidates(ctx) for ctx in contexts.values())

def begin_batch_mscatalog_query_cache() -> None:
    """Reset per-scan MSCatalog query dedup (shared across parallel device workers).

    Clears in place: driver_catalog re-exports this dict by reference, and
    catalog_microsoft_fetch reads it through that facade. Rebinding the global left
    those readers pointed at a dict that never received the warmed queries, so
    _warm_gap_mscatalog_queries re-issued batches that were already cached.
    """
    with _BATCH_MSCATALOG_LOCK:
        _BATCH_MSCATALOG_QUERY_CACHE.clear()
    clear_install_probe_cache()

def clear_batch_mscatalog_query_cache() -> None:
    with _BATCH_MSCATALOG_LOCK:
        _BATCH_MSCATALOG_QUERY_CACHE.clear()
    clear_install_probe_cache()

def clear_install_probe_cache() -> None:
    """Reset per-scan vendor/OEM install-path probe results."""
    _INSTALL_PROBE_CACHE.clear()

def _lazy_load_online_driver_store_all(
    progress: Callable[[str], None] | None = None,
) -> tuple[list[dict], str]:
    """
    Load Get-WindowsDriver -Online -All on demand for no-HWID devices.

    Disabled during GUI catalog scans — -All can hang indefinitely on some systems
    and blocks all parallel device workers when triggered from no-HWID USB/HID devices.
    """
    cached = _peek_online_driver_store_cache()
    if cached:
        return cached, ""
    if _dc('_should_skip_online_driver_store')() or _dc('_gui_catalog_session_active')():
        return [], "Full online catalog disabled during GUI catalog scan."
    if not _dc('_gui_batched_online_store_include_all')():
        return [], "Full online catalog disabled in settings."
    with _ONLINE_STORE_ALL_LOAD_LOCK:
        cached = _peek_online_driver_store_cache()
        if cached:
            return cached, ""
        if progress:
            progress(
                "Microsoft online catalog: loading full catalog for devices without "
                "a hardware ID (may take 1–2 min)…"
            )
        rows, err = _get_cached_online_driver_store_rows()
        if progress and rows:
            progress(f"Microsoft online catalog ready ({len(rows)} package(s)).")
        elif progress and err:
            progress(f"Microsoft online catalog unavailable: {err[:100]}")
        return rows, err

def warm_batched_microsoft_online_store(
    device_contexts: dict[str, dict],
    system_ctx: dict | None,
    progress: Callable[[str], None] | None = None,
) -> None:
    """
    Pre-load Microsoft Get-WindowsDriver -Online data in stable batches before device checks.

    Phase 1: per-HWID lookups in batched PowerShell sessions (GUI-safe).
    Phase 2: if any device lacks a hardware ID, load Get-WindowsDriver -Online -All
    once here (before parallel device checks) instead of mid-scan.
    """
    if not _dc('_v6_catalog_enabled')() or not _gui_catalog_mode(system_ctx):
        return
    if is_quick_check_mode() or not _gui_batched_online_store_enabled():
        return
    if not device_contexts:
        return

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    hwids = _unique_hwids_from_device_contexts(device_contexts)
    now = time.monotonic()
    pending: list[str] = []
    for hwid in hwids:
        key = hwid.upper()
        hit = _ONLINE_HWID_STORE_CACHE.get(key)
        if hit and (now - hit[1]) < _ONLINE_HWID_STORE_CACHE_TTL_SEC:
            continue
        pending.append(hwid)

    if pending:
        batch_size = max(1, _GUI_ONLINE_HWID_WARM_BATCH_SIZE)
        batches = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
        prog(
            f"Microsoft online catalog: warming {len(pending)} hardware ID(s) "
            f"in {len(batches)} batch(es)…"
        )
        for bi, batch in enumerate(batches, 1):
            prog(f"Microsoft online catalog: HWID batch {bi}/{len(batches)}…")
            batch_results = _dc('_fetch_online_driver_store_for_hwids_batch')(batch)
            now_mono = time.monotonic()
            for hwid in batch:
                rows, _err = batch_results.get(hwid.upper(), ([], ""))
                if rows:
                    _dc('_lru_cache_set')(
                        _ONLINE_HWID_STORE_CACHE,
                        hwid.upper(),
                        (rows, now_mono),
                        max_entries=_ONLINE_HWID_STORE_CACHE_MAX,
                    )
            if bi < len(batches) and _GUI_BATCH_INTER_PAUSE_SEC > 0:
                time.sleep(_GUI_BATCH_INTER_PAUSE_SEC)

def _unique_mscatalog_queries_from_device_contexts(
    contexts: dict[str, dict],
) -> list[str]:
    """Union of MSCatalog search strings for a batch (deduped, stable order)."""
    seen: set[str] = set()
    out: list[str] = []
    for ctx in contexts.values():
        if _dc('_is_primary_gpu_display_manufacturer_authoritative')(ctx):
            continue
        for query in _dc('_catalog_search_queries_for_ctx')(ctx):
            key = query.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(query.strip())
    return out

def warm_batched_mscatalog_queries(
    device_contexts: dict[str, dict],
    progress: Callable[[str], None] | None = None,
) -> None:
    """Pre-run unique MSCatalog searches once per batch before parallel device checks.

    When gui_mscatalog_batched_parallel is on (default), all unique searches
    run in ONE PowerShell process with bounded internal parallelism, seeding the
    per-scan cache so per-device catalog lookups become cache hits. Falls back to
    the legacy one-subprocess-per-query loop when parallel is off/unavailable.
    """
    parallel = _dc('_gui_mscatalog_batched_parallel_enabled')()
    if not (_dc('_gui_mscatalog_prewarm_enabled')() or parallel):
        return
    if not _dc('_v6_catalog_enabled')() or is_quick_check_mode():
        return
    if not device_contexts:
        return

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    queries = _unique_mscatalog_queries_from_device_contexts(device_contexts)
    if not queries:
        return

    pending = [
        q for q in queries
        if q.strip().lower() not in _BATCH_MSCATALOG_QUERY_CACHE
    ]
    if not pending:
        prog(f"Microsoft Update Catalog: {len(queries)} search(es) already cached.")
        return

    include_preview = catalog_include_preview_updates()

    if parallel and _dc('_warm_mscatalog_parallel')(pending, include_preview, prog):
        return

    prog(
        f"Microsoft Update Catalog: pre-warming {len(pending)} unique search(es) "
        f"({len(queries)} total for batch)…"
    )
    for qi, query in enumerate(pending, 1):
        prog(f"Microsoft Update Catalog: query {qi}/{len(pending)}…")
        _dc('_search_mscatalog_updates_cached')(
            query,
            limit=8,
            include_preview=include_preview,
        )

def _seed_mscatalog_batch_results(
    chunk: list[str],
    results: dict[str, list[dict]],
) -> tuple[int, int]:
    """Write one batch's MSCatalog rows into the per-scan cache. Returns (done, got)."""
    done = 0
    got = 0
    lower_map = {q.lower(): q for q in results}
    with _BATCH_MSCATALOG_LOCK:
        for q in chunk:
            rows = results.get(q)
            if rows is None:
                rows = results.get(lower_map.get(q.strip().lower(), ""), [])
            _BATCH_MSCATALOG_QUERY_CACHE[q.strip().lower()] = (
                list(rows) if rows else [],
                "",
            )
            done += 1
            if rows:
                got += 1
    return done, got


def _run_mscatalog_batch_with_split_retry(
    chunk: list[str],
    *,
    throttle: int,
    include_preview: bool,
    prog: Callable[[str], None],
) -> bool:
    """Run one MSCatalog batch; on timeout split in half and retry before giving up."""
    try:
        import catalog_ps_batch as cbatch
    except ImportError:
        return False
    pending: list[list[str]] = [list(chunk)]
    while pending:
        part = pending.pop(0)
        try:
            results = cbatch.search_mscatalog_batch(
                part,
                limit=8,
                throttle=throttle,
                include_preview=include_preview,
            )
        except Exception as e:  # noqa: BLE001
            if len(part) > 1:
                mid = max(1, len(part) // 2)
                pending.insert(0, part[mid:])
                pending.insert(0, part[:mid])
                prog(
                    f"Microsoft Update Catalog: batch slow ({str(e)[:50]}) — "
                    f"retrying as {mid}+{len(part) - mid} smaller group(s)…"
                )
                continue
            prog(
                f"Microsoft Update Catalog: query failed after retries "
                f"({str(e)[:60]})…"
            )
            return False
        _seed_mscatalog_batch_results(part, results)
    return True


def _warm_mscatalog_parallel(
    pending: list[str],
    include_preview: bool,
    prog: Callable[[str], None],
) -> bool:
    """Run all pending MSCatalog queries in one parallel PowerShell process.

    Returns True when the parallel path handled the work (cache seeded), False to
    let the caller fall back to the sequential loop.
    """
    try:
        import catalog_ps_batch as cbatch  # noqa: F401 — availability probe
    except ImportError:
        return False
    throttle = _gui_mscatalog_parallel_throttle()
    chunk_size = _gui_mscatalog_parallel_chunk()
    total = len(pending)
    chunks = [pending[i : i + chunk_size] for i in range(0, total, chunk_size)]
    prog(
        f"Microsoft Update Catalog: searching {total} update(s) in parallel "
        f"({throttle} at a time, {len(chunks)} group(s))…"
    )

    done = 0
    got = 0
    for ci, chunk in enumerate(chunks, 1):
        if not _run_mscatalog_batch_with_split_retry(
            chunk,
            throttle=throttle,
            include_preview=include_preview,
            prog=prog,
        ):
            if ci == 1 and done == 0:
                prog(
                    "Parallel catalog search unavailable after retries; using sequential…"
                )
            else:
                prog(
                    f"Microsoft Update Catalog: group {ci}/{len(chunks)} failed "
                    f"after retries; finishing remaining sequentially…"
                )
            return False

        with _BATCH_MSCATALOG_LOCK:
            chunk_done = len(chunk)
            chunk_got = sum(
                1
                for q in chunk
                if _BATCH_MSCATALOG_QUERY_CACHE.get(q.strip().lower(), ([], ""))[0]
            )
        done += chunk_done
        got += chunk_got
        prog(
            f"Microsoft Update Catalog: searched {done}/{total} "
            f"({got} with updates so far)…"
        )

    prog(
        f"Microsoft Update Catalog: {got} of {total} search(es) returned results."
    )
    return True

def _should_skip_online_driver_store(
    system_ctx: dict | None = None,
    ctx: dict | None = None,
) -> bool:
    """GUI uses WU optional + OEM; never Get-WindowsDriver -Online -All in the exe."""
    if _allow_per_hwid_online_store(ctx):
        return False
    if _GUI_APPLICATION_MODE:
        return True
    if _gui_catalog_session_active():
        return True
    if _gui_catalog_mode(system_ctx):
        return True
    return bool((ctx or {}).get("_gui_driver_catalog"))

def _allow_per_hwid_online_store(ctx: dict | None) -> bool:
    """v6 GUI: per-HWID Get-WindowsDriver -Online (fast) instead of -All."""
    if not _dc('_v6_catalog_enabled')():
        return False
    inst = ((ctx or {}).get("instance_id") or "").strip().upper()
    return bool(inst) and "VEN_" in inst

def _online_store_hwid_candidates(ctx: dict) -> list[str]:
    inst = (ctx.get("instance_id") or "").strip()
    if not inst:
        return []
    u = inst.upper()
    out = [inst]
    ven = re.search(r"(VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4})", u)
    if ven:
        base = f"PCI\\{ven.group(1)}"
        if base not in out:
            out.append(base)
    sub = re.search(r"(VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4}&SUBSYS_[0-9A-F]{8})", u)
    if sub:
        full = f"PCI\\{sub.group(1)}"
        if full not in out:
            out.insert(0, full)
    return out[:3]

def configure_catalog(
    *,
    quick_check: bool | None = None,
    oem_session_cache: bool | None = None,
    catalog_include_preview: bool | None = None,
) -> None:
    """Apply user preferences from Settings (see app_settings.py)."""
    global _quick_check_mode, _catalog_include_preview
    if quick_check is not None:
        _quick_check_mode = bool(quick_check)
    if oem_session_cache is not None:
        import driver_catalog as dc

        dc._oem_session_cache_enabled = bool(oem_session_cache)
    if catalog_include_preview is not None:
        _catalog_include_preview = bool(catalog_include_preview)

def catalog_include_preview_updates() -> bool:
    return _catalog_include_preview

def is_quick_check_mode() -> bool:
    return _quick_check_mode

def clear_wu_driver_cache() -> None:
    global _WU_DRIVER_ROWS_CACHE, _WU_DRIVER_CACHE_AT
    global _ONLINE_DRIVER_STORE_CACHE, _ONLINE_DRIVER_STORE_CACHE_AT
    global _PNPSIGNED_DRIVER_CACHE, _PNPSIGNED_DRIVER_CACHE_AT
    global _ONLINE_DRIVER_STORE_CLASS_BUCKETS
    _WU_DRIVER_ROWS_CACHE = None
    _WU_DRIVER_CACHE_AT = 0.0
    _ONLINE_DRIVER_STORE_CACHE = None
    _ONLINE_DRIVER_STORE_CACHE_AT = 0.0
    _PNPSIGNED_DRIVER_CACHE = None
    _PNPSIGNED_DRIVER_CACHE_AT = 0.0
    _ONLINE_DRIVER_STORE_CLASS_BUCKETS = None
    _ONLINE_HWID_STORE_CACHE.clear()
    clear_batch_mscatalog_query_cache()
    _dc('clear_vendor_scrape_cache')()
    try:
        import catalog_cache as ccat
        ccat.clear_wu_cache_file()
    except ImportError:
        pass

_MSCATALOG_STARTUP_NOTICE: str = ""

def set_mscatalog_startup_notice(message: str) -> None:
    global _MSCATALOG_STARTUP_NOTICE
    _MSCATALOG_STARTUP_NOTICE = (message or "").strip()

def consume_mscatalog_startup_notice() -> str:
    global _MSCATALOG_STARTUP_NOTICE
    msg = _MSCATALOG_STARTUP_NOTICE
    _MSCATALOG_STARTUP_NOTICE = ""
    return msg

def _fetch_online_driver_store_rows_uncached() -> tuple[list[dict], str]:
    """Get-WindowsDriver -Online (slow; cached). Supplies version strings for matching."""
    global _ONLINE_DRIVER_STORE_CACHE, _ONLINE_DRIVER_STORE_CACHE_AT
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
$rows = Get-WindowsDriver -Online -All -EA 0
if (-not $rows) { '[]' } else {
  $rows | ForEach-Object {
    $hw = ''
    try { if ($_.HardwareID) { $hw = ($_.HardwareID -join '|') } } catch {}
    [PSCustomObject]@{
      ProviderName = [string]$_.ProviderName
      ClassName = [string]$_.ClassName
      Version = [string]$_.Version
      HardwareDescription = [string]$_.HardwareDescription
      HardwareID = $hw
      Date = if ($_.Date) { $_.Date.ToString('yyyy-MM-dd') } else { '' }
    }
  } | ConvertTo-Json -Compress -Depth 4
}
"""
    ok, out = _dc('_run_catalog_ps')(ps, timeout=_ONLINE_STORE_ALL_TIMEOUT_SEC)
    if not ok:
        return [], (out or "Could not query Windows online driver catalog.")[:240]
    text = (out or "").strip()
    if not text:
        return [], "Windows online driver catalog returned no data."
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        rows = _cap_session_rows([r for r in data if isinstance(r, dict)])
        if rows:
            now = time.monotonic()
            with _ONLINE_DRIVER_STORE_LOCK:
                _ONLINE_DRIVER_STORE_CACHE = rows
                _ONLINE_DRIVER_STORE_CACHE_AT = now
                _rebuild_online_store_class_buckets(rows)
        return rows, ""
    except json.JSONDecodeError:
        return [], "Could not parse Windows online driver catalog."

def _rebuild_online_store_class_buckets(rows: list[dict]) -> None:
    global _ONLINE_DRIVER_STORE_CLASS_BUCKETS
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        cls = (row.get("ClassName") or "").strip().lower() or "_other"
        buckets.setdefault(cls, []).append(row)
    _ONLINE_DRIVER_STORE_CLASS_BUCKETS = buckets

def _get_cached_online_driver_store_rows() -> tuple[list[dict], str]:
    global _ONLINE_DRIVER_STORE_CACHE, _ONLINE_DRIVER_STORE_CACHE_AT
    now = time.monotonic()
    if (
        _ONLINE_DRIVER_STORE_CACHE is not None
        and (now - _ONLINE_DRIVER_STORE_CACHE_AT) < _ONLINE_DRIVER_STORE_CACHE_TTL_SEC
    ):
        if _ONLINE_DRIVER_STORE_CLASS_BUCKETS is None:
            _rebuild_online_store_class_buckets(_ONLINE_DRIVER_STORE_CACHE)
        return _ONLINE_DRIVER_STORE_CACHE, ""
    if _dc('_should_skip_online_driver_store')():
        return [], ""
    with _ONLINE_DRIVER_STORE_LOCK:
        if (
            _ONLINE_DRIVER_STORE_CACHE is not None
            and (now - _ONLINE_DRIVER_STORE_CACHE_AT) < _ONLINE_DRIVER_STORE_CACHE_TTL_SEC
        ):
            if _ONLINE_DRIVER_STORE_CLASS_BUCKETS is None:
                _rebuild_online_store_class_buckets(_ONLINE_DRIVER_STORE_CACHE)
            return _ONLINE_DRIVER_STORE_CACHE, ""
        return _dc('_fetch_online_driver_store_rows_uncached')()

def _parse_online_driver_store_hwid_batch_json(
    text: str,
    hwids: list[str],
) -> dict[str, tuple[list[dict], str]]:
    """Parse multi-HWID Get-WindowsDriver -Online JSON into per-HWID row lists."""
    expected = {h.upper() for h in hwids if h}
    out: dict[str, tuple[list[dict], str]] = {key: ([], "") for key in expected}
    if not text or text.lower() == "null":
        return out
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {key: ([], "Could not parse per-HWID online catalog response.") for key in expected}
    if isinstance(data, dict):
        data = [data]
    for entry in data:
        if not isinstance(entry, dict):
            continue
        query_hw = (entry.get("QueryHwId") or entry.get("query_hwid") or "").strip().upper()
        if not query_hw or query_hw not in expected:
            continue
        rows_raw = entry.get("Rows") or entry.get("rows") or []
        if isinstance(rows_raw, dict):
            rows_raw = [rows_raw]
        rows = [r for r in rows_raw if isinstance(r, dict)]
        out[query_hw] = (rows, "")
    return out

def _fetch_online_driver_store_for_hwids_batch(
    hwids: list[str],
) -> dict[str, tuple[list[dict], str]]:
    """Get-WindowsDriver -Online for multiple HWIDs in one PowerShell session."""
    cleaned = [(h or "").strip() for h in hwids if (h or "").strip()]
    if not cleaned:
        return {}
    ps_hwids = ",".join("'" + h.replace("'", "''") + "'" for h in cleaned)
    ps = f"""
$ErrorActionPreference = 'SilentlyContinue'
$results = @()
foreach ($hw in @({ps_hwids})) {{
  $rows = Get-WindowsDriver -Online -HardwareId $hw -EA 0
  if (-not $rows) {{
    $base = ($hw -split '&SUBSYS_')[0]
    if ($base -and $base -ne $hw) {{ $rows = Get-WindowsDriver -Online -HardwareId $base -EA 0 }}
  }}
  $parsed = @()
  if ($rows) {{
    foreach ($r in @($rows)) {{
      $rowHw = ''
      try {{ if ($r.HardwareID) {{ $rowHw = ($r.HardwareID -join '|') }} }} catch {{}}
      $parsed += [PSCustomObject]@{{
        ProviderName = [string]$r.ProviderName
        ClassName = [string]$r.ClassName
        Version = [string]$r.Version
        HardwareDescription = [string]$r.HardwareDescription
        HardwareID = $rowHw
        Date = if ($r.Date) {{ $r.Date.ToString('yyyy-MM-dd') }} else {{ '' }}
      }}
    }}
  }}
  [void]$results.Add([PSCustomObject]@{{
    QueryHwId = $hw
    Rows = $parsed
  }})
}}
if (-not $results) {{ '[]' }} else {{ $results | ConvertTo-Json -Compress -Depth 5 }}
"""
    timeout = min(90 * max(1, len(cleaned)), 300)
    ok, out = _dc('_run_catalog_ps')(ps, timeout=timeout)
    if not ok:
        err = (out or "Per-HWID online catalog batch query failed.")[:240]
        return {h.upper(): ([], err) for h in cleaned}
    return _parse_online_driver_store_hwid_batch_json(out or "", cleaned)

def _fetch_online_driver_store_for_hwid(hwid: str) -> tuple[list[dict], str]:
    """Get-WindowsDriver -Online scoped to one HardwareId (v6 GUI-safe)."""
    safe = (hwid or "").replace("'", "''").strip()
    if not safe:
        return [], "No hardware ID"
    ps = f"""
$ErrorActionPreference = 'SilentlyContinue'
$hw = '{safe}'
$rows = Get-WindowsDriver -Online -HardwareId $hw -EA 0
if (-not $rows) {{
  $base = ($hw -split '&SUBSYS_')[0]
  if ($base -and $base -ne $hw) {{ $rows = Get-WindowsDriver -Online -HardwareId $base -EA 0 }}
}}
if (-not $rows) {{ '[]' }} else {{
  $rows | ForEach-Object {{
    $hwids = ''
    try {{ if ($_.HardwareID) {{ $hwids = ($_.HardwareID -join '|') }} }} catch {{}}
    [PSCustomObject]@{{
      ProviderName = [string]$_.ProviderName
      ClassName = [string]$_.ClassName
      Version = [string]$_.Version
      HardwareDescription = [string]$_.HardwareDescription
      HardwareID = $hwids
      Date = if ($_.Date) {{ $_.Date.ToString('yyyy-MM-dd') }} else {{ '' }}
    }}
  }} | ConvertTo-Json -Compress -Depth 4
}}
"""
    ok, out = _dc('_run_catalog_ps')(ps, timeout=90)
    if not ok:
        return [], (out or "Per-HWID online catalog query failed.")[:240]
    text = (out or "").strip()
    if not text or text.lower() == "null":
        return [], ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        return [r for r in data if isinstance(r, dict)], ""
    except json.JSONDecodeError:
        return [], "Could not parse per-HWID online catalog response."

def _get_cached_online_driver_store_for_ctx(ctx: dict) -> tuple[list[dict], str]:
    candidates = _online_store_hwid_candidates(ctx)
    if not candidates:
        return [], "No hardware ID for online catalog lookup."
    now = time.monotonic()
    for hwid in candidates:
        key = hwid.upper()
        hit = _ONLINE_HWID_STORE_CACHE.get(key)
        if hit and (now - hit[1]) < _ONLINE_HWID_STORE_CACHE_TTL_SEC:
            _dc('_lru_cache_touch')(_ONLINE_HWID_STORE_CACHE, key)
            return list(hit[0]), ""
    last_err = ""
    for hwid in candidates:
        rows, err = _fetch_online_driver_store_for_hwid(hwid)
        if rows:
            key = hwid.upper()
            _dc('_lru_cache_set')(
                _ONLINE_HWID_STORE_CACHE,
                key,
                (rows, time.monotonic()),
                max_entries=_ONLINE_HWID_STORE_CACHE_MAX,
            )
            return rows, ""
        last_err = err or last_err
    return [], last_err

_WU_DRIVER_SEARCH_CRITERIA = (
    "IsInstalled=0 and Type='Driver' and IsHidden=0",
    "IsInstalled=0 and Type='Driver'",
    "IsInstalled=0 and Type='Driver' and IsPresent=0",
)

def _fetch_wu_driver_rows_uncached() -> tuple[list[dict], str]:
    """Run Windows Update driver searches (multiple COM strategies); returns (rows, error)."""
    criteria_ps = "','".join(c.replace("'", "''") for c in _WU_DRIVER_SEARCH_CRITERIA)
    ps = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$Session = New-Object -ComObject Microsoft.Update.Session
$Searcher = $Session.CreateUpdateSearcher()
$Searcher.Online = $true
$criteria = @('{criteria_ps}'.Split(','))
$list = New-Object System.Collections.ArrayList
$seen = @{{}}
foreach ($crit in $criteria) {{
  if (-not $crit) {{ continue }}
  try {{ $Result = $Searcher.Search($crit) }} catch {{ continue }}
  for ($i = 0; $i -lt $Result.Updates.Count; $i++) {{
    $u = $Result.Updates.Item($i)
    $uid = [string]$u.Identity.UpdateID
    if ($uid -and $seen.ContainsKey($uid)) {{ continue }}
    if ($uid) {{ $seen[$uid] = $true }}
    $ver = ''
    try {{ $ver = [string]$u.DriverVerVersion }} catch {{}}
    if (-not $ver -and $u.Title -match '(\d+\.\d+\.\d+(?:\.\d+)?)') {{ $ver = $Matches[1] }}
    $date = ''
    try {{ if ($u.LastDeploymentChangeTime) {{ $date = $u.LastDeploymentChangeTime.ToString('yyyy-MM-dd') }} }} catch {{}}
    $hw = @()
    try {{ foreach ($h in $u.HardwareIds) {{ $hw += [string]$h }} }} catch {{}}
    [void]$list.Add([PSCustomObject]@{{
      Title = [string]$u.Title
      Version = $ver
      Date = $date
      UpdateId = $uid
      HardwareIds = $hw
    }})
  }}
}}
$list | ConvertTo-Json -Compress -Depth 4
"""
    ok, out = _dc('_run_catalog_ps')(ps, timeout=120)
    if not ok:
        return [], (out or "Windows Update search failed.")[:200]
    text = (out or "").strip()
    if not text or text.lower() == "null":
        return [], ""
    try:
        data = json.loads(text)
        if data is None:
            return [], ""
        if isinstance(data, dict):
            data = [data]
        return _cap_session_rows(list(data)), ""
    except json.JSONDecodeError:
        return [], "Could not parse Windows Update response."

def fetch_wu_driver_rows_deep() -> tuple[list[dict], str]:
    """Always query Windows Update (used when refreshing the on-disk driver database)."""
    global _WU_DRIVER_ROWS_CACHE, _WU_DRIVER_CACHE_AT
    rows, err = _fetch_wu_driver_rows_uncached()
    now = time.monotonic()
    if rows:
        rows = _cap_session_rows(rows)
        _WU_DRIVER_ROWS_CACHE = rows
        _WU_DRIVER_CACHE_AT = now
    return rows, err

def _get_cached_wu_driver_rows(system_ctx: dict | None = None) -> tuple[list[dict], str]:
    global _WU_DRIVER_ROWS_CACHE, _WU_DRIVER_CACHE_AT
    now = time.monotonic()
    if (
        _WU_DRIVER_ROWS_CACHE is not None
        and (now - _WU_DRIVER_CACHE_AT) < _WU_DRIVER_CACHE_TTL_SEC
    ):
        return _WU_DRIVER_ROWS_CACHE, ""

    try:
        import catalog_cache as ccat
    except ImportError:
        ccat = None  # type: ignore[assignment]

    if ccat and ccat.is_force_deep_catalog():
        rows, err = fetch_wu_driver_rows_deep()
        trunc, orig = peek_session_rows_truncated()
        ccat.save_wu_rows(
            rows,
            err,
            system_ctx=system_ctx,
            rows_truncated=trunc,
            rows_original_count=orig if trunc else len(rows),
        )
        return rows, err

    if ccat and ccat.should_use_disk_cache():
        rows, err, blob = ccat.load_wu_rows(system_ctx)
        if blob and rows:
            rows = _cap_session_rows(rows)
            _WU_DRIVER_ROWS_CACHE = rows
            _WU_DRIVER_CACHE_AT = now
            return rows, err

    if _quick_check_mode:
        return [], "Quick check: open Optional updates in Settings for Microsoft drivers."

    rows, err = _fetch_wu_driver_rows_uncached()
    if rows:
        rows = _cap_session_rows(rows)
        _WU_DRIVER_ROWS_CACHE = rows
        _WU_DRIVER_CACHE_AT = now
        if ccat and app_set_allows_persist():
            trunc, orig = peek_session_rows_truncated()
            ccat.save_wu_rows(
                rows,
                err,
                system_ctx=system_ctx,
                rows_truncated=trunc,
                rows_original_count=orig if trunc else len(rows),
            )
    return rows, err

def app_set_allows_persist() -> bool:
    try:
        import app_settings as app_set
        return app_set.allows_catalog_disk_cache()
    except ImportError:
        return False

def persist_session_catalog_cache(system_ctx: dict | None) -> None:
    """Save in-memory WU/OEM data gathered during a live scan (no full re-fetch)."""
    try:
        import catalog_cache as ccat
    except ImportError:
        return
    ctx = system_ctx or {}
    ccat.migrate_legacy_catalog_cache(ctx)
    global _WU_DRIVER_ROWS_CACHE
    trunc, orig = peek_session_rows_truncated()
    with ccat.catalog_system_ctx_scope(ctx):
        if _WU_DRIVER_ROWS_CACHE:
            ccat.save_wu_rows(
                list(_WU_DRIVER_ROWS_CACHE),
                "",
                system_ctx=ctx,
                rows_truncated=trunc,
                rows_original_count=orig if trunc else len(_WU_DRIVER_ROWS_CACHE),
            )
        offers = oem_offers_from_session_cache(ctx)
        warmed = oem_session_warmed_vendor_tags(ctx)
        if offers:
            expected = {tag for tag, _ in _dc('_oem_live_row_warmers')(ctx)}
            ccat.save_oem_offers(
                offers,
                system_ctx=ctx,
                partial=bool(warmed) and set(warmed) != expected,
                warmed_vendors=warmed,
            )

def oem_session_warmed_vendor_tags(system_ctx: dict | None) -> list[str]:
    """OEM vendor tags with a fresh in-memory row cache (for partial disk persist)."""
    tags: list[str] = []
    ctx = system_ctx or {}
    now = time.monotonic()
    for oem_tag, _fetch_fn in _dc('_oem_live_row_warmers')(ctx):
        key = _dc('_oem_row_cache_key')(oem_tag, ctx)
        with _dc('_CATALOG_CACHE_LOCK'):
            hit = _dc('_OEM_ROWS_CACHE').get(key)
        if not hit or (now - hit[1]) >= _dc('_OEM_CACHE_TTL_SEC'):
            continue
        rows, _fallback = hit[0]
        if rows:
            tags.append(oem_tag)
    return tags

_OEM_TAG_LABELS: dict[str, str] = {
    "dell": "OEM (Dell / Alienware)",
    "lenovo": "OEM (Lenovo)",
    "hp": "OEM (HP)",
    "asus": "OEM (ASUS / ROG)",
    "msi": "OEM (MSI)",
    "gigabyte": "OEM (Gigabyte / AORUS)",
    "acer": "OEM (Acer)",
}

def oem_offers_from_session_cache(system_ctx: dict | None) -> list[dict]:
    """Build OEM disk-cache payload from warmed in-memory row cache (no live API)."""
    offers: list[dict] = []
    ctx = system_ctx or {}
    tag = _dc('_dell_service_tag')(ctx) or ""
    now = time.monotonic()
    for oem_tag, _fetch_fn in _dc('_oem_live_row_warmers')(ctx):
        key = _dc('_oem_row_cache_key')(oem_tag, ctx)
        with _dc('_CATALOG_CACHE_LOCK'):
            hit = _dc('_OEM_ROWS_CACHE').get(key)
        if not hit or (now - hit[1]) >= _dc('_OEM_CACHE_TTL_SEC'):
            continue
        rows, fallback = hit[0]
        if not rows:
            continue
        label = _OEM_TAG_LABELS.get(oem_tag, f"OEM ({oem_tag})")
        extra = ""
        if oem_tag == "dell" and tag:
            extra = f" Service tag {tag}."
        elif oem_tag == "lenovo":
            mtm = re.sub(
                r"[^A-Z0-9]",
                "",
                ((ctx.get("machine_type") or ctx.get("baseboard_product") or "").upper()),
            )[:10]
            if mtm:
                extra = f" Machine type {mtm}."
        offers.extend(
            _dc('_oem_rows_to_catalog_offers')(
                list(rows),
                label,
                fallback,
                note=f"{label} catalog.{extra}".strip(),
            )
        )
    return offers

def _v6_catalog_enabled() -> bool:
    try:
        import product_version as pv
        return pv.is_v6_line()
    except ImportError:
        return False

def ensure_mscatalog_module_ready(
    *,
    check_online: bool = True,
    force_gallery_check: bool = False,
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Prepare MSCatalogLTS (v6 only): local seed from bundle, prefer newer gallery build when online."""
    if not _dc('_v6_catalog_enabled')():
        return False, "MSCatalogLTS is v6-only"
    try:
        import catalog_ps_module as cps
    except ImportError:
        return False, "catalog_ps_module unavailable"
    ok, path = cps.prepare_mscatalog_module(
        check_online=check_online,
        force_gallery_check=force_gallery_check,
        progress=progress,
    )
    if not ok or not path:
        return False, "MSCatalogLTS module not found"
    return True, path

def _search_mscatalog_updates_cached(
    query: str,
    *,
    limit: int,
    include_preview: bool,
    cache_only: bool = False,
) -> tuple[list[dict], str]:
    """MSCatalogLTS search with per-scan query dedup for batch driver checks."""
    try:
        import catalog_ps_module as cps
    except ImportError:
        return [], "MSCatalog module unavailable"
    key = query.strip().lower()
    if not key:
        return [], ""
    with _BATCH_MSCATALOG_LOCK:
        hit = _BATCH_MSCATALOG_QUERY_CACHE.get(key)
    if hit is not None:
        return list(hit[0]), hit[1]
    if cache_only:
        return [], ""
    rows, err = cps.search_mscatalog_updates(
        query,
        limit=limit,
        include_preview=include_preview,
        include_file_names=True,
    )
    with _BATCH_MSCATALOG_LOCK:
        _BATCH_MSCATALOG_QUERY_CACHE[key] = (
            list(rows) if rows else [],
            err or "",
        )
    return rows, err or ""

def _gui_gap_catalog_fallback_enabled() -> bool:
    """After a batch scan, fire a targeted, HWID-verified Microsoft Update Catalog
    NAME search for devices that ended with zero offers.

    On by default. This fills genuine coverage gaps on hardware without OEM or
    vendor-scraper support (the batch path otherwise reduces non-Realtek devices to
    a single hardware-ID query, which the catalog web/title search never matches),
    while only surfacing catalog packages whose hardware IDs verify against the
    device — so no low-confidence or false-positive offers are introduced.
    """
    try:
        import app_settings as app_set

        return bool(app_set.load_settings().get("gui_gap_catalog_fallback", True))
    except ImportError:
        return True


def _gui_application_mode_active() -> bool:
    return _GUI_APPLICATION_MODE
