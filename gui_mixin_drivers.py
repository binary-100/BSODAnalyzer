"""Hardware profile, driver list/table, drivers tab population."""
from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiDriversMixin:
    def _drv_tables(self) -> list[QtWidgets.QTableWidget]:
        return [self.drv_unified_table]

    def _drv_status_column(self, table: QtWidgets.QTableWidget) -> int:
        return DRV_COL_STATUS

    def _has_crash_faulting_driver(self) -> bool:
        """Faulting module from the newest minidump analysis (model driver field)."""
        return core.has_crash_faulting_driver((self._last_model or {}).get("driver"))

    def _dev_needs_analysis_attention(self, dev: dict) -> bool:
        """Needs attention = devices explicitly tied to the crash report only."""
        return bool(dev.get("_crash_linked"))

    def _culprit_device_names(self, prof: dict) -> set[str]:
        if not self._has_crash_analysis_context():
            return set()
        m = self._last_model or {}
        bio = (prof or {}).get("bios_driver_info") or m.get("bios_driver_info") or {}
        ctx = (prof or self._hardware_profile or {}).get("system_ctx") or m.get("system_ctx") or {}
        resolved = core.resolve_crash_culprit_context(
            m.get("driver"),
            bio,
            code_val=m.get("stop_code_val"),
            system_ctx=ctx,
            cause_type=m.get("cause_type"),
            fix_plan=m.get("fix_plan"),
            has_crash_context=True,
        )
        return set(resolved["culprit_device_names"])

    def _sync_device_from_catalog_entry(
        self, dev: dict, entry: dict | None
    ) -> None:
        if not entry:
            return
        dev.update(drvlist._scan_metadata_from_entry(entry))
        offers = entry.get("offers")
        bio = (self._hardware_profile or {}).get("bios_driver_info") or {}
        inv = core.device_inventory_for_matching(bio)
        drvcat.attach_all_dual_version_profiles(dev, offers=offers, inventory=inv)
        if dev.get("_tier") == "culprit":
            return
        if dev.get("_check_status") == "newer":
            dev["_tier"] = "outdated"
        elif dev.get("_tier") == "outdated":
            dev["_tier"] = "normal"

    def _prepare_culprit_include_defaults(self, prof: dict) -> None:
        if not self._has_crash_faulting_driver():
            return
        culprits = self._culprit_device_names(prof)
        for dev in self._drv_unified_cache:
            n = (dev.get("name") or "").strip()
            if n and n.lower() in culprits:
                self._drv_check_excluded.discard(n)

    def _hardware_inventory_ready(self) -> bool:
        prof = self._hardware_profile
        if not prof:
            return False
        if self._full_driver_rows(prof):
            return True
        bio = prof.get("bios_driver_info") or {}
        return bool(core.device_inventory_for_matching(bio))

    def _needs_hardware_profile_scan(self) -> tuple[bool, str]:
        """Whether a WMI hardware scan must run before driver update search."""
        if not self._hardware_profile:
            return True, "loading hardware inventory"
        if not app_set.is_full_install_mode(self._settings):
            if self._session_hw_inventory_ready and self._hardware_inventory_ready():
                return False, ""
            return True, "refreshing hardware inventory for this session"
        if not hwcache.is_cache_fresh(settings=self._settings):
            days = hwcache.max_age_days(self._settings)
            return True, f"device list is older than {days} day(s)"
        if (
            self._session_hw_inventory_ready
            and self._all_devices_loaded
            and self._hardware_inventory_ready()
        ):
            return False, ""
        if hwcache.live_hardware_changed_since_cache(profile=self._hardware_profile):
            return True, "hardware or BIOS changed since last save"
        if not self._hardware_inventory_ready():
            return True, "device inventory is incomplete"
        return False, ""

    def _can_search_drivers_without_full_list(self) -> bool:
        """True when catalog search can run without loading every WMI device row."""
        if self._drv_checked_device_names():
            if self._drv_unified_cache:
                return True
            prof = self._hardware_profile
            if prof and core.device_inventory_for_matching(
                prof.get("bios_driver_info") or {}
            ):
                return True
        if not self._has_crash_analysis_context():
            prof = self._hardware_profile
            if prof and core.device_inventory_for_matching(
                prof.get("bios_driver_info") or {}
            ):
                return True
        return False

    def _drivers_tab_index(self) -> int:
        if not hasattr(self, "_drivers_tab_widget"):
            return -1
        return self.tabs.indexOf(self._drivers_tab_widget)

    def _driver_list_looks_full(self, rows: list, prof: dict | None) -> bool:
        """True when rows look like a full WMI inventory, not analysis-time subset."""
        if len(rows) < 5:
            return False
        bio = (prof or {}).get("bios_driver_info") or {}
        inv = bio.get("device_inventory") or bio.get("drivers") or []
        if inv and len(rows) <= max(len(inv), 12):
            return False
        return True

    def _sync_full_driver_inventory_flags(self, prof: dict | None = None) -> None:
        """Mark session ready when Run Analysis or Load devices supplied a full WMI list."""
        profile = prof or self._hardware_profile
        rows = self._session_all_drivers
        if not rows and profile:
            rows = self._full_driver_rows(profile)
        if rows and self._driver_list_looks_full(rows, profile):
            self._all_devices_loaded = True
            self._session_hw_inventory_ready = True

    def _drv_any_device_rows(self) -> bool:
        return any(t.rowCount() > 0 for t in self._drv_tables())

    def _fw_row_for_key(self, key: str) -> int:
        for row in range(self.fw_unified_table.rowCount()):
            item = self.fw_unified_table.item(row, FW_COL_COMPONENT)
            if item and str(item.data(QtCore.Qt.UserRole) or "") == key:
                return row
        return -1

    def _populate_drivers_tab(self) -> None:
        try:
            self._populate_drivers_tab_impl()
        except Exception as exc:  # noqa: BLE001
            import traceback

            if hasattr(self, "drv_scan_status"):
                self.drv_scan_status.setText(f"Drivers tab error: {exc}")
            self.statusBar().showMessage(
                f"Drivers tab update failed: {str(exc)[:80]}", 10000
            )
            _ = traceback.format_exc()

    def _update_drivers_tab_status_only(self, prof: dict) -> None:
        """Lightweight Drivers tab status — no Qt table build."""
        if not hasattr(self, "drv_scan_status"):
            return
        bio = prof.get("bios_driver_info") or {}
        inv_n = len(core.device_inventory_for_matching(bio))
        all_n = len(self._full_driver_rows(prof))
        parts: list[str] = []
        if all_n:
            parts.append(f"{all_n} device(s) loaded in memory")
        elif inv_n:
            parts.append(f"{inv_n} device(s) from analysis")
        if self._drv_all_load_thread and self._drv_all_load_thread.isRunning():
            parts.append("full list still loading")
        elif not self._all_devices_loaded:
            parts.append("run ① Load devices on the Drivers tab")
        self.drv_scan_status.setText(" · ".join(parts))
        if hasattr(self, "drv_hint"):
            self._set_catalog_hint(
                self.drv_hint,
                "Step 1: ① Load devices. Step 2: check Include, then ② Search for updates.",
            )

    def _populate_drivers_tab_impl(self) -> None:
        prof = self._hardware_profile
        if not prof:
            if hasattr(self, "drv_unified_table"):
                self.drv_unified_table.setRowCount(0)
            if hasattr(self, "drv_scan_status"):
                if app_set.is_full_install_mode(self._settings):
                    self.drv_scan_status.setText(
                        "Use Search for driver updates or wait for the saved list to load."
                    )
                else:
                    self.drv_scan_status.setText(
                        "Portable — use Search for driver updates on the Drivers tab."
                    )
            self._update_drivers_tab_cache_status()
            return
        if not self._drivers_tab_is_active():
            self._drv_tab_ui_stale = True
            self._update_drivers_tab_status_only(prof)
            return
        self._refresh_unified_driver_table(
            prof, on_ready=lambda: self._finish_drivers_tab_status_ui(prof)
        )

    def _finish_drivers_tab_status_ui(self, prof: dict) -> None:
        if self._shutting_down or prof is not self._hardware_profile:
            return
        if self._ensure_drivers_tab_visible_rows(prof):
            self._sync_drv_unified_table(
                on_complete=lambda: self._finish_drivers_tab_status_ui(prof)
            )
            return
        if getattr(self, "_pending_driver_search_after_tab_ready", False):
            self._pending_driver_search_after_tab_ready = False
            QtCore.QTimer.singleShot(100, self._continue_driver_search_after_tab_ready)
        if getattr(self, "_pending_auto_crash_linked_catalog", None):
            QtCore.QTimer.singleShot(200, self._flush_pending_auto_crash_linked_catalog)
        gen = prof.get("devices_with_generic_driver") or []
        probs = prof.get("devices_with_driver_problems") or []
        shown_n = len(self._drv_table_display)
        cache_n = len(self._drv_unified_cache)
        culprit_n = sum(
            1 for d in self._drv_unified_cache if self._dev_needs_analysis_attention(d)
        )
        outdated_n = sum(
            1
            for d in self._drv_unified_cache
            if d.get("_scan_verified") and d.get("_check_status") == "newer"
        )

        self._update_drv_tab_summary_line(prof)
        self._sync_driver_workflow_buttons()
        self._drv_tab_ui_stale = False
        if (
            self.drv_unified_table.rowCount() > 0
            and not self._drv_table_sync_active
        ):
            first = self._drv_first_selectable_row()
            if first >= 0:
                self.drv_unified_table.setCurrentCell(first, DRV_COL_DEVICE)
        if not shown_n:
            self._set_catalog_hint(
                self.drv_hint,
                "No devices found. Use Search for driver updates, or use the System tab for vendor links.",
            )
        else:
            self._set_catalog_hint(self.drv_hint, "")
        self._refresh_system_restore_button()
        self._end_drv_list_build_progress_if_owned()

    def _end_drv_list_build_progress_if_owned(self) -> None:
        if not getattr(self, "_drv_list_build_owns_progress", False):
            return
        self._drv_list_build_owns_progress = False
        if getattr(self, "_task_progress_depth", 0) > 0:
            self._end_task_progress()

    def _build_drivers_tab(self) -> QtWidgets.QWidget:
        tab, outer = self._new_fill_tab()
        self._drivers_tab_widget = tab

        card = apply_styled_frame(QtWidgets.QFrame(), "Card")
        self._drv_catalog_card = card
        card.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        card_lay = QtWidgets.QVBoxLayout(card)
        card_lay.setContentsMargins(12, 10, 12, 12)
        card_lay.setSpacing(8)

        title = QtWidgets.QLabel("Driver updates")
        title.setObjectName("CardTitle")
        card_lay.addWidget(title)

        self.drv_scan_status = QtWidgets.QLabel(
            "① Load devices, then ② Search for updates — no crash analysis required."
        )
        self.drv_scan_status.setObjectName("Muted")
        self.drv_scan_status.setWordWrap(True)
        self.drv_scan_status.setMinimumHeight(22)
        self.drv_scan_status.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        self.drv_scan_status.setToolTip(
            "Hover for full inventory stats, cache ages, and workflow help."
        )
        # drv_scan_status is placed inside the device-list splitter pane (see below).

        self.drv_view_filter = QtWidgets.QComboBox()
        self.drv_view_filter.setObjectName("CatalogFilterCombo")
        for label, key in (
            ("All devices", "all"),
            ("Needs attention", "log_attention"),
            ("Updates available", "updates"),
            ("Verify manually", "uncertain"),
        ):
            self.drv_view_filter.addItem(label, key)
        all_idx = self.drv_view_filter.findData("all")
        if all_idx >= 0:
            self.drv_view_filter.setCurrentIndex(all_idx)
        self.drv_view_filter.setToolTip(
            "All devices: every installed driver (run ① Load devices first).\n"
            "Needs attention: crash-linked devices only (after Run Analysis names a driver).\n"
            "Updates available: devices where Search found a newer package.\n"
            "Verify manually: devices we couldn't confirm automatically (conflicting or "
            "unverifiable version signals) — open the vendor page to check these yourself."
        )
        self.drv_view_filter.currentIndexChanged.connect(self._on_drv_filter_changed)
        self.drv_filter = QtWidgets.QLineEdit()
        self.drv_filter.setObjectName("CatalogFilterSearch")
        self.drv_filter.setPlaceholderText("Search by name…")
        self.drv_filter.textChanged.connect(self._on_drv_filter_changed)
        self._drv_filter_tray = self._build_catalog_filter_tray()
        drv_filter_tray = self._drv_filter_tray
        drv_filter_tray_lay = QtWidgets.QHBoxLayout(drv_filter_tray)
        drv_filter_tray_lay.setContentsMargins(8, 8, 8, 8)
        drv_filter_tray_lay.setSpacing(8)
        drv_filter_tray_lay.addWidget(self.drv_view_filter)
        drv_filter_tray_lay.addWidget(self.drv_filter, 1)
        self.drv_btn_scan_devices = QtWidgets.QPushButton(BTN_DRV_LOAD)
        self.drv_btn_scan_devices.setObjectName("Primary")
        self.drv_btn_scan_devices.setToolTip(
            "Step 1 — query Windows (WMI) for every installed driver device. "
            "Does not check for updates."
        )
        drv_filter_tray_lay.addWidget(self.drv_btn_scan_devices)
        self.drv_btn_check = QtWidgets.QPushButton(BTN_DRV_SEARCH)
        self.drv_btn_check.setToolTip(
            "Step 2 — check manufacturer, OEM, and Microsoft catalogs for included devices. "
            "Available after ① Load devices finishes."
        )
        self.drv_btn_check.setEnabled(False)
        drv_filter_tray_lay.addWidget(self.drv_btn_check)

        self.drv_v_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.drv_v_splitter.setObjectName("CatalogTabSplitter")
        self.drv_v_splitter.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        list_panel = QtWidgets.QWidget()
        list_panel.setMinimumHeight(UNIFIED_TAB_LIST_PANEL_MIN_HEIGHT)
        list_lay = QtWidgets.QVBoxLayout(list_panel)
        list_lay.setContentsMargins(0, 0, 0, 0)
        list_lay.setSpacing(6)
        list_lay.addWidget(self.drv_scan_status)
        list_lay.addWidget(drv_filter_tray)

        self.drv_unified_table = QtWidgets.QTableWidget(0, 5)
        self.drv_unified_table.setHorizontalHeaderLabels(
            ["", "", "Device", "Installed", "Status"]
        )
        self._configure_drv_unified_columns(self.drv_unified_table)
        # _v2 key: the old key stored widths from when Status was the stretched
        # last column (Status ~678px, Device ~240px). Bumping the key discards
        # that stale layout once so the corrected Device-stretch layout applies.
        self._restore_table_column_widths(self.drv_unified_table, CATALOG_UNIFIED_COL_WIDTHS_KEY)
        self._apply_drv_include_column_visibility()
        self._drv_include_header = inc_hdr.IncludeHeaderCheckbox(
            self.drv_unified_table,
            DRV_COL_CHECK,
            tooltip="Include all visible devices when searching for updates",
        )
        self._drv_include_header.include_all_changed.connect(
            self._on_drv_include_header_changed
        )
        self.drv_unified_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.drv_unified_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.drv_unified_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._apply_unified_catalog_table_style(self.drv_unified_table)
        self.drv_unified_table.setMinimumHeight(UNIFIED_TABLE_MIN_LIST_HEIGHT)
        self.drv_unified_table.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.drv_unified_table.verticalHeader().setVisible(False)
        self.drv_unified_table.setIconSize(
            QtCore.QSize(UNIFIED_TABLE_ICON_SIZE, UNIFIED_TABLE_ICON_SIZE)
        )
        self.drv_unified_table.itemSelectionChanged.connect(self._on_drv_unified_selection)
        self.drv_unified_table.cellClicked.connect(self._on_drv_cell_clicked)
        self.drv_unified_table.itemChanged.connect(self._on_drv_include_item_changed)
        self._drv_table_fill_block = False
        list_lay.addWidget(self.drv_unified_table, 1)
        self.drv_v_splitter.addWidget(list_panel)

        self.drv_summary_pane = apply_styled_frame(QtWidgets.QFrame(), "CatalogInspectorPane")
        self.drv_summary_pane.setMinimumHeight(UNIFIED_TAB_SECTION_MIN_HEIGHT)
        summary_lay = QtWidgets.QVBoxLayout(self.drv_summary_pane)
        summary_lay.setContentsMargins(8, 6, 8, 6)
        summary_lay.setSpacing(4)

        insp_head = QtWidgets.QHBoxLayout()
        self.drv_insp_icon = QtWidgets.QLabel()
        self.drv_insp_icon.setFixedSize(
            UNIFIED_TABLE_INSP_ICON_SIZE, UNIFIED_TABLE_INSP_ICON_SIZE
        )
        self.drv_insp_icon.setScaledContents(False)
        self.drv_insp_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        insp_head.addWidget(self.drv_insp_icon)
        head_text = QtWidgets.QVBoxLayout()
        head_text.setSpacing(2)
        self.drv_insp_title = QtWidgets.QLabel("Select a device above")
        self.drv_insp_title.setObjectName("CardTitle")
        self.drv_insp_title.setWordWrap(True)
        head_text.addWidget(self.drv_insp_title)
        self.drv_insp_subtitle = QtWidgets.QLabel(
            "Packages appear after you search for driver updates."
        )
        self.drv_insp_subtitle.setObjectName("Muted")
        self.drv_insp_subtitle.setWordWrap(True)
        self.drv_insp_subtitle.setMaximumHeight(UNIFIED_TABLE_SUBTITLE_MAX_HEIGHT)
        head_text.addWidget(self.drv_insp_subtitle)
        insp_head.addLayout(head_text, 1)
        self.drv_insp_details_btn = QtWidgets.QToolButton()
        self.drv_insp_details_btn.setText("Details")
        self.drv_insp_details_btn.setCheckable(True)
        self.drv_insp_details_btn.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.drv_insp_details_btn.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        self.drv_insp_details_btn.toggled.connect(self._toggle_drv_insp_details)
        self.drv_insp_details_btn.hide()
        insp_head.addWidget(self.drv_insp_details_btn, 0, QtCore.Qt.AlignTop)
        summary_lay.addLayout(insp_head)

        self.drv_insp_details_widget = QtWidgets.QWidget()
        details_lay = QtWidgets.QVBoxLayout(self.drv_insp_details_widget)
        details_lay.setContentsMargins(0, 0, 0, 0)
        meta_grid = QtWidgets.QGridLayout()
        meta_grid.setHorizontalSpacing(16)
        meta_grid.setVerticalSpacing(4)
        self._drv_insp_fields: dict[str, QtWidgets.QLabel] = {}
        for i, (key, label) in enumerate(
            (
                ("provider", "Provider"),
                ("driver_file", "Driver file"),
                ("category", "Category"),
                ("crash", "Crash link"),
                ("notes", "Notes"),
            )
        ):
            k = QtWidgets.QLabel(label)
            k.setObjectName("Muted")
            v = QtWidgets.QLabel("—")
            v.setWordWrap(True)
            v.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            meta_grid.addWidget(k, i // 2, (i % 2) * 2)
            meta_grid.addWidget(v, i // 2, (i % 2) * 2 + 1)
            self._drv_insp_fields[key] = v
        details_lay.addLayout(meta_grid)
        self.drv_insp_details_widget.hide()
        summary_lay.addWidget(self.drv_insp_details_widget)

        self.drv_packages_heading = QtWidgets.QLabel("Available packages")
        self.drv_packages_heading.setObjectName("SectionHeading")
        summary_lay.addWidget(self.drv_packages_heading)

        self.drv_bundle_heading = QtWidgets.QLabel("Bundle components")
        self.drv_bundle_heading.setObjectName("SectionHeading")
        self.drv_bundle_heading.hide()
        summary_lay.addWidget(self.drv_bundle_heading)

        self.drv_bundle_table = QtWidgets.QTableWidget(0, 4)
        self.drv_bundle_table.setHorizontalHeaderLabels(
            ["Component", "Installed", "Offer", "Status"]
        )
        self._configure_driver_package_columns(
            self.drv_bundle_table, compare_table=True
        )
        self.drv_bundle_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows
        )
        self.drv_bundle_table.setSelectionMode(
            QtWidgets.QAbstractItemView.NoSelection
        )
        self.drv_bundle_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers
        )
        self.drv_bundle_table.setWordWrap(True)
        self.drv_bundle_table.setMinimumHeight(56)
        self.drv_bundle_table.setMaximumHeight(160)
        self.drv_bundle_table.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._apply_compare_table_style(self.drv_bundle_table)
        self.drv_bundle_table.hide()
        summary_lay.addWidget(self.drv_bundle_table)

        self.drv_hint = QtWidgets.QPlainTextEdit()
        self.drv_hint.setReadOnly(True)
        self.drv_hint.setObjectName("CatalogHint")
        self.drv_hint.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.drv_hint.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.drv_hint.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.drv_hint.setMaximumHeight(UNIFIED_TABLE_HINT_MAX_HEIGHT)
        self.drv_hint.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.drv_hint.hide()
        summary_lay.addWidget(self.drv_hint)

        self.drv_compare_table = QtWidgets.QTableWidget(0, 3)
        self.drv_compare_table.setHorizontalHeaderLabels(
            ["Compare", "Source", "Package"]
        )
        self._configure_driver_package_columns(
            self.drv_compare_table, compare_table=True
        )
        self._restore_table_column_widths(self.drv_compare_table, CATALOG_PACKAGE_COL_WIDTHS_KEY)
        self._fit_compare_package_columns(self.drv_compare_table)
        self.drv_compare_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.drv_compare_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.drv_compare_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.drv_compare_table.setWordWrap(True)
        self.drv_compare_table.setMinimumHeight(UNIFIED_TABLE_MIN_COMPARE_HEIGHT)
        hdr = self.drv_compare_table.horizontalHeaderItem(0)
        if hdr:
            hdr.setToolTip(
                "Newer / Same / Unknown — hover a cell for compare details."
            )
        self.drv_compare_table.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        self._apply_compare_table_style(self.drv_compare_table)
        summary_lay.addWidget(self.drv_compare_table, 1)
        self.drv_compare_table.hide()
        self.drv_packages_section = self.drv_compare_table
        self.drv_v_splitter.addWidget(self.drv_summary_pane)

        self.drv_btn_install = QtWidgets.QPushButton("Install driver")
        self.drv_btn_install.setEnabled(False)
        self.drv_btn_install.setToolTip(
            "Download (when needed) and install — only when you click. Administrator required."
        )
        self.drv_btn_open_catalog = QtWidgets.QPushButton("Open in Update Catalog")
        self.drv_btn_open_catalog.setEnabled(False)
        self.drv_btn_open_catalog.setToolTip(
            "Open the selected Microsoft Update Catalog package in your browser "
            "(Package Details / hardware IDs)."
        )
        self.drv_btn_install_file = QtWidgets.QPushButton("Install from file…")
        self.drv_btn_install_file.setToolTip(
            "Pick a downloaded .cab, .inf folder, or .zip — only when you click."
        )
        self.drv_btn_restore_driver = QtWidgets.QPushButton("Restore previous driver")
        self.drv_btn_restore_driver.setEnabled(False)
        self.drv_btn_restore_driver.setToolTip(
            "Roll back to the most recent saved backup for the selected device. "
            "Use this if a new driver causes problems — not needed right after install."
        )
        self.drv_btn_restore = QtWidgets.QPushButton("Restore point")
        self.drv_btn_backup = QtWidgets.QPushButton("Back up driver")
        self.drv_btn_enable_restore = QtWidgets.QPushButton("Enable System Restore")
        self.drv_btn_enable_restore.setVisible(False)

        card_lay.addWidget(self._build_catalog_tab_progress_row("drv"))
        self._configure_catalog_tab_splitter(
            self.drv_v_splitter, settings_key=CATALOG_SPLITTER_SETTINGS_KEY
        )
        card_lay.addWidget(self.drv_v_splitter, 1)

        self.drv_inspector_frame = self.drv_summary_pane  # legacy alias

        self.drv_btn_scan_devices.clicked.connect(self._on_scan_for_devices)
        self.drv_btn_check.clicked.connect(self._on_begin_driver_update_workflow)
        self.drv_btn_install.clicked.connect(
            lambda: self._on_install_selected_driver(for_drivers_tab=True)
        )
        self.drv_btn_open_catalog.clicked.connect(
            lambda: self._on_open_catalog_for_selected_offer(for_drivers_tab=True)
        )
        self.drv_btn_install_file.clicked.connect(
            lambda: self._on_install_driver_from_file(for_drivers_tab=True)
        )
        self.drv_btn_restore_driver.clicked.connect(self._on_restore_previous_driver)
        self.drv_btn_restore.clicked.connect(self._on_create_restore_point)
        self.drv_btn_backup.clicked.connect(self._on_backup_driver)
        self.drv_btn_enable_restore.clicked.connect(self._on_enable_system_restore)
        self.drv_compare_table.itemSelectionChanged.connect(
            self._on_drv_compare_selection_changed
        )

        self._apply_drv_include_column_visibility()
        self._wire_driver_tools_menu()
        self._sync_full_install_driver_tools()
        self._sync_admin_gated_controls()
        outer.addWidget(card, 1)
        return tab

    def _wire_driver_tools_menu(self) -> None:
        """Add driver maintenance actions moved from the Drivers tab Tools dropdown."""
        tools_m = getattr(self, "_tools_menu", None)
        if tools_m is None:
            return
        export_act = self.act_export_catalog
        self.drv_act_install_file = QtGui.QAction("Install driver from file…", self)
        self.drv_act_install_file.triggered.connect(
            lambda: self._on_install_driver_from_file(for_drivers_tab=True)
        )
        self.drv_act_restore_point = QtGui.QAction("Create restore point", self)
        self.drv_act_restore_point.triggered.connect(self._on_create_restore_point)
        self.drv_act_backup_driver = QtGui.QAction("Back up driver", self)
        self.drv_act_backup_driver.triggered.connect(self._on_backup_driver)
        self.drv_act_driver_backups = QtGui.QAction("Driver backups…", self)
        self.drv_act_driver_backups.triggered.connect(self._on_driver_backups_dialog)
        self.drv_act_enable_restore = QtGui.QAction("Enable System Restore", self)
        self.drv_act_enable_restore.triggered.connect(self._on_enable_system_restore)
        self.drv_act_enable_restore.setVisible(False)
        tools_m.insertAction(export_act, self.drv_act_enable_restore)
        tools_m.insertAction(export_act, self.drv_act_driver_backups)
        tools_m.insertAction(export_act, self.drv_act_backup_driver)
        tools_m.insertAction(export_act, self.drv_act_restore_point)
        tools_m.insertAction(export_act, self.drv_act_install_file)
        tools_m.insertSeparator(export_act)
