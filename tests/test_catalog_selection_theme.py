"""Catalog table selection and Option 4 chrome track the active View theme."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import gui_theme as theme


def test_day_and_manly_table_selection_tokens_are_light() -> None:
    theme.activate_theme("day")
    assert theme.TABLE_SELECTION.lower() == "#bfdbfe"
    theme.activate_theme("manly")
    assert theme.TABLE_SELECTION.lower() == "#c8a8e8"
    theme.activate_theme("night")
    assert theme.TABLE_SELECTION.lower() == "#1e4a7a"


def test_option4_stylesheet_includes_catalog_unified_selection() -> None:
    for tid in ("night", "day", "manly"):
        theme.activate_theme(tid)
        sheet = theme.STYLESHEET
        assert "QTableWidget#CatalogUnifiedTable" in sheet
        assert "QTableWidget#CatalogCompareTable" in sheet
        assert "QScrollBar:vertical" in sheet
        assert "QLineEdit#CatalogFilterSearch" in sheet
        assert theme.TABLE_SELECTION in sheet
        assert "QFrame#CatalogFilterTray" in sheet
        assert "QSplitter#CatalogTabSplitter" in sheet
        assert "border-top: 3px solid" not in sheet.split("CatalogInspectorPane")[1].split("}")[0]
    theme.activate_theme("night")


def test_option4_per_widget_stylesheets_include_grid_and_scrollbars() -> None:
    for tid in ("night", "day", "manly"):
        theme.activate_theme(tid)
        search = theme.catalog_search_field_stylesheet()
        assert "border: 1px solid" in search
        assert theme.CARD in search
        compare = theme.catalog_table_stylesheet("CatalogCompareTable")
        assert theme._catalog_gridline_color() in compare
        assert "QScrollBar:vertical" in compare
        assert theme.ACCENT in theme.catalog_splitter_stylesheet()
        assert "border-top: 3px solid" not in theme.catalog_inspector_pane_stylesheet()
        assert "height: 3px" in theme.catalog_splitter_stylesheet()
    theme.activate_theme("night")


if __name__ == "__main__":
    test_day_and_manly_table_selection_tokens_are_light()
    test_option4_stylesheet_includes_catalog_unified_selection()
    test_option4_per_widget_stylesheets_include_grid_and_scrollbars()
    print("catalog selection theme tests OK")
