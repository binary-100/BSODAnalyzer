"""Custom Qt widgets and menu helpers for the BSOD Analyzer GUI."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from gui_theme import SEVERITY_SEGMENTS
import gui_checkbox_style as cb_style


def apply_styled_frame(
    frame: QtWidgets.QFrame,
    object_name: str = "Card",
) -> QtWidgets.QFrame:
    """QSS-rounded frame without native square QFrame chrome bleeding through."""
    frame.setObjectName(object_name)
    frame.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    frame.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
    return frame


def apply_styled_control(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Rounded QSS controls (combo, line edit, buttons) — suppress native fill."""
    widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
    return widget


def apply_catalog_filter_combo(combo: QtWidgets.QComboBox) -> QtWidgets.QComboBox:
    """Catalog filter dropdown — Fusion avoids native sunken line-edit chrome."""
    apply_styled_control(combo)
    combo.setEditable(False)
    fusion = QtWidgets.QStyleFactory.create("Fusion")
    if fusion is not None:
        combo.setStyle(fusion)
    return combo


def apply_catalog_filter_search(edit: QtWidgets.QLineEdit) -> QtWidgets.QLineEdit:
    """Catalog search field — per-widget QSS from shell theme refresh draws border/background."""
    apply_styled_control(edit)
    edit.setFrame(False)
    app = QtWidgets.QApplication.instance()
    if app is not None:
        edit.setStyle(app.style())
    return edit


def apply_catalog_filter_control(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Catalog filter combo or search — route to the correct styled helper."""
    if isinstance(widget, QtWidgets.QLineEdit):
        return apply_catalog_filter_search(widget)
    if isinstance(widget, QtWidgets.QComboBox):
        return apply_catalog_filter_combo(widget)
    return apply_styled_control(widget)


def apply_catalog_table_style(table: QtWidgets.QTableWidget) -> QtWidgets.QTableWidget:
    """Catalog tables — styled background; selection colors come from delegate + QSS."""
    apply_styled_control(table)
    return table

def _plain_menu_text(text: str) -> str:
    """Strip mnemonic & and any trailing ellipsis Qt or the OS may add."""
    t = (text or "").split("\t", 1)[0].replace("&", "").strip()
    if t.endswith("…"):
        t = t[:-1].strip()
    if t.endswith("..."):
        t = t[:-3].strip()
    return t


class _MenuFriendlyStyle(QtWidgets.QProxyStyle):
    """Prevent Qt from eliding menu labels (shows 'Preferences...' in a wide menu)."""

    @staticmethod
    def _is_menu_check_indicator(
        element: QtWidgets.QStyle.PrimitiveElement,
        widget: QtWidgets.QWidget | None,
    ) -> bool:
        pe = QtWidgets.QStyle.PrimitiveElement
        if element == pe.PE_IndicatorMenuCheckMark:
            return True
        return element == pe.PE_IndicatorCheckBox and isinstance(
            widget, QtWidgets.QMenu
        )

    def drawPrimitive(
        self,
        element: QtWidgets.QStyle.PrimitiveElement,
        option: QtWidgets.QStyleOption,
        painter: QtGui.QPainter,
        widget: QtWidgets.QWidget | None = None,
    ) -> None:
        if self._is_menu_check_indicator(element, widget):
            state = option.state
            if not (state & QtWidgets.QStyle.StateFlag.State_On):
                return
            selected = bool(state & QtWidgets.QStyle.StateFlag.State_Selected)
            disabled = not (state & QtWidgets.QStyle.StateFlag.State_Enabled)
            tick = cb_style.menu_checkmark_color(
                selected=selected,
                disabled=disabled,
            )
            cb_style.paint_checkmark_only(painter, option.rect, tick)
            return
        super().drawPrimitive(element, option, painter, widget)

    def sizeFromContents(
        self,
        ct: QtWidgets.QStyle.ContentsType,
        opt: QtWidgets.QStyleOption,
        size: QtCore.QSize,
        widget: QtWidgets.QWidget | None = None,
    ) -> QtCore.QSize:
        sz = super().sizeFromContents(ct, opt, size, widget)
        if ct == QtWidgets.QStyle.ContentsType.CT_MenuItem:
            mi = QtWidgets.QStyleOptionMenuItem(opt)
            plain = _plain_menu_text(mi.text)
            if plain:
                fm = QtGui.QFontMetrics(mi.font)
                need = fm.horizontalAdvance(plain) + 56
                if sz.width() < need:
                    sz.setWidth(need)
        elif ct == QtWidgets.QStyle.ContentsType.CT_MenuBarItem:
            plain = _plain_menu_text(getattr(opt, "text", "") or "")
            if plain:
                fm = QtGui.QFontMetrics(opt.font)
                need = fm.horizontalAdvance(plain) + 24
                if sz.width() < need:
                    sz.setWidth(need)
        return sz


def _fix_menu_popup_width(menu: QtWidgets.QMenu) -> None:
    """Ensure dropdown is wide enough for full labels before it is shown."""
    fm = QtGui.QFontMetrics(menu.font())
    width = 0
    for action in menu.actions():
        if action.isSeparator():
            continue
        plain = _plain_menu_text(action.text())
        if action.text() != plain:
            action.setText(plain)
        width = max(width, fm.horizontalAdvance(plain))
    if width > 0:
        menu.setMinimumWidth(width + 56)


class SeverityMeter(QtWidgets.QWidget):
    """Four-segment severity bar with a marker over the active level."""

    def __init__(self) -> None:
        super().__init__()
        self._level = 0
        self.setMinimumHeight(54)

    def set_level(self, level: int) -> None:
        self._level = max(0, min(3, int(level)))
        name = SEVERITY_SEGMENTS[self._level]
        self.setAccessibleName("Severity meter")
        self.setAccessibleDescription(f"Severity level: {name}")
        self.update()

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        import gui_theme as theme

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w = self.width()
        gap = 6
        seg_w = (w - gap * 3) / 4
        bar_y = 18
        bar_h = 10
        inactive = QtGui.QColor(theme.BORDER)
        for i in range(4):
            x = i * (seg_w + gap)
            active = i <= self._level
            color = (
                QtGui.QColor(theme.SEVERITY_COLORS[i])
                if active
                else inactive
            )
            p.setBrush(color)
            p.setPen(QtCore.Qt.NoPen)
            p.drawRoundedRect(QtCore.QRectF(x, bar_y, seg_w, bar_h), 4, 4)
            # label
            p.setPen(QtGui.QColor(theme.TEXT if i == self._level else theme.MUTED))
            f = p.font()
            f.setPointSize(8)
            f.setBold(i == self._level)
            p.setFont(f)
            p.drawText(QtCore.QRectF(x, bar_y + bar_h + 4, seg_w, 16),
                       QtCore.Qt.AlignCenter, SEVERITY_SEGMENTS[i])
        # marker triangle over active segment
        mx = self._level * (seg_w + gap) + seg_w / 2
        p.setBrush(QtGui.QColor(theme.TEXT))
        tri = QtGui.QPolygonF([
            QtCore.QPointF(mx, bar_y - 2),
            QtCore.QPointF(mx - 5, bar_y - 10),
            QtCore.QPointF(mx + 5, bar_y - 10),
        ])
        p.drawPolygon(tri)
        p.end()


class CatalogTableNeutralDelegate(QtWidgets.QStyledItemDelegate):
    """Suppress selection chrome on icon/Include columns; paint two-tone Include checks."""

    def __init__(
        self,
        table: QtWidgets.QTableWidget,
        *,
        neutral_columns: tuple[int, ...] = (0, 1),
        check_columns: tuple[int, ...] = (1,),
        icon_columns: tuple[int, ...] = (0,),
    ) -> None:
        super().__init__(table)
        self._neutral_columns = neutral_columns
        self._check_columns = check_columns
        self._icon_columns = icon_columns

    @staticmethod
    def _strip_check_indicator(opt: QtWidgets.QStyleOptionViewItem) -> None:
        opt.features &= ~QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        opt.checkState = QtCore.Qt.CheckState.Unchecked
        opt.text = ""
        opt.icon = QtGui.QIcon()

    @staticmethod
    def _paint_item_background(
        painter: QtGui.QPainter, opt: QtWidgets.QStyleOptionViewItem
    ) -> None:
        bg = opt.backgroundBrush
        if bg.style() != QtCore.Qt.BrushStyle.NoBrush:
            painter.fillRect(opt.rect, bg)

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        col = index.column()
        if col in self._neutral_columns:
            opt.state &= ~QtWidgets.QStyle.StateFlag.State_HasFocus
            opt.state &= ~QtWidgets.QStyle.StateFlag.State_KeyboardFocusChange
            opt.state &= ~QtWidgets.QStyle.StateFlag.State_Selected

        selected = bool(opt.state & QtWidgets.QStyle.StateFlag.State_Selected)
        selection_painted = False
        if selected and col not in self._neutral_columns:
            import gui_theme as theme

            painter.fillRect(opt.rect, QtGui.QColor(theme.TABLE_SELECTION))
            opt.state &= ~QtWidgets.QStyle.StateFlag.State_Selected
            opt.backgroundBrush = QtGui.QBrush()
            fg = index.data(QtCore.Qt.ItemDataRole.ForegroundRole)
            has_custom_fg = (
                isinstance(fg, QtGui.QBrush)
                and fg.style() != QtCore.Qt.BrushStyle.NoBrush
            )
            if not has_custom_fg:
                text_color = QtGui.QColor(theme.TEXT)
                opt.palette.setColor(QtGui.QPalette.ColorRole.Text, text_color)
                opt.palette.setColor(
                    QtGui.QPalette.ColorRole.HighlightedText, text_color
                )
            selection_painted = True

        check_raw = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
        is_check_cell = (
            col in self._check_columns
            and check_raw is not None
            and bool(index.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        )
        is_icon_cell = col in self._icon_columns

        if is_check_cell or is_icon_cell:
            self._strip_check_indicator(opt)

        if not selection_painted:
            bg = opt.backgroundBrush
            if bg.style() == QtCore.Qt.BrushStyle.NoBrush:
                import gui_theme as theme

                painter.fillRect(
                    opt.rect,
                    QtGui.QColor(theme.catalog_row_zebra_color(index.row())),
                )
            else:
                self._paint_item_background(painter, opt)

        hovered = bool(opt.state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        if hovered and not selected and col not in self._neutral_columns:
            import gui_theme as theme

            overlay = QtGui.QColor(theme.ACCENT)
            overlay.setAlpha(36)
            painter.fillRect(opt.rect, overlay)
            opt.state &= ~QtWidgets.QStyle.StateFlag.State_MouseOver
            fg = index.data(QtCore.Qt.ItemDataRole.ForegroundRole)
            has_custom_fg = (
                isinstance(fg, QtGui.QBrush)
                and fg.style() != QtCore.Qt.BrushStyle.NoBrush
            )
            if not has_custom_fg:
                text_color = QtGui.QColor(theme.TEXT)
                opt.palette.setColor(QtGui.QPalette.ColorRole.Text, text_color)
                opt.palette.setColor(
                    QtGui.QPalette.ColorRole.HighlightedText, text_color
                )

        if is_check_cell:
            state = QtCore.Qt.CheckState(int(check_raw))
            hovered = bool(opt.state & QtWidgets.QStyle.StateFlag.State_MouseOver)
            disabled = not bool(opt.state & QtWidgets.QStyle.StateFlag.State_Enabled)
            cb_style.paint_two_tone_checkbox(
                painter, opt.rect, state, hovered=hovered, disabled=disabled
            )
            return

        if is_icon_cell:
            icon = index.data(QtCore.Qt.ItemDataRole.DecorationRole)
            if icon and isinstance(icon, QtGui.QIcon) and not icon.isNull():
                widget = option.widget
                if isinstance(widget, QtWidgets.QAbstractItemView):
                    size = widget.iconSize()
                else:
                    size = QtCore.QSize(cb_style.INDICATOR_SIZE, cb_style.INDICATOR_SIZE)
                pm = icon.pixmap(size)
                if not pm.isNull():
                    x = opt.rect.x() + max(0, (opt.rect.width() - pm.width()) // 2)
                    y = opt.rect.y() + max(0, (opt.rect.height() - pm.height()) // 2)
                    painter.drawPixmap(x, y, pm)
            return

        opt.state &= (
            ~QtWidgets.QStyle.StateFlag.State_MouseOver
            & ~QtWidgets.QStyle.StateFlag.State_Selected
            & ~QtWidgets.QStyle.StateFlag.State_HasFocus
        )
        opt.showDecorationSelected = False
        opt.backgroundBrush = QtGui.QBrush()
        widget = option.widget
        style = widget.style() if widget is not None else QtWidgets.QApplication.style()
        style.drawControl(
            QtWidgets.QStyle.ControlElement.CE_ItemViewItem,
            opt,
            painter,
            widget,
        )


class CatalogDeviceNameDelegate(QtWidgets.QStyledItemDelegate):
    """Device/component column — ellipsized label plus optional crash-link ⓘ icon."""

    INFO_SIZE = 15
    INFO_MARGIN = 5

    def _info_tooltip(self, index: QtCore.QModelIndex) -> str:
        from gui_theme import DRV_CRASH_INFO_TOOLTIP_ROLE

        raw = index.data(DRV_CRASH_INFO_TOOLTIP_ROLE)
        return str(raw or "").strip()

    def _info_rect(self, cell: QtCore.QRect) -> QtCore.QRect:
        size = self.INFO_SIZE
        x = cell.right() - size - self.INFO_MARGIN
        y = cell.y() + max(0, (cell.height() - size) // 2)
        return QtCore.QRect(x, y, size, size)

    def _paint_info_icon(
        self, painter: QtGui.QPainter, rect: QtCore.QRect, *, accent: str
    ) -> None:
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(accent))
        painter.drawEllipse(rect)
        painter.setPen(QtGui.QColor("#ffffff"))
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        font.setItalic(True)
        painter.setFont(font)
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "i")
        painter.restore()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        import gui_theme as theme

        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        selected = bool(opt.state & QtWidgets.QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(opt.rect, QtGui.QColor(theme.TABLE_SELECTION))
            opt.state &= ~QtWidgets.QStyle.StateFlag.State_Selected
            opt.backgroundBrush = QtGui.QBrush()
        elif opt.backgroundBrush.style() != QtCore.Qt.BrushStyle.NoBrush:
            painter.fillRect(opt.rect, opt.backgroundBrush)
        else:
            painter.fillRect(
                opt.rect, QtGui.QColor(theme.catalog_row_zebra_color(index.row()))
            )

        hovered = bool(opt.state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        if hovered and not selected:
            overlay = QtGui.QColor(theme.ACCENT)
            overlay.setAlpha(36)
            painter.fillRect(opt.rect, overlay)

        text = (index.data(QtCore.Qt.ItemDataRole.DisplayRole) or "").strip()
        fg = index.data(QtCore.Qt.ItemDataRole.ForegroundRole)
        if isinstance(fg, QtGui.QBrush) and fg.style() != QtCore.Qt.BrushStyle.NoBrush:
            painter.setPen(fg.color())
        else:
            painter.setPen(QtGui.QColor(theme.TEXT))

        tip = self._info_tooltip(index)
        reserve = self.INFO_SIZE + self.INFO_MARGIN * 2 if tip else self.INFO_MARGIN
        text_rect = opt.rect.adjusted(self.INFO_MARGIN, 0, -reserve, 0)
        elided = opt.fontMetrics.elidedText(
            text, QtCore.Qt.TextElideMode.ElideRight, max(0, text_rect.width())
        )
        painter.drawText(
            text_rect,
            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
            elided,
        )
        if tip:
            self._paint_info_icon(
                painter, self._info_rect(opt.rect), accent=theme.ACCENT
            )

    def helpEvent(
        self,
        event: QtGui.QHelpEvent,
        view: QtWidgets.QAbstractItemView,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> bool:
        if event.type() == QtCore.QEvent.Type.ToolTip:
            tip = self._info_tooltip(index)
            if tip and self._info_rect(option.rect).contains(event.pos()):
                QtWidgets.QToolTip.showText(event.globalPos(), tip, view)
                return True
        return super().helpEvent(event, view, option, index)


class MainTabHost(QtWidgets.QWidget):
    """Tab bar fixed under the menu; optional header strip; stacked page content."""

    currentChanged = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tab_bar = QtWidgets.QTabBar()
        self._tab_bar.setObjectName("MainTabBar")
        self._tab_bar.setDrawBase(False)
        self._tab_bar.setExpanding(False)

        self._header = QtWidgets.QWidget()
        self._header_lay = QtWidgets.QVBoxLayout(self._header)
        self._header_lay.setContentsMargins(0, 2, 0, 0)
        self._header_lay.setSpacing(4)

        self._stack = QtWidgets.QStackedWidget()
        self._stack.setObjectName("MainTabStack")

        root.addWidget(self._tab_bar)
        root.addWidget(self._header)
        root.addWidget(self._stack, 1)

        self._tab_bar.currentChanged.connect(self._on_tab_index_changed)

    def _on_tab_index_changed(self, index: int) -> None:
        if index < 0 or index >= self._stack.count():
            return
        self._stack.setCurrentIndex(index)
        self.currentChanged.emit(index)

    def header_layout(self) -> QtWidgets.QVBoxLayout:
        return self._header_lay

    def set_header_visible(self, visible: bool) -> None:
        self._header.setVisible(visible)

    def addTab(self, widget: QtWidgets.QWidget, title: str) -> int:
        self._tab_bar.addTab(title)
        self._stack.addWidget(widget)
        return self._stack.count() - 1

    def currentIndex(self) -> int:
        return self._tab_bar.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        self._tab_bar.setCurrentIndex(index)

    def indexOf(self, widget: QtWidgets.QWidget) -> int:
        return self._stack.indexOf(widget)
