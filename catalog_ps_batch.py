"""
Batched + internally-parallel Microsoft Update Catalog search (BSOD Analyzer).

Runs many MSCatalog queries in ONE PowerShell process with bounded concurrency:
  - PowerShell 7 (`pwsh`): `ForEach-Object -Parallel -ThrottleLimit N`
  - Windows PowerShell 5.1 fallback: sequential loop in a single session

Why: ~85% of each MSCatalog query is the network round-trip to
catalog.update.microsoft.com, and the legacy path serializes every query behind a
process-wide lock (one `powershell.exe` per query). Running the network calls
concurrently inside a single process turns the multi-minute catalog phase into
seconds, without ever spawning multiple `powershell.exe` (the thing the global
lock was protecting against). Callers should still hold the catalog lock around
this single process so only one runs at a time.

Rows are shaped identically to `catalog_ps_module.search_mscatalog_updates` so
downstream scoring/rejection is unchanged.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

_WIN_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_MODULE_NAME = "MSCatalogLTS"
_SELECT = "Title,LastUpdated,Guid,UpdateID,Products,Classification,Size,Description,Version,FileNames"

# Sentinels wrap the JSON payload so we can recover it even when the module or a
# runspace prints stray text (e.g. Get-MSCatalogUpdate emits
# "WARNING: We did not find any results for <url>" on the warning stream, which
# `-Command` merges into stdout and would otherwise break json.loads for the
# whole batch — turning a partial-miss into a total 0-results failure).
_JSON_BEGIN = "<<<MSJSONBEGIN>>>"
_JSON_END = "<<<MSJSONEND>>>"

# The catalog web search matches update TITLES, not raw hardware IDs; PCI\VEN_…,
# HDAUDIO\FUNC_…, and …&DEV_… strings always come back "no results". Keep them out
# of the batch so throttle slots go to name searches that can actually match. The
# predicate is defined once in catalog_ps_module and shared across every path.
from catalog_ps_module import is_hwid_search as _is_hwid_search  # noqa: E402


class CatalogBatchError(RuntimeError):
    """Raised when the batch process produced no parseable payload.

    Callers should treat this as "parallel path unavailable" and fall back to
    the proven sequential per-query path rather than trusting an empty result
    (which would poison the per-scan cache and silently drop all catalog hits).
    """


def find_mscatalog_module(explicit: str | None = None) -> str | None:
    if explicit and os.path.isfile(explicit):
        return explicit
    try:
        import catalog_ps_module as cps  # type: ignore

        path = cps.resolve_active_module_dir()
        if path:
            psd1 = os.path.join(path, f"{_MODULE_NAME}.psd1")
            if os.path.isfile(psd1):
                return psd1
    except (ImportError, OSError):
        pass
    return None


def find_powershell(prefer_pwsh: bool = True) -> tuple[str, bool]:
    """Return (exe, is_pwsh7). Prefers pwsh 7 for ForEach-Object -Parallel."""
    if prefer_pwsh:
        try:
            from bsod_runtime import powershell7_exe  # type: ignore

            exe = powershell7_exe()
            if exe:
                return exe, True
        except (ImportError, OSError):
            pass
        exe = shutil.which("pwsh")
        if not exe:
            for cand in (
                os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                             "PowerShell", "7", "pwsh.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\pwsh.exe"),
            ):
                if cand and os.path.isfile(cand):
                    exe = cand
                    break
        if exe:
            return exe, True
    return "powershell", False


def _ps_prefix(psd1: str) -> str:
    return os.path.dirname(os.path.dirname(psd1)).replace("'", "''")


def _ps_array(queries: list[str]) -> str:
    return ",".join("'" + q.replace("'", "''") + "'" for q in queries)


def build_parallel_script(psd1: str, queries: list[str], *, limit: int,
                          throttle: int, include_preview: bool) -> str:
    prefix = _ps_prefix(psd1)
    modpath = psd1.replace("'", "''")
    preview = "$true" if include_preview else "$false"
    return f"""
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$InformationPreference = 'SilentlyContinue'
$env:PSModulePath = '{prefix}' + [IO.Path]::PathSeparator + $env:PSModulePath
$queries = @({_ps_array(queries)})
$results = $queries | ForEach-Object -ThrottleLimit {int(throttle)} -Parallel {{
  $ErrorActionPreference = 'SilentlyContinue'
  $ProgressPreference = 'SilentlyContinue'
  $WarningPreference = 'SilentlyContinue'
  $InformationPreference = 'SilentlyContinue'
  $q = [string]$_
  try {{
    Import-Module '{modpath}' -Force -ErrorAction Stop -WarningAction SilentlyContinue
    $rows = @(Get-MSCatalogUpdate -Search $q -IncludePreview:{preview} -IncludeFileNames -WarningAction SilentlyContinue -ErrorAction SilentlyContinue |
              Select-Object -First {int(limit)} {_SELECT})
  }} catch {{ $rows = @() }}
  [PSCustomObject]@{{ Query = $q; Rows = $rows }}
}}
$json = if (-not $results) {{ '[]' }} else {{ $results | ConvertTo-Json -Compress -Depth 6 }}
[Console]::Out.Write('{_JSON_BEGIN}'); [Console]::Out.Write($json); [Console]::Out.Write('{_JSON_END}')
"""


def build_sequential_script(psd1: str, queries: list[str], *, limit: int,
                            include_preview: bool) -> str:
    prefix = _ps_prefix(psd1)
    modpath = psd1.replace("'", "''")
    preview = "$true" if include_preview else "$false"
    return f"""
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$InformationPreference = 'SilentlyContinue'
$env:PSModulePath = '{prefix}' + [IO.Path]::PathSeparator + $env:PSModulePath
Import-Module '{modpath}' -Force -WarningAction SilentlyContinue
$out = @()
foreach ($q in @({_ps_array(queries)})) {{
  try {{
    $rows = @(Get-MSCatalogUpdate -Search $q -IncludePreview:{preview} -IncludeFileNames -WarningAction SilentlyContinue -ErrorAction SilentlyContinue |
              Select-Object -First {int(limit)} {_SELECT})
  }} catch {{ $rows = @() }}
  $out += [PSCustomObject]@{{ Query = $q; Rows = $rows }}
}}
$json = if (-not $out) {{ '[]' }} else {{ $out | ConvertTo-Json -Compress -Depth 6 }}
[Console]::Out.Write('{_JSON_BEGIN}'); [Console]::Out.Write($json); [Console]::Out.Write('{_JSON_END}')
"""


def _norm_rows(raw_rows) -> list[dict]:
    """Shape rows identically to catalog_ps_module.search_mscatalog_updates."""
    if isinstance(raw_rows, dict):
        raw_rows = [raw_rows]
    try:
        import catalog_ps_module as cps  # type: ignore
        resolve_ver = cps._resolve_catalog_row_version
        norm_date = cps._normalize_catalog_date
        norm_files = cps._normalize_catalog_file_names
        tier_of = cps._catalog_tier_from_title
        uid_from = cps.catalog_update_id_from_row
    except Exception:
        resolve_ver = lambda row, title: (str(row.get("Version") or "").strip())
        norm_date = lambda s: str(s or "")[:32]
        norm_files = lambda x: [str(v).strip() for v in x] if isinstance(x, list) else ([x.strip()] if isinstance(x, str) and x.strip() else [])
        tier_of = lambda t: "standard"
        uid_from = lambda r: str(r.get("Guid") or r.get("UpdateID") or "").strip()

    rows: list[dict] = []
    for r in raw_rows or []:
        if not isinstance(r, dict):
            continue
        title = (r.get("Title") or "").strip()
        if not title:
            continue
        last = r.get("LastUpdated") or ""
        if hasattr(last, "isoformat"):
            last = last.isoformat()
        rows.append({
            "title": title[:240],
            "version": resolve_ver(r, title),
            "date": norm_date(str(last)),
            "update_id": uid_from(r),
            "products": r.get("Products") or "",
            "classification": (r.get("Classification") or "").strip(),
            "size": (r.get("Size") or "").strip(),
            "description": (r.get("Description") or "").strip()[:400],
            "file_names": norm_files(r.get("FileNames")),
            "catalog_tier": tier_of(title),
            "source": "microsoft_catalog",
        })
    return rows


def mscatalog_batch_timeout_seconds(
    query_count: int,
    *,
    throttle: int = 5,
    is_pwsh: bool = True,
    on_battery: bool = False,
) -> int:
    """Wall-clock budget for one MSCatalog PowerShell batch."""
    per = 34 if on_battery else 18
    parallel = max(1, int(throttle)) if is_pwsh else 1
    effective = query_count / parallel
    # Avoid the old 120s floor that aborted slow-but-healthy parallel batches on battery.
    return int(max(180, effective * per + 120, query_count * 12 + 90))


def search_mscatalog_batch(
    queries: list[str],
    *,
    limit: int = 8,
    throttle: int = 5,
    include_preview: bool = False,
    module_psd1: str | None = None,
    prefer_pwsh: bool = True,
    timeout: int | None = None,
) -> dict[str, list[dict]]:
    """Run all `queries` in one PowerShell process; return {query: [rows]}."""
    uniq: list[str] = []
    seen: set[str] = set()
    hwid_empty: dict[str, list[dict]] = {}
    for q in queries:
        k = (q or "").strip()
        if not k or k.lower() in seen:
            continue
        seen.add(k.lower())
        # Hardware-ID strings never match the catalog web (title) search — seed them
        # empty and keep them out of the PowerShell batch so the parallel warm only
        # spends its slots on name searches that can actually return results.
        if _is_hwid_search(k):
            hwid_empty[k] = []
            continue
        uniq.append(k)
    if not uniq:
        return dict(hwid_empty)

    psd1 = find_mscatalog_module(module_psd1)
    if not psd1:
        raise FileNotFoundError("MSCatalogLTS.psd1 not found")

    exe, is_pwsh = find_powershell(prefer_pwsh)
    if is_pwsh:
        script = build_parallel_script(psd1, uniq, limit=limit, throttle=throttle,
                                       include_preview=include_preview)
    else:
        script = build_sequential_script(psd1, uniq, limit=limit,
                                         include_preview=include_preview)

    if timeout is None:
        on_battery = False
        try:
            import bsod_runtime as rt

            on_battery = rt.system_on_battery_power()
        except ImportError:
            pass
        timeout = mscatalog_batch_timeout_seconds(
            len(uniq),
            throttle=throttle,
            is_pwsh=is_pwsh,
            on_battery=on_battery,
        )

    try:
        proc = subprocess.run(
            [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_WIN_CREATE_NO_WINDOW,
        )
        out = proc.stdout or ""
    except subprocess.TimeoutExpired as e:
        raise CatalogBatchError(
            f"batch timed out after {timeout}s ({len(uniq)} queries)"
        ) from e

    payload = _extract_payload(out)
    if payload is None:
        # No sentinel-wrapped JSON: the process failed to produce a usable
        # result (crash, module load failure, or truncated output). Signal the
        # caller to fall back rather than silently returning all-empty.
        raise CatalogBatchError(
            f"no parseable payload from batch ({len(uniq)} queries; "
            f"stdout={len(out)} chars, rc={proc.returncode})"
        )
    try:
        data = json.loads(payload) if payload else []
    except json.JSONDecodeError as e:
        raise CatalogBatchError(f"payload was not valid JSON: {e}") from e

    result: dict[str, list[dict]] = {q: [] for q in uniq}
    result.update(hwid_empty)
    if isinstance(data, dict):
        data = [data]
    by_lower = {q.lower(): q for q in uniq}
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        q = str(entry.get("Query") or "").strip()
        canon = by_lower.get(q.lower(), q)
        result[canon] = _norm_rows(entry.get("Rows"))
    return result


def _extract_payload(out: str) -> str | None:
    """Return the JSON text between the sentinels, or None if not present."""
    if not out:
        return None
    start = out.find(_JSON_BEGIN)
    if start < 0:
        return None
    start += len(_JSON_BEGIN)
    end = out.find(_JSON_END, start)
    if end < 0:
        return None
    return out[start:end].strip()
