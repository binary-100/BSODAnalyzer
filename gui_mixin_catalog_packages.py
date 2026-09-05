"""Compare/package table formatting and catalog hint helpers."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiCatalogPackagesMixin:
    def _format_package_date(self, raw: str) -> str:
        s = (raw or "").strip()
        if not s:
            return "—"
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            return s[:10]
        m = re.search(r"/Date\((\d+)", s)
        if m:
            try:
                ms = int(m.group(1))
                if ms >= 1_000_000_000_000:
                    ts = ms / 1000.0
                elif ms >= 1_000_000_000:
                    ts = float(ms)
                else:
                    return s[:24] if len(s) > 24 else s
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass
        return s[:24] if len(s) > 24 else s

    @staticmethod
    def _format_vs_installed(vs: str) -> str:
        labels = {
            "newer": "Newer",
            "same": "Same",
            "uncertain": "Uncertain",
            "older": "Older",
            "unknown": "Unknown",
            "n/a": "—",
            "none": "No match",
        }
        return labels.get((vs or "").lower(), vs or "—")

    @staticmethod
    def _configure_drv_unified_columns(table: QtWidgets.QTableWidget) -> None:
        hdr = table.horizontalHeader()
        hdr.setFixedHeight(UNIFIED_TABLE_HEADER_HEIGHT)
        # Device holds the most text, so it should be the widest, growing to fill
        # the window (Stretch). Installed and Status keep fixed, readable widths
        # (Installed wider than Status). Previously the last section (Status) was
        # stretched, which made Status the widest column.
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(UNIFIED_TABLE_INSTALLED_COL_MIN_WIDTH)
        hdr.setSectionResizeMode(DRV_COL_ICON, QtWidgets.QHeaderView.Fixed)
        table.setColumnWidth(DRV_COL_ICON, UNIFIED_TABLE_ICON_COL_WIDTH)
        hdr.setSectionResizeMode(DRV_COL_CHECK, QtWidgets.QHeaderView.Fixed)
        table.setColumnWidth(DRV_COL_CHECK, UNIFIED_TABLE_CHECK_COL_WIDTH)
        hdr.setSectionResizeMode(DRV_COL_DEVICE, QtWidgets.QHeaderView.Stretch)
        table.setColumnWidth(DRV_COL_DEVICE, UNIFIED_TABLE_DEVICE_COL_MIN_WIDTH * 2)
        hdr.setSectionResizeMode(DRV_COL_INSTALLED, QtWidgets.QHeaderView.Interactive)
        table.setColumnWidth(DRV_COL_INSTALLED, UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE)
        hdr.setSectionResizeMode(DRV_COL_STATUS, QtWidgets.QHeaderView.Interactive)
        table.setColumnWidth(DRV_COL_STATUS, UNIFIED_TABLE_STATUS_COL_WIDTH)
        vhdr = table.verticalHeader()
        vhdr.setDefaultSectionSize(UNIFIED_TABLE_ROW_HEIGHT)
        vhdr.setMinimumSectionSize(UNIFIED_TABLE_ROW_HEIGHT)

    @staticmethod
    def _configure_fw_unified_columns(table: QtWidgets.QTableWidget) -> None:
        hdr = table.horizontalHeader()
        hdr.setFixedHeight(UNIFIED_TABLE_HEADER_HEIGHT)
        # Component column holds the most text — stretch it (widest); keep
        # Installed and Status fixed (Installed wider than Status).
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(UNIFIED_TABLE_INSTALLED_COL_MIN_WIDTH)
        hdr.setSectionResizeMode(FW_COL_ICON, QtWidgets.QHeaderView.Fixed)
        table.setColumnWidth(FW_COL_ICON, UNIFIED_TABLE_ICON_COL_WIDTH)
        hdr.setSectionResizeMode(FW_COL_CHECK, QtWidgets.QHeaderView.Fixed)
        table.setColumnWidth(FW_COL_CHECK, UNIFIED_TABLE_CHECK_COL_WIDTH)
        hdr.setSectionResizeMode(FW_COL_COMPONENT, QtWidgets.QHeaderView.Stretch)
        table.setColumnWidth(FW_COL_COMPONENT, UNIFIED_TABLE_DEVICE_COL_MIN_WIDTH * 2)
        hdr.setSectionResizeMode(FW_COL_INSTALLED, QtWidgets.QHeaderView.Interactive)
        table.setColumnWidth(FW_COL_INSTALLED, UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE)
        hdr.setSectionResizeMode(FW_COL_STATUS, QtWidgets.QHeaderView.Interactive)
        table.setColumnWidth(FW_COL_STATUS, UNIFIED_TABLE_STATUS_COL_WIDTH)
        vhdr = table.verticalHeader()
        vhdr.setDefaultSectionSize(UNIFIED_TABLE_ROW_HEIGHT)
        vhdr.setMinimumSectionSize(UNIFIED_TABLE_ROW_HEIGHT)

    @staticmethod
    def _configure_driver_package_columns(
        table: QtWidgets.QTableWidget,
        *,
        compare_table: bool = False,
    ) -> None:
        hdr = table.horizontalHeader()
        vhdr = table.verticalHeader()
        vhdr.setVisible(False)
        vhdr.setDefaultSectionSize(UNIFIED_TABLE_PACKAGE_ROW_HEIGHT)
        vhdr.setMinimumSectionSize(UNIFIED_TABLE_PACKAGE_ROW_HEIGHT)
        if compare_table or (
            table.columnCount() == 3
            and table.horizontalHeaderItem(0)
            and (table.horizontalHeaderItem(0).text() or "").strip() == "Compare"
        ):
            table.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            hdr.setStretchLastSection(True)
            hdr.setMinimumSectionSize(UNIFIED_TABLE_PACKAGE_COL_MIN_WIDTH)
            hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)
            hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
            if table.columnWidth(1) < UNIFIED_TABLE_PACKAGE_SOURCE_COL_MIN_WIDTH:
                table.setColumnWidth(1, UNIFIED_TABLE_PACKAGE_SOURCE_COL_MIN_WIDTH)
            return
        hdr.setStretchLastSection(True)
        hdr.setMinimumSectionSize(UNIFIED_TABLE_PACKAGE_COL_MIN_WIDTH)
        default = max(table.columnWidth(0), 160)
        last = max(table.columnCount() - 1, 0)
        for col in range(table.columnCount()):
            if col == last:
                hdr.setSectionResizeMode(col, QtWidgets.QHeaderView.Stretch)
            else:
                hdr.setSectionResizeMode(col, QtWidgets.QHeaderView.Interactive)
                table.setColumnWidth(col, default)

    @staticmethod
    def _fit_compare_package_columns(table: QtWidgets.QTableWidget) -> None:
        """Keep Compare/Source/Package columns within the panel (no horizontal scroll)."""
        if table.columnCount() != 3:
            return
        hdr = table.horizontalHeader()
        table.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        viewport_w = max(table.viewport().width(), 160)
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.resizeColumnToContents(0)
        w0 = max(table.columnWidth(0), UNIFIED_TABLE_PACKAGE_COL_MIN_WIDTH)
        min_pkg = 100
        min_source = UNIFIED_TABLE_PACKAGE_SOURCE_COL_MIN_WIDTH
        available = viewport_w - w0
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        if available >= min_source + min_pkg:
            table.setColumnWidth(1, min_source)
            table.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        else:
            table.setColumnWidth(1, max(min_source, available - min_pkg))
            table.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        hdr.setStretchLastSection(True)

    @staticmethod
    def _set_catalog_hint(
        widget: QtWidgets.QPlainTextEdit,
        text: str,
        *,
        tooltip: str = "",
    ) -> None:
        t = (text or "").strip()
        if t:
            widget.setPlainText(t)
            widget.setToolTip((tooltip or t).strip())
            widget.show()
        else:
            widget.clear()
            widget.setToolTip("")
            widget.hide()

    @staticmethod
    def _brief_package_compare_hint(
        status: str,
        offers: list | None,
        *,
        package_count: int | None = None,
    ) -> str:
        st = (status or "").lower()
        shown = drvcat.filter_offers_for_display(offers or [])
        n = package_count if package_count is not None else len(shown)
        if st in ("unknown", "uncertain"):
            return (
                f"Version compare {st} — {n} package(s) in the table. "
                "Hover Compare for notes; open Details for the full source list."
            )
        if st == "none":
            return "No matching packages in checked catalogs — try vendor or OEM links."
        if st == "newer":
            return f"Update available — {n} package(s) in the table."
        if st == "same":
            return f"Installed version matches catalog — {n} package(s) checked."
        return ""

    def _format_catalog_package_label(self, title: str, version: str, date: str = "") -> str:
        title = (title or "").strip()
        ver = (version or "").strip()
        if ver.lower() in ("", "—", "–", "?", "n/a", "unknown", "none"):
            ver = ""
        elif ver.lower().startswith("v"):
            ver = ver[1:].strip()
        parts: list[str] = []
        if title:
            parts.append(title)
        if ver:
            parts.append(f"v{ver}")
        pkg = "  ·  ".join(parts)
        date_fmt = self._format_package_date(date) if date else ""
        if date_fmt and date_fmt != "—":
            pkg = f"{pkg}  ·  {date_fmt}" if pkg else date_fmt
        return pkg or "—"

    @staticmethod
    def _compare_vs_colors() -> dict[str, str]:
        import gui_theme as theme

        return {
            "newer": theme.SEVERITY_COLORS[0],
            "same": theme.MUTED,
            "uncertain": theme.SEVERITY_COLORS[1],
            "older": "#6b8cff",
            "unknown": theme.SEVERITY_COLORS[1],
            "n/a": theme.MUTED,
        }

    def _refresh_compare_tables_theme(self) -> None:
        """Re-apply compare-table foreground colors after a theme switch."""
        for table in (
            getattr(self, "drv_compare_table", None),
            getattr(self, "drv_bundle_table", None),
            getattr(self, "fw_compare_table", None),
            getattr(self, "driver_compare_table", None),
        ):
            if table is None:
                continue
            if table is getattr(self, "drv_bundle_table", None):
                comp = getattr(self, "_driver_comparison", None)
                if isinstance(comp, dict):
                    self._fill_drv_bundle_table(comp)
                continue
            offers: list[dict] = []
            for row in range(table.rowCount()):
                item = table.item(row, 1) or table.item(row, 2)
                if item is None:
                    continue
                offer = item.data(QtCore.Qt.UserRole)
                if isinstance(offer, dict) and offer:
                    offers.append(offer)
            if offers:
                self._fill_driver_compare_table(table, offers)

    def _fill_driver_compare_table(self, table: QtWidgets.QTableWidget, offers: list) -> None:
        import gui_theme as theme

        offers = drvcat.filter_offers_for_display(offers)
        vs_colors = self._compare_vs_colors()
        table.setRowCount(len(offers))
        for row, offer in enumerate(offers):
            vs = offer.get("vs_installed") or "unknown"
            ver = (offer.get("version") or "").strip()
            src = offer.get("source_label") or offer.get("source", "")
            title = (
                offer.get("display_title")
                or offer.get("product_name")
                or offer.get("title")
                or ""
            ).strip()
            full_title = (offer.get("full_title") or offer.get("title") or title).strip()
            pkg = self._format_catalog_package_label(
                title, ver, offer.get("date") or ""
            )
            cells = [
                self._format_vs_installed(vs),
                src,
                pkg or "—",
            ]
            for col, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(str(text))
                item.setTextAlignment(
                    QtCore.Qt.AlignmentFlag.AlignLeft
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                )
                if col == 0:
                    item.setForeground(QtGui.QColor(vs_colors.get(vs, theme.MUTED)))
                    note = (offer.get("compare_note") or "").strip()
                    if note:
                        item.setToolTip(note)
                if col == 1:
                    tips = [
                        offer.get("notes") or "",
                        offer.get("compare_note") or "",
                        drvcat.oem_data_freshness_note(offer.get("data_freshness") or ""),
                    ]
                    item.setToolTip("\n".join(t for t in tips if t))
                    item.setData(QtCore.Qt.UserRole, offer)
                if col == 2 and (full_title or title):
                    item.setToolTip(full_title or title)
                    item.setData(QtCore.Qt.UserRole, offer)
                table.setItem(row, col, item)
        extra_rows = 0
        conflict_msg = drvcat.offer_source_conflict_summary(offers)
        if conflict_msg:
            extra_rows += 1
        if not offers:
            table.setRowCount(1)
            empty = QtWidgets.QTableWidgetItem(
                "(No displayable packages — none found, or all catalog rows are older "
                "than installed)"
            )
            empty.setFlags(QtCore.Qt.NoItemFlags)
            table.setItem(0, 0, empty)
        elif all((o.get("vs_installed") or "").lower() == "unknown" for o in offers):
            extra_rows += 1
        if extra_rows:
            table.setRowCount(len(offers) + extra_rows)
            row_idx = len(offers)
            if conflict_msg:
                note = QtWidgets.QTableWidgetItem(conflict_msg)
                note.setFlags(QtCore.Qt.NoItemFlags)
                note.setForeground(QtGui.QColor(theme.SEVERITY_COLORS[1]))
                table.setItem(row_idx, 0, note)
                table.setSpan(row_idx, 0, 1, table.columnCount())
                row_idx += 1
            if offers and all((o.get("vs_installed") or "").lower() == "unknown" for o in offers):
                note = QtWidgets.QTableWidgetItem(
                    "Packages found but version compare is Unknown — hover vs installed "
                    "for why. Use the download link and verify on the vendor site."
                )
                note.setFlags(QtCore.Qt.NoItemFlags)
                note.setForeground(QtGui.QColor(theme.SEVERITY_COLORS[1]))
                table.setItem(row_idx, 0, note)
                table.setSpan(row_idx, 0, 1, table.columnCount())
        table.resizeRowsToContents()
        for row in range(table.rowCount()):
            if table.rowHeight(row) < UNIFIED_TABLE_PACKAGE_ROW_HEIGHT:
                table.setRowHeight(row, UNIFIED_TABLE_PACKAGE_ROW_HEIGHT)
        table.setVisible(True)
        is_compare = (
            table.columnCount() == 3
            and table.horizontalHeaderItem(0)
            and (table.horizontalHeaderItem(0).text() or "").strip() == "Compare"
        )
        self._configure_driver_package_columns(table, compare_table=is_compare)
        if is_compare:
            self._fit_compare_package_columns(table)
        for row in range(table.rowCount()):
            lead = table.item(row, 0)
            if lead is None or not bool(lead.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled):
                continue
            stripe = QtGui.QColor(theme.catalog_row_zebra_color(row))
            for col in range(table.columnCount()):
                cell = table.item(row, col)
                if cell is not None:
                    cell.setBackground(stripe)
