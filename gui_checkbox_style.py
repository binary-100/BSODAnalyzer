"""Shared two-tone checkbox painting — dialogs (QSS), tables, and header indicators."""

from __future__ import annotations

from PySide6 import QtCore, QtGui

import gui_theme as theme

INDICATOR_SIZE = 16


def indicator_rect_centered(cell: QtCore.QRect, size: int = INDICATOR_SIZE) -> QtCore.QRect:
    return QtCore.QRect(
        cell.x() + max(0, (cell.width() - size) // 2),
        cell.y() + max(0, (cell.height() - size) // 2),
        size,
        size,
    )


def menu_checkmark_color(*, selected: bool = False, disabled: bool = False) -> str:
    """Tick color for menu / other non-checkbox check indicators."""
    if disabled:
        return theme.RADIO_DISABLED_TEXT
    if selected:
        return "#ffffff"
    return theme.CHECKBOX_CHECKMARK


def paint_checkmark_only(
    painter: QtGui.QPainter,
    rect: QtCore.QRect,
    color: str | None = None,
    *,
    size: int = INDICATOR_SIZE,
) -> None:
    """Paint a theme-colored tick without a checkbox box (menus, etc.)."""
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    box = indicator_rect_centered(rect, size)
    tick = color or theme.CHECKBOX_CHECKMARK
    check = QtGui.QPainterPath()
    x, y, w, h = box.x(), box.y(), box.width(), box.height()
    check.moveTo(x + w * 0.20, y + h * 0.52)
    check.lineTo(x + w * 0.42, y + h * 0.72)
    check.lineTo(x + w * 0.78, y + h * 0.28)
    tick_pen = QtGui.QPen(QtGui.QColor(tick))
    tick_pen.setWidthF(1.8)
    tick_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    tick_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(tick_pen)
    painter.drawPath(check)
    painter.restore()


def paint_two_tone_checkbox(
    painter: QtGui.QPainter,
    rect: QtCore.QRect,
    state: QtCore.Qt.CheckState,
    *,
    hovered: bool = False,
    disabled: bool = False,
) -> None:
    """Paint theme-aware two-tone checkbox (fill + border + tick or dash)."""
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

    box = indicator_rect_centered(rect, INDICATOR_SIZE)
    radius = 3.0

    if disabled:
        fill = theme.CHECKBOX_DISABLED_BG
        border = theme.BORDER
        tick = theme.RADIO_DISABLED_TEXT
    elif state == QtCore.Qt.CheckState.Checked:
        fill = theme.CHECKBOX_FILL
        border = theme.CHECKBOX_BORDER
        tick = theme.CHECKBOX_CHECKMARK
    elif state == QtCore.Qt.CheckState.PartiallyChecked:
        fill = theme.CHECKBOX_FILL
        border = theme.CHECKBOX_BORDER
        tick = theme.CHECKBOX_CHECKMARK
    else:
        fill = theme.CARD_ALT
        border = theme.ACCENT if hovered else theme.RADIO_BORDER
        tick = theme.CHECKBOX_CHECKMARK

    path = QtGui.QPainterPath()
    path.addRoundedRect(QtCore.QRectF(box), radius, radius)
    painter.fillPath(path, QtGui.QColor(fill))
    pen = QtGui.QPen(QtGui.QColor(border))
    pen.setWidthF(1.5)
    painter.setPen(pen)
    painter.drawPath(path)

    if state == QtCore.Qt.CheckState.Checked:
        paint_checkmark_only(painter, rect, tick)
    elif state == QtCore.Qt.CheckState.PartiallyChecked:
        dash_pen = QtGui.QPen(QtGui.QColor(tick))
        dash_pen.setWidthF(1.8)
        dash_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(dash_pen)
        cx = box.center().x()
        cy = box.center().y()
        half = max(3, int(box.width() * 0.22))
        painter.drawLine(cx - half, cy, cx + half, cy)

    painter.restore()
