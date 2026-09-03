"""Shared runtime helpers (paths, PowerShell, export)."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

POWERSHELL7_INSTALL_URL = (
    "https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows"
)
SEVEN_ZIP_INSTALL_URL = "https://www.7-zip.org/download.html"

_PWSH7_EXE: str | None = None
_PWSH7_VERSION: str | None = None
_PWSH7_PROBE_DONE = False

_WIN_CREATE_NO_WINDOW = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
)

def _cli_requested() -> bool:
    return any(a.strip().lower() in ("--cli", "-c", "/cli") for a in sys.argv[1:])


def ensure_cli_console() -> None:
    """Windowed frozen exe (console=False) needs a real console for --cli output."""
    if not getattr(sys, "frozen", False) or sys.platform != "win32" or not _cli_requested():
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if kernel32.GetConsoleWindow() == 0:
            kernel32.AllocConsole()
        sys.stdout = io.TextIOWrapper(
            io.open(1, "wb", closefd=False),
            encoding="utf-8",
            errors="replace",
            line_buffering=True,
        )
        sys.stderr = io.TextIOWrapper(
            io.open(2, "wb", closefd=False),
            encoding="utf-8",
            errors="replace",
            line_buffering=True,
        )
        sys.stdin = io.TextIOWrapper(
            io.open(0, "rb", closefd=False),
            encoding="utf-8",
            errors="replace",
        )
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except OSError:
        pass


def configure_console_encoding() -> None:
    """Best-effort UTF-8 console on Windows so analysis reports can print Unicode."""
    if sys.platform != "win32":
        return
    ensure_cli_console()
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except OSError:
        pass


def _safe_stream_write(stream, text: str) -> None:
    """Write text without raising UnicodeEncodeError on limited Windows consoles."""
    if not text:
        return
    raw = getattr(stream, "buffer", None)
    enc = getattr(stream, "encoding", None) or "utf-8"
    payload = text.encode(enc, errors="replace")
    if raw is not None:
        raw.write(payload)
        return
    try:
        stream.write(payload.decode(enc, errors="replace"))
    except Exception:
        stream.write(text.encode("ascii", errors="replace").decode("ascii"))


def console_print(*objects: object, sep: str = " ", end: str = "\n", file=None, flush: bool = False) -> None:
    """Print text without crashing when the console codec cannot encode Unicode."""
    stream = file or sys.stdout
    text = sep.join(str(o) for o in objects) + end
    _safe_stream_write(stream, text)
    if flush:
        stream.flush()


def get_tool_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def reset_powershell7_probe() -> None:
    """Clear cached PowerShell 7 detection (tests or after user installs pwsh)."""
    global _PWSH7_EXE, _PWSH7_VERSION, _PWSH7_PROBE_DONE
    _PWSH7_EXE = None
    _PWSH7_VERSION = None
    _PWSH7_PROBE_DONE = False


PWSH7_INSTALL_LOG_BASENAME = "BSODAnalyzer_pwsh7_install.log"
WINDDBG_INSTALL_LOG_BASENAME = "BSODAnalyzer_windbg_install.log"
# End-to-end Driver Search: PS 5.1 sequential median ~22 min vs pwsh parallel ~5 min (ROADMAP Phase 6).
PWSH7_DRIVER_SEARCH_SPEEDUP_LABEL = "about 5× faster"


def powershell7_install_log_path() -> str:
    return os.path.join(os.environ.get("TEMP", ""), PWSH7_INSTALL_LOG_BASENAME)


def windbg_install_log_path() -> str:
    return os.path.join(os.environ.get("TEMP", ""), WINDDBG_INSTALL_LOG_BASENAME)


def windbg_install_failure_message(detail: str) -> str:
    """User-facing WinDbg install failure text; mentions admin only when not elevated."""
    parts = [detail.rstrip()]
    if sys.platform == "win32":
        try:
            import ctypes

            if not ctypes.windll.shell32.IsUserAnAdmin():
                parts.append(
                    "BSOD Analyzer is not running as administrator. "
                    "Right-click the app and choose Run as administrator, then try again."
                )
        except (AttributeError, OSError):
            pass
    parts.append(f"If the installer showed an error, see:\n{windbg_install_log_path()}")
    parts.append(
        "Try Install again, continue with bundled CDB, or install WinDbg from the Microsoft Store."
    )
    return "\n\n".join(parts)


def powershell7_install_script_path() -> str:
    base = get_tool_dir()
    candidates = [
        os.path.join(base, "scripts", "install_powershell7.ps1"),
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(
            0,
            os.path.join(base, "_internal", "scripts", "install_powershell7.ps1"),
        )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return candidates[0]


def launch_powershell7_install_elevated() -> tuple[bool, str]:
    """Start the bundled PowerShell 7 installer (UAC only when not already admin)."""
    if sys.platform != "win32":
        return False, "PowerShell 7 install is only supported on Windows."
    script = powershell7_install_script_path()
    if not os.path.isfile(script):
        return False, f"Install script not found:\n{script}"
    args = f'-NoProfile -ExecutionPolicy Bypass -File "{script}"'
    try:
        import ctypes

        verb = "open"
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                verb = "runas"
        except (AttributeError, OSError):
            verb = "runas"
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            verb,
            "powershell.exe",
            args,
            None,
            1,
        )
        if rc <= 32:
            if verb == "runas":
                return False, (
                    "Could not start the PowerShell 7 installer. "
                    "Run BSOD Analyzer as administrator and try again."
                )
            return False, f"Could not start installer (ShellExecute code {rc})."
    except OSError as exc:
        return False, f"Could not start installer: {exc}"
    return True, "Started PowerShell 7 install."


def powershell7_install_failure_message(detail: str) -> str:
    """User-facing install failure text; mentions admin only when not elevated."""
    parts = [detail.rstrip()]
    if sys.platform == "win32":
        try:
            import ctypes

            if not ctypes.windll.shell32.IsUserAnAdmin():
                parts.append(
                    "BSOD Analyzer is not running as administrator. "
                    "Right-click the app and choose Run as administrator, then try again."
                )
        except (AttributeError, OSError):
            pass
    log_path = powershell7_install_log_path()
    parts.append(f"If the installer showed an error, see:\n{log_path}")
    parts.append("Try Install again, use Search anyway (slower), or install pwsh from Microsoft.")
    return "\n\n".join(parts)


def wait_for_powershell7_installed(
    *,
    timeout_sec: float = 180.0,
    poll_sec: float = 2.0,
) -> tuple[bool, str | None]:
    """Poll until pwsh 7+ appears or timeout (call reset_powershell7_probe each poll)."""
    import time

    deadline = time.monotonic() + max(5.0, timeout_sec)
    while time.monotonic() < deadline:
        reset_powershell7_probe()
        if powershell7_available():
            return True, powershell7_version()
        time.sleep(max(0.5, poll_sec))
    reset_powershell7_probe()
    return False, None


def _probe_powershell7() -> None:
    global _PWSH7_EXE, _PWSH7_VERSION, _PWSH7_PROBE_DONE
    if _PWSH7_PROBE_DONE:
        return
    _PWSH7_PROBE_DONE = True
    if sys.platform != "win32":
        return
    exe = shutil.which("pwsh")
    if not exe:
        for candidate in (
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "PowerShell", "7", "pwsh.exe"),
            os.path.join(
                os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                "PowerShell",
                "7",
                "pwsh.exe",
            ),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\pwsh.exe"),
        ):
            if candidate and os.path.isfile(candidate):
                exe = candidate
                break
    if not exe:
        return
    try:
        result = subprocess.run(
            [exe, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_WIN_CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return
        ver = (result.stdout or "").strip()
        if not ver:
            return
        major = int(ver.split(".", 1)[0])
        if major >= 7:
            _PWSH7_EXE = exe
            _PWSH7_VERSION = ver
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return


def powershell7_available() -> bool:
    _probe_powershell7()
    return _PWSH7_EXE is not None


def powershell7_version() -> str | None:
    _probe_powershell7()
    return _PWSH7_VERSION


def powershell7_exe() -> str | None:
    _probe_powershell7()
    return _PWSH7_EXE


def should_prompt_powershell7_upgrade(settings: dict | None) -> bool:
    if sys.platform != "win32":
        return False
    s = settings or {}
    if s.get("powershell7_upgrade_dismissed"):
        return False
    if s.get("powershell7_upgrade_prompt", True) is False:
        return False
    return not powershell7_available()


_7Z_EXE: str | None = None
_7Z_PROBE_DONE = False


def reset_seven_zip_probe() -> None:
    """Clear cached 7-Zip detection (tests or after user installs 7-Zip)."""
    global _7Z_EXE, _7Z_PROBE_DONE
    _7Z_EXE = None
    _7Z_PROBE_DONE = False


def _probe_seven_zip() -> None:
    global _7Z_EXE, _7Z_PROBE_DONE
    if _7Z_PROBE_DONE:
        return
    _7Z_PROBE_DONE = True
    if sys.platform != "win32":
        return
    candidates: list[str] = []
    which = shutil.which("7z")
    if which:
        candidates.append(which)
    for candidate in (
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "7-Zip", "7z.exe"),
        os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            "7-Zip",
            "7z.exe",
        ),
    ):
        if candidate and os.path.isfile(candidate) and candidate not in candidates:
            candidates.append(candidate)
    for exe in candidates:
        try:
            result = subprocess.run(
                [exe],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_WIN_CREATE_NO_WINDOW,
            )
            out = f"{result.stdout or ''}{result.stderr or ''}"
            if result.returncode in (0, 1) and "7-zip" in out.lower():
                _7Z_EXE = exe
                return
        except (OSError, subprocess.TimeoutExpired):
            continue


def seven_zip_available() -> bool:
    _probe_seven_zip()
    return _7Z_EXE is not None


def seven_zip_exe() -> str | None:
    _probe_seven_zip()
    return _7Z_EXE


def package_may_need_seven_zip(path_or_url: str) -> bool:
    low = (path_or_url or "").strip().lower().split("?")[0]
    return low.endswith(".7z")


def should_prompt_seven_zip_install(settings: dict | None) -> bool:
    if sys.platform != "win32":
        return False
    s = settings or {}
    if s.get("seven_zip_install_dismissed"):
        return False
    if s.get("seven_zip_install_prompt", True) is False:
        return False
    return not seven_zip_available()


def build_pnp_parent_lookup_script(payload_b64: str, *, parallel: bool) -> str:
    """Build PS to map instance ID -> DEVPKEY_Device_Parent."""
    header = f"""
$raw = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload_b64}'))
"""
    if parallel:
        return header + """
$parsed = $raw | ConvertFrom-Json
if ($parsed -is [System.Array]) { $ids = $parsed } else { $ids = @($parsed) }
$results = @($ids | ForEach-Object -Parallel {
  $id = [string]$_
  if (-not $id) { return $null }
  $p = (Get-PnpDeviceProperty -InstanceId $id -KeyName 'DEVPKEY_Device_Parent' -EA SilentlyContinue).Data
  if ($p) { [PSCustomObject]@{ Id = $id; Parent = [string]$p } }
} -ThrottleLimit 12)
$out = @{}
foreach ($r in $results) { if ($r) { $out[$r.Id] = $r.Parent } }
$out | ConvertTo-Json -Compress
"""
    return header + """
$parsed = $raw | ConvertFrom-Json
if ($parsed -is [System.Array]) { $ids = $parsed } else { $ids = @($parsed) }
$out = @{}
foreach ($id in $ids) {
  if (-not $id) { continue }
  $p = (Get-PnpDeviceProperty -InstanceId $id -KeyName 'DEVPKEY_Device_Parent' -EA SilentlyContinue).Data
  if ($p) { $out[[string]$id] = [string]$p }
}
$out | ConvertTo-Json -Compress
"""


def run_powershell(
    script: str,
    timeout: int = 30,
    *,
    prefer_pwsh: bool = False,
) -> tuple[bool, str]:
    _probe_powershell7()
    exe = "powershell"
    if prefer_pwsh and _PWSH7_EXE:
        exe = _PWSH7_EXE
    try:
        result = subprocess.run(
            [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_WIN_CREATE_NO_WINDOW,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Query timed out."
    except Exception as e:  # noqa: BLE001
        return False, str(e)


# Catalog/WMI PowerShell must not run concurrently — multiple subprocesses freeze/crash the GUI.
_CATALOG_PS_LOCK = threading.Lock()


def run_catalog_powershell(
    script: str,
    timeout: int = 30,
    *,
    prefer_pwsh: bool = False,
) -> tuple[bool, str]:
    """Run PowerShell under a process-wide catalog lock (WU, Get-WindowsDriver, MSCatalogLTS)."""
    with _CATALOG_PS_LOCK:
        return run_powershell(script, timeout, prefer_pwsh=prefer_pwsh)


def catalog_powershell_busy() -> bool:
    """True while a catalog PowerShell subprocess is running."""
    return _CATALOG_PS_LOCK.locked()


def get_logged_in_user_paths() -> tuple[str, str, list[str]]:
    username = os.environ.get("USERNAME", "Unknown")

    def _system_drive_root() -> str:
        drive = (os.environ.get("SystemDrive", "C:") or "C:").strip()
        if len(drive) == 2 and drive[1] == ":":
            return drive + "\\"
        if drive and not drive.endswith("\\"):
            return drive + "\\"
        return drive or "C:\\"

    drive_root = _system_drive_root()
    localappdata = (os.environ.get("LOCALAPPDATA", "") or "").strip()
    if localappdata:
        primary_crashdumps = os.path.join(localappdata, "CrashDumps")
    else:
        primary_crashdumps = os.path.join(
            drive_root, "Users", username, "AppData", "Local", "CrashDumps"
        )
    all_paths = [primary_crashdumps]

    ps = r"""
    $user = (Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction SilentlyContinue).UserName
    if ($user) { ($user -replace '.*\\', '').Trim() } else { $env:USERNAME }
    """
    ok, out = run_powershell(ps)
    if ok and out:
        username = out.strip()

    drive = drive_root.rstrip("\\")
    profile_path = os.path.join(drive_root, "Users", username)
    if os.path.isdir(profile_path):
        crashdumps = os.path.join(profile_path, "AppData", "Local", "CrashDumps")
        primary_crashdumps = crashdumps
        all_paths = [crashdumps] + [p for p in all_paths if p != crashdumps]

    try:
        users_dir = os.path.join(drive_root, "Users")
        if os.path.isdir(users_dir):
            for entry in os.listdir(users_dir):
                if entry.lower() in ("default", "default user", "all users", "public"):
                    continue
                path = os.path.join(users_dir, entry, "AppData", "Local", "CrashDumps")
                if os.path.isdir(path) and path not in all_paths:
                    all_paths.append(path)
    except (OSError, PermissionError):
        pass

    return username, primary_crashdumps, all_paths


def _windows_shell_desktop_path() -> str | None:
    """Resolve the Desktop folder Windows uses for icons (OneDrive-aware)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            raw, _ = winreg.QueryValueEx(key, "Desktop")
        path = os.path.expandvars(str(raw).strip())
        if path and os.path.isdir(path):
            return path
    except OSError:
        pass
    return None


def default_export_directory(settings: dict | None = None) -> str:
    """Best-effort export folder (OneDrive Desktop → local exports when synced)."""
    if settings is not None:
        import app_settings as app_set

        return app_set.preferred_export_directory(settings)
    shell_desktop = _windows_shell_desktop_path()
    try:
        import app_settings as app_set

        if shell_desktop and os.path.isdir(shell_desktop):
            if app_set.is_onedrive_synced_path(shell_desktop):
                local = app_set.local_export_directory()
                local.mkdir(parents=True, exist_ok=True)
                return str(local)
            return shell_desktop
        local = app_set.local_export_directory()
        if local.is_dir():
            return str(local)
    except OSError:
        pass
    if shell_desktop:
        return shell_desktop
    home = os.path.expanduser("~")
    candidates: list[str] = []
    userprofile = os.environ.get("USERPROFILE", "").strip()
    if userprofile:
        candidates.append(os.path.join(userprofile, "Desktop"))
    for rel in (
        "Desktop",
        os.path.join("OneDrive", "Desktop"),
        os.path.join("OneDrive - Personal", "Desktop"),
    ):
        path = os.path.join(home, rel)
        if path not in candidates:
            candidates.append(path)
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return userprofile or home


def notify_shell_path_updated(path: Path | str) -> None:
    """Ask Windows Explorer / OneDrive to refresh after we write export files."""
    if sys.platform != "win32":
        return
    try:
        target_path = Path(path)
        ctypes = __import__("ctypes")
        shell32 = ctypes.windll.shell32
        SHCNE_UPDATEITEM = 0x00002000
        SHCNE_UPDATEDIR = 0x00001000
        SHCNF_PATH = 0x0005
        if target_path.is_file():
            shell32.SHChangeNotifyW(
                SHCNE_UPDATEITEM, SHCNF_PATH, str(target_path.resolve()), None
            )
            shell32.SHChangeNotifyW(
                SHCNE_UPDATEDIR, SHCNF_PATH, str(target_path.parent.resolve()), None
            )
        else:
            shell32.SHChangeNotifyW(
                SHCNE_UPDATEDIR, SHCNF_PATH, str(target_path.resolve()), None
            )
        desktop = _windows_shell_desktop_path()
        if desktop:
            shell32.SHChangeNotifyW(SHCNE_UPDATEDIR, SHCNF_PATH, desktop, None)
    except (OSError, AttributeError):
        pass


def reveal_path_in_explorer(path: Path | str) -> None:
    """Open Explorer with the file or folder selected (helps OneDrive/Desktop folders)."""
    if sys.platform != "win32":
        return
    try:
        p = Path(path).resolve()
        if p.is_file():
            subprocess.run(
                ["explorer", "/select,", str(p)],
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        elif p.is_dir():
            subprocess.run(
                ["explorer", str(p)],
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except (OSError, AttributeError):
        pass


def write_text_file_sync(path: Path | str, content: str) -> None:
    """Write UTF-8 text and flush to disk so Explorer/OneDrive show the file immediately."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    notify_shell_path_updated(p)


def export_report_to_file(path: str, content: str) -> tuple[bool, str]:
    try:
        write_text_file_sync(path, content)
        return True, f"Report saved to {path}"
    except OSError as e:
        return False, str(e)


def pause_before_exit(title: str = "BSOD Analyzer", message: str | None = None) -> None:
    """Keep frozen CLI sessions visible; windowed exes often lose stdin on exit."""
    if os.environ.get("BSOD_NO_PAUSE") == "1":
        return
    msg = message or "Analysis complete.\n\nPress OK to close this window."
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, msg, title, 0x40)
            return
        except Exception:
            pass  # CLI MessageBox fallback; use stdin prompt below
    try:
        input("\nPress Enter to exit...")
    except (EOFError, OSError):
        pass


def system_on_battery_power() -> bool:
    """True when Windows reports the system is not on AC (best-effort)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        class _SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong),
            ]

        status = _SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            # 0 = offline, 1 = online, 255 = unknown
            return status.ACLineStatus == 0
    except (AttributeError, OSError, ValueError):
        pass
    return False


@contextmanager
def catalog_scan_performance_guard():
    """Reduce battery/idle throttling while catalog scans run (network + CPU)."""
    if sys.platform != "win32":
        yield
        return
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    prev = None
    try:
        import ctypes

        prev = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
    except (AttributeError, OSError):
        prev = None
    try:
        yield
    finally:
        if prev is not None:
            try:
                import ctypes

                ctypes.windll.kernel32.SetThreadExecutionState(prev)
            except (AttributeError, OSError):
                pass
