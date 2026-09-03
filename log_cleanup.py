"""
Guided cleanup of crash-related logs and dump files.

Scans minidumps, application CrashDumps, WER folders, and optional event logs.
Deletion is always explicit via a plan built from user choices — nothing is removed silently.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
from datetime import datetime
from typing import Any

import bsod_minidump as minidump
from bsod_runtime import get_logged_in_user_paths, run_powershell

# WER stores queued and archived crash report payloads (separate from .dmp files).
WER_ROOT = os.path.join(
    os.environ.get("ProgramData", r"C:\ProgramData"),
    "Microsoft",
    "Windows",
    "WER",
)

GUIDANCE_STEPS = [
    (
        "Save your findings first",
        "Run Analysis and export a report or save an analysis baseline before deleting anything. "
        "You cannot re-analyze dumps that are removed.",
    ),
    (
        "Keep recent minidumps",
        "Leave at least one or two kernel minidumps in C:\\Windows\\Minidump if problems "
        "continue — support and this tool use the newest files.",
    ),
    (
        "Fix the cause, then clean",
        "Clearing logs frees disk space but does not fix drivers or hardware. "
        "Follow the Action Plan, then clean up old artifacts.",
    ),
    (
        "Event logs are optional and destructive",
        "Clearing the System log removes BSOD history from Event Viewer. "
        "Export a backup first, or skip this step.",
    ),
]


def is_user_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _dir_size_mb(path: str) -> float:
    total = 0
    if not os.path.isdir(path):
        return 0.0
    try:
        for root, _dirs, files in os.walk(path):
            for fn in files:
                fp = os.path.join(root, fn)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        return 0.0
    return round(total / (1024 * 1024), 2)


def _list_wer_subfolder(name: str) -> dict:
    path = os.path.join(WER_ROOT, name)
    if not os.path.isdir(path):
        return {"name": name, "path": path, "exists": False, "size_mb": 0.0, "file_count": 0}
    count = 0
    try:
        for _root, _dirs, files in os.walk(path):
            count += len(files)
    except OSError:
        count = 0
    return {
        "name": name,
        "path": path,
        "exists": True,
        "size_mb": _dir_size_mb(path),
        "file_count": count,
    }


def _event_log_sizes() -> list[dict]:
    """System/Application log size via PowerShell (read-only)."""
    ps = r"""
    $ErrorActionPreference = 'SilentlyContinue'
    @('System','Application') | ForEach-Object {
        $l = Get-WinEvent -ListLog $_ -EA 0
        if ($l) {
            [PSCustomObject]@{
                LogName = $_.ToString()
                RecordCount = [int]$l.RecordCount
                FileSizeMB = [math]::Round($l.FileSize / 1MB, 2)
                IsEnabled = [bool]$l.IsEnabled
            }
        }
    } | ConvertTo-Json
    """
    ok, out = run_powershell(ps, timeout=25)
    rows: list[dict] = []
    if ok and out:
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            for row in data:
                rows.append({
                    "log_name": row.get("LogName", "?"),
                    "record_count": row.get("RecordCount", 0),
                    "size_mb": row.get("FileSizeMB", 0),
                    "enabled": row.get("IsEnabled", True),
                })
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return rows


def gather_cleanup_inventory() -> dict[str, Any]:
    """Scan crash-related artifacts and return structured inventory for the wizard."""
    logged_in_user, primary_crashdumps, all_crashdumps_paths = get_logged_in_user_paths()
    kernel = minidump.list_dumps(minidump.MINIDUMP_DIR, "Kernel")
    app_paths = [p for p in all_crashdumps_paths if p and os.path.isdir(p)]
    if not app_paths and primary_crashdumps and os.path.isdir(primary_crashdumps):
        app_paths = [primary_crashdumps]
    app_dumps = minidump.list_dumps_from_paths(app_paths, "Application")
    full_dump = minidump.check_full_dump()

    kernel_total_mb = round(sum(d.get("size_mb", 0) for d in kernel), 2)
    app_total_mb = round(sum(d.get("size_mb", 0) for d in app_dumps), 2)

    can_kernel = is_user_admin() or os.access(minidump.MINIDUMP_DIR, os.W_OK)
    can_full = bool(full_dump) and (
        is_user_admin() or os.access(full_dump["path"], os.W_OK)
    )

    return {
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_admin": is_user_admin(),
        "kernel_minidumps": kernel,
        "kernel_total_mb": kernel_total_mb,
        "kernel_dir": minidump.MINIDUMP_DIR,
        "can_delete_kernel": can_kernel,
        "app_dumps": app_dumps,
        "app_total_mb": app_total_mb,
        "app_dirs": app_paths,
        "full_dump": full_dump,
        "can_delete_full_dump": can_full,
        "wer_report_archive": _list_wer_subfolder("ReportArchive"),
        "wer_report_queue": _list_wer_subfolder("ReportQueue"),
        "wer_temp": _list_wer_subfolder("Temp"),
        "event_logs": _event_log_sizes(),
        "guidance": GUIDANCE_STEPS,
    }


def _split_keep_remove(dumps: list[dict], keep: int) -> tuple[list[dict], list[dict]]:
    if keep < 0:
        keep = 0
    sorted_dumps = sorted(dumps, key=lambda x: x.get("time", ""), reverse=True)
    return sorted_dumps[:keep], sorted_dumps[keep:]


def build_cleanup_plan(inventory: dict[str, Any], options: dict[str, Any]) -> list[dict[str, Any]]:
    """Build explicit delete list from inventory and user options."""
    plan: list[dict[str, Any]] = []

    if options.get("delete_older_kernel", True):
        keep = int(options.get("kernel_keep", 2))
        _keep, remove = _split_keep_remove(inventory.get("kernel_minidumps") or [], keep)
        for d in remove:
            plan.append({
                "path": d["path"],
                "category": "Kernel minidump",
                "size_mb": d.get("size_mb", 0),
                "detail": d.get("name", ""),
            })

    if options.get("delete_older_app", True):
        keep = int(options.get("app_keep", 1))
        _keep, remove = _split_keep_remove(inventory.get("app_dumps") or [], keep)
        for d in remove:
            plan.append({
                "path": d["path"],
                "category": "Application crash dump",
                "size_mb": d.get("size_mb", 0),
                "detail": d.get("name", ""),
            })

    if options.get("delete_full_dump") and inventory.get("full_dump"):
        fd = inventory["full_dump"]
        plan.append({
            "path": fd["path"],
            "category": "Full memory dump",
            "size_mb": fd.get("size_mb", 0),
            "detail": "MEMORY.DMP",
        })

    if options.get("delete_wer_archive") and (inventory.get("wer_report_archive") or {}).get("exists"):
        plan.append({
            "path": inventory["wer_report_archive"]["path"],
            "category": "WER ReportArchive",
            "size_mb": inventory["wer_report_archive"].get("size_mb", 0),
            "detail": "folder (all files inside)",
            "is_tree": True,
        })

    if options.get("delete_wer_queue") and (inventory.get("wer_report_queue") or {}).get("exists"):
        plan.append({
            "path": inventory["wer_report_queue"]["path"],
            "category": "WER ReportQueue",
            "size_mb": inventory["wer_report_queue"].get("size_mb", 0),
            "detail": "folder (all files inside)",
            "is_tree": True,
        })

    if options.get("delete_wer_temp") and (inventory.get("wer_temp") or {}).get("exists"):
        plan.append({
            "path": inventory["wer_temp"]["path"],
            "category": "WER Temp",
            "size_mb": inventory["wer_temp"].get("size_mb", 0),
            "detail": "folder (all files inside)",
            "is_tree": True,
        })

    if options.get("clear_system_log"):
        plan.append({
            "path": "System",
            "category": "Event log",
            "size_mb": 0,
            "detail": "Clear System log (after optional export)",
            "event_log": "System",
            "export_path": options.get("export_system_log_path") or "",
        })

    if options.get("clear_application_log"):
        plan.append({
            "path": "Application",
            "category": "Event log",
            "size_mb": 0,
            "detail": "Clear Application log (after optional export)",
            "event_log": "Application",
            "export_path": options.get("export_application_log_path") or "",
        })

    return plan


def plan_summary(plan: list[dict[str, Any]]) -> dict[str, Any]:
    file_items = [p for p in plan if not p.get("event_log")]
    return {
        "item_count": len(plan),
        "file_count": len(file_items),
        "freed_mb": round(sum(p.get("size_mb", 0) for p in file_items), 2),
    }


def export_event_log(log_name: str, export_path: str) -> tuple[bool, str]:
    if not export_path or not log_name:
        return False, "No export path."
    if not is_user_admin():
        return False, "Administrator rights are required to export event logs."
    folder = os.path.dirname(os.path.abspath(export_path))
    if folder and not os.path.isdir(folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            return False, str(e)
    ps = f"""
    $ErrorActionPreference = 'Stop'
    wevtutil epl '{log_name.replace("'", "''")}' '{export_path.replace("'", "''")}'
    """
    ok, out = run_powershell(ps, timeout=120)
    if ok:
        return True, f"Exported {log_name} log to {export_path}"
    return False, out or "Export failed"


def clear_event_log(log_name: str) -> tuple[bool, str]:
    if not is_user_admin():
        return False, "Administrator rights are required to clear event logs."
    ps = f"""
    $ErrorActionPreference = 'Stop'
    wevtutil cl '{log_name.replace("'", "''")}'
    """
    ok, out = run_powershell(ps, timeout=60)
    if ok:
        return True, f"Cleared {log_name} log"
    return False, out or "Clear failed"


def _delete_file(path: str) -> tuple[bool, str]:
    try:
        os.remove(path)
        return True, ""
    except OSError as e:
        return False, str(e)


def _clear_folder_contents(folder: str) -> tuple[int, float, list[str]]:
    deleted = 0
    freed = 0.0
    errors: list[str] = []
    if not os.path.isdir(folder):
        return 0, 0.0, [f"Not found: {folder}"]
    try:
        for name in os.listdir(folder):
            fp = os.path.join(folder, name)
            try:
                if os.path.isfile(fp) or os.path.islink(fp):
                    sz = os.path.getsize(fp)
                    os.remove(fp)
                    deleted += 1
                    freed += sz
                elif os.path.isdir(fp):
                    sz = _dir_size_mb(fp) * 1024 * 1024
                    shutil.rmtree(fp, ignore_errors=False)
                    deleted += 1
                    freed += sz
            except OSError as e:
                errors.append(f"{name}: {e}")
    except OSError as e:
        errors.append(str(e))
    return deleted, round(freed / (1024 * 1024), 2), errors


def execute_cleanup_plan(plan: list[dict[str, Any]]) -> dict[str, Any]:
    """Run a plan from build_cleanup_plan. Returns counts and error messages."""
    deleted_files = 0
    freed_mb = 0.0
    errors: list[str] = []
    actions: list[str] = []

    for item in plan:
        log_name = item.get("event_log")
        if log_name:
            export_path = (item.get("export_path") or "").strip()
            if export_path:
                ok, msg = export_event_log(log_name, export_path)
                if ok:
                    actions.append(msg)
                else:
                    errors.append(msg)
                    continue
            ok, msg = clear_event_log(log_name)
            if ok:
                actions.append(msg)
            else:
                errors.append(msg)
            continue

        path = item.get("path", "")
        if not path:
            continue

        if item.get("is_tree"):
            n, mb, errs = _clear_folder_contents(path)
            deleted_files += n
            freed_mb += mb
            errors.extend(errs)
            if n:
                actions.append(f"Cleared {n} item(s) in {item.get('category', path)} (~{mb} MB)")
            continue

        ok, err = _delete_file(path)
        if ok:
            deleted_files += 1
            freed_mb += float(item.get("size_mb", 0) or 0)
            actions.append(f"Deleted {os.path.basename(path)}")
        else:
            errors.append(f"{path}: {err}")

    return {
        "deleted_files": deleted_files,
        "freed_mb": round(freed_mb, 2),
        "errors": errors,
        "actions": actions,
    }
