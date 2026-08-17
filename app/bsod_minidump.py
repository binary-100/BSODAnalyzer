"""CDB debugger tooling and minidump discovery / WER recovery."""
from __future__ import annotations

import ctypes
import glob
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime

import log_read_windows as lrw

from bsod_runtime import console_print


def _ba(name: str):
    """Lazy bsod_analyzer lookup — avoids import cycles during module load."""
    import bsod_analyzer as ba

    return getattr(ba, name)


def minidump_capture_action_step(*, needs_config: bool) -> str | None:
    """Action Plan step to improve crash capture; None when admin + dumps already OK."""
    admin = _ba('is_user_admin')()
    if needs_config:
        if admin:
            return (
                "Enable memory dumps (Settings or Advanced tab) so the next crash "
                "records a minidump for analysis."
            )
        return (
            "Run analysis as Administrator and enable memory dumps so the next "
            "crash captures a minidump."
        )
    if not admin:
        return "Run analysis as Administrator for full event log and minidump access."
    return None

CRASH_CONTROL_KEY = r"SYSTEM\CurrentControlSet\Control\CrashControl"

DUMP_TYPES = {0: "Disabled", 1: "Small memory dump (minidump)", 2: "Kernel memory dump",
              3: "Complete memory dump", 7: "Automatic memory dump"}

WINDOWS_DIR = os.environ.get("SystemRoot", "C:\\Windows")

MINIDUMP_DIR = os.path.join(WINDOWS_DIR, "Minidump")

FULL_DUMP_PATH = os.path.join(WINDOWS_DIR, "MEMORY.DMP")

MINIDUMP_DISK_WARN_MB = 500

MINIDUMP_DISK_CRITICAL_MB = 50

WER_REPORT_ARCHIVE = os.path.join(
    os.environ.get("ProgramData", r"C:\ProgramData"),
    "Microsoft",
    "Windows",
    "WER",
    "ReportArchive",
)

class _VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", ctypes.c_uint32),
        ("dwStrucVersion", ctypes.c_uint32),
        ("dwFileVersionMS", ctypes.c_uint32),
        ("dwFileVersionLS", ctypes.c_uint32),
        ("dwProductVersionMS", ctypes.c_uint32),
        ("dwProductVersionLS", ctypes.c_uint32),
        ("dwFileFlagsMask", ctypes.c_uint32),
        ("dwFileFlags", ctypes.c_uint32),
        ("dwFileOS", ctypes.c_uint32),
        ("dwFileType", ctypes.c_uint32),
        ("dwFileSubtype", ctypes.c_uint32),
        ("dwFileDateMS", ctypes.c_uint32),
        ("dwFileDateLS", ctypes.c_uint32),
    ]

def _file_version(path: str) -> str | None:
    """Return the file version of a Windows binary (e.g. '10.0.26100.1') or None."""
    if sys.platform != "win32" or not path or not os.path.isfile(path):
        return None
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return None
        ptr = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)) or not ptr.value:
            return None
        ffi = ctypes.cast(ptr, ctypes.POINTER(_VS_FIXEDFILEINFO)).contents
        ms, ls = ffi.dwFileVersionMS, ffi.dwFileVersionLS
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return None

def _get_tool_dir() -> str:
    """Get directory containing the exe or script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _cdb_arch_dir() -> str:
    """Debugger engine subfolder: arm64 on WoA, x64 elsewhere."""
    if sys.platform == "win32":
        machine = (
            os.environ.get("PROCESSOR_ARCHITEW6432")
            or os.environ.get("PROCESSOR_ARCHITECTURE")
            or platform.machine()
            or ""
        ).upper()
        if machine in ("ARM64", "AARCH64"):
            return "arm64"
    return "x64"

def _cdb_search_arch_dirs() -> list[str]:
    """Search order for bundled/local debugger engines."""
    primary = _cdb_arch_dir()
    if primary == "arm64":
        return ["arm64", "x64"]
    return ["x64"]

def _get_local_cdb_path() -> str:
    """Path to a writable local cdb.exe next to the tool (created by install/update)."""
    return os.path.join(_get_tool_dir(), "DebuggingTools", _cdb_arch_dir(), "cdb.exe")

def _get_bundled_cdb_path() -> str | None:
    """Path to cdb.exe bundled inside the packaged app (PyInstaller _MEIPASS / onedir _internal).

    This is what makes a single-exe build self-contained: the Debugging Tools are
    extracted alongside the app at launch, so CDB works on a fresh offline machine.
    """
    bases: list[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(meipass)
    if getattr(sys, "frozen", False):
        internal = os.path.join(_get_tool_dir(), "_internal")
        if internal not in bases:
            bases.append(internal)
    for base in bases:
        for sub in _cdb_search_arch_dirs():
            path = os.path.join(base, "DebuggingTools", sub, "cdb.exe")
            if os.path.isfile(path):
                return path
    return None

def _find_windbg_app_engine_dir() -> str | None:
    """Locate the modern WinDbg app's x64 engine dir (has cdb.exe + winext\\ext.dll).

    The Store/winget WinDbg app installs under Program Files\\WindowsApps\\Microsoft.WinDbg_*.
    Its engine has a static analyze extension, so it works offline. Returns the amd64 dir.
    """
    import glob
    bases = [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "WindowsApps"),
        os.path.join(os.environ.get("ProgramW6432", "C:\\Program Files"), "WindowsApps"),
    ]
    arch_subdirs = ["arm64", "amd64"] if _cdb_arch_dir() == "arm64" else ["amd64"]
    candidates = []
    for base in bases:
        for sub in arch_subdirs:
            candidates.extend(glob.glob(os.path.join(base, "Microsoft.WinDbg_*", sub)))
    # Prefer the highest version folder name (lexical sort is good enough for these).
    for d in sorted(set(candidates), reverse=True):
        if os.path.isfile(os.path.join(d, "cdb.exe")) and os.path.isfile(os.path.join(d, "winext", "ext.dll")):
            return d
    return None

def _get_windbg_app_cdb_path() -> str | None:
    d = _find_windbg_app_engine_dir()
    return os.path.join(d, "cdb.exe") if d else None

def _cdb_engine_usable(cdb_path: str | None) -> bool:
    """True when cdb.exe has winext/ext.dll (modern static !analyze, works offline)."""
    if not cdb_path or not os.path.isfile(cdb_path):
        return False
    engine_dir = os.path.dirname(cdb_path)
    return os.path.isfile(os.path.join(engine_dir, "winext", "ext.dll"))

def _get_cdb_search_paths() -> list:
    """CDB search order: writable local copy, bundled copy, WinDbg app engine, SDK.

    Skips engine dirs missing !analyze extensions (incomplete local copies).
    """
    raw = [_get_local_cdb_path()]
    bundled = _get_bundled_cdb_path()
    if bundled:
        raw.append(bundled)
    app_cdb = _get_windbg_app_cdb_path()
    if app_cdb:
        raw.append(app_cdb)
    raw.extend([
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Windows Kits", "10", "Debuggers", sub, "cdb.exe")
        for sub in _cdb_search_arch_dirs()
    ])
    raw.extend([
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Windows Kits", "10", "Debuggers", sub, "cdb.exe")
        for sub in _cdb_search_arch_dirs()
    ])
    seen: set[str] = set()
    paths: list[str] = []
    for p in raw:
        norm = os.path.normcase(os.path.normpath(p))
        if norm in seen or not os.path.isfile(p):
            continue
        seen.add(norm)
        if _cdb_engine_usable(p):
            paths.append(p)
    return paths

def _get_bundled_installer_dir() -> str:
    """Path to folder where a bundled offline installer can be placed (DebuggingTools/Installers)."""
    return os.path.join(_get_tool_dir(), *BUNDLED_INSTALLER_SUBDIR)

def _find_bundled_installer() -> str | None:
    """Return path to bundled offline installer if present (Microsoft winsdksetup.exe preferred, else any .exe)."""
    installers_dir = _get_bundled_installer_dir()
    if not os.path.isdir(installers_dir):
        return None
    # Prefer Microsoft Windows SDK installer by name (winsdksetup.exe)
    preferred = os.path.join(installers_dir, WINSDK_SETUP_NAME)
    if os.path.isfile(preferred):
        return preferred
    # Fallback: any .exe in the folder
    try:
        for name in sorted(os.listdir(installers_dir)):
            if name.lower().endswith(".exe"):
                path = os.path.join(installers_dir, name)
                if os.path.isfile(path):
                    return path
    except OSError:
        pass
    return None

def _run_bundled_installer(installer_path: str) -> bool:
    """Run Windows SDK installer so Debugging Tools for Windows (CDB) install to default location. Returns True if install succeeded (cdb found afterward)."""
    base = os.path.basename(installer_path)
    use_silent = base.lower() == WINSDK_SETUP_NAME.lower()
    try:
        if use_silent:
            cmd = [installer_path] + WINSDK_SILENT_ARGS
            proc = subprocess.run(
                cmd,
                timeout=900,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            ok = proc.returncode == 0
        else:
            # Run installer and wait; user may need to complete GUI
            proc = subprocess.run([installer_path], timeout=900)
            ok = proc.returncode == 0
        if ok or find_cdb():
            return True
        # Installer may exit before fully done; give a moment and recheck
        import time
        time.sleep(5)
        return find_cdb()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

WINDBGX_PATHS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "WinDbgX.exe"),
    "WinDbgX.exe",
]

WINDBG_WINGET_PACKAGE = "Microsoft.WinDbg"

CDB_WINGET_PACKAGES = [
    "Microsoft.WindowsSDK.10.0.26100",
    "Microsoft.WindowsSDK.10.0.22621",
    "Microsoft.WindowsSDK.10.0.19041",
    "Microsoft.WindowsSDK.10.0.18362",
]

WINGET_OVERRIDE_ARGS = "/features OptionId.WindowsDesktopDebuggers /quiet /norestart"

BUNDLED_INSTALLER_SUBDIR = ("DebuggingTools", "Installers")

WINSDK_SETUP_NAME = "winsdksetup.exe"

WINSDK_SILENT_ARGS = ["/features", "OptionId.WindowsDesktopDebuggers", "/q", "/norestart"]

CDB_INSTALL_EXPLANATION = """
  WHY CDB IS NEEDED:
  Event logs only tell us the STOP CODE (e.g. DRIVER_IRQL_NOT_LESS_OR_EQUAL).
  To identify the EXACT driver that caused the crash (e.g. "nvlddmkm.sys"),
  we need CDB (Console Debugger) from Microsoft's Debugging Tools for Windows
  to analyze the minidump file. This gives you the precise faulting driver
  so you can update or rollback it. Without CDB, we can only show generic causes.
  The tool installs Debugging Tools for Windows (includes CDB) to the default
  location and keeps a local copy for offline use. Offline: uses Windows SDK
  installer (winsdksetup.exe) from DebuggingTools\\Installers\\. Online: gets
  latest from Microsoft (winget)."""

def _run_winget(verb: str, package: str, timeout: int = 900, override: bool = False) -> tuple[int, str]:
    """Run a winget verb (install/upgrade) for a package non-interactively, capturing output.

    When override is True, passes SDK installer args to select only the Debugging Tools
    feature (used for the legacy SDK packages). Returns (returncode, output);
    a returncode of -1 means winget could not be launched at all.
    """
    cmd = [
        "winget", verb, "--id", package, "-e",
        "--accept-package-agreements", "--accept-source-agreements",
        "--disable-interactivity",
    ]
    if override:
        cmd += ["--override", WINGET_OVERRIDE_ARGS]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return -1, "winget timed out."
    except (FileNotFoundError, OSError):
        return -1, "winget is not available on this system."

def _run_winget_install(package: str) -> bool:
    """Install the Debugging Tools (CDB) for a Windows SDK package via winget."""
    rc, _out = _run_winget("install", package, override=True)
    return rc == 0 or find_cdb() is not None

def _winget_available_version(package: str) -> str | None:
    """Newest available version of a winget package (via 'winget show'), or None."""
    try:
        proc = subprocess.run(
            ["winget", "show", "--id", package, "-e",
             "--accept-source-agreements", "--disable-interactivity"],
            capture_output=True, text=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"^\s*Version:\s*(.+)$", out, re.MULTILINE)
        return m.group(1).strip() if m else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None

def install_cdb(progress=None) -> tuple[bool, str]:
    """Install a working CDB (WinDbg app engine). Non-interactive / GUI-safe.

    Online: installs the Microsoft WinDbg app via winget (its CDB analyzes dumps offline).
    Offline: uses the bundled Windows SDK installer in DebuggingTools/Installers/ if present.
    Either way a local offline copy is saved next to the tool. Returns (ok, message).
    `progress` (optional) is called with short status strings as work proceeds.
    """
    def _say(msg: str) -> None:
        if progress:
            try:
                progress(msg)
            except Exception:
                pass  # user progress callback; must not abort CDB install

    existing = find_cdb()
    if existing:
        return True, f"CDB is already available ({existing})."

    if _is_online():
        _say("Online: installing the Microsoft WinDbg debugger via winget...")
        rc, out = _run_winget("install", WINDBG_WINGET_PACKAGE)
        if rc == -1:
            return False, ("winget is not available on this system. Install 'WinDbg' from the "
                           "Microsoft Store, or the Windows SDK Debugging Tools from "
                           "https://developer.microsoft.com/windows/downloads/windows-sdk/")
        if rc == 0 or _find_windbg_app_engine_dir() or find_cdb():
            clear_cdb_path_cache()
            _say("Saving a local offline copy in the DebuggingTools folder...")
            if _copy_debuggers_to_local():
                clear_cdb_path_cache()
                return True, "WinDbg/CDB installed and a local offline copy was saved for offline use."
            if find_cdb():
                return True, ("WinDbg/CDB installed. Run the tool once as Administrator to also save "
                              "a local offline copy.")
        return False, ("Install via winget did not complete. Try installing 'WinDbg' from the "
                       "Microsoft Store, then reopen this tool.")

    # Offline path: only the bundled installer in the tool folder (legacy SDK).
    installer = _find_bundled_installer()
    if not installer:
        return False, ("Offline and no bundled installer found. Connect to the internet to install "
                       "WinDbg, or place a Windows SDK installer (winsdksetup.exe) in:\n  "
                       f"{_get_bundled_installer_dir()}\nthen try again.")
    _say("Offline: installing CDB from the bundled Windows SDK installer...")
    if _run_bundled_installer(installer):
        clear_cdb_path_cache()
        _say("Saving a local offline copy in the DebuggingTools folder...")
        _copy_debuggers_to_local()
        clear_cdb_path_cache()
        return True, "CDB installed from the bundled installer and a local offline copy was saved."
    return False, ("The bundled installer finished but CDB was not found. Try running the tool as "
                   "Administrator.")

def get_cdb_version(cdb_path: str | None = None) -> str | None:
    """Version string of the installed cdb.exe (e.g. '10.0.26100.1'), or None if not found."""
    cdb = cdb_path or find_cdb()
    return _file_version(cdb) if cdb else None

def cdb_status() -> dict:
    """Snapshot of CDB availability for UIs.

    Keys: installed (bool), path (str|None), is_local (bool), version (str|None),
    online (bool), bundled_installer (bool).
    """
    path = find_cdb()
    bundled = _get_bundled_cdb_path()
    is_bundled = bool(path and bundled and os.path.normcase(path) == os.path.normcase(bundled))
    return {
        "installed": path is not None,
        "path": path,
        "is_local": bool(path and "DebuggingTools" in path),
        "is_bundled": is_bundled,
        "version": get_cdb_version(path) if path else None,
        "online": _is_online(),
        "bundled_installer": _find_bundled_installer() is not None,
    }

def update_cdb(progress=None) -> tuple[bool, str]:
    """When online, upgrade to the newest Debugging Tools and refresh the local offline copy.

    Reads the cdb.exe version before/after so the caller can tell the user whether a newer
    build was actually installed. Returns (ok, message). GUI-safe / non-interactive.
    """
    def _say(msg: str) -> None:
        if progress:
            try:
                progress(msg)
            except Exception:
                pass  # user progress callback; must not abort CDB upgrade

    if not _is_online():
        return False, "No internet connection. Connect to the internet to check for a newer CDB."
    before_path = find_cdb()
    if not before_path:
        return install_cdb(progress=progress)
    before_ver = get_cdb_version(before_path) or "unknown"
    _say(f"Installed CDB version: {before_ver}. Checking Microsoft for a newer WinDbg build (winget)...")
    latest_pkg = _winget_available_version(WINDBG_WINGET_PACKAGE)
    if latest_pkg:
        _say(f"Newest WinDbg package available from Microsoft: {latest_pkg}.")
    newest_note = f" Newest WinDbg available: {latest_pkg}." if latest_pkg else ""
    winget_ran = False
    for verb in ("upgrade", "install"):
        rc, out = _run_winget(verb, WINDBG_WINGET_PACKAGE)
        if rc != -1:
            winget_ran = True
        if rc == 0:
            break
    if not winget_ran:
        return False, "winget is not available, so updates cannot be checked automatically."
    _say("Refreshing the local offline copy...")
    _copy_debuggers_to_local()
    clear_cdb_path_cache()
    after_ver = get_cdb_version(find_cdb()) or before_ver
    if after_ver != before_ver:
        return True, f"Updated CDB: {before_ver} -> {after_ver} (installed build).{newest_note} Local offline copy refreshed."
    return True, f"CDB is already up to date (installed build {after_ver}).{newest_note}"

def prompt_install_cdb() -> bool:
    """CLI: explain why CDB helps, then install it (online via winget, else bundled installer)."""
    try:
        if not sys.stdin.isatty():
            return False
        if find_cdb():
            return True  # Already installed, no prompt
        console_print(CDB_INSTALL_EXPLANATION)
        r = input("\nInstall Debugging Tools for Windows (includes CDB) now? (Y/N): ").strip().upper()
        if r != "Y":
            return False
        console_print("  " + "-" * 50)
        ok, msg = install_cdb(progress=lambda m: console_print("  " + m))
        console_print("  " + "-" * 50)
        console_print("  " + msg)
        return ok
    except (EOFError, OSError):
        return False

_CDB_CACHE_UNSET = object()

_CDB_PATH_CACHE: str | None | object = _CDB_CACHE_UNSET

def clear_cdb_path_cache() -> None:
    """Invalidate memoized find_cdb() result after install/update/copy."""
    global _CDB_PATH_CACHE
    _CDB_PATH_CACHE = _CDB_CACHE_UNSET

def find_cdb() -> str | None:
    """Find CDB (Console Debugger) for minidump analysis. Prefers local copy (offline-capable)."""
    global _CDB_PATH_CACHE
    if _CDB_PATH_CACHE is not _CDB_CACHE_UNSET:
        return _CDB_PATH_CACHE  # type: ignore[return-value]
    found: str | None = None
    for p in _get_cdb_search_paths():
        if os.path.isfile(p):
            found = p
            break
    _CDB_PATH_CACHE = found
    return found

def scan_for_cdb_and_report() -> str | None:
    """Scan for cdb, print status so user knows tool is working. Returns path if found."""
    console_print("  Scanning for Debugging Tools for Windows (CDB)...", end=" ", flush=True)
    cdb_path = find_cdb()
    if cdb_path:
        ver = get_cdb_version(cdb_path)
        ver_note = f" v{ver}" if ver else ""
        if "DebuggingTools" in cdb_path:
            console_print(f"Found (local copy){ver_note}.")
        else:
            console_print(f"Found (system install){ver_note}.")
    else:
        console_print("Not found.")
    return cdb_path

def _is_online() -> bool:
    """Quick check if system has network connectivity."""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(("8.8.8.8", 53))
        sock.close()
        return True
    except (socket.error, OSError):
        return False

_CDB_COPY_SKIP_DIRS = {"sym", "ttd"}

def _copy_engine_dir(src: str, dest: str) -> bool:
    """Copy a debugger engine folder to dest, skipping huge/irrelevant subdirs."""
    try:
        os.makedirs(dest, exist_ok=True)
        for name in os.listdir(src):
            sp = os.path.join(src, name)
            dp = os.path.join(dest, name)
            if os.path.isfile(sp):
                shutil.copy2(sp, dp)
            elif os.path.isdir(sp) and name.lower() not in _CDB_COPY_SKIP_DIRS:
                try:
                    shutil.copytree(sp, dp, dirs_exist_ok=True)
                except (OSError, PermissionError):
                    pass
        return os.path.isfile(os.path.join(dest, "cdb.exe"))
    except (OSError, PermissionError):
        return False

def _copy_debuggers_to_local() -> bool:
    """Copy a working debugger engine to the local folder for offline use.

    Prefers the WinDbg app engine (static !analyze, offline-capable); falls back to the
    SDK Debugging Tools install only if the WinDbg app is not present.
    """
    dest = os.path.join(_get_tool_dir(), "DebuggingTools", _cdb_arch_dir())
    # 1. Preferred: the WinDbg app engine (offline analyze works).
    app_dir = _find_windbg_app_engine_dir()
    if app_dir and _copy_engine_dir(app_dir, dest):
        return True
    # 2. Fallback: the legacy SDK Debugging Tools (analyze may need internet).
    for base in [os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                 os.environ.get("ProgramFiles", "C:\\Program Files")]:
        src = os.path.join(base, "Windows Kits", "10", "Debuggers", "x64")
        if os.path.isdir(src) and os.path.isfile(os.path.join(src, "cdb.exe")):
            if _copy_engine_dir(src, dest):
                return True
    return False

def repair_local_cdb_engine_if_needed() -> tuple[bool, str]:
    """Refresh the writable local DebuggingTools copy when it lacks winext\\ext.dll.

    Prefers the WinDbg app engine (same as install_cdb offline copy). Returns
    (repaired, message). Does nothing when local copy is missing or already usable.
    """
    local = _get_local_cdb_path()
    if not os.path.isfile(local):
        return False, "No local Debugging Tools copy to repair."
    if _cdb_engine_usable(local):
        return False, "Local debugger engine already supports !analyze."
    app_dir = _find_windbg_app_engine_dir()
    if not app_dir:
        return False, (
            "Local debugger engine is incomplete and WinDbg app was not found — "
            "install WinDbg from Microsoft Store, then re-run analysis."
        )
    if not _copy_debuggers_to_local():
        return False, "Could not copy WinDbg app engine into the local DebuggingTools folder."
    clear_cdb_path_cache()
    if _cdb_engine_usable(_get_local_cdb_path()):
        ver = get_cdb_version(_get_local_cdb_path()) or ""
        ver_bit = f" ({ver})" if ver else ""
        return True, f"Repaired local Debugging Tools from WinDbg app engine{ver_bit}."
    return False, "Copy finished but local debugger engine is still incomplete."

def _check_and_offer_cdb_update() -> None:
    """CLI: when online, offer to update Debugging Tools to the newest build."""
    if not _is_online() or not sys.stdin.isatty():
        return
    if not find_cdb():
        return
    try:
        cur = get_cdb_version()
        ver_note = f" (currently {cur})" if cur else ""
        r = input(f"\nCheck for a newer CDB version{ver_note}? (Y/N): ").strip().upper()
        if r != "Y":
            return
        ok, msg = update_cdb(progress=lambda m: console_print("  " + m))
        console_print("  " + msg)
    except (EOFError, OSError):
        pass

def find_windbgx() -> str | None:
    """Find WinDbgX for opening dumps."""
    for p in WINDBGX_PATHS:
        if os.path.isfile(p) or p == "WinDbgX.exe":
            return p
    return None

def launch_latest_dump_in_windbg() -> tuple[bool, str]:
    """Open the most recent kernel minidump in WinDbg with a guided command script.

    Loads symbols and runs !analyze -v automatically so the user lands on the result.
    Returns (success, message).
    """
    kernel_dumps = list_dumps(MINIDUMP_DIR, "Kernel")
    if not kernel_dumps:
        return False, "No kernel minidumps found."
    windbgx = find_windbgx()
    if not windbgx:
        return False, "WinDbg not found. Install it from the Microsoft Store if desired."
    try:
        guided_cmds = ".symfix; .reload /f; !analyze -v; kv"
        subprocess.Popen(
            [windbgx, "-z", kernel_dumps[0]["path"], "-c", guided_cmds],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True, "WinDbg launched with the latest minidump (running !analyze -v). Symbols may take a moment to download."
    except Exception as e:
        return False, str(e)

def analyze_minidump_with_cdb(dump_path: str, cdb_path: str | None = None) -> dict | None:
    """Run cdb !analyze -v and kv on minidump. Returns structured analysis dict."""
    cdb = cdb_path or find_cdb()
    if not cdb:
        return None
    try:
        cmd = [cdb, "-z", dump_path, "-G", "-c", "!analyze -v; kv; Q"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        output = (result.stdout or "") + (result.stderr or "")
        parsed = {
            "faulting_driver": None,
            "bugcheck_p1": None,
            "bugcheck_str": None,
            "bugcheck_code": None,
            "process_name": None,
            "failure_bucket_id": None,
            "symbol_name": None,
            "stack_frames": [],
            "raw": [],
        }
        in_stack_text = False
        stack_text_lines = []
        in_kv = False
        for line in output.splitlines():
            s = line.strip()
            if not s:
                if in_stack_text and stack_text_lines:
                    in_stack_text = False
                continue
            if "MODULE_NAME:" in s:
                m = re.search(r"MODULE_NAME:\s+(.+)", s)
                if m:
                    parsed["faulting_driver"] = m.group(1).strip()
                parsed["raw"].append(s)
            elif "IMAGE_NAME:" in s:
                m = re.search(r"IMAGE_NAME:\s+(.+)", s)
                if m:
                    img = m.group(1).strip()
                    if not parsed["faulting_driver"]:
                        parsed["faulting_driver"] = img
                parsed["raw"].append(s)
            elif "FAILURE_BUCKET_ID:" in s:
                m = re.search(r"FAILURE_BUCKET_ID:\s+(.+)", s)
                if m:
                    parsed["failure_bucket_id"] = m.group(1).strip()
                parsed["raw"].append(s)
                if not parsed["faulting_driver"] and parsed["failure_bucket_id"]:
                    bucket = parsed["failure_bucket_id"]
                    if "!" in bucket:
                        mod = bucket.split("!")[0].split("_")[-1]
                        if mod and mod.lower() != "unknown":
                            parsed["faulting_driver"] = mod if mod.endswith((".sys", ".dll")) else mod + ".sys"
            elif "BUGCHECK_STR:" in s:
                m = re.search(r"BUGCHECK_STR:\s+(.+)", s)
                if m:
                    parsed["bugcheck_str"] = m.group(1).strip()
                parsed["raw"].append(s)
            elif "SYMBOL_NAME:" in s:
                m = re.search(r"SYMBOL_NAME:\s+(.+)", s)
                if m:
                    parsed["symbol_name"] = m.group(1).strip()
                parsed["raw"].append(s)
            elif "PROCESS_NAME:" in s:
                m = re.search(r"PROCESS_NAME:\s+(.+)", s)
                if m:
                    parsed["process_name"] = m.group(1).strip()
                parsed["raw"].append(s)
            elif "FAULTING_MODULE:" in s:
                parsed["raw"].append(s)
            elif "BUGCHECK_P1:" in s and parsed["bugcheck_p1"] is None:
                # Modern !analyze: "BUGCHECK_P1: ffff9d8e28faff80" (bare hex, no 0x).
                m = re.search(r"BUGCHECK_P1:\s*(?:0x)?([0-9a-fA-F]+)", s)
                if m:
                    parsed["bugcheck_p1"] = "0x" + m.group(1).strip()
                parsed["raw"].append(s)
            elif "Arg1:" in s and parsed["bugcheck_p1"] is None:
                m = re.search(r"Arg1:\s*(?:0x)?([0-9a-fA-F]+)", s)
                if m:
                    parsed["bugcheck_p1"] = "0x" + m.group(1).strip()
            elif ("Bugcheck code" in s or "BUGCHECK_CODE:" in s) and parsed["bugcheck_code"] is None:
                # cdb prints the code in hex, with or without a 0x prefix ("50" == 0x50).
                m = re.search(r"(?:Bugcheck code|BUGCHECK_CODE):\s*(?:0x)?([0-9a-fA-F]+)", s, re.I)
                if m:
                    try:
                        parsed["bugcheck_code"] = "0x%X" % int(m.group(1), 16)
                    except ValueError:
                        parsed["bugcheck_code"] = m.group(1).strip()
            elif s.startswith("STACK_TEXT:"):
                in_stack_text = True
                stack_text_lines = []
            elif in_stack_text:
                if s.startswith("SYMBOL_STACK_INDEX:") or s.startswith("FOLLOWUP_NAME:"):
                    in_stack_text = False
                else:
                    stack_text_lines.append(s)
            elif "Call Site" in s and "Child-SP" in s:
                in_kv = True
            elif in_kv and ":" in s and ("!" in s or "nt" in s.lower()):
                frame = s.split(":")[-1].strip()
                if frame and len(parsed["stack_frames"]) < 4:
                    parsed["stack_frames"].append(frame)
            elif s.startswith("# ") and "kb" not in s.lower() and len(parsed["stack_frames"]) < 4:
                parts = s.split(None, 2)
                if len(parts) >= 3 and "!" in parts[2]:
                    parsed["stack_frames"].append(parts[2].strip())
        if stack_text_lines and not parsed["stack_frames"]:
            for st in stack_text_lines[:4]:
                if "!" in st:
                    parsed["stack_frames"].append(st.split()[-1] if " " in st else st)
        # Modern !analyze output has no "BUGCHECK_STR:" line; derive a readable stop code
        # from the parsed bugcheck code so the report still shows e.g. "PAGE_FAULT... (0x50)".
        if not parsed["bugcheck_str"] and parsed["bugcheck_code"]:
            try:
                code_int = int(parsed["bugcheck_code"], 16)
                name = _ba("get_bugcheck_info")(code_int)[0]
                parsed["bugcheck_str"] = name if name.lower().startswith("0x") else f"{name} (0x{code_int:08X})"
            except (ValueError, TypeError):
                pass
        parsed["raw"] = parsed["raw"][:20]
        if parsed["stack_frames"]:
            parsed["raw"].append("Stack: " + " -> ".join(parsed["stack_frames"][:3]))
        has_data = any([
            parsed["faulting_driver"], parsed["failure_bucket_id"], parsed["bugcheck_str"],
            parsed["raw"], parsed["stack_frames"],
        ])
        if has_data:
            return enrich_windbg_analysis(parsed)
        return None
    except Exception:
        return None

_KERNEL_MODULE_ALIASES = {
    "nt": "ntoskrnl.exe",
    "ntkrnlmp": "ntoskrnl.exe",
    "ntkrnlpa": "ntoskrnl.exe",
    "ntoskrnl": "ntoskrnl.exe",
}

_DUMP_EVENT_MATCH_HOURS = lrw.DUMP_INCIDENT_MATCH_HOURS

def _normalize_stack_frame(frame: str) -> str:
    if "!" not in frame:
        return frame
    mod, rest = frame.split("!", 1)
    alias = _KERNEL_MODULE_ALIASES.get(mod.lower().strip())
    if alias:
        return f"{alias}!{rest}"
    return frame

def _kernel_only_stack_top(stack_frames: list) -> str | None:
    kernel_bases = frozenset({
        "nt", "ntkrnlmp", "ntkrnlpa", "ntoskrnl", "hal",
        "win32k", "win32kbase", "win32kfull", "dxgkrnl",
    })
    if not stack_frames:
        return None
    for frame in stack_frames[:5]:
        mod = frame.split("!", 1)[0].lower()
        mod = mod.replace(".sys", "").replace(".dll", "").replace(".exe", "")
        if mod and mod not in kernel_bases:
            return None
    top_mod = stack_frames[0].split("!", 1)[0].lower()
    top_mod = top_mod.replace(".sys", "").replace(".dll", "").replace(".exe", "")
    if top_mod in ("nt", "ntkrnlmp", "ntkrnlpa", "ntoskrnl"):
        return "ntoskrnl.exe"
    alias = _KERNEL_MODULE_ALIASES.get(top_mod)
    return alias

def enrich_windbg_analysis(parsed: dict) -> dict:
    frames = parsed.get("stack_frames") or []
    if frames:
        parsed["stack_frames"] = [_normalize_stack_frame(f) for f in frames]
    fd = (parsed.get("faulting_driver") or "").strip()
    if fd:
        base = fd.lower().split(".")[0]
        alias = _KERNEL_MODULE_ALIASES.get(base)
        if alias:
            parsed["faulting_driver"] = alias
    elif parsed.get("stack_frames"):
        hint = _kernel_only_stack_top(parsed["stack_frames"])
        if hint:
            parsed["kernel_stack_top"] = hint
    return parsed

def _expand_windows_path(raw: str) -> str:
    """Expand %SystemRoot% and nested env vars in registry paths."""
    if not raw:
        return ""
    expanded = os.path.expandvars(str(raw).strip())
    if "%" in expanded:
        expanded = os.path.expandvars(expanded)
    return os.path.normpath(expanded) if expanded else ""

def get_crash_dump_settings() -> dict:
    """Read CrashControl registry: dump type and optional MinidumpDir override."""
    settings = {
        "crash_dump_enabled": None,
        "dump_type_label": "Unable to read (run as Administrator)",
        "minidump_dir": MINIDUMP_DIR,
        "minidump_dir_registry": None,
        "registry_read_ok": False,
    }
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, CRASH_CONTROL_KEY, 0, winreg.KEY_READ
        )
        val, _ = winreg.QueryValueEx(key, "CrashDumpEnabled")
        settings["crash_dump_enabled"] = val
        settings["dump_type_label"] = DUMP_TYPES.get(val, f"Unknown ({val})")
        settings["registry_read_ok"] = True
        try:
            raw_dir, _ = winreg.QueryValueEx(key, "MinidumpDir")
            if raw_dir and str(raw_dir).strip():
                settings["minidump_dir_registry"] = str(raw_dir).strip()
                expanded = _expand_windows_path(str(raw_dir).strip())
                if expanded:
                    settings["minidump_dir"] = expanded
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except (OSError, FileNotFoundError):
        pass
    return settings

def get_minidump_search_directories(settings: dict | None = None) -> list[str]:
    """Directories to scan for kernel minidumps (registry path + default)."""
    cfg = settings or get_crash_dump_settings()
    dirs: list[str] = []
    for candidate in (cfg.get("minidump_dir"), MINIDUMP_DIR):
        if not candidate:
            continue
        norm = os.path.normcase(os.path.normpath(str(candidate)))
        if norm not in {os.path.normcase(os.path.normpath(d)) for d in dirs}:
            dirs.append(str(candidate))
    return dirs

def get_drive_free_space_mb(path: str) -> float | None:
    """Free space on the drive hosting path, in megabytes."""
    if not path:
        return None
    target = path
    if not os.path.exists(target):
        drive, _ = os.path.splitdrive(os.path.abspath(target))
        if drive:
            target = drive + os.sep
        else:
            return None
    try:
        usage = shutil.disk_usage(target)
        return round(usage.free / (1024 * 1024), 1)
    except OSError:
        return None

def minidump_prerequisite_action_steps(prereqs: dict) -> list[str]:
    """Action Plan lines when minidump folder or disk blocks capture."""
    steps: list[str] = []
    if not prereqs.get("folder_exists"):
        eff = prereqs.get("effective_dir") or MINIDUMP_DIR
        steps.append(
            f"Create the minidump folder and grant Administrators write access: {eff}"
        )
    elif not prereqs.get("folder_writable"):
        eff = prereqs.get("effective_dir") or MINIDUMP_DIR
        steps.append(
            f"Fix minidump folder permissions so Windows can write crash dumps: {eff}"
        )
    free_mb = prereqs.get("free_space_mb")
    if free_mb is not None and not prereqs.get("disk_ok"):
        steps.append(
            f"Free disk space on the system drive ({free_mb} MB free; "
            f"need at least {MINIDUMP_DISK_CRITICAL_MB} MB for minidumps)."
        )
    elif free_mb is not None and prereqs.get("disk_warn"):
        steps.append(
            f"Low disk space ({free_mb} MB free) — free space before the next crash "
            "so Windows can write a minidump."
        )
    reg = prereqs.get("registry_dir")
    eff = prereqs.get("effective_dir")
    if reg and eff and os.path.normcase(reg) != os.path.normcase(MINIDUMP_DIR):
        if not os.path.isdir(eff):
            steps.append(
                f"Registry MinidumpDir points to {eff} but that folder is missing."
            )
    return steps

def assess_minidump_prerequisites(settings: dict | None = None) -> dict:
    """Folder, permissions, disk space, and registry MinidumpDir for capture readiness."""
    cfg = settings or get_crash_dump_settings()
    effective_dir = cfg.get("minidump_dir") or MINIDUMP_DIR
    directories = get_minidump_search_directories(cfg)
    folder_exists = os.path.isdir(effective_dir)
    folder_writable = folder_exists and os.access(effective_dir, os.W_OK)
    free_mb = get_drive_free_space_mb(effective_dir)
    disk_ok = free_mb is None or free_mb >= MINIDUMP_DISK_CRITICAL_MB
    disk_warn = free_mb is not None and MINIDUMP_DISK_CRITICAL_MB <= free_mb < MINIDUMP_DISK_WARN_MB
    action_steps = minidump_prerequisite_action_steps(
        {
            "effective_dir": effective_dir,
            "registry_dir": cfg.get("minidump_dir_registry"),
            "folder_exists": folder_exists,
            "folder_writable": folder_writable,
            "free_space_mb": free_mb,
            "disk_ok": disk_ok,
            "disk_warn": disk_warn,
        }
    )
    dir_detail = effective_dir
    if cfg.get("minidump_dir_registry"):
        dir_detail = f"{effective_dir} (registry MinidumpDir)"
    if not folder_exists:
        dir_detail = f"Missing: {effective_dir}"
    elif not folder_writable:
        dir_detail = f"Not writable: {effective_dir}"
    disk_detail = ""
    if free_mb is not None:
        disk_detail = f"{free_mb} MB free on system drive"
        if not disk_ok:
            disk_detail += f" — below {MINIDUMP_DISK_CRITICAL_MB} MB minimum"
        elif disk_warn:
            disk_detail += f" — below {MINIDUMP_DISK_WARN_MB} MB recommended"
    return {
        "effective_dir": effective_dir,
        "registry_dir": cfg.get("minidump_dir_registry"),
        "directories": directories,
        "folder_exists": folder_exists,
        "folder_writable": folder_writable,
        "free_space_mb": free_mb,
        "disk_ok": disk_ok,
        "disk_warn": disk_warn,
        "dir_detail": dir_detail,
        "disk_detail": disk_detail,
        "action_steps": action_steps,
    }

def collect_kernel_minidumps() -> tuple[list, dict]:
    """List kernel minidumps from registry + default folders; return (dumps, crash settings)."""
    settings = get_crash_dump_settings()
    dumps = list_dumps_from_paths(get_minidump_search_directories(settings), "Kernel")
    return dumps, settings

def _dump_entry_from_path(path: str, *, label: str = "Kernel") -> dict | None:
    try:
        stat = os.stat(path)
        mtime = datetime.fromtimestamp(stat.st_mtime)
        return {
            "path": path,
            "name": os.path.basename(path),
            "time": mtime.strftime("%Y-%m-%d %H:%M:%S"),
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "label": label,
        }
    except OSError:
        return None

def parse_report_wer(text: str) -> dict:
    """Parse WER Report.wer key=value lines."""
    parsed: dict[str, str] = {}
    for line in (text or "").splitlines():
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        parsed[key.strip()] = val.strip()
    return parsed

def _module_from_wer_bucket(bucket: str) -> str | None:
    if not bucket:
        return None
    for part in reversed(bucket.replace("\\", "/").split("_")):
        if re.search(r"\.(sys|dll|exe)$", part, re.I):
            return part
    match = re.search(r"([\w.-]+\.(?:sys|dll|exe))", bucket, re.I)
    return match.group(1) if match else None

def _wer_report_module_hint(parsed: dict) -> str | None:
    for key in ("FaultingModule", "Module", "P1"):
        val = parsed.get(key, "")
        if val and re.search(r"\.(sys|dll|exe)\b", val, re.I):
            return os.path.basename(val.split()[0])
    for key in ("BucketId", "BucketingStringKey", "Response.BucketId"):
        mod = _module_from_wer_bucket(parsed.get(key, ""))
        if mod:
            return mod
    return None

def find_wer_archive_report_for_dump(
    dump_basename: str,
    event_time: str,
    *,
    window_minutes: int = 90,
) -> dict | None:
    """Locate archived WER report referencing a cited minidump path."""
    if not dump_basename or not os.path.isdir(WER_REPORT_ARCHIVE):
        return None
    event_dt = _ba('_parse_event_time')(event_time)
    basename_lower = dump_basename.lower()
    best: dict | None = None
    best_delta = window_minutes * 60 + 1
    try:
        for entry in os.scandir(WER_REPORT_ARCHIVE):
            if not entry.is_dir():
                continue
            report_path = os.path.join(entry.path, "Report.wer")
            if not os.path.isfile(report_path):
                continue
            try:
                folder_mtime = entry.stat().st_mtime
            except OSError:
                folder_mtime = None
            if event_dt and folder_mtime is not None:
                delta = abs(folder_mtime - event_dt.timestamp())
                if delta > window_minutes * 60:
                    continue
            try:
                with open(report_path, "r", encoding="utf-8", errors="replace") as handle:
                    text = handle.read(65536)
            except OSError:
                continue
            parsed = parse_report_wer(text)
            dump_in_report = os.path.basename(parsed.get("DumpFile", "")).lower()
            if dump_in_report != basename_lower and basename_lower not in text.lower():
                continue
            if event_dt and folder_mtime is not None:
                delta = abs(folder_mtime - event_dt.timestamp())
                if best is None or delta < best_delta:
                    best_delta = delta
                    best = {
                        "report_path": report_path,
                        "folder": entry.path,
                        "parsed": parsed,
                    }
            elif best is None:
                best = {
                    "report_path": report_path,
                    "folder": entry.path,
                    "parsed": parsed,
                }
    except OSError:
        return None
    return best

def _search_minidump_by_basename(basename: str, directories: list[str]) -> str | None:
    if not basename:
        return None
    target = basename.lower()
    for directory in directories:
        candidate = os.path.join(directory, basename)
        if os.path.isfile(candidate):
            return candidate
        if not os.path.isdir(directory):
            continue
        try:
            for name in os.listdir(directory):
                if name.lower() == target:
                    path = os.path.join(directory, name)
                    if os.path.isfile(path):
                        return path
        except OSError:
            continue
    return None

def reconcile_wer_dumpfile_gaps(
    events: list,
    kernel_dumps: list,
    minidump_directories: list[str],
    *,
    minidump_prereqs: dict | None = None,
) -> dict:
    """Recover relocated minidumps and WER archive hints when Event 1001 DumpFile is missing."""
    prereqs = minidump_prereqs or {}
    search_dirs = list(minidump_directories or [])
    for evt in events or []:
        cited = (evt.get("dump") or "").strip()
        if cited:
            parent = os.path.dirname(cited)
            if parent and parent not in search_dirs:
                search_dirs.append(parent)
    existing_paths = {
        os.path.normcase(d.get("path", "")) for d in (kernel_dumps or []) if d.get("path")
    }
    relocated: list[dict] = []
    module_hints: list[dict] = []
    gaps: list[dict] = []
    action_steps: list[str] = []
    data_gap_messages: list[str] = []

    for evt in events or []:
        if evt.get("code_source") != "wer1001":
            continue
        cited = (evt.get("dump") or "").strip()
        if not cited or os.path.isfile(cited):
            continue
        basename = os.path.basename(cited)
        event_time = evt.get("time", "")
        found_path = _search_minidump_by_basename(basename, search_dirs)
        if found_path and os.path.normcase(found_path) not in existing_paths:
            entry = _dump_entry_from_path(found_path, label="Kernel (relocated)")
            if entry:
                relocated.append(
                    {
                        "cited_path": cited,
                        "found_path": found_path,
                        "event_time": event_time,
                        "entry": entry,
                    }
                )
                existing_paths.add(os.path.normcase(found_path))
                evt["dump"] = found_path
                evt["dump_recovered"] = "relocated"
            continue
        if found_path:
            evt["dump"] = found_path
            evt["dump_recovered"] = "relocated"
            continue

        wer_report = find_wer_archive_report_for_dump(basename, event_time)
        module = _wer_report_module_hint(wer_report["parsed"]) if wer_report else None
        if module:
            module_hints.append(
                {
                    "event_time": event_time,
                    "cited_path": cited,
                    "module": module,
                    "source": "wer_archive",
                    "report_path": wer_report.get("report_path", ""),
                    "bucket": (
                        wer_report.get("parsed", {}).get("BucketId")
                        or wer_report.get("parsed", {}).get("BucketingStringKey")
                        or ""
                    ),
                }
            )
            evt["wer_module_hint"] = module
            continue

        gaps.append({"event_time": event_time, "cited_path": cited})
        free_mb = prereqs.get("free_space_mb")
        if free_mb is not None and not prereqs.get("disk_ok"):
            data_gap_messages.append(
                f"WER cited minidump {cited} but the file is missing — "
                f"system drive may be too full ({free_mb} MB free)."
            )
        elif not prereqs.get("folder_writable"):
            eff = prereqs.get("effective_dir") or MINIDUMP_DIR
            data_gap_messages.append(
                f"WER cited minidump {cited} but the file is missing — "
                f"minidump folder is not writable ({eff})."
            )
        else:
            data_gap_messages.append(
                f"WER cited minidump {cited} but the file is missing on disk "
                "(deleted, moved, or removed by cleanup)."
            )

    if relocated:
        action_steps.append(
            f"Recovered {len(relocated)} minidump(s) from alternate folder(s) — "
            "analysis will use the on-disk copy."
        )
    if module_hints and not relocated:
        mods = ", ".join(dict.fromkeys(h["module"] for h in module_hints))
        action_steps.append(
            f"No minidump on disk for recent WER crash record(s); archived WER report "
            f"suggests: {mods} (lower confidence than !analyze)."
        )

    return {
        "gaps": gaps,
        "relocated_dumps": relocated,
        "module_hints": module_hints,
        "action_steps": action_steps,
        "data_gap_messages": data_gap_messages,
        "recovered_count": len(relocated) + len(module_hints),
    }

def merge_recovered_kernel_dumps(kernel_dumps: list, wer_recovery: dict) -> list:
    """Append relocated minidumps discovered during WER DumpFile reconciliation."""
    merged = list(kernel_dumps or [])
    seen = {os.path.normcase(d.get("path", "")) for d in merged if d.get("path")}
    for rec in wer_recovery.get("relocated_dumps") or []:
        entry = rec.get("entry")
        path = (entry or {}).get("path") or rec.get("found_path")
        if not path:
            continue
        norm = os.path.normcase(path)
        if norm in seen:
            continue
        if entry:
            merged.append(entry)
        else:
            built = _dump_entry_from_path(path, label="Kernel (relocated)")
            if built:
                merged.append(built)
        seen.add(norm)
    merged.sort(key=lambda x: x.get("time", ""), reverse=True)
    return merged

def build_capture_readiness(
    *,
    needs_config: bool,
    dump_config: str,
    kernel_dumps: list | None,
    events: list | None,
    windbg_analysis: dict | None,
    cdb_path: str | None = None,
    cdb_repair: dict | None = None,
    minidump_prereqs: dict | None = None,
) -> dict:
    """In-app capture state — admin, dumps, debugger, minidump folder, dump/incident match."""
    cdb_path = cdb_path if cdb_path is not None else find_cdb()
    prereqs = minidump_prereqs or assess_minidump_prerequisites()
    checks: list[dict] = []

    def _add(key: str, label: str, ok: bool, detail: str = "") -> None:
        checks.append({"key": key, "label": label, "ok": bool(ok), "detail": detail.strip()})

    admin = _ba('is_user_admin')()
    _add(
        "admin",
        "Running as Administrator",
        admin,
        "Full event log access" if admin else "Relaunch as admin for complete logs",
    )
    _add(
        "dumps",
        "Memory dumps enabled",
        not needs_config,
        dump_config if not needs_config else "Use Enable Memory Dump (Advanced tab)",
    )
    cdb_usable = bool(cdb_path and _cdb_engine_usable(cdb_path))
    if not cdb_path:
        cdb_detail = "Install Debugging Tools (Advanced tab)"
    elif not cdb_usable:
        cdb_detail = f"Incomplete engine at {cdb_path} — WinDbg app fallback may apply"
    else:
        cdb_detail = os.path.basename(os.path.dirname(cdb_path)) + "\\cdb.exe"
    repair = cdb_repair or {}
    if repair.get("repaired") and repair.get("message"):
        cdb_detail = repair["message"]
    elif repair.get("attempted") and not repair.get("repaired") and repair.get("message"):
        cdb_detail = repair["message"]
    _add("cdb", "Debugger (!analyze)", cdb_usable, cdb_detail)

    _add(
        "minidump_dir",
        "Minidump folder writable",
        prereqs.get("folder_writable"),
        prereqs.get("dir_detail") or MINIDUMP_DIR,
    )
    if prereqs.get("free_space_mb") is not None:
        _add(
            "disk_space",
            "Disk space for minidumps",
            prereqs.get("disk_ok") and not prereqs.get("disk_warn"),
            prereqs.get("disk_detail") or "",
        )

    evts = events or []
    dumps = kernel_dumps or []
    dump_matches = _ba('_dump_matches_recent_events')(windbg_analysis, evts) if evts else True
    latest_incident = evts[0].get("time", "?")[:10] if evts else "—"
    newest_dump_t = dumps[0].get("time", "")[:10] if dumps else ""
    if not evts:
        match_detail = "No recent crash events in log window"
    elif dump_matches:
        match_detail = "Latest minidump matches the latest incident"
    elif newest_dump_t:
        match_detail = (
            f"Newest dump is from {newest_dump_t}; latest incident is {latest_incident}"
        )
    else:
        match_detail = f"No minidump on disk for latest incident ({latest_incident})"
    _add("dump_match", "Dump matches latest incident", dump_matches, match_detail)

    core_keys = ("admin", "dumps", "cdb", "minidump_dir")
    core_ready = all(c["ok"] for c in checks if c["key"] in core_keys)
    disk_check = next((c for c in checks if c["key"] == "disk_space"), None)
    if disk_check and not disk_check["ok"]:
        core_ready = False
    lines = [
        f"{'OK' if c['ok'] else 'NEEDS ATTENTION'}: {c['label']}"
        + (f" — {c['detail']}" if c.get("detail") else "")
        for c in checks
    ]
    return {
        "checks": checks,
        "capture_ready": core_ready,
        "dump_matches_latest": dump_matches,
        "lines": lines,
        "minidump_prerequisites": prereqs,
        "action_steps": list(prereqs.get("action_steps") or []),
    }

def list_dumps(directory: str, label: str) -> list:
    """List dump files in directory with metadata."""
    dumps = []
    if not os.path.isdir(directory):
        return dumps
    try:
        for f in os.listdir(directory):
            if f.lower().endswith(".dmp"):
                path = os.path.join(directory, f)
                try:
                    stat = os.stat(path)
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    dumps.append({
                        "path": path,
                        "name": f,
                        "time": mtime.strftime("%Y-%m-%d %H:%M:%S"),
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "label": label,
                    })
                except OSError:
                    pass
        dumps.sort(key=lambda x: x["time"], reverse=True)
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot read minidump folder {directory}. "
            "Run BSOD Analyzer as Administrator."
        ) from exc
    return dumps

def list_dumps_from_paths(directories: list, label: str) -> list:
    """List dump files from multiple directories (e.g. all user CrashDumps)."""
    seen = set()
    all_dumps = []
    for d in directories:
        for dump in list_dumps(d, label):
            key = (dump["name"], dump["time"])
            if key not in seen:
                seen.add(key)
                all_dumps.append(dump)
    all_dumps.sort(key=lambda x: x["time"], reverse=True)
    return all_dumps

def check_full_dump() -> dict | None:
    """Check if full memory dump exists."""
    if not os.path.isfile(FULL_DUMP_PATH):
        return None
    try:
        stat = os.stat(FULL_DUMP_PATH)
        return {
            "path": FULL_DUMP_PATH,
            "time": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
        }
    except OSError:
        return None

def get_dump_config() -> tuple[int | None, str]:
    """Get current crash dump configuration from registry. Returns (value, description)."""
    settings = get_crash_dump_settings()
    if not settings.get("registry_read_ok"):
        return None, settings.get("dump_type_label", "Unable to read (run as Administrator)")
    return settings.get("crash_dump_enabled"), settings.get("dump_type_label", "Unknown")

def configure_memory_dump(dump_type: int = 1) -> tuple[bool, str]:
    """Configure Windows to create memory dumps on crash. Requires Administrator."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, CRASH_CONTROL_KEY, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "CrashDumpEnabled", 0, winreg.REG_DWORD, dump_type)
        winreg.CloseKey(key)
        return True, f"Configured: {DUMP_TYPES.get(dump_type, dump_type)}. Restart may be needed."
    except PermissionError:
        return False, "Access denied. Run as Administrator to configure."
    except Exception as e:
        return False, str(e)

def enable_memory_dumps_or_report_status(dump_type: int = 1) -> tuple[str, bool]:
    """
    Enable memory dumps if disabled; if already enabled, report current setting.
    Returns (message, registry_was_changed).
    """
    dump_val, dump_config = get_dump_config()
    if dump_val is not None and dump_val != 0:
        return f"Memory dumps are already enabled in the Windows registry ({dump_config}).", False
    ok, msg = configure_memory_dump(dump_type)
    return msg, ok
