"""Catalog tab layout presets, splitters, table chrome, column persist."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiCatalogLayoutMixin:
    def _migrate_catalog_layout_settings(self) -> None:
        """One-time merge of per-tab layout keys so Drivers/Firmware stay aligned."""
        if self._settings.get(CATALOG_SPLITTER_SETTINGS_KEY) is None:
            for legacy in ("drv_tab_splitter_sizes", "fw_tab_splitter_sizes"):
                val = self._settings.get(legacy)
                if (
                    isinstance(val, list)
                    and len(val) == 3
                    and all(isinstance(n, int) for n in val)
                ):
                    self._settings[CATALOG_SPLITTER_SETTINGS_KEY] = list(val)
                    break
        if self._settings.get(CATALOG_UNIFIED_COL_WIDTHS_KEY) is None:
            from gui_theme import (
                DRV_COL_INSTALLED,
                UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE,
            )

            for legacy in (
                "catalog_unified_col_widths_v2",
                "drv_unified_col_widths_v2",
                "fw_unified_col_widths_v2",
            ):
                val = self._settings.get(legacy)
                if isinstance(val, list) and val:
                    migrated = list(val)
                    while len(migrated) <= DRV_COL_INSTALLED:
                        migrated.append(UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE)
                    if (
                        migrated[DRV_COL_INSTALLED]
                        < UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE
                    ):
                        migrated[DRV_COL_INSTALLED] = (
                            UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE
                        )
                    self._settings[CATALOG_UNIFIED_COL_WIDTHS_KEY] = migrated
                    break
        if self._settings.get(CATALOG_PACKAGE_COL_WIDTHS_KEY) is None:
            for legacy in ("drv_package_col_widths", "fw_package_col_widths"):
                val = self._settings.get(legacy)
                if isinstance(val, list) and val:
                    self._settings[CATALOG_PACKAGE_COL_WIDTHS_KEY] = list(val)
                    break

    def _apply_unified_catalog_table_style(self, table: QtWidgets.QTableWidget) -> None:
        table.setObjectName("CatalogUnifiedTable")
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.setGridStyle(QtCore.Qt.PenStyle.SolidLine)
        apply_catalog_table_style(table)
        pal = table.palette()
        pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(TABLE_SELECTION))
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(TEXT))
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(CARD_ALT))
        pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(CARD))
        table.setPalette(pal)
        if not getattr(table, "_catalog_neutral_delegate", None):
            table._catalog_neutral_delegate = CatalogTableNeutralDelegate(table)
            table.setItemDelegate(table._catalog_neutral_delegate)
        if not getattr(table, "_catalog_device_name_delegate", None):
            from gui_theme import DRV_COL_DEVICE
            from gui_widgets import CatalogDeviceNameDelegate

            table._catalog_device_name_delegate = CatalogDeviceNameDelegate(table)
            table.setItemDelegateForColumn(
                DRV_COL_DEVICE, table._catalog_device_name_delegate
            )

    def _apply_compare_table_style(self, table: QtWidgets.QTableWidget) -> None:
        """Package compare grid — own object name; no icon/check neutral columns."""
        table.setObjectName("CatalogCompareTable")
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.setGridStyle(QtCore.Qt.PenStyle.SolidLine)
        apply_catalog_table_style(table)
        pal = table.palette()
        pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(TABLE_SELECTION))
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(TEXT))
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(CARD_ALT))
        pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(CARD))
        table.setPalette(pal)
        if not getattr(table, "_catalog_row_delegate", None):
            table._catalog_row_delegate = CatalogTableNeutralDelegate(
                table,
                neutral_columns=(),
                check_columns=(),
                icon_columns=(),
            )
            table.setItemDelegate(table._catalog_row_delegate)

    @staticmethod
    def _build_catalog_filter_tray() -> QtWidgets.QFrame:
        """Filter row tray — CARD_ALT inset; combo/search keep Fusion (no white line)."""
        return apply_styled_frame(QtWidgets.QFrame(), "CatalogFilterTray")

    def _configure_catalog_filter_controls(self) -> None:
        from gui_theme import CATALOG_FILTER_CONTROL_HEIGHT

        h = CATALOG_FILTER_CONTROL_HEIGHT
        for combo in (self.drv_view_filter, self.fw_view_filter):
            combo.setMinimumWidth(CATALOG_VIEW_FILTER_MIN_WIDTH)
            combo.setObjectName("CatalogFilterCombo")
            combo.setFixedHeight(h)
            apply_catalog_filter_control(combo)
        for edit in (self.drv_filter, self.fw_filter):
            edit.setObjectName("CatalogFilterSearch")
            edit.setFixedHeight(h)
            apply_catalog_filter_control(edit)
        for btn in (
            self.drv_btn_scan_devices,
            self.fw_btn_scan_components,
            self.drv_btn_check,
            self.fw_btn_check,
        ):
            btn.setFixedHeight(h)
            apply_styled_control(btn)
        for btn in (self.drv_btn_scan_devices, self.fw_btn_scan_components):
            btn.setMinimumWidth(CATALOG_LOAD_BTN_MIN_WIDTH)
        for btn in (self.drv_btn_check, self.fw_btn_check):
            btn.setMinimumWidth(CATALOG_SEARCH_BTN_MIN_WIDTH)

    def _apply_catalog_chrome_widgets(self) -> None:
        """Option 4 catalog chrome — per-widget QSS (native Windows style ignores global rules)."""
        import gui_theme as theme

        if theme.CATALOG_CHROME_OUTLINE < 4:
            return
        for combo in (getattr(self, "drv_view_filter", None), getattr(self, "fw_view_filter", None)):
            if combo is not None:
                combo.setStyleSheet(theme.catalog_filter_combo_stylesheet())
        for edit in (getattr(self, "drv_filter", None), getattr(self, "fw_filter", None)):
            if edit is not None:
                edit.setStyleSheet(theme.catalog_search_field_stylesheet())
        for tray in (
            getattr(self, "_drv_filter_tray", None),
            getattr(self, "_fw_filter_tray", None),
        ):
            if tray is not None:
                tray.setStyleSheet(theme.catalog_filter_tray_stylesheet())
        for pane in (
            getattr(self, "drv_summary_pane", None),
            getattr(self, "fw_summary_pane", None),
        ):
            if pane is not None:
                pane.setStyleSheet(theme.catalog_inspector_pane_stylesheet())
        for splitter in (
            getattr(self, "drv_v_splitter", None),
            getattr(self, "fw_v_splitter", None),
        ):
            if splitter is not None:
                splitter.setHandleWidth(UNIFIED_SPLITTER_HANDLE_WIDTH)
                splitter.setStyleSheet(theme.catalog_splitter_stylesheet())
        for table, name in (
            (getattr(self, "drv_unified_table", None), "CatalogUnifiedTable"),
            (getattr(self, "fw_unified_table", None), "CatalogUnifiedTable"),
            (getattr(self, "drv_compare_table", None), "CatalogCompareTable"),
            (getattr(self, "fw_compare_table", None), "CatalogCompareTable"),
        ):
            if table is not None:
                table.setObjectName(name)
                table.setStyleSheet(theme.catalog_table_stylesheet(name))

    def _catalog_packages_visible(self, kind: str) -> bool:
        section = (
            getattr(self, "drv_packages_section", None)
            if kind == "drivers"
            else getattr(self, "fw_packages_section", None)
        )
        return bool(section is not None and section.isVisible())

    def _expanded_catalog_splitter_sizes(self, kind: str) -> list[int]:
        cached = getattr(self, f"_{kind}_inspector_split_sizes", None)
        if isinstance(cached, list) and len(cached) == 2:
            return [int(cached[0]), int(cached[1])]
        saved = self._normalize_catalog_splitter_sizes(
            self._settings.get(CATALOG_SPLITTER_SETTINGS_KEY)
        )
        if saved:
            return saved
        preset = self._catalog_layout_preset()
        sizes = [int(n) for n in preset["splitter"]]  # type: ignore[index]
        if len(sizes) == 3:
            sizes = [sizes[0], sizes[1] + sizes[2]]
        return sizes

    def _apply_compact_catalog_splitter(self, splitter: QtWidgets.QSplitter) -> None:
        total = sum(splitter.sizes())
        if total <= 0:
            splitter.setSizes([480, UNIFIED_TAB_INSPECTOR_COMPACT_HEIGHT])
            return
        handles = splitter.handleWidth() * max(0, splitter.count() - 1)
        usable = max(total - handles, UNIFIED_TAB_SECTION_MIN_HEIGHT * 2)
        compact = UNIFIED_TAB_INSPECTOR_COMPACT_HEIGHT
        list_h = max(usable - compact, UNIFIED_TAB_LIST_PANEL_MIN_HEIGHT)
        splitter.blockSignals(True)
        splitter.setSizes([list_h, compact])
        splitter.blockSignals(False)

    def _sync_catalog_inspector_splitter(self, kind: str, *, expanded: bool) -> None:
        splitter = (
            getattr(self, "drv_v_splitter", None)
            if kind == "drivers"
            else getattr(self, "fw_v_splitter", None)
        )
        if splitter is None or splitter.count() < 2:
            return
        if expanded:
            sizes = self._expanded_catalog_splitter_sizes(kind)
            splitter.blockSignals(True)
            splitter.setSizes(sizes)
            splitter.blockSignals(False)
            setattr(self, f"_{kind}_inspector_split_sizes", list(splitter.sizes()))
        else:
            self._apply_compact_catalog_splitter(splitter)

    def _sync_catalog_tab_layout(self, active: str) -> None:
        """Mirror splitter and column widths between Drivers and Firmware tabs."""
        if active == "drivers":
            src_split, dst_split = self.drv_v_splitter, self.fw_v_splitter
            src_tbl, dst_tbl = self.drv_unified_table, self.fw_unified_table
            src_pkg, dst_pkg = self.drv_compare_table, self.fw_compare_table
        else:
            src_split, dst_split = self.fw_v_splitter, self.drv_v_splitter
            src_tbl, dst_tbl = self.fw_unified_table, self.drv_unified_table
            src_pkg, dst_pkg = self.fw_compare_table, self.drv_compare_table
        src_kind = active
        dst_kind = "firmware" if active == "drivers" else "drivers"
        if self._catalog_packages_visible(src_kind):
            sizes = src_split.sizes()
            if sizes and all(n >= UNIFIED_TAB_SECTION_MIN_HEIGHT for n in sizes):
                if self._catalog_packages_visible(dst_kind):
                    dst_split.blockSignals(True)
                    dst_split.setSizes(list(sizes))
                    dst_split.blockSignals(False)
                    self._settings[CATALOG_SPLITTER_SETTINGS_KEY] = list(sizes)
                else:
                    self._sync_catalog_inspector_splitter(dst_kind, expanded=False)
        elif not self._catalog_packages_visible(dst_kind):
            self._apply_compact_catalog_splitter(dst_split)
        for col in range(min(src_tbl.columnCount(), dst_tbl.columnCount())):
            width = src_tbl.columnWidth(col)
            if width >= 24:
                dst_tbl.setColumnWidth(col, width)
        for col in range(min(src_pkg.columnCount(), dst_pkg.columnCount())):
            width = src_pkg.columnWidth(col)
            if width >= 24:
                dst_pkg.setColumnWidth(col, width)

    def _bind_shared_catalog_table_columns(
        self,
        table: QtWidgets.QTableWidget,
        *,
        peer: QtWidgets.QTableWidget,
        settings_key: str,
    ) -> None:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(350)

        def _flush() -> None:
            widths = [table.columnWidth(c) for c in range(table.columnCount())]
            self._settings[settings_key] = widths
            for col, width in enumerate(widths):
                if col >= peer.columnCount() or width < 24:
                    continue
                if (
                    peer.horizontalHeader().sectionResizeMode(col)
                    == QtWidgets.QHeaderView.ResizeMode.Fixed
                ):
                    continue
                peer.setColumnWidth(col, width)
            self._save_app_settings()
            if settings_key == CATALOG_PACKAGE_COL_WIDTHS_KEY:
                self._fit_compare_package_columns(table)
                self._fit_compare_package_columns(peer)

        timer.timeout.connect(_flush)
        table.horizontalHeader().sectionResized.connect(lambda *args: timer.start())

    def _bind_shared_catalog_splitter_persist(
        self,
        splitter: QtWidgets.QSplitter,
        *,
        peer: QtWidgets.QSplitter,
        settings_key: str,
        kind: str,
    ) -> None:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(350)

        def _flush() -> None:
            if not self._catalog_packages_visible(kind):
                return
            sizes = list(splitter.sizes())
            self._settings[settings_key] = sizes
            setattr(self, f"_{kind}_inspector_split_sizes", sizes)
            if self._catalog_packages_visible(
                "firmware" if kind == "drivers" else "drivers"
            ):
                peer.blockSignals(True)
                peer.setSizes(sizes)
                peer.blockSignals(False)
            self._save_app_settings()

        timer.timeout.connect(_flush)
        splitter.splitterMoved.connect(lambda _pos, _index: timer.start())

    def _finalize_catalog_tabs_layout(self) -> None:
        """Wire shared layout persistence after both Drivers and Firmware tabs exist."""
        self._configure_catalog_filter_controls()
        for col in range(
            min(self.drv_unified_table.columnCount(), self.fw_unified_table.columnCount())
        ):
            width = self.drv_unified_table.columnWidth(col)
            if width >= 24:
                self.fw_unified_table.setColumnWidth(col, width)
        for col in range(
            min(self.drv_compare_table.columnCount(), self.fw_compare_table.columnCount())
        ):
            width = self.drv_compare_table.columnWidth(col)
            if width >= 24:
                self.fw_compare_table.setColumnWidth(col, width)
        self._fit_compare_package_columns(self.drv_compare_table)
        self._fit_compare_package_columns(self.fw_compare_table)
        self._bind_shared_catalog_table_columns(
            self.drv_unified_table,
            peer=self.fw_unified_table,
            settings_key=CATALOG_UNIFIED_COL_WIDTHS_KEY,
        )
        self._bind_shared_catalog_table_columns(
            self.fw_unified_table,
            peer=self.drv_unified_table,
            settings_key=CATALOG_UNIFIED_COL_WIDTHS_KEY,
        )
        self._bind_shared_catalog_table_columns(
            self.drv_compare_table,
            peer=self.fw_compare_table,
            settings_key=CATALOG_PACKAGE_COL_WIDTHS_KEY,
        )
        self._bind_shared_catalog_table_columns(
            self.fw_compare_table,
            peer=self.drv_compare_table,
            settings_key=CATALOG_PACKAGE_COL_WIDTHS_KEY,
        )
        self._bind_shared_catalog_splitter_persist(
            self.drv_v_splitter,
            peer=self.fw_v_splitter,
            settings_key=CATALOG_SPLITTER_SETTINGS_KEY,
            kind="drivers",
        )
        self._bind_shared_catalog_splitter_persist(
            self.fw_v_splitter,
            peer=self.drv_v_splitter,
            settings_key=CATALOG_SPLITTER_SETTINGS_KEY,
            kind="firmware",
        )

    def _catalog_layout_preset(self) -> dict:
        import gui_theme as theme

        key = str(
            self._settings.get(theme.CATALOG_LAYOUT_PRESET_KEY)
            or theme.CATALOG_LAYOUT_DEFAULT
        )
        return theme.CATALOG_LAYOUT_PRESETS.get(key) or theme.CATALOG_LAYOUT_PRESETS[
            theme.CATALOG_LAYOUT_DEFAULT
        ]

    def _catalog_layout_preset_id(self) -> str:
        import gui_theme as theme

        key = str(
            self._settings.get(theme.CATALOG_LAYOUT_PRESET_KEY)
            or theme.CATALOG_LAYOUT_DEFAULT
        )
        if key in theme.CATALOG_LAYOUT_PRESETS:
            return key
        return theme.CATALOG_LAYOUT_DEFAULT

    def _should_apply_preset_splitter(self) -> bool:
        import gui_theme as theme

        saved = self._settings.get(theme.CATALOG_SPLITTER_SETTINGS_KEY)
        if not isinstance(saved, list) or len(saved) != 3:
            return True
        try:
            sizes = tuple(int(n) for n in saved)
        except (TypeError, ValueError):
            return True
        return sizes == theme.CATALOG_LAYOUT_LEGACY_SPLITTER

    def _apply_startup_catalog_layout(self) -> None:
        """Ship 3C comfortable catalog layout + 12px content typography on first launch."""
        import gui_theme as theme

        preset_key = theme.CATALOG_LAYOUT_PRESET_KEY
        stored = self._settings.get(preset_key)
        preset_id = self._catalog_layout_preset_id()
        migrated = False
        if stored in (None, "", "current"):
            preset_id = theme.CATALOG_LAYOUT_DEFAULT
            self._settings[preset_key] = preset_id
            migrated = True
        apply_splitter = migrated or self._should_apply_preset_splitter()
        if apply_splitter and isinstance(
            self._settings.get(theme.CATALOG_SPLITTER_SETTINGS_KEY), list
        ):
            if tuple(self._settings[theme.CATALOG_SPLITTER_SETTINGS_KEY]) == (
                theme.CATALOG_LAYOUT_LEGACY_SPLITTER
            ):
                self._settings.pop(theme.CATALOG_SPLITTER_SETTINGS_KEY, None)
        self.apply_catalog_layout_preset(
            preset_id, persist=migrated, apply_splitter=apply_splitter
        )

    def _catalog_unified_row_heights(self) -> tuple[int, int]:
        preset = self._catalog_layout_preset()
        return int(preset["row_height"]), int(preset["row_height_dual"])

    def apply_catalog_layout_preset(
        self, preset_id: str, *, persist: bool = False, apply_splitter: bool = True
    ) -> None:
        """Apply a catalog tab layout preset (Drivers + Firmware). Preview via catalog_layout_preview.py."""
        import gui_theme as theme

        preset = theme.CATALOG_LAYOUT_PRESETS.get(preset_id)
        if not preset:
            return
        if persist:
            self._settings[theme.CATALOG_LAYOUT_PRESET_KEY] = preset_id
            self._save_app_settings()
        sizes = tuple(int(n) for n in preset["splitter"])  # type: ignore[index]
        if len(sizes) == 3:
            sizes = (sizes[0], sizes[1] + sizes[2])
        list_min = int(preset["list_panel_min"])
        table_min = int(preset["table_min_height"])
        for splitter, kind in (
            (getattr(self, "drv_v_splitter", None), "drivers"),
            (getattr(self, "fw_v_splitter", None), "firmware"),
        ):
            if splitter is not None and apply_splitter:
                if self._catalog_packages_visible(kind):
                    splitter.setSizes(list(sizes))
                    setattr(self, f"_{kind}_inspector_split_sizes", list(sizes))
                else:
                    self._apply_compact_catalog_splitter(splitter)
        pairs = (
            (getattr(self, "drv_unified_table", None), getattr(self, "drv_v_splitter", None)),
            (getattr(self, "fw_unified_table", None), getattr(self, "fw_v_splitter", None)),
        )
        for table, splitter in pairs:
            if table is not None:
                table.setMinimumHeight(table_min)
                icw = preset.get("installed_col_width")
                if icw is not None and table.columnCount() > DRV_COL_INSTALLED:
                    installed_col = (
                        FW_COL_INSTALLED
                        if table is getattr(self, "fw_unified_table", None)
                        else DRV_COL_INSTALLED
                    )
                    table.setColumnWidth(installed_col, int(icw))
            if splitter is not None and splitter.widget(0) is not None:
                splitter.widget(0).setMinimumHeight(list_min)
        if hasattr(self, "drv_unified_table"):
            hdr = self.drv_unified_table.verticalHeader()
            single, _dual = self._catalog_unified_row_heights()
            hdr.setDefaultSectionSize(single)
            hdr.setMinimumSectionSize(single)
        if hasattr(self, "fw_unified_table"):
            hdr = self.fw_unified_table.verticalHeader()
            single, _dual = self._catalog_unified_row_heights()
            hdr.setDefaultSectionSize(single)
            hdr.setMinimumSectionSize(single)
        self._apply_catalog_tab_typography(preset)

    def _apply_catalog_tab_typography(self, preset: dict) -> None:
        fs = int(preset.get("catalog_font_size") or 13)
        tfs = int(preset.get("catalog_title_font_size") or 14)
        hh = int(preset.get("header_height") or UNIFIED_TABLE_HEADER_HEIGHT)
        # Font sizes only — never set card QSS on QTableWidget (drops Option 4 chrome).
        ctrl_font = QtGui.QFont()
        ctrl_font.setPixelSize(fs)
        title_font = QtGui.QFont()
        title_font.setPixelSize(tfs)
        title_font.setWeight(QtGui.QFont.Weight.DemiBold)
        for card in (
            getattr(self, "_drv_catalog_card", None),
            getattr(self, "_fw_catalog_card", None),
        ):
            if card is not None:
                for cls in (
                    QtWidgets.QComboBox,
                    QtWidgets.QLineEdit,
                    QtWidgets.QPushButton,
                ):
                    for widget in card.findChildren(cls):
                        widget.setFont(ctrl_font)
                for widget in card.findChildren(QtWidgets.QLabel):
                    if widget.objectName() == "CardTitle":
                        widget.setFont(title_font)
                    elif widget.objectName() == "Muted":
                        widget.setFont(ctrl_font)
        for table in (
            getattr(self, "drv_unified_table", None),
            getattr(self, "fw_unified_table", None),
        ):
            if table is not None:
                table.setFont(ctrl_font)
                table.horizontalHeader().setFixedHeight(hh)

    @staticmethod
    def _normalize_catalog_splitter_sizes(raw: object) -> list[int] | None:
        """Two-pane catalog split; fold legacy 3-pane saved sizes into list + inspector."""
        if not isinstance(raw, list) or not raw:
            return None
        try:
            sizes = [int(n) for n in raw]
        except (TypeError, ValueError):
            return None
        if len(sizes) == 2:
            return sizes
        if len(sizes) == 3:
            return [sizes[0], sizes[1] + sizes[2]]
        return None

    def _configure_catalog_tab_splitter(
        self, splitter: QtWidgets.QSplitter, *, settings_key: str
    ) -> None:
        splitter.setObjectName("CatalogTabSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(UNIFIED_SPLITTER_HANDLE_WIDTH)
        splitter.setOpaqueResize(True)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        self._apply_compact_catalog_splitter(splitter)

    def _bind_catalog_splitter_persist(
        self, splitter: QtWidgets.QSplitter, *, settings_key: str
    ) -> None:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(350)

        def _flush() -> None:
            self._settings[settings_key] = list(splitter.sizes())
            self._save_app_settings()

        timer.timeout.connect(_flush)
        splitter.splitterMoved.connect(lambda _pos, _index: timer.start())

    def _restore_table_column_widths(
        self, table: QtWidgets.QTableWidget, settings_key: str
    ) -> None:
        from gui_theme import DRV_COL_INSTALLED, UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE

        saved = self._settings.get(settings_key)
        if not isinstance(saved, list):
            return
        for col, width in enumerate(saved):
            if col >= table.columnCount():
                break
            if not isinstance(width, int) or width < 24:
                continue
            if (
                settings_key == CATALOG_UNIFIED_COL_WIDTHS_KEY
                and col == DRV_COL_INSTALLED
                and width < UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE
            ):
                width = UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE
            if (
                table.horizontalHeader().sectionResizeMode(col)
                == QtWidgets.QHeaderView.ResizeMode.Fixed
            ):
                continue
            if settings_key == CATALOG_PACKAGE_COL_WIDTHS_KEY and table.columnCount() == 3:
                hdr0 = table.horizontalHeaderItem(0)
                if hdr0 and (hdr0.text() or "").strip() == "Compare" and col == 1:
                    viewport_w = max(table.viewport().width(), 160)
                    w0 = max(table.columnWidth(0), 72)
                    width = min(width, max(72, viewport_w - w0 - 100))
            table.setColumnWidth(col, width)

    def _bind_table_column_width_persist(
        self, table: QtWidgets.QTableWidget, *, settings_key: str
    ) -> None:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(350)

        def _flush() -> None:
            widths = [table.columnWidth(c) for c in range(table.columnCount())]
            self._settings[settings_key] = widths
            self._save_app_settings()

        timer.timeout.connect(_flush)
        table.horizontalHeader().sectionResized.connect(lambda *args: timer.start())
