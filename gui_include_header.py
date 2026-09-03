"""Header checkbox for Include columns on driver/firmware tables."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import gui_checkbox_style as cb_style


class _ItemViewCheckIndicator(QtWidgets.QWidget):
    """Same painted indicator as driver/firmware Include column checkmarks."""

    clicked = QtCore.Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        style_hint: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._style_hint = style_hint or self
        self._state = QtCore.Qt.CheckState.Unchecked
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def checkState(self) -> QtCore.Qt.CheckState:
        return self._state

    def setCheckState(self, state: QtCore.Qt.CheckState) -> None:
        if self._state == state:
            return
        self._state = state
        self.update()

    def sizeHint(self) -> QtCore.QSize:
        # Use our painted indicator size — querying PM_IndicatorWidth on a Fusion-
        # styled QTableWidget during early header layout can crash on Windows.
        side = cb_style.INDICATOR_SIZE
        return QtCore.QSize(side, side)

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        cb_style.paint_two_tone_checkbox(
            painter,
            self.rect(),
            self._state,
            hovered=self.underMouse(),
        )
        painter.end()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _TableStyleCheckIndicator(_ItemViewCheckIndicator):
    """Include-column header indicator; uses table style metrics."""

    def __init__(
        self,
        table: QtWidgets.QTableWidget,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent, style_hint=table)
        self._table = table


class ItemViewStyleCheckBox(QtWidgets.QWidget):
    """Checkbox using the same two-tone indicator as Drivers/Firmware Include rows."""

    toggled = QtCore.Signal(bool)

    def __init__(self, text: str = "", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = False
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(8)
        self._indicator = _ItemViewCheckIndicator(self)
        self._indicator.clicked.connect(self._toggle)
        self._label = QtWidgets.QLabel(text)
        self._label.setWordWrap(False)
        self._label.installEventFilter(self)
        lay.addWidget(self._indicator, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self._label, 1)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self._label and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            me = event
            if isinstance(me, QtGui.QMouseEvent) and me.button() == QtCore.Qt.MouseButton.LeftButton:
                self._toggle()
                return True
        return super().eventFilter(obj, event)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked)
        if self._checked == checked:
            return
        self._checked = checked
        state = (
            QtCore.Qt.CheckState.Checked
            if checked
            else QtCore.Qt.CheckState.Unchecked
        )
        self._indicator.setCheckState(state)
        self.toggled.emit(checked)

    def _toggle(self) -> None:
        self.setChecked(not self._checked)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (
            QtCore.Qt.Key.Key_Space,
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Enter,
        ):
            self._toggle()
            event.accept()
            return
        super().keyPressEvent(event)


class IncludeHeaderCheckbox(QtCore.QObject):
    """Checkbox in the table header to include or exclude all visible rows."""

    include_all_changed = QtCore.Signal(bool)

    def __init__(
        self,
        table: QtWidgets.QTableWidget,
        column: int,
        *,
        tooltip: str = "Include all visible rows in search",
    ) -> None:
        super().__init__(table)
        self._table = table
        self._column = column
        self._syncing = False
        hdr = table.horizontalHeader()
        hdr_item = table.horizontalHeaderItem(column)
        if hdr_item is not None:
            hdr_item.setToolTip(tooltip)
            hdr_item.setText("")
        self._indicator = _TableStyleCheckIndicator(table, hdr.viewport())
        self._indicator.setToolTip(tooltip)
        self._indicator.setAccessibleName("Include all")
        self._indicator.setAccessibleDescription(tooltip)
        self._indicator.clicked.connect(self._on_clicked)
        hdr.sectionResized.connect(self._schedule_reposition)
        hdr.geometriesChanged.connect(self._schedule_reposition)
        model = table.model()
        if model is not None:
            model.rowsInserted.connect(self._schedule_reposition)
            model.rowsRemoved.connect(self._schedule_reposition)
            model.layoutChanged.connect(self._schedule_reposition)
        sb = table.verticalScrollBar()
        sb.valueChanged.connect(self._schedule_reposition)
        sb.rangeChanged.connect(self._schedule_reposition)
        table.horizontalScrollBar().valueChanged.connect(self._schedule_reposition)
        self._reposition_timer = QtCore.QTimer(self)
        self._reposition_timer.setSingleShot(True)
        self._reposition_timer.setInterval(16)
        self._reposition_timer.timeout.connect(self._reposition)
        QtCore.QTimer.singleShot(0, self._reposition)

    def refresh(self) -> None:
        self._schedule_reposition()
        self._indicator.update()

    def _schedule_reposition(self, *_args) -> None:
        """Coalesce header layout signals — avoids stack stress during bulk table fills."""
        if not self._table.updatesEnabled():
            return
        self._reposition_timer.start()

    def _column_visible(self) -> bool:
        hdr = self._table.horizontalHeader()
        if self._table.isColumnHidden(self._column):
            return False
        if hdr.isSectionHidden(self._column):
            return False
        if hdr.sectionSize(self._column) < 24:
            return False
        return True

    @staticmethod
    def _check_indicator_opt(
        item: QtWidgets.QTableWidgetItem,
        cell: QtCore.QRect,
        viewport: QtWidgets.QWidget,
    ) -> QtWidgets.QStyleOptionViewItem:
        opt = QtWidgets.QStyleOptionViewItem()
        opt.initFrom(viewport)
        opt.rect = cell
        opt.features = QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        opt.checkState = item.checkState()
        opt.state = (
            QtWidgets.QStyle.StateFlag.State_Enabled
            | QtWidgets.QStyle.StateFlag.State_Active
        )
        cs = item.checkState()
        if cs == QtCore.Qt.CheckState.Checked:
            opt.state |= QtWidgets.QStyle.StateFlag.State_On
        elif cs == QtCore.Qt.CheckState.PartiallyChecked:
            opt.state |= QtWidgets.QStyle.StateFlag.State_NoChange
        else:
            opt.state |= QtWidgets.QStyle.StateFlag.State_Off
        return opt

    def _reposition(self, *_args) -> None:
        if not self._table.updatesEnabled():
            return
        if self._table.horizontalHeader() is None:
            return
        if not self._column_visible():
            self._indicator.hide()
            return

        hdr = self._table.horizontalHeader()
        table = self._table
        col = self._column

        col_w = hdr.sectionSize(col)
        col_left_hdr = hdr.sectionViewportPosition(col)
        ind_w = self._indicator.sizeHint().width()
        target_left = col_left_hdr + max(0, (col_w - ind_w) // 2)

        h = hdr.viewport().height()
        ind_w = self._indicator.sizeHint().width()
        ind_h = self._indicator.sizeHint().height()
        top = max(0, (h - ind_h) // 2)

        viewport_w = hdr.viewport().width()
        left = min(max(0, target_left), max(0, viewport_w - ind_w))

        self._indicator.setGeometry(left, top, ind_w, ind_h)
        self._indicator.show()
        self._indicator.raise_()

    def sync_from_rows(self, included: int, total: int) -> None:
        self._syncing = True
        try:
            if total <= 0 or included <= 0:
                self._indicator.setCheckState(QtCore.Qt.CheckState.Unchecked)
            elif included >= total:
                self._indicator.setCheckState(QtCore.Qt.CheckState.Checked)
            else:
                self._indicator.setCheckState(QtCore.Qt.CheckState.PartiallyChecked)
        finally:
            self._syncing = False

    def _on_clicked(self) -> None:
        if self._syncing:
            return
        state = self._indicator.checkState()
        if state == QtCore.Qt.CheckState.Checked:
            self._indicator.setCheckState(QtCore.Qt.CheckState.Unchecked)
        else:
            self._indicator.setCheckState(QtCore.Qt.CheckState.Checked)
        want = self._indicator.checkState() != QtCore.Qt.CheckState.Unchecked
        self.include_all_changed.emit(want)
