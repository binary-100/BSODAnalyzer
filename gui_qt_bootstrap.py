"""Qt plugin path and platform selection before QApplication (interactive GUI vs tests).

Writes a diagnostic log agents can read after GUI/test runs:
  %TEMP%\\BSODAnalyzer\\qt_platform.log  (see log_path())

**Tests:** never rely on ``QT_QPA_PLATFORM=offscreen`` alone — call
``register_qt_plugins_for_import()`` or run via ``tests/run_test_module.py`` /
``run_tests.bat`` so PySide6 platform DLLs resolve (avoids native error popups).
"""

from __future__ import annotations

import builtins
import importlib.util
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_LOG_ENV_KEYS = (
    "QT_QPA_PLATFORM",
    "QT_PLUGIN_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
    "QT_LOGGING_RULES",
    "PYTHONPATH",
)

_QT_ENV_KEYS = (
    "QT_QPA_PLATFORM",
    "QT_PLUGIN_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
)


def log_path() -> Path:
    """Agent-readable Qt platform diagnostic log."""
    base = Path(os.environ.get("TEMP", ".")) / "BSODAnalyzer"
    base.mkdir(parents=True, exist_ok=True)
    return base / "qt_platform.log"


def read_qt_platform_log(*, tail_lines: int = 80) -> str:
    """Return the last N lines of the platform log (for agent post-run checks)."""
    path = log_path()
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if tail_lines <= 0:
        return "\n".join(lines)
    return "\n".join(lines[-tail_lines:])


def normalize_qt_env() -> None:
    """Strip Qt env vars — cmd ``set VAR=val &&`` often leaves trailing spaces."""
    for key in _QT_ENV_KEYS:
        raw = os.environ.get(key)
        if raw is None:
            continue
        cleaned = raw.strip()
        if not cleaned:
            os.environ.pop(key, None)
        elif cleaned != raw:
            os.environ[key] = cleaned


def is_offscreen_test_mode() -> bool:
    normalize_qt_env()
    return os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"


def _append_log(event: str, lines: list[str]) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pid = os.getpid()
    cmd = " ".join(sys.argv[:6])
    if len(sys.argv) > 6:
        cmd += " ..."
    block = [f"[{stamp}] pid={pid} event={event}", f"  argv: {cmd}", *lines, ""]
    try:
        with log_path().open("a", encoding="utf-8") as fh:
            fh.write("\n".join(block))
    except OSError:
        pass


def _pyside_plugins_dir() -> Path | None:
    spec = importlib.util.find_spec("PySide6")
    if spec is None or not spec.origin:
        return None
    root = Path(spec.origin).resolve().parent / "plugins"
    return root if root.is_dir() else None


_plugins_registered = False
_import_guard_installed = False
_original_import: Callable[..., Any] | None = None


def register_qt_plugins_for_import() -> None:
    """Set Qt plugin env vars before the first PySide6 import (idempotent, no QApplication)."""
    global _plugins_registered
    normalize_qt_env()
    if _plugins_registered:
        return
    plugins = _pyside_plugins_dir()
    if plugins is None:
        return
    os.environ["QT_PLUGIN_PATH"] = str(plugins)
    platforms = plugins / "platforms"
    if platforms.is_dir():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms)
    _plugins_registered = True
    try:
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.addLibraryPath(str(plugins))
        if platforms.is_dir():
            QCoreApplication.addLibraryPath(str(platforms))
    except ImportError:
        pass


def install_pyside6_import_guard() -> None:
    """Ensure register_qt_plugins_for_import() runs before any PySide6 submodule import."""
    global _import_guard_installed, _original_import
    if _import_guard_installed:
        return
    _original_import = builtins.__import__

    def _guarded_import(
        name: str,
        globals: Any = None,
        locals: Any = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "PySide6" or name.startswith("PySide6."):
            register_qt_plugins_for_import()
        return _original_import(name, globals, locals, fromlist, level)

    builtins.__import__ = _guarded_import
    _import_guard_installed = True


def _register_plugin_paths() -> None:
    """Point Qt at PySide6 plugin dir (env vars + addLibraryPath)."""
    register_qt_plugins_for_import()


def _log_environment(*, mode: str) -> None:
    lines = [f"  mode: {mode}"]
    try:
        import PySide6

        lines.append(f"  PySide6: {PySide6.__file__}")
    except ImportError as exc:
        lines.append(f"  PySide6: IMPORT FAILED ({exc})")
    plugins = _pyside_plugins_dir()
    if plugins is not None:
        platforms = plugins / "platforms"
        plat_dlls = (
            sorted(p.name for p in platforms.glob("*.dll"))
            if platforms.is_dir()
            else []
        )
        lines.append(f"  plugins: {plugins}")
        lines.append(f"  platform_dlls: {', '.join(plat_dlls) or '(none)'}")
    else:
        lines.append("  plugins: (not found)")
    for key in _LOG_ENV_KEYS:
        val = os.environ.get(key)
        if val:
            lines.append(f"  {key}={val!r}")
    _append_log("environment", lines)


def _install_qt_message_logger() -> None:
    try:
        from PySide6.QtCore import qInstallMessageHandler
    except ImportError:
        return

    def _handler(mode, _context, message) -> None:  # type: ignore[no-untyped-def]
        _append_log("qt_message", [f"  [{int(mode)}] {message}"])

    qInstallMessageHandler(_handler)


def probe_qt_platform(*, mode: str) -> bool:
    """
    Try to construct QApplication; log result to qt_platform.log.

    Returns True when a platform plugin loads successfully.
    Reuses an existing QApplication instance when present.
    """
    normalize_qt_env()
    _register_plugin_paths()
    _log_environment(mode=mode)
    _install_qt_message_logger()
    try:
        from PySide6 import QtWidgets
    except ImportError as exc:
        _append_log(
            "probe_failed",
            [f"  PySide6 import failed: {exc}", f"  traceback: {traceback.format_exc()}"],
        )
        return False

    existing = QtWidgets.QApplication.instance()
    if existing is not None:
        _append_log(
            "probe_ok",
            [
                "  note: reused existing QApplication",
                f"  platform: {existing.platformName()}",
            ],
        )
        return True

    _append_log("probe_start", [f"  creating QApplication([]) mode={mode}"])
    try:
        app = QtWidgets.QApplication([])
    except Exception as exc:
        _append_log(
            "probe_failed",
            [
                f"  QApplication raised: {type(exc).__name__}: {exc}",
                f"  traceback: {traceback.format_exc()}",
            ],
        )
        return False

    name = app.platformName()
    if not name:
        _append_log("probe_failed", ["  QApplication returned empty platformName()"])
        return False

    _append_log("probe_ok", [f"  platform: {name}"])
    return True


def prepare_interactive_gui(*, probe: bool = True) -> None:
    """Native Windows GUI — clear test offscreen mode and ensure Qt finds bundled plugins."""
    normalize_qt_env()
    os.environ.pop("QT_QPA_PLATFORM", None)
    _register_plugin_paths()
    if probe:
        probe_qt_platform(mode="interactive")


def ensure_offscreen_for_tests(*, probe: bool = False) -> None:
    """Headless Qt for automated tests — must run before QApplication is constructed."""
    normalize_qt_env()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _register_plugin_paths()
    if probe:
        probe_qt_platform(mode="test_offscreen")


def prepare_before_qapplication(*, interactive: bool = False) -> None:
    normalize_qt_env()
    if interactive or (
        not os.environ.get("QT_QPA_PLATFORM")
        and sys.argv
        and any(a.strip().lower() in ("--gui", "-g", "/gui") for a in sys.argv[1:])
    ):
        prepare_interactive_gui()
    else:
        ensure_offscreen_for_tests()


normalize_qt_env()
if os.environ.get("QT_QPA_PLATFORM", "").strip():
    install_pyside6_import_guard()
    register_qt_plugins_for_import()
