"""Qt GUI palette, stylesheet, and table column constants."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from PySide6 import QtCore, QtWidgets

# Default main window — 16:10 (1536×960); fits 1080p with taskbar (~993px usable height).
DEFAULT_WINDOW_WIDTH = 1536
DEFAULT_WINDOW_HEIGHT = 960
DEFAULT_WINDOW_MIN_WIDTH = 960
DEFAULT_WINDOW_MIN_HEIGHT = 640


def center_window_on_screen(window: QtWidgets.QWidget) -> None:
    """Move *window* to the center of its screen's available work area."""
    screen = window.screen()
    if screen is None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
    if screen is None:
        return
    frame = window.frameGeometry()
    frame.moveCenter(screen.availableGeometry().center())
    window.move(frame.topLeft())

MONO = "Consolas, 'Cascadia Mono', monospace"

UI_THEME_KEY = "ui_theme"
UI_THEME_DEFAULT = "night"

# Active palette tokens (updated by activate_theme).
BG = "#1e1e23"
CARD = "#26262d"
CARD_ALT = "#2c2c34"
BORDER = "#3a3a44"
TEXT = "#e7e7ec"
MUTED = "#9a9aa6"
ACCENT = "#2f81f7"
TABLE_SELECTION = "#1e4a7a"
BTN_HOVER = "#34343d"
BTN_DISABLED_BG = "#242429"
PRIMARY_HOVER = "#4593ff"
LINK_HOVER = "#6aa8ff"
ADMIN_BG = "#3a2f1a"
ADMIN_BORDER = "#6b5420"
ADMIN_TEXT = "#f0e0b0"
ADMIN_ICON = "#f0c040"
RADIO_BORDER = "#5a5a66"
RADIO_DISABLED_TEXT = "#4a4a52"
CHECKBOX_DISABLED_BG = "#242429"
CHECKBOX_FILL = "#1e4a7a"
CHECKBOX_BORDER = "#2f81f7"
CHECKBOX_CHECKMARK = "#6aa8ff"
WARNING_FG = "#e6a23c"

# Required for two-tone QCheckBox styling; new themes should set explicitly (see
# resolve_checkbox_tokens for fallbacks when omitted).
CHECKBOX_THEME_TOKEN_KEYS = ("CHECKBOX_FILL", "CHECKBOX_BORDER", "CHECKBOX_CHECKMARK")

SEVERITY_COLORS: dict[int, str] = {
    0: "#3fb950",
    1: "#d8a000",
    2: "#f5731f",
    3: "#e5484d",
}
DRV_TIER_CULPRIT_FG = "#e5484d"
DRV_TIER_OUTDATED_FG = "#d8a000"
DRV_TIER_CULPRIT_BG = "#3a2228"
DRV_TIER_OUTDATED_BG = "#3a3420"
CATALOG_ROW_CURRENT_BG = ""
UPDATE_STATUS_COLORS: dict[str, str] = {}
STYLESHEET = ""
_active_theme_id = UI_THEME_DEFAULT

# Informational status hint when many Include-checked devices are scanned at once.
_LARGE_DRIVER_SCAN_HINT_THRESHOLD = 20

SEVERITY_SEGMENTS = ["Low", "Moderate", "High", "Critical"]

UPDATE_STATUS_LABELS = {
    "pending": "Not checked yet",
    "checking": "Checking…",
    "newer": "Update available",
    "same": "Up to date",
    "uncertain": "Verify manually",
    "older": "Catalog older",
    "unknown": "Unknown compare",
    "none": "No catalog match",
    "n/a": "—",
    "error": "Check failed",
}

# Unified catalog row tiers (Drivers + Firmware — same rules on both tabs)
CATALOG_ROW_CURRENT_BG_ALPHA = 40  # green tint when verified up to date
CATALOG_NAME_COLUMNS = frozenset({2, 3})  # device/component + installed (same indices)


def catalog_row_zebra_color(row: int) -> str:
    """Stripe background for catalog rows (matches QTableWidget Base / AlternateBase)."""
    return CARD if (row & 1) else CARD_ALT
DRV_SECTION_HEADER_ROLE = "__section_header__"
DRV_COL_ICON = 0
DRV_COL_CHECK = 1
DRV_COL_DEVICE = 2
DRV_COL_INSTALLED = 3
DRV_COL_STATUS = 4

# Device-column crash-link info icon (ⓘ) tooltip — separate from row tooltips.
DRV_CRASH_INFO_TOOLTIP_ROLE = QtCore.Qt.ItemDataRole.UserRole + 41
_DRV_TABLE_SYNC_INLINE_MAX = 60
_DRV_TABLE_SYNC_BATCH = 10
_DRV_TABLE_SYNC_DELAY_MS = 25
_DRV_INDEX_HINTS_MAX = 80
_DRV_TABLE_DISPLAY_CAP = 120

# Drivers / Firmware tab workflow (step 1 = load inventory, step 2 = catalog search)
BTN_DRV_LOAD = "① Load devices"
BTN_DRV_SEARCH = "② Search for updates"
BTN_DRV_LOADING = "Loading devices…"
BTN_FW_LOAD = "① Load components"
BTN_FW_SEARCH = "② Search for updates"
BTN_FW_LOADING = "Loading components…"
FW_COL_ICON = 0
FW_COL_CHECK = 1
FW_COL_COMPONENT = 2
FW_COL_INSTALLED = 3
FW_COL_STATUS = 4

# Unified driver/firmware table geometry (header + rows stay aligned)
UNIFIED_TABLE_ICON_SIZE = 28
UNIFIED_TABLE_ROW_HEIGHT = 38
UNIFIED_TABLE_ROW_HEIGHT_DUAL_VERSION = 52
UNIFIED_TABLE_ROW_HEIGHT_COMPACT = 32
UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMPACT = 44
# Option 3 revised — catalog tab −1px font tier (12px body, 13px card title).
CATALOG_TAB_FONT_SIZE = 12
CATALOG_TAB_TITLE_FONT_SIZE = 13
UNIFIED_TABLE_HEADER_HEIGHT_COMPACT = 34
UNIFIED_TABLE_ROW_HEIGHT_COMPACT_12 = 28
UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMPACT_12 = 40
UNIFIED_TABLE_ROW_HEIGHT_SINGLE_COMFORT = 30
UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMFORT = 48
# Minimum table height to show 4 dual-version rows + header (balanced layout).
UNIFIED_TABLE_LIST_ROWS_TARGET = 4
UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_REVISED = (
    UNIFIED_TABLE_HEADER_HEIGHT_COMPACT
    + UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMPACT_12 * UNIFIED_TABLE_LIST_ROWS_TARGET
)  # 34 + 160 = 194
UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_3B_PLUS = (
    UNIFIED_TABLE_HEADER_HEIGHT_COMPACT
    + 46 * UNIFIED_TABLE_LIST_ROWS_TARGET
)  # 34 + 184 = 218 — 12px font, 46px dual rows, 282px list pane
UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_COMFORT = (
    UNIFIED_TABLE_HEADER_HEIGHT_COMPACT
    + UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMFORT * UNIFIED_TABLE_LIST_ROWS_TARGET
    + 16  # visible gap below row 4 inside table viewport
)  # 34 + 192 + 16 = 242
UNIFIED_TABLE_LIST_VIEWPORT_MIN_HEIGHT = (
    UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMFORT * UNIFIED_TABLE_LIST_ROWS_TARGET + 16
)  # 208 — four 48px dual rows fully visible + slack
UNIFIED_TAB_LIST_CHROME_HEIGHT_12 = 62
UNIFIED_TAB_LIST_PANEL_MIN_REVISED = (
    UNIFIED_TAB_LIST_CHROME_HEIGHT_12 + UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_REVISED
)  # 256
UNIFIED_TAB_LIST_PANEL_MIN_3B_PLUS = (
    UNIFIED_TAB_LIST_CHROME_HEIGHT_12 + UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_3B_PLUS
)  # 280 ≈ 282
UNIFIED_TAB_LIST_PANEL_MIN_COMFORT = (
    UNIFIED_TAB_LIST_CHROME_HEIGHT_12 + UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_COMFORT
)  # 304 — bump to 320 in preset for card title/progress overhead in real window
UNIFIED_TAB_LIST_PANEL_MIN_COMFORT_WINDOW = 320
UNIFIED_TABLE_HEADER_HEIGHT = 38
UNIFIED_TABLE_ICON_COL_WIDTH = 36
UNIFIED_TABLE_CHECK_COL_WIDTH = 34
UNIFIED_TABLE_INSTALLED_COL_WIDTH = 200
UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE = 200  # dual-line Installed (incl. peripheral verify hint)
UNIFIED_TABLE_STATUS_COL_WIDTH = 126
UNIFIED_TABLE_INSP_ICON_SIZE = 44
UNIFIED_TABLE_DEVICE_COL_MIN_WIDTH = 120
UNIFIED_TABLE_INSTALLED_COL_MIN_WIDTH = 72
UNIFIED_TABLE_STATUS_COL_MIN_WIDTH = 72
UNIFIED_TABLE_PACKAGE_COL_MIN_WIDTH = 72
UNIFIED_TABLE_PACKAGE_SOURCE_COL_MIN_WIDTH = 150
# Shared Drivers/Firmware tab chrome — keep filter row and tables aligned when switching tabs.
CATALOG_VIEW_FILTER_MIN_WIDTH = 168
CATALOG_LOAD_BTN_MIN_WIDTH = 168
CATALOG_SEARCH_BTN_MIN_WIDTH = 168
CATALOG_SPLITTER_SETTINGS_KEY = "catalog_tab_splitter_sizes"
CATALOG_UNIFIED_COL_WIDTHS_KEY = "catalog_unified_col_widths_v3"
CATALOG_PACKAGE_COL_WIDTHS_KEY = "catalog_package_col_widths"
# Default vertical split in Drivers/Firmware tabs — equal thirds (list | summary | packages)
UNIFIED_TAB_SPLITTER_SIZES = (233, 233, 233)
UNIFIED_TAB_SECTION_MIN_HEIGHT = 72
UNIFIED_TAB_LIST_PANEL_MIN_HEIGHT = UNIFIED_TAB_SECTION_MIN_HEIGHT
UNIFIED_TAB_INSPECTOR_MIN_HEIGHT = UNIFIED_TAB_SECTION_MIN_HEIGHT
# Summary-only inspector (device header, no compare table) — keeps list tall until search.
UNIFIED_TAB_INSPECTOR_COMPACT_HEIGHT = 118
UNIFIED_TAB_PACKAGES_PANEL_MIN_HEIGHT = UNIFIED_TAB_SECTION_MIN_HEIGHT
UNIFIED_SPLITTER_HANDLE_WIDTH = 3
TASK_PROGRESS_BAR_HEIGHT = 14
TASK_PROGRESS_LABEL_LINE_HEIGHT = 18
# Catalog tabs: bar only. Banner tabs (Summary/Action/…): caption + bar.
TASK_PROGRESS_FRAME_HEIGHT = TASK_PROGRESS_BAR_HEIGHT + 4
TASK_PROGRESS_BANNER_FRAME_HEIGHT = (
    TASK_PROGRESS_LABEL_LINE_HEIGHT + 4 + TASK_PROGRESS_BAR_HEIGHT
)
CATALOG_TAB_PROGRESS_FRAME_HEIGHT = 36
TASK_PROGRESS_LABEL_MAX_WIDTH = 300
# Shared horizontal inset for catalog progress bar + filter row (card padding handles edges).
CATALOG_CHROME_H_INSET = 0
# Filter dropdown / search field height — match catalog action buttons.
CATALOG_FILTER_CONTROL_HEIGHT = 36
# Catalog filter combo — inset label text inside the box (box stays aligned with table).
CATALOG_FILTER_COMBO_PAD_LEFT = 22
# Catalog tab outline chrome — option 4 (filter tray + accent highlights).
CATALOG_CHROME_OUTLINE = 4
# Standard margins for Summary / Action / Details / System / Advanced tab bodies.
TAB_BODY_MARGIN_TOP = 12
TAB_BODY_MARGINS = (0, TAB_BODY_MARGIN_TOP, 0, 0)
# Drivers/Firmware: banner hidden — match tab→first-box gap (MainTabHost header top inset).
CATALOG_TAB_BODY_MARGIN_TOP = 2
CATALOG_TAB_BODY_MARGINS = (0, CATALOG_TAB_BODY_MARGIN_TOP, 0, 0)
UNIFIED_TABLE_MIN_LIST_HEIGHT = 72
UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT = (
    UNIFIED_TABLE_HEADER_HEIGHT
    + UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMPACT * UNIFIED_TABLE_LIST_ROWS_TARGET
)  # 38 + 176 = 214
UNIFIED_TAB_LIST_CHROME_HEIGHT = 68  # status 22 + gaps 12 + filter row ~34
UNIFIED_TAB_LIST_PANEL_MIN_BALANCED = (
    UNIFIED_TAB_LIST_CHROME_HEIGHT + UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT
)  # 282
UNIFIED_TABLE_MIN_COMPARE_HEIGHT = 72
UNIFIED_TABLE_PACKAGE_ROW_HEIGHT = 52
UNIFIED_TABLE_HINT_MAX_HEIGHT = 36
UNIFIED_TABLE_SUBTITLE_MAX_HEIGHT = 72

# Catalog tab layout presets — run scripts/catalog_layout_preview.py to compare live.
CATALOG_LAYOUT_PRESET_KEY = "catalog_layout_preset"
CATALOG_LAYOUT_DEFAULT = "balanced_comfortable"
# Legacy equal-thirds splitter — migrate to 3C on upgrade when still saved.
CATALOG_LAYOUT_LEGACY_SPLITTER = (233, 233, 233)
CATALOG_LAYOUT_PRESETS: dict[str, dict[str, object]] = {
    "current": {
        "label": "A — Current (baseline)",
        "description": "Equal vertical split; 38px rows (52px when two version lines). ~2–3 visible.",
        "splitter": (233, 233, 233),
        "row_height": UNIFIED_TABLE_ROW_HEIGHT,
        "row_height_dual": UNIFIED_TABLE_ROW_HEIGHT_DUAL_VERSION,
        "list_panel_min": UNIFIED_TAB_LIST_PANEL_MIN_HEIGHT,
        "table_min_height": UNIFIED_TABLE_MIN_LIST_HEIGHT,
    },
    "roomier_list": {
        "label": "B — Taller device list",
        "description": "Give the scroll list ~45% of tab height; keep full-size rows.",
        "splitter": (340, 220, 180),
        "row_height": UNIFIED_TABLE_ROW_HEIGHT,
        "row_height_dual": UNIFIED_TABLE_ROW_HEIGHT_DUAL_VERSION,
        "list_panel_min": 280,
        "table_min_height": 200,
    },
    "compact_rows": {
        "label": "C — Compact rows",
        "description": "Same split as today but shorter rows and tighter installed text.",
        "splitter": (233, 233, 233),
        "row_height": UNIFIED_TABLE_ROW_HEIGHT_COMPACT,
        "row_height_dual": UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMPACT,
        "list_panel_min": UNIFIED_TAB_LIST_PANEL_MIN_HEIGHT,
        "table_min_height": UNIFIED_TABLE_MIN_LIST_HEIGHT,
    },
    "balanced": {
        "label": "3A — Balanced (13px)",
        "description": (
            "4 dual-version rows at 44px; Installed 168px; split 340/200/170; "
            "13px catalog font (app default)."
        ),
        "splitter": (340, 200, 170),
        "row_height": UNIFIED_TABLE_ROW_HEIGHT_COMPACT,
        "row_height_dual": UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMPACT,
        "header_height": UNIFIED_TABLE_HEADER_HEIGHT,
        "list_panel_min": UNIFIED_TAB_LIST_PANEL_MIN_BALANCED,
        "table_min_height": UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT,
        "installed_col_width": UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE,
        "catalog_font_size": 13,
        "catalog_title_font_size": 14,
    },
    "balanced_revised": {
        "label": "3B — Revised (12px, tight pane)",
        "description": "12px catalog font; 40px dual rows; 256px list pane — too cramped.",
        "splitter": (340, 200, 170),
        "row_height": UNIFIED_TABLE_ROW_HEIGHT_COMPACT_12,
        "row_height_dual": UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMPACT_12,
        "header_height": UNIFIED_TABLE_HEADER_HEIGHT_COMPACT,
        "list_panel_min": UNIFIED_TAB_LIST_PANEL_MIN_REVISED,
        "table_min_height": UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_REVISED,
        "installed_col_width": UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE,
        "catalog_font_size": CATALOG_TAB_FONT_SIZE,
        "catalog_title_font_size": CATALOG_TAB_TITLE_FONT_SIZE,
    },
    "balanced_revised_plus": {
        "label": "3B+ — 12px @ 282px list pane",
        "description": (
            "12px font, 282px list pane, 46px dual rows — 4 rows fit but bottom edge tight."
        ),
        "splitter": (340, 200, 170),
        "row_height": 30,
        "row_height_dual": 46,
        "header_height": UNIFIED_TABLE_HEADER_HEIGHT_COMPACT,
        "list_panel_min": UNIFIED_TAB_LIST_PANEL_MIN_3B_PLUS,
        "table_min_height": UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_3B_PLUS,
        "installed_col_width": UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE,
        "catalog_font_size": CATALOG_TAB_FONT_SIZE,
        "catalog_title_font_size": CATALOG_TAB_TITLE_FONT_SIZE,
    },
    "balanced_comfortable": {
        "label": "3C — Comfortable (recommended)",
        "description": (
            "12px font, 320px list pane, 48px dual rows — four dual-line Installed "
            "devices fully visible (192px viewport + 16px slack)."
        ),
        "splitter": (420, 170, 110),
        "row_height": UNIFIED_TABLE_ROW_HEIGHT_SINGLE_COMFORT,
        "row_height_dual": UNIFIED_TABLE_ROW_HEIGHT_DUAL_COMFORT,
        "header_height": UNIFIED_TABLE_HEADER_HEIGHT_COMPACT,
        "list_panel_min": UNIFIED_TAB_LIST_PANEL_MIN_COMFORT_WINDOW,
        "table_min_height": UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_COMFORT,
        "installed_col_width": UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE,
        "catalog_font_size": CATALOG_TAB_FONT_SIZE,
        "catalog_title_font_size": CATALOG_TAB_TITLE_FONT_SIZE,
    },
}

def _theme_token_sets() -> dict[str, dict[str, Any]]:
    """Per-theme palette tokens.

    New themes must define every key shown here. Checkbox two-tone styling uses
    CHECKBOX_FILL (soft tint), CHECKBOX_BORDER (accent frame), and
    CHECKBOX_CHECKMARK (strong accent tick). If omitted, resolve_checkbox_tokens()
    falls back to TABLE_SELECTION, ACCENT, and LINK_HOVER / PRIMARY_HOVER.
    """
    return {
        "night": {
            "label": "Night (dark)",
            "BG": "#1e1e23",
            "CARD": "#26262d",
            "CARD_ALT": "#2c2c34",
            "BORDER": "#3a3a44",
            "TEXT": "#e7e7ec",
            "MUTED": "#9a9aa6",
            "ACCENT": "#2f81f7",
            "TABLE_SELECTION": "#1e4a7a",
            "BTN_HOVER": "#34343d",
            "BTN_DISABLED_BG": "#242429",
            "PRIMARY_HOVER": "#4593ff",
            "LINK_HOVER": "#6aa8ff",
            "ADMIN_BG": "#3a2f1a",
            "ADMIN_BORDER": "#6b5420",
            "ADMIN_TEXT": "#f0e0b0",
            "ADMIN_ICON": "#f0c040",
            "RADIO_BORDER": "#5a5a66",
            "RADIO_DISABLED_TEXT": "#4a4a52",
            "CHECKBOX_DISABLED_BG": "#242429",
            "CHECKBOX_FILL": "#1e4a7a",
            "CHECKBOX_BORDER": "#2f81f7",
            "CHECKBOX_CHECKMARK": "#6aa8ff",
            "WARNING_FG": "#e6a23c",
            "SEVERITY_COLORS": {
                0: "#3fb950",
                1: "#d8a000",
                2: "#f5731f",
                3: "#e5484d",
            },
            "DRV_TIER_CULPRIT_BG": "#3a2228",
            "DRV_TIER_OUTDATED_BG": "#3a3420",
            "CATALOG_ROW_CURRENT_BG": "#243d30",
        },
        "day": {
            "label": "Day (light)",
            "BG": "#eef0f4",
            "CARD": "#ffffff",
            "CARD_ALT": "#f4f5f8",
            "BORDER": "#cdd0d8",
            "TEXT": "#121218",
            "MUTED": "#484852",
            "ACCENT": "#2563eb",
            "TABLE_SELECTION": "#bfdbfe",
            "BTN_HOVER": "#e8eaef",
            "BTN_DISABLED_BG": "#f0f1f4",
            "PRIMARY_HOVER": "#1d4ed8",
            "LINK_HOVER": "#1d4ed8",
            "ADMIN_BG": "#fffbeb",
            "ADMIN_BORDER": "#d97706",
            "ADMIN_TEXT": "#92400e",
            "ADMIN_ICON": "#d97706",
            "RADIO_BORDER": "#9ca3af",
            "RADIO_DISABLED_TEXT": "#9ca3af",
            "CHECKBOX_DISABLED_BG": "#f0f1f4",
            "CHECKBOX_FILL": "#bfdbfe",
            "CHECKBOX_BORDER": "#2563eb",
            "CHECKBOX_CHECKMARK": "#1d4ed8",
            "WARNING_FG": "#b45309",
            "SEVERITY_COLORS": {
                0: "#15803d",
                1: "#b45309",
                2: "#c2410c",
                3: "#b91c1c",
            },
            "DRV_TIER_CULPRIT_BG": "#fee2e2",
            "DRV_TIER_OUTDATED_BG": "#fef3c7",
            "CATALOG_ROW_CURRENT_BG": "#dcfce7",
        },
        "manly": {
            "label": "Manly mode",
            "BG": "#c8b0e8",
            "CARD": "#f0e6fa",
            "CARD_ALT": "#e6d6f4",
            "BORDER": "#a080c8",
            "TEXT": "#281832",
            "MUTED": "#544068",
            "ACCENT": "#6838b8",
            "TABLE_SELECTION": "#c8a8e8",
            "BTN_HOVER": "#dcc8f0",
            "BTN_DISABLED_BG": "#e8dcf4",
            "PRIMARY_HOVER": "#5028a0",
            "LINK_HOVER": "#5028a0",
            "ADMIN_BG": "#f0dfa0",
            "ADMIN_BORDER": "#b8860b",
            "ADMIN_TEXT": "#5c4810",
            "ADMIN_ICON": "#a07008",
            "RADIO_BORDER": "#9070b0",
            "RADIO_DISABLED_TEXT": "#9070b0",
            "CHECKBOX_DISABLED_BG": "#e8dcf4",
            "CHECKBOX_FILL": "#c8b0e8",
            "CHECKBOX_BORDER": "#6838b8",
            "CHECKBOX_CHECKMARK": "#5028a0",
            "WARNING_FG": "#9a5a10",
            "SEVERITY_COLORS": {
                0: "#2a7a50",
                1: "#9a5a10",
                2: "#c86848",
                3: "#a83850",
            },
            "DRV_TIER_CULPRIT_BG": "#f5c0cc",
            "DRV_TIER_OUTDATED_BG": "#f5d9a8",
            "CATALOG_ROW_CURRENT_BG": "#b8e6cc",
        },
    }


THEME_PRESETS: dict[str, dict[str, Any]] = _theme_token_sets()


def _rebuild_update_status_colors() -> None:
    global UPDATE_STATUS_COLORS
    UPDATE_STATUS_COLORS = {
        "newer": SEVERITY_COLORS[1],
        "same": SEVERITY_COLORS[0],
        "unknown": SEVERITY_COLORS[1],
        "none": MUTED,
        "error": SEVERITY_COLORS[3],
        "pending": MUTED,
        "checking": ACCENT,
    }


def resolve_checkbox_tokens(tokens: dict[str, Any]) -> dict[str, str]:
    """Defaults for two-tone checkbox SVG when a new theme omits explicit tokens."""
    return {
        "CHECKBOX_FILL": str(
            tokens.get("CHECKBOX_FILL") or tokens.get("TABLE_SELECTION") or tokens["ACCENT"]
        ),
        "CHECKBOX_BORDER": str(tokens.get("CHECKBOX_BORDER") or tokens["ACCENT"]),
        "CHECKBOX_CHECKMARK": str(
            tokens.get("CHECKBOX_CHECKMARK")
            or tokens.get("LINK_HOVER")
            or tokens.get("PRIMARY_HOVER")
            or tokens["ACCENT"]
        ),
    }


def _assign_theme_tokens(tokens: dict[str, Any]) -> None:
    global BG, CARD, CARD_ALT, BORDER, TEXT, MUTED, ACCENT
    global TABLE_SELECTION, BTN_HOVER, BTN_DISABLED_BG, PRIMARY_HOVER, LINK_HOVER
    global ADMIN_BG, ADMIN_BORDER, ADMIN_TEXT, ADMIN_ICON
    global RADIO_BORDER, RADIO_DISABLED_TEXT, CHECKBOX_DISABLED_BG
    global CHECKBOX_FILL, CHECKBOX_BORDER, CHECKBOX_CHECKMARK, WARNING_FG
    global SEVERITY_COLORS, DRV_TIER_CULPRIT_FG, DRV_TIER_OUTDATED_FG
    global DRV_TIER_CULPRIT_BG, DRV_TIER_OUTDATED_BG, CATALOG_ROW_CURRENT_BG
    BG = tokens["BG"]
    CARD = tokens["CARD"]
    CARD_ALT = tokens["CARD_ALT"]
    BORDER = tokens["BORDER"]
    TEXT = tokens["TEXT"]
    MUTED = tokens["MUTED"]
    ACCENT = tokens["ACCENT"]
    TABLE_SELECTION = tokens["TABLE_SELECTION"]
    BTN_HOVER = tokens["BTN_HOVER"]
    BTN_DISABLED_BG = tokens["BTN_DISABLED_BG"]
    PRIMARY_HOVER = tokens["PRIMARY_HOVER"]
    LINK_HOVER = tokens["LINK_HOVER"]
    ADMIN_BG = tokens["ADMIN_BG"]
    ADMIN_BORDER = tokens["ADMIN_BORDER"]
    ADMIN_TEXT = tokens["ADMIN_TEXT"]
    ADMIN_ICON = tokens["ADMIN_ICON"]
    RADIO_BORDER = tokens["RADIO_BORDER"]
    RADIO_DISABLED_TEXT = tokens["RADIO_DISABLED_TEXT"]
    CHECKBOX_DISABLED_BG = tokens["CHECKBOX_DISABLED_BG"]
    cb = resolve_checkbox_tokens(tokens)
    CHECKBOX_FILL = cb["CHECKBOX_FILL"]
    CHECKBOX_BORDER = cb["CHECKBOX_BORDER"]
    CHECKBOX_CHECKMARK = cb["CHECKBOX_CHECKMARK"]
    WARNING_FG = tokens["WARNING_FG"]
    SEVERITY_COLORS = dict(tokens["SEVERITY_COLORS"])
    DRV_TIER_CULPRIT_BG = tokens["DRV_TIER_CULPRIT_BG"]
    DRV_TIER_OUTDATED_BG = tokens["DRV_TIER_OUTDATED_BG"]
    CATALOG_ROW_CURRENT_BG = str(tokens.get("CATALOG_ROW_CURRENT_BG") or "")
    DRV_TIER_CULPRIT_FG = SEVERITY_COLORS[3]
    DRV_TIER_OUTDATED_FG = SEVERITY_COLORS[1]
    _rebuild_update_status_colors()


def checkbox_checked_indicator_uri(
    *,
    box_fill: str | None = None,
    box_border: str | None = None,
    checkmark: str | None = None,
    disabled: bool = False,
) -> str:
    """SVG data-URI for QCheckBox::indicator:checked — two-tone theme checkbox."""
    if disabled:
        fill = CHECKBOX_DISABLED_BG
        border = BORDER
        tick = RADIO_DISABLED_TEXT
    else:
        fill = box_fill or CHECKBOX_FILL
        border = box_border or CHECKBOX_BORDER
        tick = checkmark or CHECKBOX_CHECKMARK
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
        f'<rect x="1" y="1" width="14" height="14" rx="3" fill="{fill}" stroke="{border}" '
        f'stroke-width="1.5"/>'
        f'<path d="M4.2 8.1 L6.8 10.7 L11.8 5.2" fill="none" stroke="{tick}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )
    return "url(data:image/svg+xml;charset=utf-8," + quote(svg) + ")"


def checkbox_partial_indicator_uri(
    *,
    box_fill: str | None = None,
    box_border: str | None = None,
    dash: str | None = None,
) -> str:
    """SVG for tri-state / partial Include header checkbox."""
    fill = box_fill or CHECKBOX_FILL
    border = box_border or CHECKBOX_BORDER
    mark = dash or CHECKBOX_CHECKMARK
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
        f'<rect x="1" y="1" width="14" height="14" rx="3" fill="{fill}" stroke="{border}" '
        f'stroke-width="1.5"/>'
        f'<path d="M5 8 H11" fill="none" stroke="{mark}" stroke-width="1.8" '
        f'stroke-linecap="round"/>'
        "</svg>"
    )
    return "url(data:image/svg+xml;charset=utf-8," + quote(svg) + ")"


def menu_checkmark_indicator_uri(*, checkmark: str | None = None) -> str:
    """SVG data-URI for QMenu::indicator:checked — tick only, no box."""
    tick = checkmark or CHECKBOX_CHECKMARK
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
        f'<path d="M4.2 8.1 L6.8 10.7 L11.8 5.2" fill="none" stroke="{tick}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )
    return "url(data:image/svg+xml;charset=utf-8," + quote(svg) + ")"


def _hex_with_alpha(hex_color: str, alpha: int) -> str:
    """#RRGGBB → #AARRGGBB for QSS (alpha 0–255)."""
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return hex_color
    return f"#{max(0, min(255, alpha)):02x}{h}"


def _catalog_gridline_color() -> str:
    """Grid lines visible on Day/Manly — slightly stronger than flat BORDER on CARD."""
    return _hex_with_alpha(TEXT, 56)


def _modern_scrollbar_styles() -> str:
    """Flat scrollbars — replaces native dithered Mac/Win95 chrome."""
    track = CARD_ALT
    handle = _hex_with_alpha(BORDER, 220)
    handle_hover = _hex_with_alpha(ACCENT, 200)
    return f"""
QScrollBar:vertical {{
    background: {track};
    width: 10px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {handle};
    min-height: 28px;
    border-radius: 5px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {handle_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: {track};
    height: 10px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {handle};
    min-width: 28px;
    border-radius: 5px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {handle_hover};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
"""


def _catalog_outline_styles() -> str:
    """Option 4 catalog chrome — filter tray, accent table header, bordered inspector."""
    if CATALOG_CHROME_OUTLINE < 4:
        return ""
    handle = _hex_with_alpha(ACCENT, 200)
    grid = _catalog_gridline_color()
    return f"""
QFrame#CatalogFilterTray {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
}}
QLineEdit#CatalogFilterSearch {{
    background-color: {CARD};
    border: 1px solid {BORDER};
}}
QLineEdit#CatalogFilterSearch:focus {{
    border: 1px solid {ACCENT};
}}
QTableWidget#CatalogUnifiedTable {{
    background-color: {CARD_ALT};
    alternate-background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {grid};
    selection-background-color: {TABLE_SELECTION};
    selection-color: {TEXT};
}}
QTableWidget#CatalogUnifiedTable::item:selected {{
    background-color: {TABLE_SELECTION};
    color: {TEXT};
}}
QTableWidget#CatalogCompareTable {{
    background-color: {CARD_ALT};
    alternate-background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {grid};
    selection-background-color: {TABLE_SELECTION};
    selection-color: {TEXT};
}}
QTableWidget#CatalogCompareTable::item {{
    border-right: 1px solid {grid};
    border-bottom: 1px solid {grid};
}}
QTableWidget#CatalogCompareTable QHeaderView::section {{
    border-bottom: 2px solid {ACCENT};
}}
QFrame#CatalogInspectorPane {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QSplitter#CatalogTabSplitter::handle:vertical {{
    background: {handle};
    height: 3px;
    margin: 0;
    border-radius: 0;
}}
"""


def _catalog_scrollbar_substyles(parent_selector: str) -> str:
    """Flat scrollbars scoped under *parent_selector* (per-table widget QSS)."""
    track = CARD_ALT
    handle = _hex_with_alpha(BORDER, 220)
    handle_hover = _hex_with_alpha(ACCENT, 200)
    prefix = f"{parent_selector.strip()} " if parent_selector.strip() else ""
    return f"""
{prefix}QScrollBar:vertical {{
    background: {track};
    width: 10px;
    margin: 0;
    border: none;
}}
{prefix}QScrollBar::handle:vertical {{
    background: {handle};
    min-height: 28px;
    border-radius: 5px;
    margin: 2px;
}}
{prefix}QScrollBar::handle:vertical:hover {{
    background: {handle_hover};
}}
{prefix}QScrollBar::add-line:vertical, {prefix}QScrollBar::sub-line:vertical {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
{prefix}QScrollBar::add-page:vertical, {prefix}QScrollBar::sub-page:vertical {{
    background: transparent;
}}
{prefix}QScrollBar:horizontal {{
    background: {track};
    height: 10px;
    margin: 0;
    border: none;
}}
{prefix}QScrollBar::handle:horizontal {{
    background: {handle};
    min-width: 28px;
    border-radius: 5px;
    margin: 2px;
}}
{prefix}QScrollBar::handle:horizontal:hover {{
    background: {handle_hover};
}}
{prefix}QScrollBar::add-line:horizontal, {prefix}QScrollBar::sub-line:horizontal {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
{prefix}QScrollBar::add-page:horizontal, {prefix}QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
"""


def catalog_search_field_stylesheet() -> str:
    """Per-widget search box — global MainWindow QSS misses native LineEdit chrome."""
    return f"""QLineEdit {{
    background-color: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 12px;
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}"""


def catalog_filter_combo_stylesheet() -> str:
    """Per-widget filter dropdown — accent border per Option 4 mockup."""
    return f"""QComboBox {{
    background-color: {CARD_ALT};
    color: {TEXT};
    border: 1px solid {ACCENT};
    border-radius: 6px;
    padding: 4px 28px 4px {CATALOG_FILTER_COMBO_PAD_LEFT}px;
    min-height: 18px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {ACCENT};
    margin-right: 4px;
}}
QComboBox QAbstractItemView {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT};
    outline: none;
}}"""


def catalog_filter_tray_stylesheet() -> str:
    return f"""QFrame {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}"""


def catalog_inspector_pane_stylesheet() -> str:
    return f"""QFrame {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}"""


def catalog_splitter_stylesheet() -> str:
    return f"""QSplitter::handle:vertical {{
    background-color: {ACCENT};
    height: 3px;
    margin: 0;
    border-radius: 0;
}}"""


def catalog_table_stylesheet(object_name: str) -> str:
    """Per-table QSS — grid lines + flat scrollbars (native style ignores global rules)."""
    grid = _catalog_gridline_color()
    parent = f"QTableWidget#{object_name}"
    return f"""
{parent} {{
    background-color: {CARD_ALT};
    alternate-background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {grid};
    selection-background-color: {TABLE_SELECTION};
    selection-color: {TEXT};
}}
{parent}::item {{
    border-right: 1px solid {grid};
    border-bottom: 1px solid {grid};
}}
{parent}::item:selected {{
    background-color: {TABLE_SELECTION};
    color: {TEXT};
}}
{parent} QHeaderView::section {{
    border-bottom: 2px solid {ACCENT};
}}
{_catalog_scrollbar_substyles(parent)}
"""


def build_stylesheet() -> str:
    checkbox_checked = checkbox_checked_indicator_uri()
    checkbox_checked_disabled = checkbox_checked_indicator_uri(disabled=True)
    checkbox_partial = checkbox_partial_indicator_uri()
    menu_checkmark = menu_checkmark_indicator_uri()
    catalog_splitter_handle = _hex_with_alpha(ACCENT, 200)
    catalog_grid = _catalog_gridline_color()
    scrollbar_styles = _modern_scrollbar_styles()
    outline_styles = _catalog_outline_styles()
    return f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}}
QFrame#Banner {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#AdminNotice {{
    background-color: {ADMIN_BG};
    border: 1px solid {ADMIN_BORDER};
    border-radius: 8px;
}}
QLabel#AdminNoticeText {{ color: {ADMIN_TEXT}; font-size: 12px; }}
QLabel#AdminNoticeIcon {{ color: {ADMIN_ICON}; font-size: 16px; }}
QFrame#Card {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#Card QTextBrowser,
QFrame#Card QPlainTextEdit {{
    background-color: transparent;
    border: none;
    padding: 0;
    border-radius: 0;
}}
QLabel#CauseTitle {{ font-size: 20px; font-weight: 600; }}
QLabel#CauseSub {{ color: {MUTED}; font-size: 12px; }}
QLabel#CardTitle {{ font-size: 13px; font-weight: 600; }}
QLabel#SectionValue {{ font-weight: 600; font-size: 12px; }}
QLabel#Muted {{ color: {MUTED}; font-size: 12px; }}

QTabWidget::pane {{ border: none; top: -1px; }}
QTabBar#MainTabBar {{
    background: transparent;
}}
QTabBar#MainTabBar::tab {{
    background-color: {CARD};
    color: {MUTED};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 7px 16px;
    margin-right: 3px;
    margin-top: 2px;
    min-width: 72px;
    font-size: 13px;
}}
QTabBar#MainTabBar::tab:selected {{
    background-color: {BG};
    color: {TEXT};
    font-weight: 600;
    margin-top: 0px;
    padding-top: 9px;
    border-color: {BORDER};
}}
QTabBar#MainTabBar::tab:hover:!selected {{
    color: {TEXT};
    background-color: {CARD_ALT};
}}
QStackedWidget#MainTabStack {{
    border: none;
    background-color: {BG};
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 8px 16px;
    margin-right: 6px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}

QTextBrowser, QPlainTextEdit {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px;
    font-size: 12px;
    selection-background-color: {ACCENT};
}}
QPlainTextEdit#CatalogHint {{
    background-color: transparent;
    border: none;
    padding: 2px 0;
    color: {MUTED};
    font-size: 12px;
}}

QPushButton {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 16px;
    color: {TEXT};
}}
QPushButton:hover {{ background-color: {BTN_HOVER}; }}
QPushButton:disabled {{ color: {MUTED}; background-color: {BTN_DISABLED_BG}; }}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {CARD};
    text-align: center;
    min-height: 18px;
    padding: 2px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 2px;
    margin: 0px;
}}
QProgressBar#TaskProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background-color: {CARD_ALT};
    text-align: center;
    min-height: {TASK_PROGRESS_BAR_HEIGHT}px;
    max-height: {TASK_PROGRESS_BAR_HEIGHT}px;
    padding: 0px;
}}
QProgressBar#TaskProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 7px;
    margin: 1px;
}}
QLabel#TaskProgressCaption {{
    color: {MUTED};
    font-size: 12px;
    padding: 0;
    margin: 0;
}}
QWidget#TaskProgressFrame[catalogChrome="true"] {{
    margin-bottom: 0px;
}}
QPushButton#Primary {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background-color: {PRIMARY_HOVER}; }}
QToolButton#ToolsMenuButton {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    color: {TEXT};
    min-width: 88px;
}}
QToolButton#ToolsMenuButton:hover {{
    background-color: {BTN_HOVER};
}}
QToolButton#ToolsMenuButton::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 14px;
    right: 8px;
}}

QPushButton#Link {{
    background: transparent;
    border: none;
    color: {ACCENT};
    padding: 8px 4px;
    text-align: right;
}}
QPushButton#Link:hover {{ color: {LINK_HOVER}; text-decoration: underline; }}
QStatusBar {{ color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QScrollArea {{ border: none; background: transparent; }}

QMenuBar {{
    background-color: {BG};
    spacing: 4px;
    padding: 2px 8px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 14px;
    margin: 0 2px;
}}
QMenuBar::item:selected {{
    background-color: {CARD_ALT};
    border-radius: 4px;
}}
QMenu {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 40px 6px 16px;
    min-width: 12em;
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: white;
}}
QMenu::indicator {{
    width: 16px;
    height: 16px;
}}
QMenu::indicator:checked {{
    image: {menu_checkmark};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 12px;
}}

QGroupBox {{
    font-weight: 600;
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 10px;
    padding: 12px 10px 8px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {TEXT};
}}

QToolBox::tab {{
    background: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    color: {MUTED};
}}
QToolBox::tab:selected {{
    color: {TEXT};
    font-weight: 600;
    border-color: {ACCENT};
}}
QToolBox QWidget {{
    background: {CARD};
}}

QListWidget {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
}}
QLineEdit {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
}}
QComboBox {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 28px 6px 12px;
}}
QComboBox#CatalogFilterCombo,
QLineEdit#CatalogFilterSearch {{
    border-radius: 6px;
    color: {TEXT};
    padding-top: 4px;
    padding-bottom: 4px;
    min-height: 18px;
}}
QComboBox#CatalogFilterCombo {{
    padding-left: {CATALOG_FILTER_COMBO_PAD_LEFT}px;
    padding-right: 28px;
    border: 1px solid {ACCENT};
}}
QComboBox#CatalogFilterCombo:focus {{
    border: 1px solid {PRIMARY_HOVER};
}}
QComboBox#CatalogFilterCombo:hover {{
    border-color: {PRIMARY_HOVER};
}}
QComboBox#CatalogFilterCombo QLineEdit {{
    background-color: transparent;
    border: none;
    margin: 0;
    padding: 0;
    color: {TEXT};
}}
QLineEdit#CatalogFilterSearch {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    padding-left: 12px;
    padding-right: 12px;
}}
QLineEdit#CatalogFilterSearch:focus {{
    border: 1px solid {ACCENT};
}}
QTableWidget#CatalogCompareTable {{
    background-color: {CARD_ALT};
    alternate-background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {catalog_grid};
    selection-background-color: {TABLE_SELECTION};
    selection-color: {TEXT};
}}
QTableWidget#CatalogCompareTable::item {{
    border-right: 1px solid {catalog_grid};
    border-bottom: 1px solid {catalog_grid};
    padding: 2px 5px;
}}
QTableWidget#CatalogCompareTable::item:selected {{
    background-color: {TABLE_SELECTION};
    color: {TEXT};
}}
QTableWidget#CatalogCompareTable QHeaderView::section {{
    border-bottom: 2px solid {ACCENT};
}}
QFrame#CatalogFilterTray {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
}}
QFrame#CatalogInspectorPane {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {ACCENT};
    margin-right: 4px;
}}
QComboBox QAbstractItemView {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT};
    outline: none;
}}

QTableWidget {{
    background-color: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {catalog_grid};
    selection-background-color: {TABLE_SELECTION};
    selection-color: {TEXT};
}}
QTableWidget::item {{
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 2px 5px;
}}
QTableWidget::item:selected {{
    background-color: {TABLE_SELECTION};
    color: {TEXT};
    border: none;
    outline: none;
}}
QTableWidget::item:selected:active {{
    border: none;
    outline: none;
}}
QTableWidget::item:focus {{
    outline: none;
    border: none;
}}
QHeaderView::section {{
    background-color: {CARD};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {BORDER};
    padding: 4px 6px;
}}
QTableWidget#CatalogUnifiedTable QHeaderView::section {{
    border-bottom: 2px solid {ACCENT};
}}

QSplitter::handle:vertical {{
    background: {BORDER};
    height: 6px;
    margin: 2px 0;
}}
QSplitter::handle:vertical:hover {{
    background: {ACCENT};
}}
QSplitter#CatalogTabSplitter::handle:vertical {{
    background: {catalog_splitter_handle};
    height: 3px;
    margin: 0;
    border-radius: 0;
}}
QSplitter#CatalogTabSplitter::handle:vertical:hover {{
    background: {ACCENT};
}}
QLabel#StepLabel {{
    color: {ACCENT};
    font-weight: 600;
    font-size: 12px;
}}
QLabel#SectionHeading {{
    color: {TEXT};
    font-weight: 600;
    font-size: 13px;
    margin-top: 4px;
}}

QRadioButton {{
    color: {MUTED};
    spacing: 8px;
    padding: 4px 2px;
}}
QRadioButton:checked {{
    color: {TEXT};
    font-weight: 600;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 9px;
    border: 2px solid {RADIO_BORDER};
    background: {CARD_ALT};
}}
QRadioButton::indicator:hover {{
    border-color: {ACCENT};
}}
QRadioButton::indicator:checked {{
    border: 2px solid {ACCENT};
    background: qradialgradient(
        cx: 0.5, cy: 0.5, radius: 0.45,
        fx: 0.5, fy: 0.5,
        stop: 0 {ACCENT}, stop: 0.55 {ACCENT}, stop: 0.56 {CARD_ALT}
    );
}}
QRadioButton:disabled {{
    color: {RADIO_DISABLED_TEXT};
}}
QRadioButton::indicator:disabled {{
    border-color: {BORDER};
    background: {CHECKBOX_DISABLED_BG};
}}

QCheckBox {{
    color: {TEXT};
    spacing: 8px;
    padding: 4px 2px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 2px solid {RADIO_BORDER};
    background: {CARD_ALT};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    border: none;
    background: transparent;
    image: {checkbox_checked};
}}
QCheckBox::indicator:disabled {{
    border-color: {BORDER};
    background: {CHECKBOX_DISABLED_BG};
}}
QCheckBox::indicator:checked:disabled {{
    border: none;
    background: transparent;
    image: {checkbox_checked_disabled};
}}
{scrollbar_styles}
{outline_styles}
"""


def activate_theme(theme_id: str | None = None) -> str:
    """Apply palette tokens and rebuild STYLESHEET. Returns active theme id."""
    global STYLESHEET, _active_theme_id
    tid = theme_id if theme_id in THEME_PRESETS else UI_THEME_DEFAULT
    _active_theme_id = tid
    _assign_theme_tokens(THEME_PRESETS[tid])
    STYLESHEET = build_stylesheet()
    return tid


def current_theme_id() -> str:
    return _active_theme_id


activate_theme(UI_THEME_DEFAULT)
