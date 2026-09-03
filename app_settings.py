"""
Persistent app settings, snapshots, ignored devices, and cached driver/firmware checks.

Maintenance USB (portable launcher): durable state under %LOCALAPPDATA%\\BSODAnalyzer\\
on the PC being serviced — not beside the exe on the stick.

Full-install mode uses the same PC-local root (optional custom_data_dir override).
Legacy ``BSODAnalyzer_portable\\`` beside the exe is ignored (orphan detection / OneDrive warning only).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

APP_NAME = "BSODAnalyzer"
SETTINGS_VERSION = 2
_PORTABLE_SETTINGS_DIRNAME = "BSODAnalyzer_portable"
_last_settings_save_error: str | None = None


def _exe_parent_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def is_full_install_mode(settings: dict | None = None) -> bool:
    s = settings if settings is not None else load_settings()
    return (s.get("install_mode") or "portable") == "full"


def allows_persistent_driver_data(settings: dict | None = None) -> bool:
    """True when driver list, check cache, and driver index may be written to disk."""
    return is_full_install_mode(settings)


def allows_catalog_disk_cache(settings: dict | None = None) -> bool:
    """True when WU/OEM catalog JSON may be read/written (portable + full install)."""
    return True


def catalog_cache_dir(settings: dict | None = None, *, system_ctx: dict | None = None) -> Path:
    """On-disk Windows Update + OEM catalog cache (portable: per-unit subfolder)."""
    s = settings if settings is not None else load_settings()
    if is_full_install_mode(s):
        d = full_install_data_dir(s)
    else:
        try:
            import catalog_cache as ccat  # noqa: WPS433
            fp_name = ccat.fingerprint_cache_dirname(system_ctx)
        except ImportError:
            fp_name = "_unidentified"
        d = maintenance_data_dir() / "driver_catalog" / fp_name
    d.mkdir(parents=True, exist_ok=True)
    return d



def maintenance_data_dir() -> Path:
    """PC-local durable store for maintenance USB and full install (default LOCALAPPDATA)."""
    return default_full_install_data_dir()


def enterprise_manifest_cache_dir() -> Path:
    d = maintenance_data_dir() / "driver_catalog" / "_enterprise_manifests"
    d.mkdir(parents=True, exist_ok=True)
    return d


def portable_exports_dir() -> Path:
    """Portable-mode export folder helper (PC-local; not beside exe)."""
    return local_export_directory()


def default_full_install_data_dir() -> Path:
    """Default %LOCALAPPDATA%\\BSODAnalyzer (not synced by OneDrive in typical setups)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / APP_NAME


def full_install_data_dir(settings: dict | None = None) -> Path:
    """Directory for full-install caches (hardware profile, driver index, check cache)."""
    s = settings if settings is not None else load_settings()
    custom = (s.get("custom_data_dir") or "").strip()
    if custom:
        p = Path(custom).expanduser()
        try:
            p = p.resolve()
        except OSError:
            p = p.absolute()
        if p.is_absolute():
            return p
    return default_full_install_data_dir()


def is_onedrive_synced_path(path: Path | str) -> bool:
    """True when *path* lives under a known OneDrive sync root."""
    try:
        p = Path(path).expanduser().resolve()
    except OSError:
        p = Path(path).expanduser().absolute()
    p_str = str(p).lower()
    for env_key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        root = (os.environ.get(env_key) or "").strip()
        if not root:
            continue
        try:
            root_p = Path(root).resolve()
        except OSError:
            root_p = Path(root)
        root_s = str(root_p).lower()
        if p_str == root_s or p_str.startswith(root_s + os.sep):
            return True
    for part in p.parts:
        pl = part.lower()
        if "backup" in pl:
            continue
        if pl == "onedrive":
            return True
        if pl.startswith("onedrive-") and not pl.startswith("onedrive-backup"):
            return True
        if pl.startswith("onedrive "):
            return True
    return False


def local_export_directory() -> Path:
    """Local (non-synced) folder for session exports."""
    return _ensure_dir() / "exports"


def preferred_export_directory(settings: dict | None = None) -> str:
    """Best folder for exports — avoids OneDrive Desktop when possible."""
    import bsod_runtime as rt

    s = settings if isinstance(settings, dict) else {}
    custom = (s.get("export_directory") or "").strip()
    if custom:
        try:
            resolved = Path(custom).expanduser()
            if resolved.is_dir():
                return str(resolved)
        except OSError:
            pass
    local = local_export_directory()
    try:
        local.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    shell_desktop = rt._windows_shell_desktop_path()
    if shell_desktop and os.path.isdir(shell_desktop):
        if is_onedrive_synced_path(shell_desktop):
            return str(local)
        return shell_desktop
    if local.is_dir():
        return str(local)
    return rt.default_export_directory()


def onedrive_export_destination_warning(path: Path | str) -> str | None:
    """Warn when exports target a OneDrive-synced folder (Desktop, etc.)."""
    if not is_onedrive_synced_path(path):
        return None
    return (
        f"Export folder is under OneDrive sync ({path}). "
        "New files may not appear on the Desktop until OneDrive finishes uploading, "
        "or until this app closes. Prefer a local folder such as "
        f"{local_export_directory()} (default when Desktop is synced)."
    )


def onedrive_data_dir_warning(settings: dict | None = None) -> str | None:
    if not is_full_install_mode(settings):
        return None
    data_dir = full_install_data_dir(settings)
    if not is_onedrive_synced_path(data_dir):
        return None
    return (
        f"Full-install data is under a OneDrive-synced folder ({data_dir}). "
        "SQLite caches may lock or corrupt when synced — relocate under Settings → Preferences."
    )


def data_sync_warning(settings: dict | None = None) -> str | None:
    """OneDrive / cloud-sync warning for full-install data or legacy stick-side folders."""
    s = settings if settings is not None else load_settings()
    full_warn = onedrive_data_dir_warning(s)
    if full_warn:
        return full_warn
    if is_full_install_mode(s):
        return None
    legacy = portable_settings_dir()
    if legacy.is_dir() and any(legacy.iterdir()):
        if is_onedrive_synced_path(legacy):
            return (
                f"Legacy portable data on the stick is under a OneDrive-synced folder ({legacy}). "
                "Remove or relocate that folder on the USB copy if possible."
            )
    if is_onedrive_synced_path(_exe_parent_dir()):
        return (
            f"Application folder is under a OneDrive-synced path ({_exe_parent_dir()}). "
            "Run from a local or non-synced USB path when possible."
        )
    return None


_MIGRATE_CRITICAL_FILES = frozenset({"settings.json"})


def _rollback_migrated_files(moved: list[tuple[Path, Path]]) -> None:
    for dest, orig in reversed(moved):
        try:
            if dest.is_file() and not orig.exists():
                shutil.move(str(dest), str(orig))
        except OSError:
            pass


def resolve_custom_data_dir(path: str | Path) -> tuple[Path | None, str | None]:
    p = Path(path).expanduser()
    try:
        p = p.resolve()
    except OSError as exc:
        return None, f"Invalid folder: {exc}"
    if not p.is_absolute():
        return None, "Choose an absolute folder path."
    return p, None


def normalize_custom_data_dir(path: str | Path) -> str:
    """Return custom_data_dir for settings — empty string when using the default folder."""
    raw = (str(path) if path is not None else "").strip()
    if not raw:
        return ""
    resolved, _err = resolve_custom_data_dir(raw)
    if resolved is None:
        return raw
    default = default_full_install_data_dir()
    try:
        if resolved.resolve() == default.resolve():
            return ""
    except OSError:
        if str(resolved).lower() == str(default).lower():
            return ""
    return str(resolved)


def _write_data_dir_pointer(custom_dir: str | Path) -> None:
    """Stub at default LOCALAPPDATA so cold start finds settings after relocation."""
    resolved, _err = resolve_custom_data_dir(custom_dir)
    if resolved is None:
        return
    default = default_full_install_data_dir()
    try:
        if resolved.resolve() == default.resolve():
            return
    except OSError:
        if str(resolved).lower() == str(default).lower():
            return
    stub = {
        "version": SETTINGS_VERSION,
        "install_mode": "full",
        "install_mode_chosen": True,
        "custom_data_dir": str(resolved),
    }
    stub_path = default / "settings.json"
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    stub_path.write_text(json.dumps(stub, indent=2), encoding="utf-8")


def migrate_full_install_data(from_dir: Path, to_dir: Path) -> tuple[bool, str]:
    """Move full-install cache files to a new folder (best-effort, rollback on failure)."""
    src = Path(from_dir)
    dst = Path(to_dir)
    try:
        if src.resolve() == dst.resolve():
            return True, "Already using that folder."
    except OSError:
        if str(src).lower() == str(dst).lower():
            return True, "Already using that folder."
    dst.mkdir(parents=True, exist_ok=True)
    moved: list[tuple[Path, Path]] = []
    skipped: list[str] = []
    if not src.is_dir():
        _write_data_dir_pointer(dst)
        return True, f"Data folder ready at {dst}."
    for item in sorted(src.iterdir(), key=lambda p: p.name.lower()):
        target = dst / item.name
        if target.exists():
            skipped.append(item.name)
            continue
        try:
            shutil.move(str(item), str(target))
            moved.append((target, src / item.name))
        except OSError as exc:
            _rollback_migrated_files(moved)
            return False, f"Could not move {item.name}: {exc}"
    try:
        if dst.resolve() != default_full_install_data_dir().resolve():
            _write_data_dir_pointer(dst)
    except OSError:
        _write_data_dir_pointer(dst)
    if skipped:
        skipped_lower = {name.lower() for name in skipped}
        if not moved:
            listing = ", ".join(skipped[:8])
            if len(skipped) > 8:
                listing += ", …"
            return False, (
                "Could not relocate — the destination folder already contains: "
                f"{listing}"
            )
        if _MIGRATE_CRITICAL_FILES & skipped_lower:
            _rollback_migrated_files(moved)
            return False, (
                "Could not move settings.json — a file already exists at the destination. "
                "Remove or rename the conflicting file, then try again."
            )
    msg = f"Relocated {len(moved)} item(s) to {dst}."
    if skipped:
        listing = ", ".join(skipped[:5])
        if len(skipped) > 5:
            listing += ", …"
        msg += f" Skipped {len(skipped)} existing file(s): {listing}"
    return True, msg


def portable_settings_dir() -> Path:
    """Legacy stick-side folder beside the executable (orphan detection only; not used for reads/writes)."""
    return _exe_parent_dir() / _PORTABLE_SETTINGS_DIRNAME


def _read_install_mode_from_disk() -> str:
    """Read install_mode only — must not call load_settings (avoids recursion)."""
    for base in (maintenance_data_dir(), default_full_install_data_dir()):
        path = base / "settings.json"
        if not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                mode = (loaded.get("install_mode") or "portable").strip().lower()
                if mode in ("full", "portable"):
                    return mode
        except (json.JSONDecodeError, OSError):
            continue
    default_stub = default_full_install_data_dir() / "settings.json"
    if default_stub.is_file():
        try:
            loaded = json.loads(default_stub.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = (loaded.get("custom_data_dir") or "").strip()
                if raw:
                    resolved, _err = resolve_custom_data_dir(raw)
                    if resolved is not None:
                        custom_path = resolved / "settings.json"
                        if custom_path.is_file():
                            loaded2 = json.loads(custom_path.read_text(encoding="utf-8"))
                            if isinstance(loaded2, dict):
                                mode = (
                                    loaded2.get("install_mode") or "portable"
                                ).strip().lower()
                                if mode in ("full", "portable"):
                                    return mode
        except (json.JSONDecodeError, OSError):
            pass
    return "portable"


def _config_dir(settings: dict | None = None) -> Path:
    if settings is not None:
        mode = (settings.get("install_mode") or "portable").strip().lower()
    else:
        mode = _read_install_mode_from_disk()
    if mode == "full":
        return full_install_data_dir(settings)
    return maintenance_data_dir()


def _ensure_dir(settings: dict | None = None) -> Path:
    d = _config_dir(settings)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_data_dir_pointer_stub(data: dict) -> bool:
    """True when default settings.json only redirects to a custom data folder."""
    if not (data.get("custom_data_dir") or "").strip():
        return False
    return not data.get("remember_driver_firmware_checks") and not data.get(
        "use_driver_index"
    )


def _settings_path() -> Path:
    """Resolve settings.json — maintenance USB uses PC-local storage only."""
    redirect = _read_portable_redirect()
    if redirect is not None:
        return redirect
    pc_local_path = maintenance_data_dir() / "settings.json"
    default_full_path = default_full_install_data_dir() / "settings.json"
    if pc_local_path.is_file():
        try:
            loaded = json.loads(pc_local_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                mode = (loaded.get("install_mode") or "").strip().lower()
                if mode != "full":
                    return pc_local_path
        except (json.JSONDecodeError, OSError):
            pass
    custom_dir: Path | None = None
    default_loaded: dict | None = None
    if default_full_path.is_file():
        try:
            loaded = json.loads(default_full_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                default_loaded = loaded
                raw = (loaded.get("custom_data_dir") or "").strip()
                if raw:
                    resolved, _err = resolve_custom_data_dir(raw)
                    if resolved is not None:
                        custom_dir = resolved
                        custom_settings = resolved / "settings.json"
                        if custom_settings.is_file():
                            return custom_settings
                        if _is_data_dir_pointer_stub(loaded):
                            resolved.mkdir(parents=True, exist_ok=True)
                            return custom_settings
        except (json.JSONDecodeError, OSError):
            pass
    if default_full_path.is_file() and (
        default_loaded is None or not _is_data_dir_pointer_stub(default_loaded)
    ):
        return default_full_path
    if custom_dir is not None:
        custom_dir.mkdir(parents=True, exist_ok=True)
        return custom_dir / "settings.json"
    pc_local_path.parent.mkdir(parents=True, exist_ok=True)
    return pc_local_path


def remove_full_install_settings_file(settings: dict | None = None) -> None:
    """Drop full-install settings when switching to portable (avoids reload on restart)."""
    paths: set[Path] = {
        default_full_install_data_dir() / "settings.json",
    }
    if settings is not None:
        custom = normalize_custom_data_dir(settings.get("custom_data_dir") or "")
        if custom:
            resolved, _err = resolve_custom_data_dir(custom)
            if resolved is not None:
                paths.add(resolved / "settings.json")
    try:
        paths.add(full_install_data_dir(settings) / "settings.json")
    except OSError:
        pass
    for path in paths:
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass


def _checks_path() -> Path:
    return _ensure_dir() / "check_cache.json"


def _ignored_path() -> Path:
    return _ensure_dir() / "ignored_devices.json"


DEFAULT_SETTINGS: dict[str, Any] = {
    "version": SETTINGS_VERSION,
    "install_mode": "portable",  # portable | full
    "install_mode_chosen": False,
    "use_driver_index": False,
    "auto_load_all_drivers_on_scan": True,
    "device_cache_max_age_days": 30,
    "catalog_cache_max_age_days": 30,
    "quick_check_mode": False,
    "oem_session_cache": True,
    "catalog_include_preview": False,
    "catalog_auto_refresh_prompt": False,
    "prompt_install_mode_on_first_launch": False,
    "default_include_common_devices": True,
    "remember_driver_firmware_checks": False,
    "drv_tab_splitter_sizes": None,
    "fw_tab_splitter_sizes": None,
    "drv_unified_col_widths": None,
    "fw_unified_col_widths": None,
    # _v2 keys: reset once so the corrected Device-stretch column layout applies
    # (old keys held widths from when Status was the stretched last column).
    "drv_unified_col_widths_v2": None,
    "fw_unified_col_widths_v2": None,
    "drv_package_col_widths": None,
    "fw_package_col_widths": None,
    "show_crash_timeline": True,
    "show_reliability_events": True,
    "first_run_complete": False,
    "onedrive_sync_warn_seen": False,
    "onedrive_export_warn_seen": False,
    "export_directory": "",
    "powershell7_upgrade_prompt": True,
    "powershell7_upgrade_dismissed": False,
    "cdb_online_install_prompt": True,
    "cdb_online_install_dismissed": False,
    "seven_zip_install_prompt": True,
    "seven_zip_install_dismissed": False,
    "last_maintenance_at": "",
    "custom_data_dir": "",
    "vendor_endpoint_manifest_url": "",
    "app_update_manifest_url": "",
    "vendor_js_render_fallback": True,
    "mscatalog_auto_update": True,
    "nvidia_html_lookup_fallback": False,
    "gui_batched_online_store": True,
    "gui_batched_online_store_include_all": False,
    "gui_catalog_parallel_workers": 6,
    "gui_mscatalog_prewarm": False,
    # Parallel batch warm: run each batch's unique MSCatalog searches in ONE PowerShell process
    # with bounded internal parallelism (pwsh 7) instead of one serialized
    # subprocess per query. Main catalog-scan speed-up. Falls back to sequential
    # automatically when pwsh 7 is unavailable.
    "gui_mscatalog_batched_parallel": True,
    "gui_mscatalog_parallel_throttle": 6,
    # Queries per parallel sub-batch. Smaller chunks keep the progress bar/status
    # moving during the catalog phase (each chunk posts a "searched N/total"
    # update) and let partial results seed the cache if a later chunk fails.
    "gui_mscatalog_parallel_chunk": 24,
    "auto_crash_linked_catalog": True,
    "ui_theme": "night",
    "driver_backup_folder": "",
    "driver_backup_before_install": True,
    "driver_backup_keep_count": 3,
    "driver_install_checklist_seen": False,
}


def is_portable_layout() -> bool:
    """True when the user selected portable mode (not full install)."""
    return not is_full_install_mode()


def apply_full_install_defaults(settings: dict) -> dict:
    """Full install: persistent device list + check cache under LOCALAPPDATA."""
    out = dict(settings)
    out["install_mode"] = "full"
    out["install_mode_chosen"] = True
    out["use_driver_index"] = True
    out["auto_load_all_drivers_on_scan"] = True
    out["quick_check_mode"] = False
    out["oem_session_cache"] = True
    out["remember_driver_firmware_checks"] = True
    out["catalog_auto_refresh_prompt"] = True
    return out


def apply_portable_defaults(settings: dict) -> dict:
    """Portable: no driver inventory or check results saved between sessions."""
    out = dict(settings)
    out["install_mode"] = "portable"
    out["install_mode_chosen"] = True
    out["use_driver_index"] = False
    out["auto_load_all_drivers_on_scan"] = True
    out["remember_driver_firmware_checks"] = False
    out["quick_check_mode"] = False
    out["catalog_auto_refresh_prompt"] = False
    return out


def catalog_max_age_days(settings: dict | None = None) -> int:
    s = settings if settings is not None else load_settings()
    try:
        days = int(s.get("catalog_cache_max_age_days", s.get("device_cache_max_age_days", 30)))
    except (TypeError, ValueError):
        days = 30
    return max(1, min(days, 365))


def touch_last_maintenance(when: str | None = None) -> None:
    s = load_settings()
    s["last_maintenance_at"] = when or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    save_settings(s)


def last_maintenance_summary(settings: dict | None = None) -> str:
    s = settings if settings is not None else load_settings()
    raw = (s.get("last_maintenance_at") or "").strip()
    if not raw:
        return "No driver activity recorded yet"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).days
        return f"Last driver activity: {days} day(s) ago ({raw[:10]})"
    except ValueError:
        return f"Last driver activity: {raw[:10]}"


def clear_full_install_caches() -> None:
    """Remove on-disk driver data when switching to portable mode."""
    try:
        import hardware_cache as hwcache
        hwcache.clear_cache()
    except ImportError:
        pass
    try:
        import catalog_cache as ccat
        ccat.clear_catalog_cache()
    except ImportError:
        pass
    clear_check_cache()
    try:
        import driver_index as drvidx
        drvidx.clear_index()
    except ImportError:
        for name in ("driver_index.sqlite", "hardware_profile_cache.sqlite"):
            fp = full_install_data_dir() / name
            if fp.is_file():
                try:
                    fp.unlink()
                except OSError:
                    pass


def load_settings() -> dict[str, Any]:
    path = _settings_path()
    data = dict(DEFAULT_SETTINGS)
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (json.JSONDecodeError, OSError):
            pass
        if not data.get("install_mode_chosen") and data.get("install_mode") in (
            "full",
            "portable",
        ):
            data["install_mode_chosen"] = True
    if not is_full_install_mode(data):
        data["remember_driver_firmware_checks"] = False
        data["use_driver_index"] = False
    return data


def peek_settings_save_error() -> str | None:
    """Return and clear the last settings save failure message (for status bar)."""
    global _last_settings_save_error
    err = _last_settings_save_error
    _last_settings_save_error = None
    return err


def _exe_settings_key() -> str:
    return hashlib.sha256(str(_exe_parent_dir()).lower().encode()).hexdigest()[:16]


def _portable_redirect_path() -> Path:
    return default_full_install_data_dir() / "portable_redirects" / f"{_exe_settings_key()}.json"


def _portable_fallback_settings_path() -> Path:
    return (
        default_full_install_data_dir()
        / "portable_settings"
        / _exe_settings_key()
        / "settings.json"
    )


def _read_portable_redirect() -> Path | None:
    path = _portable_redirect_path()
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return None
        target = Path(str(loaded.get("settings_path") or "").strip())
        if target.is_file():
            return target
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _activate_portable_redirect(settings_path: Path) -> None:
    redirect = _portable_redirect_path()
    redirect.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        redirect,
        json.dumps({"settings_path": str(settings_path)}, indent=2),
    )


def _clear_readonly(path: Path) -> None:
    if not path.is_file():
        return
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _atomic_write_text(path: Path, text: str, *, retries: int = 3) -> tuple[bool, str | None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    last_err: str | None = None
    for attempt in range(max(retries, 1)):
        try:
            _clear_readonly(path)
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
            return True, None
        except OSError as exc:
            last_err = str(exc)
            try:
                if tmp.is_file():
                    tmp.unlink()
            except OSError:
                pass
            if attempt + 1 < retries:
                time.sleep(0.12 * (attempt + 1))
    return False, last_err


def save_settings(settings: dict[str, Any]) -> bool:
    global _last_settings_save_error
    data = dict(DEFAULT_SETTINGS)
    data.update(settings)
    data["version"] = SETTINGS_VERSION
    if is_full_install_mode(data):
        data["custom_data_dir"] = normalize_custom_data_dir(
            data.get("custom_data_dir") or ""
        )
    text = json.dumps(data, indent=2)
    redirect = _read_portable_redirect()
    path = redirect if redirect is not None else _ensure_dir(data) / "settings.json"
    ok, err = _atomic_write_text(path, text)
    if ok:
        _last_settings_save_error = None
        if is_full_install_mode(data):
            custom = (data.get("custom_data_dir") or "").strip()
            if custom:
                _write_data_dir_pointer(custom)
        return True
    if is_full_install_mode(data):
        _last_settings_save_error = f"Could not save settings: {err}"
        return False
    fallback = _portable_fallback_settings_path()
    ok_fb, err_fb = _atomic_write_text(fallback, text)
    if ok_fb:
        _activate_portable_redirect(fallback)
        _last_settings_save_error = (
            "Settings could not be saved to PC-local storage "
            f"({err or 'permission denied'}). "
            f"Using local copy under {fallback.parent}."
        )
        return True
    _last_settings_save_error = f"Could not save settings: {err_fb or err}"
    return False


def load_ignored_devices() -> set[str]:
    if not allows_persistent_driver_data():
        return set()
    path = _ignored_path()
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x).strip() for x in data if str(x).strip()}
    except (json.JSONDecodeError, OSError):
        pass
    return set()


def save_ignored_devices(names: set[str]) -> None:
    if not allows_persistent_driver_data():
        return
    _ignored_path().write_text(
        json.dumps(sorted(names), indent=2),
        encoding="utf-8",
    )


def load_check_cache() -> dict[str, dict]:
    """Legacy read — prefer driver_index; migrates JSON on first access."""
    if not allows_persistent_driver_data():
        return {}
    try:
        import driver_index as drvidx
        drvidx.migrate_legacy_check_cache()
    except ImportError:
        pass
    path = _checks_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_check_cache(cache: dict[str, dict]) -> None:
    """Deprecated — writes legacy JSON only if caller still uses this API."""
    if not allows_persistent_driver_data():
        return
    _checks_path().write_text(json.dumps(cache, indent=2), encoding="utf-8")


def update_check_cache_entry(
    kind: str,
    key: str,
    *,
    status: str,
    installed_version: str = "",
    fetched_at: str = "",
    extra: dict | None = None,
) -> None:
    """kind: 'driver' | 'firmware'; persisted in driver_index.sqlite."""
    if not allows_persistent_driver_data():
        return
    try:
        import driver_index as drvidx
    except ImportError:
        cache = load_check_cache()
        entry = {
            "kind": kind,
            "status": status,
            "installed_version": installed_version,
            "fetched_at": fetched_at or datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        if extra:
            entry.update(extra)
        cache[f"{kind}:{key}"] = entry
        save_check_cache(cache)
        return
    detail = json.dumps(extra) if extra else ""
    if kind == "firmware":
        drvidx.save_firmware_check(
            key,
            status,
            installed_version=installed_version,
            fetched_at=fetched_at,
            detail=detail,
        )
    else:
        drvidx.save_check_result(
            key,
            status,
            installed_version=installed_version,
            fetched_at=fetched_at,
            detail=detail,
        )


def get_check_cache_entry(kind: str, key: str) -> dict | None:
    if not allows_persistent_driver_data():
        return None
    try:
        import driver_index as drvidx
    except ImportError:
        return load_check_cache().get(f"{kind}:{key}")
    if kind == "firmware":
        row = drvidx.get_firmware_cached(key)
    else:
        row = drvidx.get_cached_status(key)
    if not row:
        return None
    return {
        "kind": kind,
        "status": row.get("status"),
        "installed_version": row.get("installed_version"),
        "fetched_at": row.get("fetched_at") or row.get("checked_at"),
    }


def clear_check_cache() -> None:
    if not allows_persistent_driver_data():
        return
    try:
        import driver_index as drvidx
        drvidx.clear_index()
        return
    except ImportError:
        pass
    path = _checks_path()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def snapshot_from_model(model: dict) -> dict:
    """Minimal snapshot for compare — no full report."""
    events = model.get("incidents") or []
    times = [e.get("time") for e in events if e.get("time")]
    timeline = model.get("crash_timeline") or {}
    return {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "stop_name": model.get("stop_name") or "",
        "driver": model.get("driver") or "",
        "severity_name": model.get("severity_name") or "",
        "recurring_count": model.get("recurring_count") or 0,
        "last_crash": model.get("last_crash") or (times[0] if times else ""),
        "crash_timeline": timeline,
        "generic_driver_count": len(model.get("devices_with_generic_driver") or []),
        "problem_driver_count": len(model.get("devices_with_driver_problems") or []),
        "bios_version": (
            (model.get("bios_driver_info") or {}).get("bios") or {}
        ).get("version")
        or "",
        "gpu_vendor": (model.get("system_ctx") or {}).get("gpu_vendor") or "",
        "stability_index": (model.get("reliability_ctx") or {}).get("stability_index"),
        "livekernel_count": len((model.get("reliability_ctx") or {}).get("livekernel") or []),
    }


def save_snapshot(model: dict, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(snapshot_from_model(model), indent=2),
        encoding="utf-8",
    )


def load_snapshot(path: str | Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def compare_snapshots(old: dict, new: dict) -> list[str]:
    """Human-readable lines describing what changed."""
    lines: list[str] = []
    if not old or not new:
        return ["Need both a saved baseline and a current analysis to compare."]
    lines.append(f"Baseline saved: {old.get('saved_at', '?')}")
    lines.append(f"Current as of: {new.get('saved_at', '?')}")
    lines.append("")

    def _chg(label: str, a: Any, b: Any) -> None:
        if str(a or "") != str(b or ""):
            lines.append(f"• {label}: was “{a or '—'}” → now “{b or '—'}”")

    _chg("Likely driver", old.get("driver"), new.get("driver"))
    _chg("Stop code", old.get("stop_name"), new.get("stop_name"))
    _chg("Severity", old.get("severity_name"), new.get("severity_name"))
    _chg("Recurring incidents", old.get("recurring_count"), new.get("recurring_count"))
    _chg("Last crash time", old.get("last_crash"), new.get("last_crash"))
    _chg("Generic-driver devices", old.get("generic_driver_count"), new.get("generic_driver_count"))
    _chg("Problem-driver devices", old.get("problem_driver_count"), new.get("problem_driver_count"))
    _chg("BIOS version", old.get("bios_version"), new.get("bios_version"))

    ot = old.get("crash_timeline") or {}
    nt = new.get("crash_timeline") or {}
    if ot or nt:
        lines.append("")
        lines.append("Crash frequency:")
        _chg("  BSODs in last 7 days", ot.get("count_7d"), nt.get("count_7d"))
        _chg("  BSODs in last 30 days", ot.get("count_30d"), nt.get("count_30d"))

    _chg("Stability index", old.get("stability_index"), new.get("stability_index"))
    _chg("Live Kernel events (count)", old.get("livekernel_count"), new.get("livekernel_count"))

    if len(lines) <= 4:
        lines.append("")
        lines.append("No significant differences in tracked fields.")
    return lines


def format_diagnosis_clipboard(model: dict) -> str:
    """Plain-text summary for support tickets."""
    lines = ["BSOD Analyzer diagnosis", "—" * 40]
    lines.append(f"Severity: {model.get('severity_name', '?')}")
    lines.append(f"Summary: {model.get('cause_title', '?')}")
    if model.get("driver"):
        lines.append(f"Faulting driver: {model.get('driver')}")
    if model.get("stop_name"):
        lines.append(f"Stop code: {model.get('stop_name')}")
    tl = model.get("crash_timeline") or {}
    if tl:
        lines.append(
            f"Crashes: {tl.get('count_7d', 0)} in 7 days, {tl.get('count_30d', 0)} in 30 days"
        )
        if tl.get("last_clean_hint"):
            lines.append(f"Note: {tl['last_clean_hint']}")
    rel = model.get("reliability_ctx") or {}
    stab = rel.get("stability_index")
    if stab is not None:
        lines.append(f"Stability index: {stab} (10 = most stable)")
    lk = rel.get("livekernel") or []
    if lk:
        lines.append(f"Live Kernel events in log: {len(lk)}")
    pe = (model.get("plain_english") or "").strip()
    if pe:
        lines.append("")
        lines.append(pe[:1200])
    recs = model.get("recommendations") or []
    if recs:
        lines.append("")
        lines.append("Top actions:")
        for r in recs[:6]:
            lines.append(f"  - {r}")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


def release_notes_path() -> Path | None:
    """Best-effort path to VERSION.txt beside the exe or in the project tree."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "VERSION.txt")
    root = Path(__file__).resolve().parent
    candidates.extend(
        (
            root / "VERSION.txt",
            root / "BSODAnalyzer_v5" / "VERSION.txt",
        )
    )
    for path in candidates:
        if path.is_file():
            return path
    return None
