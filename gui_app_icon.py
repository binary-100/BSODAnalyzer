"""
C4 app icon — Lens + Chip + Bug — from the approved gallery artwork.

Runtime icons follow Night / Day / Manly via setWindowIcon(). PNGs are extracted
from docs/logo_concept_C4_lens_chip_bug_themes.png by scripts/build_app_icon.py.
The frozen exe uses assets/app_icon/BSODAnalyzer.ico (Night default).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import gui_theme as theme

_ICON_DIR_NAMES = (
    "assets/app_icon",
    "app_icon",
)
_THEME_PNG = "app_icon_{theme_id}.png"


def _repo_app_icon_dir() -> Path | None:
    here = Path(__file__).resolve().parent
    for name in _ICON_DIR_NAMES:
        d = here / name
        if d.is_dir():
            return d
    return None


def _bundled_app_icon_dir() -> Path | None:
    import sys

    meipass = getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    base = Path(str(meipass))
    for name in _ICON_DIR_NAMES:
        d = base / name
        if d.is_dir():
            return d
    return None


def app_icon_dir() -> Path | None:
    return _bundled_app_icon_dir() or _repo_app_icon_dir()


def png_path_for_theme(theme_id: str) -> Path | None:
    tid = theme_id if theme_id in theme.THEME_PRESETS else theme.UI_THEME_DEFAULT
    name = _THEME_PNG.format(theme_id=tid)
    base = app_icon_dir()
    if base is not None:
        path = base / name
        if path.is_file():
            return path
    fallback = Path(__file__).resolve().parent / "assets" / "app_icon" / name
    return fallback if fallback.is_file() else None


def pixmap_for_theme(theme_id: str, size: int) -> QtGui.QPixmap | None:
    path = png_path_for_theme(theme_id)
    if path is None:
        return None
    pm = QtGui.QPixmap(str(path))
    if pm.isNull():
        return None
    if pm.width() != size or pm.height() != size:
        return pm.scaled(
            size,
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
    return pm


@lru_cache(maxsize=8)
def app_icon_for_theme(theme_id: str) -> QtGui.QIcon:
    icon = QtGui.QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = pixmap_for_theme(theme_id, size)
        if pm is not None and not pm.isNull():
            icon.addPixmap(pm)
    return icon


def apply_window_icon(window: QtWidgets.QWidget) -> None:
    """Set themed icon on the main window and QApplication (taskbar / Alt+Tab)."""
    tid = theme.current_theme_id()
    icon = app_icon_for_theme(tid)
    if icon.isNull():
        return
    window.setWindowIcon(icon)
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.setWindowIcon(icon)


def clear_icon_cache() -> None:
    app_icon_for_theme.cache_clear()
