"""Tab host wiring and Summary/Action/Details/System/Advanced tab layout."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiTabsMixin:
    def _build_tabs(self) -> MainTabHost:
        self.tabs.addTab(self._build_summary_tab(), "Summary")
        self.tabs.addTab(self._build_action_tab(), "Action Plan")
        self.tabs.addTab(self._build_details_tab(), "Crash Details")
        self.tabs.addTab(self._build_system_tab(), "System")
        self.tabs.addTab(self._build_drivers_tab(), "Drivers")
        self.tabs.addTab(self._build_firmware_tab(), "Firmware")
        self.tabs.addTab(self._build_advanced_tab(), "Advanced")
        self.tabs.currentChanged.connect(self._on_main_tab_changed)
        self._apply_catalog_tab_accessibility()
        return self.tabs

    def _build_summary_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        w.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        lay = QtWidgets.QHBoxLayout(w)
        self._apply_tab_body_margins(lay)
        lay.setSpacing(12)

        # Left: plain English card
        left = apply_styled_frame(QtWidgets.QFrame(), "Card")
        left.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(16, 14, 16, 16)
        title = QtWidgets.QLabel("What happened (in plain English)")
        title.setObjectName("CardTitle")
        ll.addWidget(title)
        self._summary_refresh_frame = QtWidgets.QWidget()
        sr_lay = QtWidgets.QHBoxLayout(self._summary_refresh_frame)
        sr_lay.setContentsMargins(0, 0, 0, 6)
        sr_lay.setSpacing(8)
        self._summary_refresh_label = QtWidgets.QLabel(
            "Refreshing summary with full device list…"
        )
        self._summary_refresh_label.setObjectName("Muted")
        self._summary_refresh_bar = QtWidgets.QProgressBar()
        self._summary_refresh_bar.setRange(0, 0)
        self._summary_refresh_bar.setFixedHeight(8)
        self._summary_refresh_bar.setTextVisible(False)
        sr_lay.addWidget(self._summary_refresh_label, 1)
        sr_lay.addWidget(self._summary_refresh_bar, 2)
        self._summary_refresh_frame.setVisible(False)
        ll.addWidget(self._summary_refresh_frame)
        self.plain_text = QtWidgets.QTextBrowser()
        self.plain_text.setOpenExternalLinks(True)
        self.plain_text.document().setDocumentMargin(6)
        ll.addWidget(self.plain_text, 1)
        self.driver_update_frame = apply_styled_frame(QtWidgets.QFrame(), "Card")
        dul = QtWidgets.QVBoxLayout(self.driver_update_frame)
        dul.setContentsMargins(12, 10, 12, 10)
        dul.setSpacing(6)
        self.driver_update_title = QtWidgets.QLabel("Update driver")
        self.driver_update_title.setObjectName("CardTitle")
        dul.addWidget(self.driver_update_title)
        self.driver_update_hint = QtWidgets.QLabel("")
        self.driver_update_hint.setWordWrap(True)
        self.driver_update_hint.setObjectName("Muted")
        dul.addWidget(self.driver_update_hint)
        self.driver_compare_table = QtWidgets.QTableWidget(0, 5)
        self.driver_compare_table.setHorizontalHeaderLabels(
            ["Source", "Version", "Date", "vs installed", "Package"]
        )
        self._configure_driver_package_columns(self.driver_compare_table)
        self.driver_compare_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.driver_compare_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.driver_compare_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.driver_compare_table.setAlternatingRowColors(True)
        self.driver_compare_table.setVisible(False)
        self.driver_compare_table.setMaximumHeight(200)
        dul.addWidget(self.driver_compare_table)
        safeguard = QtWidgets.QHBoxLayout()
        safeguard.setSpacing(8)
        self.btn_restore_point = QtWidgets.QPushButton("Create restore point")
        self.btn_backup_driver = QtWidgets.QPushButton("Back up driver")
        self.btn_enable_restore = QtWidgets.QPushButton("Enable System Restore")
        self.btn_enable_restore.setVisible(False)
        self.btn_enable_restore.setToolTip(
            "System Restore is off. Enable it on your system drive, then you can create restore points."
        )
        safeguard.addWidget(self.btn_restore_point)
        safeguard.addWidget(self.btn_backup_driver)
        safeguard.addWidget(self.btn_enable_restore)
        safeguard.addStretch(1)
        dul.addLayout(safeguard)
        self.driver_update_buttons = QtWidgets.QHBoxLayout()
        self.driver_update_buttons.setSpacing(8)
        self.btn_check_drivers = QtWidgets.QPushButton("Check for newer drivers")
        self.btn_open_drivers_tab = QtWidgets.QPushButton("Drivers tab…")
        self.btn_open_drivers_tab.setToolTip(
            "Full device list, install drivers, and optional safeguards (never automatic)."
        )
        self.driver_update_buttons.addWidget(self.btn_check_drivers)
        self.driver_update_buttons.addWidget(self.btn_open_drivers_tab)
        self.driver_update_buttons.addStretch(1)
        dul.addLayout(self.driver_update_buttons)
        self.btn_check_drivers.clicked.connect(self._on_check_driver_catalog)
        self.btn_open_drivers_tab.clicked.connect(
            lambda: self._focus_drivers_tab_for_device("")
        )
        self.btn_restore_point.clicked.connect(self._on_create_restore_point)
        self.btn_backup_driver.clicked.connect(self._on_backup_driver)
        self.btn_enable_restore.clicked.connect(self._on_enable_system_restore)
        self.driver_compare_table.itemSelectionChanged.connect(self._on_driver_row_selected)
        self.driver_update_frame.setVisible(False)
        ll.addWidget(self.driver_update_frame)
        lay.addWidget(left, 3)

        # Right: severity + at a glance
        right = apply_styled_frame(QtWidgets.QFrame(), "Card")
        right.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(16, 14, 16, 16)
        rl.setSpacing(10)
        sev_title = QtWidgets.QLabel("Severity")
        sev_title.setObjectName("CardTitle")
        rl.addWidget(sev_title)
        self.sev_label = QtWidgets.QLabel("—")
        self.sev_label.setAccessibleName("Severity level")
        self.sev_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        rl.addWidget(self.sev_label)
        self.meter = SeverityMeter()
        rl.addWidget(self.meter)
        rl.addSpacing(6)
        tl_title = QtWidgets.QLabel("Incident timeline")
        tl_title.setObjectName("CardTitle")
        rl.addWidget(tl_title)
        self.crash_timeline_view = QtWidgets.QTextBrowser()
        self.crash_timeline_view.setReadOnly(True)
        self.crash_timeline_view.setOpenExternalLinks(False)
        self.crash_timeline_view.document().setDocumentMargin(4)
        self.crash_timeline_view.setMaximumHeight(220)
        self.crash_timeline_view.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.crash_timeline_view.setObjectName("IncidentTimeline")
        self.crash_timeline_view.setPlaceholderText(
            "Run Analysis to see shutdown vs BSOD vs boot recovery."
        )
        rl.addWidget(self.crash_timeline_view)
        # Legacy alias for tests / older references
        self.crash_timeline_label = self.crash_timeline_view
        rl.addSpacing(6)
        rel_title = QtWidgets.QLabel("Reliability / Live Kernel")
        rel_title.setObjectName("CardTitle")
        rl.addWidget(rel_title)
        self.reliability_label = QtWidgets.QLabel(
            "Run Analysis to query stability and live-kernel events."
        )
        self.reliability_label.setWordWrap(True)
        self.reliability_label.setObjectName("Muted")
        rl.addWidget(self.reliability_label)
        rl.addSpacing(6)
        glance_title = QtWidgets.QLabel("At a glance")
        glance_title.setObjectName("CardTitle")
        rl.addWidget(glance_title)
        self.glance = QtWidgets.QGridLayout()
        self.glance.setColumnStretch(0, 1)
        self.glance.setColumnStretch(1, 0)
        self.glance.setVerticalSpacing(8)
        rl.addLayout(self.glance)
        rl.addStretch(1)
        lay.addWidget(right, 2)
        return w

    def _build_action_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        w.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        lay = QtWidgets.QVBoxLayout(w)
        self._apply_tab_body_margins(lay)
        lay.setSpacing(10)
        self._build_action_plan_step_host(lay)
        # Legacy QTextBrowser kept for theme-refresh hooks; hidden.
        self.action_text = QtWidgets.QTextBrowser()
        self.action_text.hide()
        return w

    def _build_details_tab(self) -> QtWidgets.QWidget:
        w, lay = self._new_standard_tab()
        self.details_text = QtWidgets.QTextBrowser()
        lay.addWidget(self.details_text, 1)
        return w

    @staticmethod
    def _apply_tab_body_margins(
        layout: QtWidgets.QBoxLayout,
    ) -> None:
        layout.setContentsMargins(*TAB_BODY_MARGINS)

    def _new_standard_tab(self) -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        """Tab body with the same top inset as Details / System / Advanced."""
        tab = QtWidgets.QWidget()
        tab.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        lay = QtWidgets.QVBoxLayout(tab)
        self._apply_tab_body_margins(lay)
        lay.setSpacing(0)
        return tab, lay

    def _new_fill_tab(self) -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        """Tab body for Drivers/Firmware — same tab→card gap as banner tabs."""
        tab = QtWidgets.QWidget()
        tab.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        lay = QtWidgets.QVBoxLayout(tab)
        lay.setContentsMargins(*CATALOG_TAB_BODY_MARGINS)
        lay.setSpacing(0)
        return tab, lay

    @staticmethod
    def _step_label(number: int, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(f"Step {number} — {text}")
        lbl.setObjectName("StepLabel")
        lbl.setWordWrap(True)
        return lbl

    @staticmethod
    def _section_heading(text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("SectionHeading")
        return lbl

    @staticmethod
    def _tools_menu_button(menu: QtWidgets.QMenu, label: str = "Tools") -> QtWidgets.QToolButton:
        btn = QtWidgets.QToolButton()
        btn.setObjectName("ToolsMenuButton")
        btn.setText(label)
        btn.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        btn.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setMenu(menu)
        btn.setMinimumWidth(92)
        btn.setFixedHeight(32)
        btn.setAutoRaise(False)
        return btn

    @staticmethod
    def _add_equal_width_buttons(
        layout: QtWidgets.QHBoxLayout, *buttons: QtWidgets.QPushButton
    ) -> None:
        """Share horizontal space evenly so action buttons fit the panel width."""
        for btn in buttons:
            btn.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            layout.addWidget(btn, 1)

    def _build_system_tab(self) -> QtWidgets.QWidget:
        w, lay = self._new_standard_tab()
        self.system_text = QtWidgets.QTextBrowser()
        self.system_text.setOpenLinks(False)
        self.system_text.setMouseTracking(True)
        # ToolTip events are delivered to the scroll-area viewport, so filter that.
        self.system_text.viewport().installEventFilter(self)
        self.system_text.anchorClicked.connect(self._on_system_anchor)
        lay.addWidget(self.system_text, 1)
        return w

    def _build_advanced_tab(self) -> QtWidgets.QWidget:
        w, lay = self._new_standard_tab()
        lay.setSpacing(8)

        # --- Debugger (CDB) management card ---
        lay.addWidget(self._build_cdb_card())

        self._build_minidump_panel(lay)

        self.dump_status = QtWidgets.QLabel("")
        self.dump_status.setObjectName("Muted")
        self.dump_status.setWordWrap(True)
        lay.addWidget(self.dump_status)
        self.raw_text = QtWidgets.QPlainTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setStyleSheet(f"font-family: {MONO}; font-size: 12px;")
        lay.addWidget(self.raw_text, 1)
        row = QtWidgets.QHBoxLayout()
        self.btn_windbg = QtWidgets.QPushButton("Open latest dump in WinDbg")
        self.btn_windbg.clicked.connect(self.on_windbg)
        row.addWidget(self.btn_windbg)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    def _build_cdb_card(self) -> QtWidgets.QFrame:
        card = apply_styled_frame(QtWidgets.QFrame(), "Card")
        cl = QtWidgets.QVBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)
        title = QtWidgets.QLabel("Debugger (CDB) — required for faulting-driver detail")
        title.setObjectName("CardTitle")
        cl.addWidget(title)
        self.cdb_status_label = QtWidgets.QLabel("")
        self.cdb_status_label.setObjectName("Muted")
        self.cdb_status_label.setWordWrap(True)
        cl.addWidget(self.cdb_status_label)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.btn_cdb_install = QtWidgets.QPushButton("Install CDB")
        self.btn_cdb_install.clicked.connect(self.on_install_cdb)
        self.btn_cdb_update = QtWidgets.QPushButton("Check for CDB updates")
        self.btn_cdb_update.clicked.connect(self.on_update_cdb)
        row.addWidget(self.btn_cdb_install)
        row.addWidget(self.btn_cdb_update)
        row.addStretch(1)
        cl.addLayout(row)
        return card

    # ---- Toolbar ----
