"""Drivers tab unified table: row styling, populate, filter, selection."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiDriversTableMixin:
    def _set_device_row_status(
        self,
        row: int,
        status: str,
        *,
        table: QtWidgets.QTableWidget | None = None,
        version_hint: str = "",
        none_reason: str = "",
        dev: dict | None = None,
    ) -> None:
        table = table or self.drv_unified_table
        if status == "newer" and version_hint:
            label = "Update"
        elif status == "same":
            label = self._crash_linked_same_status_label(dev) or "Up to date"
        elif status == "unknown":
            label = "Unknown"
        elif status == "uncertain":
            label = "Verify"
        elif status == "none":
            import driver_catalog as dc

            label = dc.none_reason_display_label(none_reason) or "No match"
        elif status == "checking":
            label = "Checking…"
        elif status == "pending":
            label = "Not checked"
        elif status == "error":
            label = "Failed"
        else:
            label = self._update_status_label(status)
        import gui_theme as theme

        item = QtWidgets.QTableWidgetItem(label)
        color = theme.UPDATE_STATUS_COLORS.get(status, theme.MUTED)
        item.setForeground(QtGui.QColor(color))
        status_col = self._drv_status_column(table)
        table.setItem(row, status_col, item)

    def _catalog_row_a11y_summary(
        self, tier: str, status: str, device_label: str
    ) -> str:
        parts: list[str] = []
        name = (device_label or "").strip()
        if name:
            parts.append(name)
        tier = (tier or "normal").strip()
        if tier == "culprit":
            parts.append("Crash-related device")
        elif tier == "outdated":
            parts.append("Needs attention")
        status_key = (status or "pending").strip()
        status_text = UPDATE_STATUS_LABELS.get(status_key, status_key)
        parts.append(f"Status: {status_text}")
        return ". ".join(parts) + "."

    def _apply_catalog_row_accessibility(
        self,
        table: QtWidgets.QTableWidget,
        row: int,
        *,
        tier: str,
        status: str,
    ) -> None:
        is_fw = table is getattr(self, "fw_unified_table", None)
        name_col = FW_COL_COMPONENT if is_fw else DRV_COL_DEVICE
        icon_col = FW_COL_ICON if is_fw else DRV_COL_ICON
        check_col = FW_COL_CHECK if is_fw else DRV_COL_CHECK
        name_item = table.item(row, name_col)
        label = (name_item.text() if name_item else "").strip()
        summary = self._catalog_row_a11y_summary(tier, status, label)
        role = QtCore.Qt.ItemDataRole.AccessibleTextRole
        for col in (name_col, self._drv_status_column(table)):
            item = table.item(row, col)
            if item is None:
                continue
            item.setData(role, summary)
            if col == name_col:
                item.setToolTip(summary)
        icon_item = table.item(row, icon_col)
        if icon_item is not None:
            icon_item.setData(role, f"Device icon. {summary}")
        check_item = table.item(row, check_col)
        if check_item is not None and (
            check_item.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable
        ):
            included = check_item.checkState() == QtCore.Qt.CheckState.Checked
            check_item.setData(
                role,
                f"{summary} Include in catalog search: "
                f"{'checked' if included else 'unchecked'}.",
            )

    @staticmethod
    def _catalog_row_highlight_kind(
        tier: str,
        status: str,
        *,
        crash_linked: bool = False,
        scan_verified: bool = False,
    ) -> str:
        """Shared Drivers/Firmware row background rule."""
        tier = (tier or "normal").strip()
        status = (status or "pending").strip()
        if tier == "culprit" or crash_linked:
            if status == "same" and scan_verified:
                return "current"
            return "culprit"
        if status == "newer" or tier == "outdated":
            return "update"
        if status == "same":
            return "current"
        return "none"

    def _dev_is_crash_linked(self, dev: dict | None) -> bool:
        if not dev:
            return False
        return bool(dev.get("_crash_linked") or dev.get("_tier") == "culprit")

    def _crash_linked_same_status_label(self, dev: dict | None) -> str | None:
        if not dev or not self._dev_is_crash_linked(dev):
            return None
        if (dev.get("_check_status") or "").strip() != "same":
            return None
        if self._fix_progress_note_for_device(dev):
            return "Updated since crash"
        return None

    def _crash_link_info_tooltip(self, dev: dict) -> str:
        lines = [
            "Crash analysis flagged this device for attention — "
            "check that its driver is current.",
        ]
        fix = self._fix_progress_note_for_device(dev)
        if fix:
            lines.extend(["", fix])
        elif dev.get("_scan_verified") and (dev.get("_check_status") or "") == "same":
            lines.extend(
                [
                    "",
                    "Catalog check shows the installed driver is up to date. "
                    "That may mean a recent update addressed the issue — "
                    "watch for new blue screens after driver or BIOS changes.",
                ]
            )
        return "\n".join(lines)

    def _apply_device_crash_info_tooltip(
        self, device_item: QtWidgets.QTableWidgetItem, dev: dict
    ) -> None:
        from gui_theme import DRV_CRASH_INFO_TOOLTIP_ROLE

        if self._dev_is_crash_linked(dev):
            device_item.setData(
                DRV_CRASH_INFO_TOOLTIP_ROLE, self._crash_link_info_tooltip(dev)
            )
        else:
            device_item.setData(DRV_CRASH_INFO_TOOLTIP_ROLE, None)

    def _apply_catalog_row_style(
        self,
        table: QtWidgets.QTableWidget,
        row: int,
        *,
        tier: str,
        status: str,
        dev: dict | None = None,
    ) -> None:
        """Apply unified row tint on Drivers and Firmware catalog tables."""
        import gui_theme as theme

        crash_linked = self._dev_is_crash_linked(dev) if dev else tier == "culprit"
        scan_verified = bool((dev or {}).get("_scan_verified"))
        kind = self._catalog_row_highlight_kind(
            tier,
            status,
            crash_linked=crash_linked,
            scan_verified=scan_verified,
        )
        status_col = self._drv_status_column(table)
        bg = None
        fg = None
        if kind == "culprit":
            bg = QtGui.QColor(theme.DRV_TIER_CULPRIT_BG)
            fg = QtGui.QColor(theme.DRV_TIER_CULPRIT_FG)
        elif kind == "update":
            bg = QtGui.QColor(theme.DRV_TIER_OUTDATED_BG)
            # Status column keeps amber "Update" label; device/version stay readable.
        elif kind == "current":
            bg = QtGui.QColor(
                theme.CATALOG_ROW_CURRENT_BG or theme.SEVERITY_COLORS[0]
            )
        row_bg = bg if bg else QtGui.QColor(theme.catalog_row_zebra_color(row))
        for col in range(2, table.columnCount()):
            if col == status_col:
                continue
            item = table.item(row, col)
            if not item:
                continue
            item.setBackground(row_bg)
            if fg and col in CATALOG_NAME_COLUMNS:
                item.setForeground(fg)
            else:
                item.setForeground(QtGui.QColor(theme.TEXT))
        for col in (DRV_COL_ICON, DRV_COL_CHECK):
            item = table.item(row, col)
            if item:
                item.setBackground(row_bg)
        self._apply_catalog_row_accessibility(
            table, row, tier=tier, status=status
        )

    def _set_catalog_row_status(
        self,
        table: QtWidgets.QTableWidget,
        row: int,
        status: str,
        *,
        tier: str = "normal",
        version_hint: str = "",
        none_reason: str = "",
        dev: dict | None = None,
    ) -> None:
        self._set_device_row_status(
            row,
            status,
            table=table,
            version_hint=version_hint,
            none_reason=none_reason,
            dev=dev,
        )
        self._apply_catalog_row_style(
            table, row, tier=tier, status=status, dev=dev
        )

    _STATUS_LABEL_OVERRIDES = {
        "Update": "newer",
        "Up to date": "same",
        "Updated since crash": "same",
        "Unknown": "unknown",
        "Verify": "uncertain",
        "No match": "none",
        "Checking…": "checking",
        "Not checked": "pending",
        "Failed": "error",
    }

    def _status_key_from_row_label(self, label: str) -> str:
        text = (label or "").strip()
        if not text:
            return "pending"
        for status, mapped in UPDATE_STATUS_LABELS.items():
            if mapped == text:
                return status
        return self._STATUS_LABEL_OVERRIDES.get(text, "pending")

    def _tier_for_driver_name(self, name: str) -> str:
        key = (name or "").strip()
        if not key:
            return "normal"
        for dev in self._session_all_drivers or []:
            dev_name = (dev.get("name") or dev.get("device") or "").strip()
            if dev_name == key:
                return str(dev.get("_tier") or "normal")
        return "normal"

    def _tier_for_fw_key(self, key: str) -> str:
        lookup = (key or "").strip()
        if not lookup:
            return "normal"
        for ent in getattr(self, "_fw_last_rows", []) or []:
            if (ent.get("key") or "").strip() == lookup:
                return str(ent.get("_tier") or "normal")
        return "normal"

    def _refresh_catalog_row_styles(self) -> None:
        """Re-apply status and row tint colors after a theme change."""
        for table, is_fw in (
            (getattr(self, "drv_unified_table", None), False),
            (getattr(self, "fw_unified_table", None), True),
        ):
            if table is None:
                continue
            status_col = self._drv_status_column(table)
            name_col = FW_COL_COMPONENT if is_fw else DRV_COL_DEVICE
            for row in range(table.rowCount()):
                if not is_fw and self._drv_is_section_row(table, row):
                    continue
                name_item = table.item(row, name_col)
                if not name_item:
                    continue
                status_item = table.item(row, status_col)
                status = self._status_key_from_row_label(
                    status_item.text() if status_item else ""
                )
                if is_fw:
                    tier = self._tier_for_fw_key(
                        str(name_item.data(QtCore.Qt.UserRole) or "")
                    )
                else:
                    tier = self._tier_for_driver_name(
                        str(name_item.data(QtCore.Qt.UserRole) or name_item.text())
                    )
                self._set_device_row_status(row, status, table=table)
                self._apply_catalog_row_style(table, row, tier=tier, status=status)

    def _apply_drv_row_tier_style(
        self, table: QtWidgets.QTableWidget, row: int, tier: str
    ) -> None:
        """Backward-compatible alias — prefer _apply_catalog_row_style with status."""
        status_item = table.item(row, self._drv_status_column(table))
        status = "pending"
        if status_item:
            label = (status_item.text() or "").strip().lower()
            if label in ("update", "update available"):
                status = "newer"
            elif label in ("up to date", "updated since crash"):
                status = "same"
            elif label in ("no match", "no catalog match"):
                status = "none"
        self._apply_catalog_row_style(table, row, tier=tier, status=status)

    def _driver_watchlist_from_profile(self, prof: dict) -> list[dict]:
        """Merge generic-driver and problem devices into one deduped list."""
        gen = prof.get("devices_with_generic_driver") or []
        probs = prof.get("devices_with_driver_problems") or []
        by_name: dict[str, dict] = {}
        for d in gen:
            name = (d.get("name") or "").strip()
            if not name:
                continue
            row = dict(d)
            row["_reasons"] = ["Generic driver"]
            by_name[name] = row
        for d in probs:
            name = (d.get("name") or "").strip()
            if not name:
                continue
            if name in by_name:
                if "Driver problem" not in by_name[name]["_reasons"]:
                    by_name[name]["_reasons"].append("Driver problem")
            else:
                row = dict(d)
                row["_reasons"] = ["Driver problem"]
                by_name[name] = row
        return sorted(by_name.values(), key=lambda x: (x.get("name") or "").lower())

    def _drv_device_name_from_row(self, row: int) -> str:
        item = self.drv_unified_table.item(row, DRV_COL_DEVICE)
        if not item:
            item = self.drv_unified_table.item(row, DRV_COL_ICON)
        if not item:
            return ""
        role = str(item.data(QtCore.Qt.UserRole) or "").strip()
        if role == DRV_SECTION_HEADER_ROLE:
            return ""
        return role or str(item.text()).strip()

    def _drv_include_checked(self, name: str) -> bool:
        return (name or "").strip() not in self._drv_check_excluded

    def _drv_device_excluded_from_catalog(self, dev: dict) -> bool:
        try:
            import driver_catalog as dc
            return dc.is_driver_scan_excluded_device(dev)
        except ImportError:
            return False

    def _drv_set_row_include(self, row: int, checked: bool) -> None:
        item = self.drv_unified_table.item(row, DRV_COL_CHECK)
        if not item or not (item.flags() & QtCore.Qt.ItemIsUserCheckable):
            return
        self._drv_table_fill_block = True
        try:
            item.setCheckState(
                QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
            )
        finally:
            self._drv_table_fill_block = False

    def _drv_visible_device_names(self) -> list[str]:
        names: list[str] = []
        table = self.drv_unified_table
        for row in range(table.rowCount()):
            if self._drv_is_section_row(table, row):
                continue
            name = self._drv_device_name_from_row(row)
            if name:
                names.append(name)
        return names

    def _drv_devices_for_filter(self) -> list[dict]:
        """Devices matching the current view filter (full cache — not table display cap)."""
        needle = (
            (self.drv_filter.text() or "").strip().lower()
            if hasattr(self, "drv_filter")
            else ""
        )
        return [
            d
            for d in self._drv_unified_cache
            if self._drv_device_visible(d, needle)
        ]

    def _drv_checked_device_names(self) -> list[str]:
        mode = (
            self.drv_view_filter.currentData()
            if hasattr(self, "drv_view_filter")
            else "all"
        )
        if mode in ("all", "common", "uncommon") or self._drv_include_column_hidden():
            visible_names = [
                (d.get("name") or "").strip()
                for d in self._drv_devices_for_filter()
                if (d.get("name") or "").strip()
            ]
        else:
            visible_names = self._drv_visible_device_names()
        if self._drv_include_column_hidden():
            names = visible_names
        else:
            names = [n for n in visible_names if self._drv_include_checked(n)]
        cache = {
            (d.get("name") or "").strip(): d
            for d in getattr(self, "_drv_unified_cache", [])
        }
        return [
            n
            for n in names
            if not self._drv_device_excluded_from_catalog(cache.get(n, {"name": n}))
        ]

    def _drv_select_all_visible(self) -> None:
        self._drv_include_user_customized = True
        for name in self._drv_visible_device_names():
            self._drv_check_excluded.discard(name)
        self._drv_apply_include_column_states()
        self._on_drv_unified_selection()

    def _drv_clear_all_visible(self) -> None:
        self._drv_include_user_customized = True
        for name in self._drv_visible_device_names():
            self._drv_check_excluded.add(name)
        self._drv_apply_include_column_states()
        self._on_drv_unified_selection()

    def _drv_apply_include_column_states(self) -> None:
        table = self.drv_unified_table
        self._drv_table_fill_block = True
        try:
            for row in range(table.rowCount()):
                if self._drv_is_section_row(table, row):
                    continue
                name = self._drv_device_name_from_row(row)
                self._drv_set_row_include(row, self._drv_include_checked(name))
        finally:
            self._drv_table_fill_block = False
        self._sync_drv_include_header()

    def _on_drv_include_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if getattr(self, "_drv_table_fill_block", False):
            return
        if item.column() != DRV_COL_CHECK:
            return
        name = self._drv_device_name_from_row(item.row())
        if not name:
            return
        self._drv_include_user_customized = True
        if item.checkState() == QtCore.Qt.Checked:
            self._drv_check_excluded.discard(name)
        else:
            self._drv_check_excluded.add(name)
        self._sync_drv_include_header()
        self._on_drv_unified_selection()

    def _on_drv_cell_clicked(self, row: int, col: int) -> None:
        if self._drv_is_section_row(self.drv_unified_table, row):
            return
        if col == DRV_COL_CHECK:
            return
        self.drv_unified_table.selectRow(row)
        self._on_drv_device_row_selected(self.drv_unified_table)

    def _tier_note_label(self, dev: dict) -> str:
        tier = dev.get("_tier") or "normal"
        reasons = ", ".join(dev.get("_reasons") or [])
        fix_note = self._fix_progress_note_for_device(dev)
        if tier == "culprit" or dev.get("_crash_linked"):
            driver = (self._last_model or {}).get("driver") or ""
            if dev.get("_crash_synthetic"):
                base = f"Crash module — update scan uses {driver}"
                return f"{base} · {fix_note}" if fix_note else base
            if any("platform/chipset" in (r or "").lower() for r in (dev.get("_reasons") or [])):
                base = "Crash logs — platform/chipset (check Include, then Search)"
                return f"{base} · {fix_note}" if fix_note else base
            extra = f" · {reasons}" if reasons else ""
            base = f"Crash suspect ({driver}){extra}" if driver else f"Crash suspect{extra}"
            return f"{base} · {fix_note}" if fix_note else base
        if tier == "attention" or dev.get("_analysis_attention"):
            if reasons:
                return self._append_fix_progress_note(reasons, fix_note)
            return self._append_fix_progress_note(
                "Generic or problem driver — check Include, then Search",
                fix_note,
            )
        if tier == "outdated":
            if self._has_dual_version_profile(dev):
                return self._append_fix_progress_note("Update available", fix_note)
            inst = (dev.get("version") or dev.get("_installed_at_scan") or "").strip()
            new_ver = (dev.get("_available_version") or "").strip()
            src = (dev.get("_available_source") or "").strip()
            if new_ver:
                line = f"{inst or '?'} → {new_ver} available"
                if src:
                    line += f" ({src})"
                return self._append_fix_progress_note(line, fix_note)
            return self._append_fix_progress_note("Update available", fix_note)
        if dev.get("_scan_verified"):
            if self._has_dual_version_profile(dev):
                st = dev.get("_check_status") or ""
                if st == "newer":
                    line = "Update available"
                elif st == "same":
                    line = "Up to date"
                else:
                    line = self._update_status_label(st)
                return self._append_fix_progress_note(line, fix_note)
            inst = (dev.get("_installed_at_scan") or dev.get("version") or "").strip()
            cat = (dev.get("_available_version") or "").strip()
            src = (dev.get("_available_source") or "").strip()
            st = dev.get("_check_status") or ""
            if inst and cat:
                if st == "newer":
                    line = f"{inst} → {cat}"
                elif st == "same":
                    line = f"{inst} — up to date (catalog {cat})"
                else:
                    line = f"Installed {inst}; catalog {cat}"
                if src:
                    line += f" ({src})"
                return self._append_fix_progress_note(line, fix_note)
            if inst and inst not in ("?", "—"):
                return self._append_fix_progress_note(
                    f"Installed {inst} — no newer version in checked sources",
                    fix_note,
                )
        if not dev.get("_scan_verified") and dev.get("_index_last_status"):
            when = drvidx.format_checked_at_short(dev.get("_index_checked_at"))
            st = dev.get("_index_last_status") or ""
            label = self._update_status_label(st) if st in UPDATE_STATUS_LABELS else st
            return f"Last check {when}: {label} — run Search to refresh"
        if fix_note:
            return fix_note
        return reasons or "—"

    def _append_fix_progress_note(self, line: str, fix_note: str | None) -> str:
        if fix_note:
            return f"{line} · {fix_note}" if line else fix_note
        return line

    def _has_dual_version_profile(self, dev: dict) -> bool:
        return drvcat.pick_dual_version_profile(dev)[0] is not None

    def _dual_version_inventory(self) -> list:
        bio = (self._hardware_profile or {}).get("bios_driver_info") or {}
        return core.device_inventory_for_matching(bio)

    def _ensure_all_dual_version_profiles(
        self,
        dev: dict,
        offers: list | None = None,
        inventory: list | None = None,
    ) -> tuple[str, dict] | tuple[None, None]:
        if inventory is None:
            inventory = self._dual_version_inventory()
        drvcat.attach_all_dual_version_profiles(
            dev, offers=offers, inventory=inventory
        )
        return drvcat.pick_dual_version_profile(dev)

    def _installed_version_cell(self, dev: dict) -> tuple[str, str]:
        self._ensure_all_dual_version_profiles(dev)
        return drvcat.format_dual_version_installed_for_dev(dev)

    def _gpu_version_subtitle(self, dev: dict, result: dict | None = None) -> str:
        offers = (result or {}).get("offers") if result else None
        self._ensure_all_dual_version_profiles(dev, offers=offers)
        return drvcat.format_dual_version_subtitle_for_dev(dev, offers=offers)

    def _drv_row_height_for_device(self, dev: dict) -> int:
        _single, dual = self._catalog_unified_row_heights()
        if self._has_dual_version_profile(dev):
            return dual
        return _single

    def _fix_progress_note_for_device(self, dev: dict) -> str | None:
        try:
            import fix_progress as fp

            label, crash_dt = self._resolve_fix_progress_last_crash()
            if not crash_dt:
                return None
            return fp.fix_progress_note(
                dev,
                last_crash_dt=crash_dt,
                last_crash_label=label,
            )
        except ImportError:
            return None

    def _resolve_fix_progress_last_crash(self) -> tuple[str, object | None]:
        cached = getattr(self, "_fix_progress_last_crash_cache", None)
        if cached is not None:
            return cached
        try:
            import fix_progress as fp

            result = fp.resolve_last_crash(self._last_model)
        except ImportError:
            result = ("", None)
        self._fix_progress_last_crash_cache = result
        return result

    def _toggle_drv_insp_details(self, expanded: bool) -> None:
        if not hasattr(self, "drv_insp_details_widget"):
            return
        self.drv_insp_details_widget.setVisible(expanded)
        self.drv_insp_details_btn.setArrowType(
            QtCore.Qt.ArrowType.DownArrow
            if expanded
            else QtCore.Qt.ArrowType.RightArrow
        )

    def _set_drv_bundle_section_visible(self, visible: bool) -> None:
        if hasattr(self, "drv_bundle_table"):
            self.drv_bundle_table.setVisible(visible)
        if hasattr(self, "drv_bundle_heading"):
            self.drv_bundle_heading.setVisible(visible)

    def _fill_drv_bundle_table(self, result: dict | None) -> None:
        """Per-component bundle compare (chipset platform / OEM graphics rollup)."""
        if not hasattr(self, "drv_bundle_table"):
            return
        import bundle_verification as bv

        table = self.drv_bundle_table
        table.setRowCount(0)
        rows = bv.bundle_compare_rows_from_catalog_entry(result or {})
        note = ((result or {}).get("bundle_compare_note") or "").strip()
        if not rows:
            self._set_drv_bundle_section_visible(False)
            return
        self._set_drv_bundle_section_visible(True)
        if hasattr(self, "drv_bundle_heading"):
            heading = "Bundle components"
            if note:
                heading = f"{heading} — {note[:120]}"
            self.drv_bundle_heading.setText(heading)
            self.drv_bundle_heading.setToolTip(note or "")
        table.setRowCount(len(rows))
        for row_idx, comp in enumerate(rows):
            label = (comp.get("label") or "?").strip()
            inst = (comp.get("installed_version") or "?").strip()
            offer = (comp.get("offer_version") or "?").strip()
            vs = bv.bundle_compare_vs_label(comp.get("vs_offer") or "")
            tip = (comp.get("device_name") or label).strip()
            for col, text in enumerate((label, inst, offer, vs)):
                item = QtWidgets.QTableWidgetItem(text)
                item.setToolTip(tip)
                item.setFlags(
                    QtCore.Qt.ItemFlag.ItemIsEnabled
                )
                table.setItem(row_idx, col, item)
        table.resizeRowsToContents()

    def _set_drv_packages_section_visible(self, visible: bool) -> None:
        if hasattr(self, "drv_packages_section"):
            self.drv_packages_section.setVisible(visible)
        if hasattr(self, "drv_packages_heading"):
            self.drv_packages_heading.setVisible(visible)
        self._sync_catalog_inspector_splitter("drivers", expanded=visible)

    def _device_dict_by_name(self, name: str) -> dict | None:
        key = (name or "").strip().lower()
        if not key:
            return None
        for dev in self._drv_unified_cache:
            if (dev.get("name") or "").strip().lower() == key:
                return dev
        return None

    def _update_drv_inspector_header(self, dev: dict | None, result: dict | None = None) -> None:
        if not hasattr(self, "drv_insp_title"):
            return
        if dev is None:
            self.drv_insp_icon.clear()
            self.drv_insp_title.setText("Select a device above")
            self.drv_insp_subtitle.setText(
                "Packages appear after you search for driver updates."
            )
            for fld in self._drv_insp_fields.values():
                fld.setText("—")
            self.drv_insp_details_btn.hide()
            self.drv_insp_details_btn.setChecked(False)
            self._toggle_drv_insp_details(False)
            if hasattr(self, "drv_packages_heading"):
                self.drv_packages_heading.setText("Available packages")
            self._set_drv_packages_section_visible(False)
            self._set_drv_bundle_section_visible(False)
            return
        name = (dev.get("display_name") or dev.get("name") or "?").strip()
        icon = vicons.large_icon_for_device(dev, size=UNIFIED_TABLE_INSP_ICON_SIZE)
        vicons.set_vendor_icon_label(
            self.drv_insp_icon, icon, size=UNIFIED_TABLE_INSP_ICON_SIZE
        )
        self.drv_insp_title.setText(name)
        st = (dev.get("_check_status") or "pending").strip()
        inst = (dev.get("_installed_at_scan") or dev.get("version") or "?").strip()
        offers_pending = result and (
            (result.get("offers") or [])
            or (result.get("status") or "none") not in ("none", "pending")
        )
        gpu_sub = self._gpu_version_subtitle(dev, result)
        sub_blocks: list[str] = []
        if gpu_sub:
            sub_blocks.append(gpu_sub)
        sub_parts: list[str] = []
        if offers_pending:
            sub_parts.append(self._update_status_label(st))
        elif not gpu_sub:
            sub_parts.extend([f"Installed: {inst}", self._update_status_label(st)])
        if dev.get("_crash_linked"):
            driver = (self._last_model or {}).get("driver") or ""
            sub_parts.append(
                f"Crash-linked ({driver})" if driver else "Crash-linked"
            )
        if dev.get("_possible_coverage_gap") or (result or {}).get(
            "possible_coverage_gap"
        ):
            sub_parts.append(
                "Installed may be newer than all official catalog offers (Dell/Microsoft/vendor)"
            )
        notes = self._tier_note_label(dev)
        if notes and notes != "—":
            if gpu_sub:
                if notes.startswith("Update available · "):
                    sub_parts.append(notes.split(" · ", 1)[-1])
                elif not notes.startswith("Update available"):
                    sub_parts.append(notes)
            else:
                sub_parts.append(notes)
        parent_name = (dev.get("parent_device_name") or "").strip()
        if parent_name:
            sub_parts.append(f"PnP parent (Windows): {parent_name}")
        if sub_parts:
            sub_blocks.append(" · ".join(sub_parts))
        self.drv_insp_subtitle.setText("\n".join(sub_blocks) if sub_blocks else "—")
        vk = vicons.vendor_key_for_device(dev)
        provider = (dev.get("manufacturer") or "").strip()
        if not provider and vk:
            provider = vk.replace("_", " ").title()
        self._drv_insp_fields["provider"].setText(provider or "—")
        drv_file = (dev.get("driver") or dev.get("name") or "—").strip()
        self._drv_insp_fields["driver_file"].setText(drv_file)
        self._drv_insp_fields["category"].setText(
            (dev.get("device_class") or "—").strip() or "—"
        )
        if dev.get("_crash_linked"):
            driver = (self._last_model or {}).get("driver") or ""
            self._drv_insp_fields["crash"].setText(
                f"Linked to crash module {driver}" if driver else "Crash-linked"
            )
        else:
            self._drv_insp_fields["crash"].setText("—")
        notes_text = notes
        if result:
            catalog_note = (result.get("catalog_note") or "").strip()
            if catalog_note:
                notes_text = (
                    catalog_note
                    if not notes or notes == "—"
                    else f"{notes}\n\n{catalog_note}"
                )
            status = (result.get("status") or st).lower()
            if status in ("unknown", "uncertain"):
                uncertain = drvcat.build_uncertain_inspector_summary(
                    result.get("offers") or [],
                    inst,
                    status=status,
                )
                if uncertain:
                    notes_text = (
                        uncertain
                        if not notes or notes == "—"
                        else f"{notes}\n\n{uncertain}"
                    )
            self._drv_insp_fields["notes"].setText(notes_text)
        self._fill_drv_bundle_table(result)
        self.drv_insp_details_btn.show()
        self.drv_insp_details_btn.setChecked(False)
        self._toggle_drv_insp_details(False)
        if hasattr(self, "drv_packages_heading"):
            self.drv_packages_heading.setText("Available packages")
        offers = (result or {}).get("offers") or []
        scanned = (result or {}).get("status") not in (None, "none", "pending") or bool(
            dev.get("_scan_verified")
        )
        self._set_drv_packages_section_visible(bool(offers) or scanned)

    def _populate_drv_row(
        self,
        table: QtWidgets.QTableWidget,
        row: int,
        dev: dict,
    ) -> None:
        name = dev.get("name") or "?"
        label = (dev.get("display_name") or name).strip()
        ver, ver_tip = self._installed_version_cell(dev)
        self._ensure_all_dual_version_profiles(dev)
        mfr = (dev.get("manufacturer") or "").strip()
        tier = dev.get("_tier") or "normal"
        icon_item = QtWidgets.QTableWidgetItem("")
        icon_item.setIcon(vicons.icon_for_device(dev, size=UNIFIED_TABLE_ICON_SIZE))
        icon_item.setTextAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        icon_item.setFlags(
            QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
        )
        table.setItem(row, DRV_COL_ICON, icon_item)
        device_item = QtWidgets.QTableWidgetItem(label)
        device_item.setData(QtCore.Qt.UserRole, name)
        tip_parts = []
        if mfr:
            tip_parts.append(f"Windows manufacturer: {mfr}")
        if label != name:
            tip_parts.append(f"PnP name: {name}")
        signed = dev.get("driver") or ""
        if signed:
            tip_parts.append(f"Signed driver: {signed}")
        tip_parts.append(self._tier_note_label(dev))
        if tip_parts:
            device_item.setToolTip("\n".join(tip_parts))
        self._apply_device_crash_info_tooltip(device_item, dev)
        table.setItem(row, DRV_COL_DEVICE, device_item)
        ver_item = QtWidgets.QTableWidgetItem(ver)
        ver_item.setToolTip(ver_tip)
        ver_item.setTextAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        table.setItem(row, DRV_COL_INSTALLED, ver_item)
        check_item = QtWidgets.QTableWidgetItem("")
        check_item.setTextAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        check_item.setFlags(
            check_item.flags()
            | QtCore.Qt.ItemFlag.ItemIsUserCheckable
            | QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        check_item.setCheckState(
            QtCore.Qt.CheckState.Checked
            if self._drv_include_checked(name)
            else QtCore.Qt.CheckState.Unchecked
        )
        check_item.setToolTip(
            "Include this device when you click Search for driver updates."
            if not self._drv_device_excluded_from_catalog(dev)
            else "Firmware-class device — use the Firmware tab, not driver catalog search."
        )
        table.setItem(row, DRV_COL_CHECK, check_item)
        status = dev.get("_check_status") or "pending"
        self._set_catalog_row_status(
            table,
            row,
            status,
            tier=tier,
            version_hint=(dev.get("_available_version") or "").strip(),
            none_reason=(dev.get("_none_reason") or "").strip(),
            dev=dev,
        )
        table.setRowHeight(row, self._drv_row_height_for_device(dev))

    def _update_drv_row_from_device(self, row: int, dev: dict) -> None:
        """Refresh one table row in place when cache data changed."""
        table = self.drv_unified_table
        name = (dev.get("name") or "?").strip() or "?"
        label = (dev.get("display_name") or name).strip()
        ver, ver_tip = self._installed_version_cell(dev)
        self._ensure_all_dual_version_profiles(dev)
        tier = dev.get("_tier") or "normal"
        icon_item = table.item(row, DRV_COL_ICON)
        if icon_item:
            icon_item.setIcon(vicons.icon_for_device(dev, size=UNIFIED_TABLE_ICON_SIZE))
        label_item = table.item(row, DRV_COL_DEVICE)
        if label_item:
            if label_item.text() != label:
                label_item.setText(label)
            label_item.setData(QtCore.Qt.UserRole, name)
            self._apply_device_crash_info_tooltip(label_item, dev)
        ver_item = table.item(row, DRV_COL_INSTALLED)
        if ver_item and ver_item.text() != ver:
            ver_item.setText(ver)
            ver_item.setToolTip(ver_tip)
        check_item = table.item(row, DRV_COL_CHECK)
        if check_item:
            want = (
                QtCore.Qt.Checked
                if self._drv_include_checked(name)
                else QtCore.Qt.Unchecked
            )
            if check_item.checkState() != want:
                check_item.setCheckState(want)
        status = dev.get("_check_status") or "pending"
        self._set_catalog_row_status(
            table,
            row,
            status,
            tier=tier,
            version_hint=(dev.get("_available_version") or "").strip(),
            none_reason=(dev.get("_none_reason") or "").strip(),
            dev=dev,
        )
        table.setRowHeight(row, self._drv_row_height_for_device(dev))

    def _sync_drv_unified_table_rows(self, start: int, end: int) -> None:
        table = self.drv_unified_table
        devices = self._drv_table_display
        end = min(end, len(devices))
        if table.rowCount() < end:
            table.setRowCount(end)
        for row in range(start, end):
            dev = devices[row]
            name = (dev.get("name") or "").strip()
            item = table.item(row, DRV_COL_DEVICE)
            existing = str(item.data(QtCore.Qt.UserRole) or "") if item else ""
            if item and existing == name:
                self._update_drv_row_from_device(row, dev)
            else:
                self._populate_drv_row(table, row, dev)

    def _finish_drv_table_sync(self) -> None:
        table = self.drv_unified_table
        self._drv_table_sync_active = False
        self._drv_table_fill_block = False
        table.blockSignals(False)
        table.setUpdatesEnabled(True)
        cb = self._drv_table_sync_on_ready
        self._drv_table_sync_on_ready = None
        if cb:
            cb()
        self._flush_pending_drv_filter()

    def _drv_table_sync_step(self, generation: int) -> None:
        if self._shutting_down:
            self._cancel_drv_table_sync()
            return
        if generation != self._drv_table_sync_gen:
            return
        if not self._drivers_tab_is_active():
            self._cancel_drv_table_sync()
            self._drv_tab_ui_stale = True
            return
        devices = self._drv_table_display
        total = len(devices)
        start = self._drv_table_sync_pos
        end = min(start + _DRV_TABLE_SYNC_BATCH, total)
        self._sync_drv_unified_table_rows(start, end)
        self._drv_table_sync_pos = end
        if end < total:
            if self._drivers_tab_is_active():
                self.statusBar().showMessage(
                    f"Building device list ({end}/{total})…", 8000
                )
            QtCore.QTimer.singleShot(
                _DRV_TABLE_SYNC_DELAY_MS,
                lambda g=generation: self._drv_table_sync_step(g),
            )
            return
        self._finish_drv_table_sync()

    def _sync_drv_unified_table(
        self, *, on_complete: Callable[[], None] | None = None
    ) -> None:
        """Populate driver table from _drv_table_display; grows rows in small batches."""
        self._drv_table_sync_gen += 1
        generation = self._drv_table_sync_gen
        self._drv_table_sync_on_ready = on_complete
        devices = self._drv_table_display
        table = self.drv_unified_table
        if not devices:
            table.setRowCount(0)
            self._finish_drv_table_sync()
            return
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        self._drv_table_fill_block = True
        table.setRowCount(0)
        if len(devices) <= _DRV_TABLE_SYNC_INLINE_MAX:
            self._sync_drv_unified_table_rows(0, len(devices))
            self._finish_drv_table_sync()
            return
        self._drv_table_sync_active = True
        self._drv_table_sync_pos = 0
        if self._drivers_tab_is_active():
            self.statusBar().showMessage(
                f"Building device list (0/{len(devices)})…", 8000
            )
        QtCore.QTimer.singleShot(
            0, lambda g=generation: self._drv_table_sync_step(g)
        )

    def _refresh_unified_driver_table(
        self,
        prof: dict,
        *,
        on_ready: Callable[[], None] | None = None,
        full: bool | None = None,
    ) -> None:
        if self._shutting_down:
            if on_ready:
                on_ready()
            return
        try:
            if full is None:
                mode = (
                    self.drv_view_filter.currentData()
                    if hasattr(self, "drv_view_filter")
                    else "log_attention"
                )
                full = mode in ("all", "common", "uncommon") and bool(
                    self._all_devices_loaded
                )
            if self._drv_list_build_thread and self._drv_list_build_thread.isRunning():
                self._drv_list_build_pending = True
                self._drv_list_build_on_ready = on_ready
                self._drv_list_build_pending_full = full
                return
            self._drv_list_build_generation += 1
            gen = self._drv_list_build_generation
            self._drv_list_build_on_ready = on_ready
            self._drv_list_build_pending_full = full
            self.statusBar().showMessage("Building device list…", 8000)
            if getattr(self, "_task_progress_depth", 0) > 0:
                self._set_task_progress(label="Building device list…", maximum=0)
            else:
                self._begin_task_progress("Building device list…", maximum=0)
                self._drv_list_build_owns_progress = True
            batch = self._driver_batch_comparison
            session_batch = (
                {"devices": list((batch or {}).get("devices") or [])}
                if batch
                else None
            )
            self._drv_list_build_thread = QtCore.QThread()
            self._drv_list_build_worker = BuildDriverListWorker(
                self._profile_snapshot_for_driver_list(prof),
                full=bool(full),
                settings=dict(self._settings),
                session_batch=session_batch,
                crash_driver=(self._last_model or {}).get("driver"),
                last_model=self._last_model,
                last_fmt_args=self._last_fmt_args,
                generation=gen,
            )
            self._drv_list_build_worker.moveToThread(self._drv_list_build_thread)
            self._drv_list_build_thread.started.connect(self._drv_list_build_worker.run)
            self._drv_list_build_worker.finished.connect(
                self._signal_relay.drv_list_build_finished
            )
            self._drv_list_build_worker.failed.connect(
                self._signal_relay.drv_list_build_failed
            )
            self._drv_list_build_worker.finished.connect(
                self._drv_list_build_thread.quit
            )
            self._drv_list_build_worker.failed.connect(
                self._drv_list_build_thread.quit
            )
            self._drv_list_build_thread.finished.connect(
                self._cleanup_drv_list_build_thread
            )
            self._drv_list_build_thread.start()
        except Exception as exc:  # noqa: BLE001 — keep GUI alive if table build fails
            import traceback

            detail = traceback.format_exc()
            if hasattr(self, "drv_scan_status"):
                self.drv_scan_status.setText(
                    f"Could not build device list: {exc}"
                )
            self.statusBar().showMessage(
                f"Driver list update failed: {str(exc)[:80]}", 10000
            )
            _ = detail
            self._end_drv_list_build_progress_if_owned()
            if on_ready:
                on_ready()

    def _apply_common_device_include_defaults(self, prof: dict) -> None:
        if not self._settings.get("default_include_common_devices", True):
            return
        if getattr(self, "_drv_include_user_customized", False):
            return
        culprits: set[str] = set()
        if self._has_crash_faulting_driver():
            culprits = self._culprit_device_names(prof)
        for dev in self._drv_unified_cache:
            name = (dev.get("name") or "").strip()
            if not name:
                continue
            if self._drv_device_excluded_from_catalog(dev):
                self._drv_check_excluded.add(name)
                continue
            if name.lower() in culprits:
                self._drv_check_excluded.discard(name)
            elif dev.get("_common_hw"):
                self._drv_check_excluded.discard(name)
            else:
                self._drv_check_excluded.add(name)

    def _drv_passes_view_filter(self, dev: dict) -> bool:
        if not hasattr(self, "drv_view_filter"):
            return True
        mode = self.drv_view_filter.currentData() or "log_attention"
        tier = dev.get("_tier") or "normal"
        if mode == "log_attention":
            if not self._has_crash_faulting_driver():
                return False
            return self._dev_needs_analysis_attention(dev)
        if mode == "all":
            return True
        if mode == "updates":
            return bool(dev.get("_scan_verified")) and (
                dev.get("_check_status") or ""
            ) == "newer"
        if mode == "uncertain":
            # "Verify manually" view: devices whose update status we could not
            # confirm automatically (conflicting signals / blocked vendor check).
            return bool(dev.get("_scan_verified")) and (
                dev.get("_check_status") or ""
            ) == "uncertain"
        return True

    def _drv_device_visible(self, dev: dict, needle: str) -> bool:
        if not self._drv_passes_view_filter(dev):
            return False
        if needle:
            label = (dev.get("display_name") or dev.get("name") or "").lower()
            if needle not in label and needle not in (dev.get("name") or "").lower():
                return False
        return True

    def _drv_is_section_row(self, table: QtWidgets.QTableWidget, row: int) -> bool:
        return False

    def _drv_row_is_visible(self, row: int) -> bool:
        table = self.drv_unified_table
        if row < 0 or row >= table.rowCount():
            return False
        return not self._drv_is_section_row(table, row)

    def _rebuild_drv_table_display(self) -> str:
        """Filter cache into table rows (capped). Returns optional cap note."""
        needle = (
            (self.drv_filter.text() or "").strip().lower()
            if hasattr(self, "drv_filter")
            else ""
        )
        visible = [
            d
            for d in self._drv_unified_cache
            if self._drv_device_visible(d, needle)
        ]
        note = ""
        mode = (
            self.drv_view_filter.currentData()
            if hasattr(self, "drv_view_filter")
            else "all"
        )
        if mode != "all" and len(visible) > _DRV_TABLE_DISPLAY_CAP:
            total = len(visible)
            note = (
                f"Showing first {_DRV_TABLE_DISPLAY_CAP} of {total} — "
                "use Needs attention or search to narrow."
            )
            visible = visible[:_DRV_TABLE_DISPLAY_CAP]
        self._drv_table_display = visible
        self._update_drv_tab_summary_line()
        return note

    def _after_drv_table_sync(self) -> None:
        if self._drv_table_sync_active:
            return
        self._sync_drv_include_header()
        self._on_drv_unified_selection()

    def _cancel_drv_table_sync(self) -> None:
        self._drv_table_sync_gen += 1
        if self._drv_table_sync_active:
            table = self.drv_unified_table
            self._drv_table_sync_active = False
            self._drv_table_fill_block = False
            table.blockSignals(False)
            table.setUpdatesEnabled(True)
            self._drv_table_sync_on_ready = None
            self._flush_pending_drv_filter()

    def _schedule_drv_filter_apply(self) -> None:
        if self._drv_table_sync_active:
            self._drv_filter_pending = True
            return
        self._drv_filter_debounce.start()

    def _flush_pending_drv_filter(self) -> None:
        if self._shutting_down or not getattr(self, "_drv_filter_pending", False):
            return
        self._drv_filter_pending = False
        if self._drv_table_sync_active:
            self._drv_filter_pending = True
            return
        self._apply_drv_filter()

    def _apply_drv_filter(self) -> None:
        if self._drv_table_sync_active:
            self._drv_filter_pending = True
            return
        prof = self._hardware_profile
        mode = (
            self.drv_view_filter.currentData()
            if hasattr(self, "drv_view_filter")
            else "log_attention"
        )
        need_full = mode in ("all", "common", "uncommon") and bool(
            self._all_devices_loaded
        )
        if prof and (
            not self._drv_unified_cache
            or (need_full and len(self._drv_unified_cache) < 40)
        ):
            self._refresh_unified_driver_table(prof, full=need_full)
            return
        cap_note = self._rebuild_drv_table_display()
        if cap_note and hasattr(self, "drv_scan_status"):
            base = self.drv_scan_status.text() or ""
            if cap_note not in base:
                self.drv_scan_status.setText(
                    f"{base} · {cap_note}" if base else cap_note
                )

        def _done() -> None:
            self._after_drv_table_sync()

        self._sync_drv_unified_table(on_complete=_done)

    def _driver_other_devices_from_profile(
        self,
        prof: dict,
        *,
        full_list: list[dict] | None = None,
    ) -> list[dict]:
        watch_names = {
            (d.get("name") or "").strip().lower()
            for d in self._driver_watchlist_from_profile(prof)
        }
        if full_list is not None:
            rows_src = full_list
        else:
            bio = prof.get("bios_driver_info") or {}
            rows_src = self._full_driver_rows(prof) or core.device_inventory_for_matching(bio)
        devices: list[dict] = list(
            core.chipset_driver_catalog_entries(
                prof.get("system_ctx") or {},
                inventory=core.device_inventory_for_matching(
                    prof.get("bios_driver_info") or {}
                ),
            )
        )
        for d in rows_src:
            name = (d.get("name") or "").strip()
            if not name or name.lower() in watch_names:
                continue
            row = dict(d)
            row["_reasons"] = ["Installed driver"]
            devices.append(row)
        return sorted(
            devices,
            key=lambda x: (x.get("display_name") or x.get("name") or "").lower(),
        )

    def _on_drv_filter_changed(self, _text: str = "") -> None:
        self._apply_drv_include_column_visibility()
        mode = self.drv_view_filter.currentData() if hasattr(self, "drv_view_filter") else ""
        if mode in ("all", "common", "uncommon") and not self._all_devices_loaded:
            self.statusBar().showMessage(
                "Run ① Load devices on the Drivers tab to load the full inventory.",
                8000,
            )
        if mode == "updates" and hasattr(self, "drv_hint"):
            cache = getattr(self, "_drv_unified_cache", []) or []
            pending = sum(
                1
                for d in cache
                if (d.get("_check_status") or "pending") == "pending"
                and not d.get("_scan_verified")
            )
            newer = sum(
                1 for d in cache if (d.get("_check_status") or "") == "newer"
            )
            if pending and not newer:
                self._set_catalog_hint(
                    self.drv_hint,
                    f"Updates available shows devices with a confirmed newer package "
                    f"({newer} right now). {pending} device(s) have not been scanned yet — "
                    "run ② Search for updates (All devices, on AC power) for a full list.",
                )
            elif pending:
                self._set_catalog_hint(
                    self.drv_hint,
                    f"{newer} newer package(s) found; {pending} device(s) still not scanned. "
                    "Run ② Search for updates again for complete coverage.",
                )
        if mode in ("all", "common", "uncommon") and self._all_devices_loaded:
            prof = self._hardware_profile
            if prof and len(self._drv_unified_cache) < 30:
                self._drv_tab_ui_stale = True
        self._schedule_drv_filter_apply()

    def _drv_selected_device_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for table in self._drv_tables():
            for idx in table.selectionModel().selectedRows():
                if self._drv_is_section_row(table, idx.row()):
                    continue
                item = table.item(idx.row(), DRV_COL_DEVICE)
                if not item:
                    continue
                role = str(item.data(QtCore.Qt.UserRole) or "").strip()
                if role == DRV_SECTION_HEADER_ROLE:
                    continue
                n = role or str(item.text()).strip()
                if n and n not in seen:
                    seen.add(n)
                    names.append(n)
        return names

    def _drv_row_for_name(self, name: str) -> tuple[QtWidgets.QTableWidget, int]:
        table = self.drv_unified_table
        for row in range(table.rowCount()):
            if self._drv_is_section_row(table, row):
                continue
            item = table.item(row, DRV_COL_DEVICE)
            if item and str(item.data(QtCore.Qt.UserRole) or item.text()) == name:
                return table, row
        return table, -1

    def _installed_version_for_device(self, device_name: str) -> str:
        key = (device_name or "").strip()
        if not key:
            return ""
        for dev in self._drv_unified_cache or []:
            if (dev.get("name") or "").strip() == key:
                return (
                    dev.get("_installed_at_scan") or dev.get("version") or ""
                ).strip()
        _tbl, row = self._drv_row_for_name(key)
        if row >= 0:
            item = _tbl.item(row, DRV_COL_INSTALLED)
            if item:
                return str(item.text() or "").strip()
        return ""

    def _drv_first_selectable_row(self) -> int:
        table = self.drv_unified_table
        for row in range(table.rowCount()):
            if not self._drv_is_section_row(table, row) and not table.isRowHidden(row):
                return row
        return -1

    def _drv_primary_table(self) -> QtWidgets.QTableWidget | None:
        if self.drv_unified_table.selectionModel().hasSelection():
            return self.drv_unified_table
        return None

    def _on_drv_unified_selection(self) -> None:
        self._sync_driver_workflow_buttons()
        row = self.drv_unified_table.currentRow()
        if row >= 0 and not self._drv_is_section_row(self.drv_unified_table, row):
            self._on_drv_device_row_selected(self.drv_unified_table)
        else:
            self._update_drv_inspector_header(None)
            self._fill_driver_compare_table(self.drv_compare_table, [])
            self._set_catalog_hint(
                self.drv_hint,
                "Select a device above to view details and catalog packages.",
            )
            self._on_drv_compare_selection_changed()
        if hasattr(self, "_update_driver_restore_button"):
            self._update_driver_restore_button()

