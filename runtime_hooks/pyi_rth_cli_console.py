"""PyInstaller runtime hook: attach a UTF-8 console for frozen --cli (windowed exe)."""

from __future__ import annotations

import sys


def _cli_requested() -> bool:
    return any(a.strip().lower() in ("--cli", "-c", "/cli") for a in sys.argv[1:])


def _bootstrap_cli_console() -> None:
    if not getattr(sys, "frozen", False) or sys.platform != "win32" or not _cli_requested():
        return
    try:
        import ctypes
        import io

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
    except Exception:
        pass


_bootstrap_cli_console()
