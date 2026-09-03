"""Firmware tab, SSD inventory, firmware catalog checks."""
from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiFirmwareMixin:


    def _populate_firmware_tab(self, *, load_support_links: bool = True) -> None:
        prof = self._hardware_profile
        if not prof:
            return
        self._refresh_unified_firmware_table(prof)
        self._update_fw_tab_summary_line()
        self._sync_fw_workflow_buttons()
        if self.fw_unified_table.rowCount():
            self.fw_unified_table.selectRow(0)
            QtCore.QTimer.singleShot(0, self._on_fw_unified_selection)
        if load_support_links:
            self._schedule_firmware_support_links_refresh()

    def _schedule_firmware_support_links_when_idle(self) -> None:
        """Defer only while catalog-context lookup is already running."""
        if self._shutting_down:
            return
        if self._ctx_thread and self._ctx_thread.isRunning():
            QtCore.QTimer.singleShot(2000, self._schedule_firmware_support_links_when_idle)
            return
        self._schedule_firmware_support_links_refresh()

    def _apply_firmware_support_links(self, ctx: dict) -> None:
        import gui_theme as theme

        links = []
        for item in fwcat.get_firmware_support_links(ctx):
            url = self._esc(item.get("url", ""))
            label = self._esc(item.get("label", "Support"))
            links.append(f'<a href="{url}" style="color:{theme.ACCENT}">{label}</a>')
        support_text = "Support: " + " · ".join(links) if links else ""
        self.fw_support_links.setText(support_text)
        self.fw_support_links.setVisible(bool(links))

    def _schedule_firmware_support_links_refresh(self) -> None:
        if self._shutting_down:
            return
        prof = self._hardware_profile
        if not prof:
            if hasattr(self, "fw_support_links"):
                self.fw_support_links.setVisible(False)
            return
        ctx = dict(prof.get("system_ctx") or {})
        if self._catalog_ctx_is_complete(ctx):
            self._apply_firmware_support_links(ctx)
            return
        self._schedule_catalog_context_enrichment(quiet=False)

    @QtCore.Slot(object)
    def _on_catalog_context_ready(self, ctx: object) -> None:
        if self._shutting_down or not isinstance(ctx, dict):
            return
        prof = self._hardware_profile
        if prof is not None:
            merged = dict(prof.get("system_ctx") or {})
            merged.update(ctx)
            prof["system_ctx"] = merged
            self._bind_catalog_from_profile()
        self._apply_firmware_support_links(ctx)

    @QtCore.Slot(str)
    def _on_catalog_context_failed(self, err: str) -> None:
        if self._shutting_down:
            return
        self.fw_support_links.setText("Support links unavailable (hardware query failed).")
        self.fw_support_links.setVisible(True)
        self.statusBar().showMessage(f"Firmware support links: {err[:80]}", 6000)

    def _cleanup_catalog_context_thread(self) -> None:
        self._ctx_thread = None
        self._ctx_worker = None

    def _focus_firmware_tab(self) -> None:
        if hasattr(self, "_firmware_tab_widget"):
            idx = self.tabs.indexOf(self._firmware_tab_widget)
            if idx >= 0:
                self.tabs.setCurrentIndex(idx)
                prof = self._hardware_profile
                if prof:
                    self._populate_firmware_tab()

    def _build_firmware_tab(self) -> QtWidgets.QWidget:
        tab, outer = self._new_fill_tab()
        self._firmware_tab_widget = tab

        card = apply_styled_frame(QtWidgets.QFrame(), "Card")
        self._fw_catalog_card = card
        card.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        title = QtWidgets.QLabel("Firmware updates")
        title.setObjectName("CardTitle")
        lay.addWidget(title)

        self.fw_scan_status = QtWidgets.QLabel(
            "① Load components, then ② Search for updates — download-only, never auto-flashes."
        )
        self.fw_scan_status.setObjectName("Muted")
        self.fw_scan_status.setWordWrap(True)
        self.fw_scan_status.setMinimumHeight(22)
        self.fw_scan_status.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        # fw_scan_status lives inside the component-list splitter pane (see below).
        self.fw_workflow_banner = QtWidgets.QLabel("")
        self.fw_components_heading = QtWidgets.QLabel("")
        self.fw_list_count_label = QtWidgets.QLabel("")

        self.fw_view_filter = QtWidgets.QComboBox()
        self.fw_view_filter.setObjectName("CatalogFilterCombo")
        for label, key in (
            ("All components", "all"),
            ("Needs attention", "log_attention"),
            ("Updates available", "updates"),
            ("Verify manually", "uncertain"),
            ("Secondary (USB / PnP)", "secondary"),
        ):
            self.fw_view_filter.addItem(label, key)
        fw_all_idx = self.fw_view_filter.findData("all")
        if fw_all_idx >= 0:
            self.fw_view_filter.setCurrentIndex(fw_all_idx)
        self.fw_view_filter.setToolTip(
            "All components: BIOS, SSD, and USB/peripheral firmware rows.\n"
            "Run Analysis or ① Load components fills this list.\n"
            "Needs attention: crash-related rows — all visible included in search.\n"
            "Updates available: newer package found after Search.\n"
            "Verify manually: components we couldn't confirm automatically — open the "
            "vendor page to check these yourself.\n"
            "Secondary: USB peripherals and Windows FIRMWARE-class devices — "
            "unchecked by default; include when searching if desired."
        )
        self.fw_view_filter.currentIndexChanged.connect(self._on_fw_filter_changed)
        self.fw_filter = QtWidgets.QLineEdit()
        self.fw_filter.setObjectName("CatalogFilterSearch")
        self.fw_filter.setPlaceholderText("Search by name…")
        self.fw_filter.textChanged.connect(self._on_fw_filter_changed)
        self._fw_filter_tray = self._build_catalog_filter_tray()
        fw_filter_tray = self._fw_filter_tray
        fw_filter_tray_lay = QtWidgets.QHBoxLayout(fw_filter_tray)
        fw_filter_tray_lay.setContentsMargins(8, 8, 8, 8)
        fw_filter_tray_lay.setSpacing(8)
        fw_filter_tray_lay.addWidget(self.fw_view_filter)
        fw_filter_tray_lay.addWidget(self.fw_filter, 1)
        self.fw_btn_scan_components = QtWidgets.QPushButton(BTN_FW_LOAD)
        self.fw_btn_scan_components.setObjectName("Primary")
        self.fw_btn_scan_components.setToolTip(
            "Step 1 — load BIOS, SSD, and USB peripheral firmware inventory. "
            "Runs a hardware scan first if needed. Does not check for updates."
        )
        fw_filter_tray_lay.addWidget(self.fw_btn_scan_components)
        self.fw_btn_check = QtWidgets.QPushButton(BTN_FW_SEARCH)
        self.fw_btn_check.setToolTip(
            "Step 2 — look up download pages for included components. "
            "Available after ① Load components finishes."
        )
        self.fw_btn_check.setEnabled(False)
        fw_filter_tray_lay.addWidget(self.fw_btn_check)

        self.fw_v_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.fw_v_splitter.setObjectName("CatalogTabSplitter")
        self.fw_v_splitter.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        fw_list_panel = QtWidgets.QWidget()
        fw_list_panel.setMinimumHeight(UNIFIED_TAB_LIST_PANEL_MIN_HEIGHT)
        fw_list_lay = QtWidgets.QVBoxLayout(fw_list_panel)
        fw_list_lay.setContentsMargins(0, 0, 0, 0)
        fw_list_lay.setSpacing(6)
        fw_list_lay.addWidget(self.fw_scan_status)
        fw_list_lay.addWidget(fw_filter_tray)

        self.fw_unified_table = QtWidgets.QTableWidget(0, 5)
        self.fw_unified_table.setHorizontalHeaderLabels(
            ["", "", "Component", "Installed", "Status"]
        )
        self._configure_fw_unified_columns(self.fw_unified_table)
        self._restore_table_column_widths(self.fw_unified_table, CATALOG_UNIFIED_COL_WIDTHS_KEY)
        self._apply_fw_include_column_visibility()
        self._fw_include_header = inc_hdr.IncludeHeaderCheckbox(
            self.fw_unified_table,
            FW_COL_CHECK,
            tooltip="Include all visible components when searching for updates",
        )
        self._fw_include_header.include_all_changed.connect(
            self._on_fw_include_header_changed
        )
        self.fw_unified_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.fw_unified_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.fw_unified_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._apply_unified_catalog_table_style(self.fw_unified_table)
        self.fw_unified_table.setMinimumHeight(UNIFIED_TABLE_MIN_LIST_HEIGHT)
        self.fw_unified_table.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.fw_unified_table.verticalHeader().setVisible(False)
        self.fw_unified_table.setIconSize(
            QtCore.QSize(UNIFIED_TABLE_ICON_SIZE, UNIFIED_TABLE_ICON_SIZE)
        )
        self.fw_unified_table.itemSelectionChanged.connect(self._on_fw_unified_selection)
        self.fw_unified_table.cellClicked.connect(self._on_fw_cell_clicked)
        self.fw_unified_table.itemChanged.connect(self._on_fw_include_item_changed)
        self._fw_table_fill_block = False
        fw_list_lay.addWidget(self.fw_unified_table, 1)
        self.fw_v_splitter.addWidget(fw_list_panel)

        self.fw_summary_pane = apply_styled_frame(QtWidgets.QFrame(), "CatalogInspectorPane")
        self.fw_summary_pane.setMinimumHeight(UNIFIED_TAB_SECTION_MIN_HEIGHT)
        fw_summary_lay = QtWidgets.QVBoxLayout(self.fw_summary_pane)
        fw_summary_lay.setContentsMargins(8, 6, 8, 6)
        fw_summary_lay.setSpacing(4)

        fw_insp_head = QtWidgets.QHBoxLayout()
        self.fw_insp_icon = QtWidgets.QLabel()
        self.fw_insp_icon.setFixedSize(
            UNIFIED_TABLE_INSP_ICON_SIZE, UNIFIED_TABLE_INSP_ICON_SIZE
        )
        self.fw_insp_icon.setScaledContents(False)
        self.fw_insp_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        fw_insp_head.addWidget(self.fw_insp_icon)
        fw_head_text = QtWidgets.QVBoxLayout()
        fw_head_text.setSpacing(2)
        self.fw_insp_title = QtWidgets.QLabel("Select a component above")
        self.fw_insp_title.setObjectName("CardTitle")
        self.fw_insp_title.setWordWrap(True)
        fw_head_text.addWidget(self.fw_insp_title)
        self.fw_insp_subtitle = QtWidgets.QLabel(
            "Packages appear after you search for firmware updates."
        )
        self.fw_insp_subtitle.setObjectName("Muted")
        self.fw_insp_subtitle.setWordWrap(True)
        self.fw_insp_subtitle.setMaximumHeight(UNIFIED_TABLE_SUBTITLE_MAX_HEIGHT)
        fw_head_text.addWidget(self.fw_insp_subtitle)
        fw_insp_head.addLayout(fw_head_text, 1)
        self.fw_insp_details_btn = QtWidgets.QToolButton()
        self.fw_insp_details_btn.setText("Details")
        self.fw_insp_details_btn.setCheckable(True)
        self.fw_insp_details_btn.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.fw_insp_details_btn.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        self.fw_insp_details_btn.toggled.connect(self._toggle_fw_insp_details)
        self.fw_insp_details_btn.hide()
        fw_insp_head.addWidget(self.fw_insp_details_btn, 0, QtCore.Qt.AlignTop)
        fw_summary_lay.addLayout(fw_insp_head)

        self.fw_insp_details_widget = QtWidgets.QWidget()
        fw_details_lay = QtWidgets.QVBoxLayout(self.fw_insp_details_widget)
        fw_details_lay.setContentsMargins(0, 0, 0, 0)
        fw_meta_grid = QtWidgets.QGridLayout()
        fw_meta_grid.setHorizontalSpacing(16)
        fw_meta_grid.setVerticalSpacing(4)
        self._fw_insp_fields: dict[str, QtWidgets.QLabel] = {}
        for i, (key, label) in enumerate(
            (
                ("kind", "Type"),
                ("installed", "Installed version"),
                ("notes", "Notes"),
                ("crash", "Crash link"),
            )
        ):
            k = QtWidgets.QLabel(label)
            k.setObjectName("Muted")
            v = QtWidgets.QLabel("—")
            v.setWordWrap(True)
            v.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            fw_meta_grid.addWidget(k, i // 2, (i % 2) * 2)
            fw_meta_grid.addWidget(v, i // 2, (i % 2) * 2 + 1)
            self._fw_insp_fields[key] = v
        fw_details_lay.addLayout(fw_meta_grid)
        self.fw_insp_details_widget.hide()
        fw_summary_lay.addWidget(self.fw_insp_details_widget)

        self.fw_packages_heading = QtWidgets.QLabel("Available packages")
        self.fw_packages_heading.setObjectName("SectionHeading")
        fw_summary_lay.addWidget(self.fw_packages_heading)
        self.fw_hint = QtWidgets.QPlainTextEdit()
        self.fw_hint.setReadOnly(True)
        self.fw_hint.setObjectName("CatalogHint")
        self.fw_hint.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.fw_hint.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.fw_hint.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.fw_hint.setMaximumHeight(UNIFIED_TABLE_HINT_MAX_HEIGHT)
        self.fw_hint.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.fw_hint.hide()
        fw_summary_lay.addWidget(self.fw_hint)
        self.fw_support_links = QtWidgets.QLabel("")
        self.fw_support_links.setWordWrap(True)
        self.fw_support_links.setOpenExternalLinks(True)
        self.fw_support_links.setObjectName("Muted")
        self.fw_support_links.hide()
        fw_summary_lay.addWidget(self.fw_support_links)

        self.fw_compare_table = QtWidgets.QTableWidget(0, 3)
        self.fw_compare_table.setHorizontalHeaderLabels(
            ["Compare", "Source", "Package"]
        )
        self._configure_driver_package_columns(
            self.fw_compare_table, compare_table=True
        )
        self._restore_table_column_widths(self.fw_compare_table, CATALOG_PACKAGE_COL_WIDTHS_KEY)
        self._fit_compare_package_columns(self.fw_compare_table)
        self.fw_compare_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.fw_compare_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.fw_compare_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.fw_compare_table.setWordWrap(True)
        self.fw_compare_table.setMinimumHeight(UNIFIED_TABLE_MIN_COMPARE_HEIGHT)
        self.fw_compare_table.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        self._apply_compare_table_style(self.fw_compare_table)
        fw_summary_lay.addWidget(self.fw_compare_table, 1)
        self.fw_compare_table.hide()
        self.fw_packages_section = self.fw_compare_table
        self.fw_v_splitter.addWidget(self.fw_summary_pane)

        self.fw_btn_download = QtWidgets.QPushButton("Open download page")
        self.fw_btn_download.setEnabled(False)
        self.fw_btn_set_installed = QtWidgets.QPushButton("Set installed firmware…")
        self.fw_btn_set_installed.setEnabled(False)
        self.fw_btn_set_installed.setToolTip(
            "Save the MCU firmware version you confirmed in a vendor updater "
            "(used for USB peripherals when Windows only reports the HID driver)."
        )

        lay.addWidget(self._build_catalog_tab_progress_row("fw"))
        self._configure_catalog_tab_splitter(
            self.fw_v_splitter, settings_key=CATALOG_SPLITTER_SETTINGS_KEY
        )
        lay.addWidget(self.fw_v_splitter, 1)

        self.fw_inspector_frame = self.fw_summary_pane  # legacy alias

        self.fw_btn_scan_components.clicked.connect(self._on_scan_for_components)
        self.fw_btn_check.clicked.connect(self._on_check_firmware_catalog)
        self.fw_btn_download.clicked.connect(self._on_download_selected_firmware)
        self.fw_btn_set_installed.clicked.connect(self._on_fw_set_user_installed)
        self.fw_compare_table.itemSelectionChanged.connect(self._on_fw_compare_selection_changed)

        self._apply_fw_include_column_visibility()
        self._finalize_catalog_tabs_layout()
        outer.addWidget(card, 1)
        return tab
