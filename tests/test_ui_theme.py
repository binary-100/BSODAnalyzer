"""UI theme activation — Night, Day, and Manly mode palettes."""

from __future__ import annotations

import gui_theme as theme


def test_theme_presets_include_night_day_and_manly() -> None:
    assert "night" in theme.THEME_PRESETS
    assert "day" in theme.THEME_PRESETS
    assert "manly" in theme.THEME_PRESETS
    assert theme.THEME_PRESETS["manly"]["label"] == "Manly mode"


def test_activate_theme_swaps_stylesheet_and_tokens() -> None:
    theme.activate_theme("night")
    night_bg = theme.BG
    night_stylesheet = theme.STYLESHEET
    assert night_bg == "#1e1e23"
    assert "#1e1e23" in night_stylesheet

    theme.activate_theme("day")
    assert theme.BG == "#eef0f4"
    assert theme.TEXT == "#121218"
    assert theme.TABLE_SELECTION == "#bfdbfe"
    assert theme.DRV_TIER_OUTDATED_BG == "#fef3c7"
    assert theme.UPDATE_STATUS_COLORS["same"] == theme.SEVERITY_COLORS[0]
    assert theme.STYLESHEET != night_stylesheet
    assert "#eef0f4" in theme.STYLESHEET

    theme.activate_theme("night")


def test_manly_mode_uses_bold_pastel_row_tints() -> None:
    theme.activate_theme("manly")
    assert theme.BG == "#c8b0e8"
    assert theme.BG != theme.THEME_PRESETS["day"]["BG"]
    assert theme.TEXT == "#281832"
    assert theme.ACCENT == "#6838b8"
    assert theme.DRV_TIER_OUTDATED_BG == "#f5d9a8"
    assert theme.DRV_TIER_CULPRIT_BG == "#f5c0cc"
    assert theme.CATALOG_ROW_CURRENT_BG == "#b8e6cc"
    assert theme.THEME_PRESETS["manly"]["label"] == "Manly mode"
    theme.activate_theme("night")


def test_manly_mode_has_purple_cast_not_neutral_gray() -> None:
    """Manly window chrome must read lavender, not day-like cool gray."""
    day = theme.THEME_PRESETS["day"]
    manly = theme.THEME_PRESETS["manly"]

    def _rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    dr, dg, db = _rgb(day["BG"])
    mr, mg, mb = _rgb(manly["BG"])
    # Day is neutral (R≈G≈B); Manly blue channel should lead for a lilac cast.
    assert abs(dr - dg) < 8 and abs(dg - db) < 8
    assert mb > mg + 18
    assert mr > mg + 8
    theme.activate_theme("night")


def test_manly_mode_row_style_reads_live_theme_tokens() -> None:
    """Regression: row styling must use gui_theme at runtime, not import snapshots."""
    theme.activate_theme("manly")
    assert theme.CATALOG_ROW_CURRENT_BG == "#b8e6cc"
    assert theme.DRV_TIER_OUTDATED_BG == "#f5d9a8"
    theme.activate_theme("night")


def test_unknown_theme_falls_back_to_default() -> None:
    theme.activate_theme("invalid")
    assert theme.current_theme_id() == theme.UI_THEME_DEFAULT


def test_all_theme_presets_define_checkbox_two_tone_tokens() -> None:
    for tid, tokens in theme.THEME_PRESETS.items():
        for key in theme.CHECKBOX_THEME_TOKEN_KEYS:
            assert key in tokens, f"{tid} missing {key}"
            assert tokens[key]


def test_resolve_checkbox_tokens_falls_back_for_minimal_preset() -> None:
    minimal = {
        "ACCENT": "#112233",
        "TABLE_SELECTION": "#aabbcc",
        "LINK_HOVER": "#445566",
        "PRIMARY_HOVER": "#778899",
    }
    resolved = theme.resolve_checkbox_tokens(minimal)
    assert resolved["CHECKBOX_FILL"] == "#aabbcc"
    assert resolved["CHECKBOX_BORDER"] == "#112233"
    assert resolved["CHECKBOX_CHECKMARK"] == "#445566"


def test_all_themes_stylesheet_uses_checkbox_tick_image() -> None:
    for tid in theme.THEME_PRESETS:
        theme.activate_theme(tid)
        sheet = theme.STYLESHEET
        assert "data:image/svg+xml" in sheet
        for selector in (
            "QCheckBox::indicator:checked",
        ):
            start = sheet.index(selector)
            block = sheet[start : start + 280]
            assert "image: url(data:image/svg+xml" in block
            assert "background: transparent" in block


def test_checkbox_checked_uri_two_tone_per_theme() -> None:
    expected = {
        "night": ("1e4a7a", "2f81f7", "6aa8ff"),
        "day": ("bfdbfe", "2563eb", "1d4ed8"),
        "manly": ("c8b0e8", "6838b8", "5028a0"),
    }
    for tid, (fill, border, tick) in expected.items():
        theme.activate_theme(tid)
        uri = theme.checkbox_checked_indicator_uri().lower()
        assert fill in uri
        assert border in uri
        assert tick in uri
    theme.activate_theme("night")


def test_menu_checkmark_uri_uses_theme_tick_only() -> None:
    expected = {
        "night": "6aa8ff",
        "day": "1d4ed8",
        "manly": "5028a0",
    }
    for tid, tick in expected.items():
        theme.activate_theme(tid)
        uri = theme.menu_checkmark_indicator_uri().lower()
        assert tick in uri
        assert "rect" not in uri
        assert "QMenu::indicator:checked" in theme.STYLESHEET
    theme.activate_theme("night")


def test_stylesheet_has_no_itemview_indicator_rules() -> None:
    theme.activate_theme("night")
    assert "QAbstractItemView::indicator" not in theme.STYLESHEET


def test_center_window_on_screen() -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = QtWidgets.QWidget()
    win.resize(theme.DEFAULT_WINDOW_WIDTH, theme.DEFAULT_WINDOW_HEIGHT)
    theme.center_window_on_screen(win)
    screen = win.screen() or app.primaryScreen()
    assert screen is not None
    avail = screen.availableGeometry()
    frame = win.frameGeometry()
    assert abs(frame.center().x() - avail.center().x()) <= 2
    assert abs(frame.center().y() - avail.center().y()) <= 2


if __name__ == "__main__":
    test_theme_presets_include_night_day_and_manly()
    test_activate_theme_swaps_stylesheet_and_tokens()
    test_manly_mode_uses_bold_pastel_row_tints()
    test_manly_mode_row_style_reads_live_theme_tokens()
    test_unknown_theme_falls_back_to_default()
    test_all_theme_presets_define_checkbox_two_tone_tokens()
    test_resolve_checkbox_tokens_falls_back_for_minimal_preset()
    test_all_themes_stylesheet_uses_checkbox_tick_image()
    test_checkbox_checked_uri_two_tone_per_theme()
    test_menu_checkmark_uri_uses_theme_tick_only()
    test_stylesheet_has_no_itemview_indicator_rules()
    test_center_window_on_screen()
    print("OK")
