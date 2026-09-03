"""Tests for C4 themed app icon (gallery PNG artwork)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui  # noqa: E402

_QT_APP = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])

import gui_app_icon as app_icon  # noqa: E402
import gui_theme as theme  # noqa: E402


def test_c4_gallery_source_exists() -> None:
    assert (_ROOT / "docs" / "logo_concept_C4_lens_chip_bug_themes.png").is_file()


def test_app_icon_pngs_exist_for_all_themes() -> None:
    for tid in theme.THEME_PRESETS:
        path = app_icon.png_path_for_theme(tid)
        assert path is not None and path.is_file(), tid


def test_app_icon_renders_for_all_themes() -> None:
    for tid in theme.THEME_PRESETS:
        pm = app_icon.pixmap_for_theme(tid, 64)
        assert pm is not None and not pm.isNull(), tid
        icon = app_icon.app_icon_for_theme(tid)
        assert not icon.isNull(), tid


def test_gallery_night_icon_has_red_bug_not_blue_placeholder() -> None:
    """Regression: old SVG placeholder used all-blue art; gallery C4 has a red bug."""
    pm = app_icon.pixmap_for_theme("night", 256)
    assert pm is not None
    img = pm.toImage()
    max_red = 0
    for y in range(80, 176):
        for x in range(80, 176):
            c = img.pixelColor(x, y)
            max_red = max(max_red, c.red())
    assert max_red > 200


def test_apply_window_icon_sets_themed_icon() -> None:
    win = mock.MagicMock()
    theme.activate_theme("day")
    app_icon.apply_window_icon(win)
    win.setWindowIcon.assert_called_once()
    icon = win.setWindowIcon.call_args[0][0]
    assert not icon.isNull()
    theme.activate_theme("night")


def test_build_app_icon_produces_ico() -> None:
    ico = _ROOT / "assets" / "app_icon" / "BSODAnalyzer.ico"
    assert ico.is_file(), "Run scripts/build_app_icon.py before tests or build"
    assert ico.stat().st_size > 500


if __name__ == "__main__":
    test_c4_gallery_source_exists()
    test_app_icon_pngs_exist_for_all_themes()
    test_app_icon_renders_for_all_themes()
    test_gallery_night_icon_has_red_bug_not_blue_placeholder()
    test_apply_window_icon_sets_themed_icon()
    test_build_app_icon_produces_ico()
    print("gui app icon tests OK")
