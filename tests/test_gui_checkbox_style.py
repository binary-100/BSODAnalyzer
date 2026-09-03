"""Two-tone checkbox painting — table Include column and theme tokens."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

import gui_checkbox_style as cb_style  # noqa: E402
import gui_theme as theme  # noqa: E402


def _sample_pixel(img: QtGui.QImage, x: int, y: int) -> tuple[int, int, int]:
    c = img.pixelColor(x, y)
    return c.red(), c.green(), c.blue()


def _count_pixels(img: QtGui.QImage, color: str, region: QtCore.QRect) -> int:
    """Pixels in `region` exactly matching `color`.

    Preferred over probing one hard-coded coordinate: the style decides where the
    indicator sits, so a small metrics change moves the mark a couple of pixels and a
    single-pixel assertion fails even though the colour is correct.
    """
    want = QtGui.QColor(color).getRgb()[:3]
    hits = 0
    for y in range(region.top(), region.bottom() + 1):
        for x in range(region.left(), region.right() + 1):
            if _sample_pixel(img, x, y) == want:
                hits += 1
    return hits


def test_paint_two_tone_checked_uses_theme_fill_not_bare_tick() -> None:
    theme.activate_theme("night")
    img = QtGui.QImage(20, 20, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor("#000000").rgba())
    painter = QtGui.QPainter(img)
    cb_style.paint_two_tone_checkbox(
        painter,
        QtCore.QRect(2, 2, 16, 16),
        QtCore.Qt.CheckState.Checked,
    )
    painter.end()
    # Center should be fill tint (#1e4a7a), not empty/black
    r, g, b = _sample_pixel(img, 10, 10)
    assert r > 20 and g > 20 and b > 40


def test_paint_two_tone_differs_by_theme() -> None:
    theme.activate_theme("night")
    img_n = QtGui.QImage(20, 20, QtGui.QImage.Format.Format_ARGB32)
    img_n.fill(0)
    p = QtGui.QPainter(img_n)
    cb_style.paint_two_tone_checkbox(p, QtCore.QRect(2, 2, 16, 16), QtCore.Qt.CheckState.Checked)
    p.end()

    theme.activate_theme("manly")
    img_m = QtGui.QImage(20, 20, QtGui.QImage.Format.Format_ARGB32)
    img_m.fill(0)
    p = QtGui.QPainter(img_m)
    cb_style.paint_two_tone_checkbox(p, QtCore.QRect(2, 2, 16, 16), QtCore.Qt.CheckState.Checked)
    p.end()

    assert _sample_pixel(img_n, 10, 10) != _sample_pixel(img_m, 10, 10)
    theme.activate_theme("night")


def test_paint_checkmark_only_matches_theme_token() -> None:
    theme.activate_theme("day")
    img = QtGui.QImage(20, 20, QtGui.QImage.Format.Format_ARGB32)
    img.fill(0)
    painter = QtGui.QPainter(img)
    cb_style.paint_checkmark_only(
        painter,
        QtCore.QRect(2, 2, 16, 16),
        theme.CHECKBOX_CHECKMARK,
    )
    painter.end()
    r, g, b = _sample_pixel(img, 8, 11)
    assert b > 180 and r < 80


def test_menu_checkmark_uses_theme_color() -> None:
    from gui_widgets import _MenuFriendlyStyle

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    theme.activate_theme("day")
    # QProxyStyle takes ownership of its base style. Production hands the proxy to
    # app.setStyle(), which transfers ownership to Qt; a test that only holds the proxy
    # would delete the QApplication's live style on GC and abort the interpreter
    # (0xC0000409) at shutdown. A private base style also keeps the indicator geometry
    # independent of whichever style the host platform defaults to.
    style = _MenuFriendlyStyle(QtWidgets.QStyleFactory.create("Fusion"))
    menu = QtWidgets.QMenu()
    act = QtGui.QAction("Night theme", menu)
    act.setCheckable(True)
    act.setChecked(True)
    menu.addAction(act)
    opt = QtWidgets.QStyleOptionMenuItem()
    opt.initFrom(menu)
    opt.text = act.text()
    opt.checked = True
    opt.checkType = QtWidgets.QStyleOptionMenuItem.CheckType.NonExclusive
    opt.menuItemType = QtWidgets.QStyleOptionMenuItem.MenuItemType.Normal
    opt.rect = QtCore.QRect(0, 0, 220, 28)
    opt.state = (
        QtWidgets.QStyle.StateFlag.State_Enabled
        | QtWidgets.QStyle.StateFlag.State_On
    )
    img = QtGui.QImage(220, 28, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(theme.CARD).rgba())
    painter = QtGui.QPainter(img)
    style.drawControl(
        QtWidgets.QStyle.ControlElement.CE_MenuItem,
        opt,
        painter,
        menu,
    )
    painter.end()
    # The checkmark is painted in the indicator strip on the left of the item.
    indicator = QtCore.QRect(0, 0, 40, 28)
    assert _count_pixels(img, theme.CHECKBOX_CHECKMARK, indicator) > 0
    theme.activate_theme("night")


def test_catalog_delegate_paints_single_centered_checkbox() -> None:
    """Regression: QSS + delegate must not paint two Include checkboxes per row."""
    from gui_widgets import CatalogTableNeutralDelegate

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    theme.activate_theme("night")
    table = QtWidgets.QTableWidget(1, 2)
    item = QtWidgets.QTableWidgetItem("")
    item.setFlags(
        item.flags()
        | QtCore.Qt.ItemFlag.ItemIsUserCheckable
        | QtCore.Qt.ItemFlag.ItemIsEnabled
    )
    item.setCheckState(QtCore.Qt.CheckState.Checked)
    table.setItem(0, 1, item)
    delegate = CatalogTableNeutralDelegate(table)
    table.setItemDelegate(delegate)
    img = QtGui.QImage(80, 40, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(theme.CARD_ALT).rgba())
    painter = QtGui.QPainter(img)
    opt = QtWidgets.QStyleOptionViewItem()
    opt.rect = QtCore.QRect(40, 4, 34, 32)
    opt.state = QtWidgets.QStyle.StateFlag.State_Enabled
    index = table.model().index(0, 1)
    delegate.paint(painter, opt, index)
    painter.end()

    fill = QtGui.QColor(theme.CHECKBOX_FILL)
    hit_cols: list[int] = []
    for x in range(40, 74):
        c = img.pixelColor(x, 20)
        if (
            abs(c.red() - fill.red()) < 28
            and abs(c.green() - fill.green()) < 28
            and abs(c.blue() - fill.blue()) < 28
        ):
            hit_cols.append(x)
    assert hit_cols, "expected painted checkbox fill in row"
    span = hit_cols[-1] - hit_cols[0] + 1
    assert span <= 20, f"checkbox paint too wide ({span}px) — likely double draw"
    center = (hit_cols[0] + hit_cols[-1]) / 2
    cell_center = 40 + 34 / 2
    assert abs(center - cell_center) < 6, "checkbox should be centered in cell"
    theme.activate_theme("night")


def test_catalog_delegate_paints_check_column() -> None:
    from gui_widgets import CatalogTableNeutralDelegate

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    theme.activate_theme("day")
    table = QtWidgets.QTableWidget(1, 2)
    item = QtWidgets.QTableWidgetItem("")
    item.setFlags(
        item.flags()
        | QtCore.Qt.ItemFlag.ItemIsUserCheckable
        | QtCore.Qt.ItemFlag.ItemIsEnabled
    )
    item.setCheckState(QtCore.Qt.CheckState.Checked)
    table.setItem(0, 1, item)
    delegate = CatalogTableNeutralDelegate(table)
    table.setItemDelegate(delegate)
    img = QtGui.QImage(80, 40, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(theme.CARD_ALT).rgba())
    painter = QtGui.QPainter(img)
    opt = QtWidgets.QStyleOptionViewItem()
    opt.rect = QtCore.QRect(40, 4, 36, 32)
    opt.state = QtWidgets.QStyle.StateFlag.State_Enabled
    index = table.model().index(0, 1)
    delegate.paint(painter, opt, index)
    painter.end()
    r, g, b = _sample_pixel(img, 58, 20)
    assert b > 100  # day fill #bfdbfe is blue-heavy
    theme.activate_theme("night")


def test_catalog_delegate_hover_uses_accent_not_native_blue() -> None:
    """Regression: super().paint re-initStyleOption restored Windows dark-blue hover."""
    from gui_widgets import CatalogTableNeutralDelegate

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    theme.activate_theme("day")
    table = QtWidgets.QTableWidget(1, 3)
    table.setShowGrid(True)
    item = QtWidgets.QTableWidgetItem("Realtek Audio")
    table.setItem(0, 2, item)
    delegate = CatalogTableNeutralDelegate(table)
    table.setItemDelegate(delegate)
    img = QtGui.QImage(200, 32, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtGui.QColor(theme.catalog_row_zebra_color(0)).rgba())
    painter = QtGui.QPainter(img)
    opt = QtWidgets.QStyleOptionViewItem()
    opt.rect = QtCore.QRect(0, 0, 200, 32)
    opt.state = (
        QtWidgets.QStyle.StateFlag.State_Enabled
        | QtWidgets.QStyle.StateFlag.State_MouseOver
    )
    opt.widget = table
    index = table.model().index(0, 2)
    delegate.paint(painter, opt, index)
    painter.end()
    r, g, b = _sample_pixel(img, 100, 16)
    # Native Windows hover is saturated blue (~0,120,215); accent overlay stays pale.
    assert not (b > 180 and r < 60 and g < 140), (
        f"hover looks like native Windows blue ({r},{g},{b})"
    )
    theme.activate_theme("night")


def test_item_view_style_checkbox_single_toggle() -> None:
    """Export dialog checkboxes must toggle once per click (no double-toggle)."""
    import gui_include_header as inc_hdr

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    cb = inc_hdr.ItemViewStyleCheckBox("Export crash report")
    cb.setChecked(True)
    assert cb.isChecked()
    cb._indicator.clicked.emit()
    assert not cb.isChecked()
    cb._indicator.clicked.emit()
    assert cb.isChecked()


if __name__ == "__main__":
    test_paint_two_tone_checked_uses_theme_fill_not_bare_tick()
    test_paint_two_tone_differs_by_theme()
    test_catalog_delegate_paints_check_column()
    test_catalog_delegate_hover_uses_accent_not_native_blue()
    test_item_view_style_checkbox_single_toggle()
    print("checkbox style tests OK")
