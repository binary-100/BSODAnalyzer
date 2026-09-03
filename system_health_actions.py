"""In-app launchers for Action Plan system health steps (memory test, SFC, DISM)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Literal

ActionKind = Literal["memory_test", "sfc", "dism", "chkdsk"]

_MEMORY_RE = re.compile(r"memory diagnostic|mdsched|test ram", re.I)
_SFC_RE = re.compile(r"sfc\s*/scannow|check system files|system file", re.I)
_DISM_RE = re.compile(r"dism\s*/online|restorehealth|cleanup-image|repair windows image", re.I)
_CHKDsk_RE = re.compile(r"chkdsk\s*/f|check disk|check the system drive", re.I)


def action_kinds_for_step(step_text: str) -> list[ActionKind]:
    """Return inline action button kinds for one Action Plan step (may be multiple)."""
    text = (step_text or "").strip()
    if not text:
        return []
    kinds: list[ActionKind] = []
    if _MEMORY_RE.search(text):
        kinds.append("memory_test")
    if _SFC_RE.search(text):
        kinds.append("sfc")
    if _DISM_RE.search(text):
        kinds.append("dism")
    if _CHKDsk_RE.search(text):
        kinds.append("chkdsk")
    return kinds


def action_kind_for_step(step_text: str) -> ActionKind | None:
    kinds = action_kinds_for_step(step_text)
    return kinds[0] if kinds else None


def action_button_label(kind: ActionKind) -> str:
    return {
        "memory_test": "Start memory test",
        "sfc": "Run SFC now",
        "dism": "Run DISM now",
        "chkdsk": "Schedule disk check",
    }[kind]


def action_confirm_message(kind: ActionKind) -> str:
    return {
        "memory_test": (
            "Windows Memory Diagnostic will open.\n\n"
            "Choose “Restart now and check for problems” when prompted. "
            "Your work will be lost if you have not saved it.\n\n"
            "The PC reboots once to test RAM — results appear after you log back in."
        ),
        "sfc": (
            "System File Checker (sfc /scannow) will run now.\n\n"
            "This usually takes 15–30 minutes. You can keep using the PC, "
            "but leave BSOD Analyzer open to see the result.\n\n"
            "Administrator rights are required."
        ),
        "dism": (
            "DISM will repair the Windows component store "
            "(RestoreHealth).\n\n"
            "This can take 20–60 minutes and needs an internet connection. "
            "Run this after driver/Windows Update fixes if crashes continue.\n\n"
            "Administrator rights are required."
        ),
        "chkdsk": (
            "Check Disk (chkdsk /f) will be scheduled on the system drive.\n\n"
            "Windows runs the scan on the next reboot before you log in. Save your work first.\n\n"
            "Administrator rights are required."
        ),
    }[kind]


def launch_memory_diagnostic() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Only supported on Windows."
    root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = os.path.join(root, "System32", "mdsched.exe")
    if not os.path.isfile(exe):
        return False, "mdsched.exe was not found on this PC."
    try:
        subprocess.Popen(
            [exe],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True, "Opened Windows Memory Diagnostic."
    except OSError as e:
        return False, str(e)


def run_sfc_scannow(*, timeout_sec: int = 7200) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Only supported on Windows."
    root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = os.path.join(root, "System32", "sfc.exe")
    if not os.path.isfile(exe):
        return False, "sfc.exe was not found."
    try:
        proc = subprocess.run(
            [exe, "/scannow"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        tail = out[-4000:] if len(out) > 4000 else out
        if proc.returncode == 0:
            return True, tail or "SFC finished with no output."
        return False, tail or f"SFC exited with code {proc.returncode}."
    except subprocess.TimeoutExpired:
        return False, f"SFC did not finish within {timeout_sec // 60} minutes."
    except OSError as e:
        return False, str(e)


def run_dism_restore_health(*, timeout_sec: int = 7200) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Only supported on Windows."
    root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = os.path.join(root, "System32", "Dism.exe")
    if not os.path.isfile(exe):
        return False, "Dism.exe was not found."
    try:
        proc = subprocess.run(
            [exe, "/Online", "/Cleanup-Image", "/RestoreHealth"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        tail = out[-4000:] if len(out) > 4000 else out
        if proc.returncode == 0:
            return True, tail or "DISM RestoreHealth finished."
        return False, tail or f"DISM exited with code {proc.returncode}."
    except subprocess.TimeoutExpired:
        return False, f"DISM did not finish within {timeout_sec // 60} minutes."
    except OSError as e:
        return False, str(e)


def schedule_chkdsk_system_drive() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Only supported on Windows."
    root = os.environ.get("SystemRoot", r"C:\Windows")
    system_drive = os.path.splitdrive(root)[0] or "C:"
    if not system_drive.endswith(":"):
        system_drive += ":"
    try:
        proc = subprocess.run(
            ["chkdsk", system_drive, "/f"],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            input="Y\n",
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        tail = out[-2000:] if len(out) > 2000 else out
        if proc.returncode in (0, 1):
            return True, tail or f"Check Disk scheduled on {system_drive} (runs at next reboot)."
        return False, tail or f"chkdsk exited with code {proc.returncode}."
    except subprocess.TimeoutExpired:
        return False, "chkdsk did not finish scheduling within 2 minutes."
    except OSError as e:
        return False, str(e)
