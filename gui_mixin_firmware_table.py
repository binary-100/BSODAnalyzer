"""Firmware unified table fill, filter, selection, and comparison cache."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiFirmwareTableMixin:
    def _fw_tier_note_label(self, row: dict) -> str:
        tier = row.get("_tier") or "normal"
        reasons = ", ".join(row.get("_reasons") or [])
        if tier == "culprit":
            return reasons or "Crash-related — check firmware"
        if tier == "outdated":
            return "Update available"
        if row.get("_scan_verified"):
            inst = (row.get("installed") or "").strip()
            key = row.get("key") or ""
            pkg_entry = self._fw_catalog_entry_for_key(key) if key else None
            pkg_offers = (pkg_entry or {}).get("offers") or []
            if not pkg_offers:
                pkg_offers = self._fw_offers_for_target(key)
            best = drvcat.best_versioned_offer(pkg_offers)
            cat = (best.get("version") or "").strip() if best else ""
            src = (best.get("source_label") or "").strip() if best else ""
            st = row.get("_check_status") or ""
            if inst and cat and inst not in ("?", "—", "Loading…"):
                if st == "newer":
                    line = f"{inst} → {cat}"
                elif st == "same":
                    line = f"{inst} — up to date (catalog {cat})"
                else:
                    line = f"Installed {inst}; catalog {cat}"
                if src:
                    line += f" ({src})"
                return line
            if inst and inst not in ("?", "—", "Loading…"):
                return f"Installed {inst} — no newer firmware in checked sources"
        if not row.get("_scan_verified") and row.get("_index_last_status"):
            when = drvidx.format_checked_at_short(row.get("_index_checked_at"))
            st = row.get("_index_last_status") or ""
            label = self._update_status_label(st) if st in UPDATE_STATUS_LABELS else st
            return f"Last check {when}: {label} — run Search to refresh"
        if (row.get("key") or "") == "ssd:loading":
            return "Loading drive info…"
        return reasons or "—"

    def _firmware_priority_info_tooltip(self, ent: dict) -> str:
        """Plain-language ⓘ copy for Firmware tab rows highlighted after Run Analysis."""
        key = ent.get("key") or ""
        code = self._firmware_stop_code()
        if key == "bios":
            lines = [
                "Highlighted because your crash stop code often relates to BIOS or "
                "platform firmware — not because BIOS is known to be faulty.",
            ]
        elif key.startswith("ssd:"):
            lines = [
                "Highlighted because your crash stop code is storage-related — "
                "worth checking SSD firmware among other steps.",
                "This does not mean the drive caused the crash or that firmware is outdated.",
            ]
        else:
            lines = [
                "Highlighted for attention based on your crash analysis.",
            ]
        if code is not None:
            lines.append(f"Stop code: 0x{code:08X}")
        status = (ent.get("_check_status") or "pending").strip()
        if status == "pending":
            lines.extend(
                [
                    "",
                    "Status is Not checked — click Search on the Firmware tab "
                    "to compare installed firmware with vendor sources.",
                ]
            )
        elif status == "same" and ent.get("_scan_verified"):
            lines.extend(
                [
                    "",
                    "Catalog check shows installed firmware matches the best known package.",
                ]
            )
        elif status == "newer":
            lines.extend(
                [
                    "",
                    "A newer firmware package was found — review packages before updating.",
                ]
            )
        return "\n".join(lines)

    def _apply_firmware_priority_info_tooltip(
        self, comp_item: QtWidgets.QTableWidgetItem, ent: dict
    ) -> None:
        from gui_theme import DRV_CRASH_INFO_TOOLTIP_ROLE

        if (ent.get("_tier") or "normal") == "culprit":
            comp_item.setData(
                DRV_CRASH_INFO_TOOLTIP_ROLE,
                self._firmware_priority_info_tooltip(ent),
            )
        else:
            comp_item.setData(DRV_CRASH_INFO_TOOLTIP_ROLE, None)

    @staticmethod
    def _format_fw_installed_display(raw: str, ent: dict | None = None) -> str:
        s = (raw or "").strip()
        if s in ("", "—", "?", "Loading…"):
            return s or "—"
        key = (ent or {}).get("key") or ""
        src = (ent or {}).get("installed_source") or ""
        if s == "0" and (
            key.startswith("winfw:") or (ent or {}).get("_tier") == "secondary"
        ):
            return "Not reported"
        if src == "driver_package" and s.startswith("10.0."):
            return f"{s}\ndriver pkg"
        if src in ("hid_driver", "driver_version") and key.startswith("peripheral:"):
            if s not in ("—", "?"):
                return f"{s}\ndriver — verify in vendor app"
            return "—\nverify in vendor app"
        return s

    def _fw_row_height_for_entry(self, ent: dict, installed: str) -> int:
        single, dual = self._catalog_unified_row_heights()
        text = (installed or "").strip()
        if "\n" in text:
            return dual
        src = (ent.get("installed_source") or "").strip()
        if src in ("hid_driver", "driver_version", "driver_package"):
            return dual
        if len(text) > 22:
            return dual
        return single

    @staticmethod
    def _fw_needs_vendor_verify(ent: dict | None) -> bool:
        if not ent:
            return False
        key = (ent.get("key") or "").strip()
        if not key.startswith("peripheral:"):
            return False
        return (ent.get("installed_source") or "").strip() in (
            "hid_driver",
            "driver_version",
        )

    @staticmethod
    def _fw_vendor_verify_hint(ent: dict) -> str:
        try:
            import firmware_peripheral_vendors as fpv

            info = fpv.vendor_verify_info(ent.get("vendor_key") or "")
        except ImportError:
            info = {}
        app = (info.get("app_name") or "").strip() or "the vendor desktop app"
        return (
            f"Windows does not report keyboard/mouse MCU firmware. "
            f"Open {app} or the vendor updater, then click Confirm firmware version."
        )

    def _set_fw_row_status(
        self, row: int, status: str, ent: dict | None = None
    ) -> None:
        tier = (ent or {}).get("_tier") or "normal"
        hint = ""
        if status == "newer" and ent:
            hint = (ent.get("_available_version") or "").strip()
        self._set_catalog_row_status(
            self.fw_unified_table,
            row,
            status,
            tier=tier,
            version_hint=hint,
        )

    def _fill_fw_unified_table(self, rows: list[dict]) -> None:
        self._fw_last_rows = list(rows or [])
        table = self.fw_unified_table
        self._fw_table_fill_block = True
        try:
            table.setRowCount(len(rows))
            for row_idx, ent in enumerate(rows):
                key = ent.get("key") or ""
                component = ent.get("component") or "?"
                installed = self._format_fw_installed_display(
                    ent.get("installed") or "?", ent
                )
                tier = ent.get("_tier") or "normal"
                checkable = key not in ("ssd:loading",)
                icon_item = QtWidgets.QTableWidgetItem("")
                icon_item.setIcon(vicons.icon_for_firmware_entry(ent))
                icon_item.setTextAlignment(
                    QtCore.Qt.AlignmentFlag.AlignHCenter
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                )
                icon_item.setFlags(
                    QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
                )
                table.setItem(row_idx, FW_COL_ICON, icon_item)
                comp_item = QtWidgets.QTableWidgetItem(str(component))
                comp_item.setData(QtCore.Qt.UserRole, key)
                comp_item.setToolTip(self._fw_tier_note_label(ent))
                self._apply_firmware_priority_info_tooltip(comp_item, ent)
                table.setItem(row_idx, FW_COL_COMPONENT, comp_item)
                inst_item = QtWidgets.QTableWidgetItem(str(installed))
                inst_item.setTextAlignment(
                    QtCore.Qt.AlignmentFlag.AlignLeft
                    | QtCore.Qt.AlignmentFlag.AlignTop
                )
                inst_item.setToolTip(str(installed).replace("\n", " · "))
                table.setItem(row_idx, FW_COL_INSTALLED, inst_item)
                check_item = QtWidgets.QTableWidgetItem("")
                check_item.setTextAlignment(
                    QtCore.Qt.AlignmentFlag.AlignHCenter
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                )
                if checkable:
                    check_item.setFlags(
                        check_item.flags()
                        | QtCore.Qt.ItemIsUserCheckable
                        | QtCore.Qt.ItemIsEnabled
                    )
                    check_item.setCheckState(
                        QtCore.Qt.Checked
                        if key not in self._fw_check_excluded
                        else QtCore.Qt.Unchecked
                    )
                    check_item.setToolTip(
                        "Include when you click Search for firmware updates."
                    )
                else:
                    check_item.setFlags(QtCore.Qt.NoItemFlags)
                table.setItem(row_idx, FW_COL_CHECK, check_item)
                status = ent.get("_check_status") or "pending"
                self._set_fw_row_status(row_idx, status, ent)
                table.setRowHeight(
                    row_idx, self._fw_row_height_for_entry(ent, installed)
                )
        finally:
            self._fw_table_fill_block = False
        self._sync_fw_include_header()
        self._update_fw_list_count_label(len(rows))

        self._update_fw_tab_summary_line()

    def _update_fw_list_count_label(self, shown: int | None = None) -> None:
        self._update_fw_tab_summary_line()

    def _toggle_fw_insp_details(self, expanded: bool) -> None:
        if not hasattr(self, "fw_insp_details_widget"):
            return
        self.fw_insp_details_widget.setVisible(expanded)
        self.fw_insp_details_btn.setArrowType(
            QtCore.Qt.ArrowType.DownArrow
            if expanded
            else QtCore.Qt.ArrowType.RightArrow
        )

    def _set_fw_packages_section_visible(self, visible: bool) -> None:
        if hasattr(self, "fw_packages_section"):
            self.fw_packages_section.setVisible(visible)
        if hasattr(self, "fw_packages_heading"):
            self.fw_packages_heading.setVisible(visible)
        if hasattr(self, "fw_support_links") and visible:
            self.fw_support_links.hide()
        self._sync_catalog_inspector_splitter("firmware", expanded=visible)

    def _update_fw_inspector_header(self, ent: dict | None) -> None:
        if not hasattr(self, "fw_insp_title"):
            return
        if ent is None:
            self.fw_insp_icon.clear()
            self.fw_insp_title.setText("Select a component above")
            self.fw_insp_subtitle.setText(
                "Packages appear after you search for firmware updates."
            )
            for fld in self._fw_insp_fields.values():
                fld.setText("—")
            self.fw_insp_details_btn.hide()
            self.fw_insp_details_btn.setChecked(False)
            self._toggle_fw_insp_details(False)
            if hasattr(self, "fw_packages_heading"):
                self.fw_packages_heading.setText("Available packages")
            self._set_fw_packages_section_visible(False)
            return
        label = (ent.get("component") or "?").strip()
        icon = vicons.large_icon_for_firmware_entry(ent, size=UNIFIED_TABLE_INSP_ICON_SIZE)
        vicons.set_vendor_icon_label(
            self.fw_insp_icon, icon, size=UNIFIED_TABLE_INSP_ICON_SIZE
        )
        self.fw_insp_title.setText(label)
        st = (ent.get("_check_status") or "pending").strip()
        inst = self._format_fw_installed_display(ent.get("installed") or "?", ent)
        sub_parts = [f"Installed: {inst}", self._update_status_label(st)]
        if self._fw_needs_vendor_verify(ent):
            sub_parts.append("Verify in vendor app")
        notes = self._fw_tier_note_label(ent)
        if notes and notes != "—":
            sub_parts.append(notes)
        self.fw_insp_subtitle.setText(" · ".join(sub_parts))
        key = ent.get("key") or ""
        if key == "bios":
            kind = "Motherboard BIOS"
        elif key.startswith("ssd:"):
            kind = "SSD firmware"
        elif key.startswith("peripheral:"):
            kind = "USB peripheral firmware"
        elif key.startswith("winfw:"):
            kind = "Windows firmware device"
        else:
            kind = "Firmware"
        self._fw_insp_fields["kind"].setText(kind)
        self._fw_insp_fields["installed"].setText(inst)
        self._fw_insp_fields["notes"].setText(notes)
        if ent.get("_tier") == "culprit":
            code = self._firmware_stop_code()
            if key == "bios":
                self._fw_insp_fields["crash"].setText(
                    f"Crash-related (stop 0x{code:08X})" if code else "Crash-related"
                )
            elif key.startswith("ssd:"):
                self._fw_insp_fields["crash"].setText(
                    f"Storage-related crash (0x{code:08X})"
                    if code
                    else "Storage-related crash"
                )
            else:
                self._fw_insp_fields["crash"].setText("Crash-related")
        else:
            self._fw_insp_fields["crash"].setText("—")
        self.fw_insp_details_btn.show()
        self.fw_insp_details_btn.setChecked(False)
        self._toggle_fw_insp_details(False)
        if hasattr(self, "fw_packages_heading"):
            self.fw_packages_heading.setText("Available packages")
        self._set_fw_packages_section_visible(True)
        if hasattr(self, "fw_support_links"):
            self.fw_support_links.hide()

    def _fw_cache_row_from_table_row(self, row: int) -> dict | None:
        key = self._fw_key_from_row(row)
        if not key:
            return None
        return self._fw_cache_row_for_key(key)

    def _resort_fw_unified_cache(self) -> None:
        bios_priority = self._firmware_bios_crash_priority()
        ssd_priority = self._firmware_ssd_crash_priority()

        def tier(ent: dict) -> int:
            key = ent.get("key") or ""
            status = ent.get("_check_status") or "pending"
            if key == "bios" and bios_priority:
                return 0
            if (
                key.startswith("ssd:")
                and key not in ("ssd:loading", "ssd:none")
                and ssd_priority
            ):
                return 0
            if status == "newer":
                return 1
            if key == "ssd:loading":
                return 2
            return 3

        code = self._firmware_stop_code()
        for ent in self._fw_unified_cache:
            t = tier(ent)
            ent["_tier"] = ("culprit", "outdated", "attention", "normal")[t]
            if ent["_tier"] == "culprit":
                if ent.get("key") == "bios":
                    ent["_reasons"] = [
                        f"Crash-related (stop 0x{code:08X})" if code else "Crash-related"
                    ]
                elif (ent.get("key") or "").startswith("ssd:"):
                    ent["_reasons"] = [
                        f"Storage-related crash (0x{code:08X})"
                        if code
                        else "Storage-related crash"
                    ]
            elif ent["_tier"] == "outdated":
                ent["_reasons"] = ["Update available"]
            elif ent.get("key") == "ssd:loading":
                ent["_reasons"] = ["Loading drive info…"]
        self._fw_unified_cache.sort(
            key=lambda x: (tier(x), (x.get("component") or "").lower())
        )

    def _refresh_unified_firmware_table(self, prof: dict) -> None:
        self._fw_unified_cache = self._build_unified_firmware_list(prof)
        if self._firmware_comparison:
            self._apply_fw_comparison_to_cache(self._firmware_comparison)
        self._resort_fw_unified_cache()
        self._apply_fw_include_defaults()
        self._apply_fw_filter()
        self._apply_fw_include_column_visibility()
        self._fw_apply_include_column_states()

    def _fw_passes_view_filter(self, ent: dict) -> bool:
        if not hasattr(self, "fw_view_filter"):
            return True
        mode = self.fw_view_filter.currentData() or "log_attention"
        tier = ent.get("_tier") or "normal"
        if mode == "log_attention":
            return tier == "culprit"
        if mode == "updates":
            return bool(ent.get("_scan_verified")) and (
                ent.get("_check_status") or ""
            ) == "newer"
        if mode == "uncertain":
            return bool(ent.get("_scan_verified")) and (
                ent.get("_check_status") or ""
            ) == "uncertain"
        if mode == "secondary":
            return (ent.get("_tier") or "") == "secondary"
        return True

    def _apply_fw_filter(self) -> None:
        selected_key = ""
        row = self.fw_unified_table.currentRow()
        if row >= 0:
            selected_key = self._fw_key_from_row(row)
        needle = (
            (self.fw_filter.text() or "").strip().lower()
            if hasattr(self, "fw_filter")
            else ""
        )
        filtered = [
            e for e in self._fw_unified_cache if self._fw_component_visible(e, needle)
        ]
        self._fill_fw_unified_table(filtered)
        self._update_fw_tab_summary_line()
        if filtered:
            restore = 0
            if selected_key:
                for i, ent in enumerate(filtered):
                    if (ent.get("key") or "") == selected_key:
                        restore = i
                        break
            self.fw_unified_table.selectRow(restore)
            self._on_fw_unified_selection()
        else:
            self._sync_fw_workflow_buttons()
            self._update_fw_inspector_header(None)
            self._fill_driver_compare_table(self.fw_compare_table, [])
        self._sync_fw_workflow_buttons()

    def _on_fw_filter_changed(self, _index: int = 0) -> None:
        self._apply_fw_include_column_visibility()
        if hasattr(self, "_fw_filter_debounce"):
            self._fw_filter_debounce.start()
        elif self._fw_unified_cache:
            self._apply_fw_filter()

    def _fw_key_from_row(self, row: int) -> str:
        item = self.fw_unified_table.item(row, FW_COL_COMPONENT)
        return str(item.data(QtCore.Qt.UserRole) or "").strip() if item else ""

    def _fw_visible_keys(self) -> list[str]:
        keys: list[str] = []
        for row in range(self.fw_unified_table.rowCount()):
            key = self._fw_key_from_row(row)
            if key and key != "ssd:loading":
                keys.append(key)
        return keys

    def _fw_checked_target_keys(self) -> list[str]:
        visible = self._fw_visible_keys()
        if self._fw_include_column_hidden():
            return visible
        return [k for k in visible if k not in self._fw_check_excluded]

    def _fw_select_all_visible(self) -> None:
        for key in self._fw_visible_keys():
            self._fw_check_excluded.discard(key)
        self._fw_apply_include_column_states()
        self._on_fw_unified_selection()

    def _fw_clear_all_visible(self) -> None:
        for key in self._fw_visible_keys():
            self._fw_check_excluded.add(key)
        self._fw_apply_include_column_states()
        self._on_fw_unified_selection()

    def _fw_apply_include_column_states(self) -> None:
        table = self.fw_unified_table
        self._fw_table_fill_block = True
        try:
            for row in range(table.rowCount()):
                key = self._fw_key_from_row(row)
                item = table.item(row, FW_COL_CHECK)
                if not item or not (item.flags() & QtCore.Qt.ItemIsUserCheckable):
                    continue
                item.setCheckState(
                    QtCore.Qt.Checked
                    if key not in self._fw_check_excluded
                    else QtCore.Qt.Unchecked
                )
        finally:
            self._fw_table_fill_block = False
        self._sync_fw_include_header()

    def _on_fw_include_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if getattr(self, "_fw_table_fill_block", False):
            return
        if item.column() != FW_COL_CHECK:
            return
        key = self._fw_key_from_row(item.row())
        if not key or key == "ssd:loading":
            return
        self._fw_include_user_customized = True
        if item.checkState() == QtCore.Qt.Checked:
            self._fw_check_excluded.discard(key)
        else:
            self._fw_check_excluded.add(key)
        self._sync_fw_include_header()
        self._sync_fw_workflow_buttons()
        self._on_fw_unified_selection()

    def _on_fw_cell_clicked(self, row: int, col: int) -> None:
        if col == FW_COL_CHECK:
            return
        key = self._fw_key_from_row(row)
        if key == "ssd:loading":
            return
        self.fw_unified_table.selectRow(row)
        self._on_fw_unified_selection()

    def _apply_fw_comparison_to_cache(self, comparison: dict) -> None:
        offers = comparison.get("offers") or []
        for ent in self._fw_unified_cache:
            key = ent.get("key") or ""
            if key == "bios":
                related = [o for o in offers if o.get("kind") == "bios"]
            elif key.startswith("ssd:"):
                model = key[4:].strip().lower()
                if model == "none":
                    related = [o for o in offers if o.get("kind") == "ssd"]
                elif model == "loading":
                    related = []
                else:
                    related = [
                        o
                        for o in offers
                        if o.get("kind") == "ssd"
                        and (
                            (o.get("installed_model") or "").lower() == model
                            or model in (o.get("title") or "").lower()
                        )
                    ]
            elif key.startswith("peripheral:") or key.startswith("winfw:"):
                related = [
                    o
                    for o in offers
                    if o.get("target_key") == key
                    or (
                        o.get("kind") == "peripheral"
                        and (o.get("target_key") or "") == key
                    )
                ]
            else:
                related = []
            ent["_check_status"] = self._firmware_status_from_offers(related)
            ent["_scan_verified"] = True
            t = ent.get("_check_status") or "pending"
            if ent.get("_tier") != "culprit":
                ent["_tier"] = "outdated" if t == "newer" else ent.get("_tier") or "normal"

    def _firmware_status_from_offers(self, offers: list) -> str:
        return drvcat.summarize_offer_status(offers)

    def _merge_firmware_comparison(self, new_comp: dict) -> dict:
        """Merge partial firmware check results into stored comparison."""
        old = self._firmware_comparison or {}
        old_offers = list(old.get("offers") or [])
        new_offers = list(new_comp.get("offers") or [])
        checked_keys = set(new_comp.get("target_keys") or [])

        def _offer_key(o: dict) -> tuple:
            return (
                o.get("kind"),
                o.get("source"),
                o.get("version"),
                (o.get("title") or "")[:80],
                (o.get("installed_model") or "").lower(),
            )

        if checked_keys:
            kept = []
            for o in old_offers:
                kind = o.get("kind")
                if kind == "bios" and "bios" in checked_keys:
                    continue
                if kind == "ssd":
                    model = (o.get("installed_model") or "").lower()
                    if any(
                        k.startswith("ssd:")
                        and (
                            k[4:].strip().lower() == model
                            or k == "ssd:none"
                        )
                        for k in checked_keys
                    ):
                        continue
                if kind == "peripheral":
                    tk = (o.get("target_key") or "").strip()
                    if tk and tk in checked_keys:
                        continue
                kept.append(o)
            merged_offers = kept + new_offers
        else:
            merged_offers = new_offers

        seen: set[tuple] = set()
        unique: list[dict] = []
        for o in merged_offers:
            key = _offer_key(o)
            if key in seen:
                continue
            seen.add(key)
            unique.append(o)

        merged = dict(old)
        merged.update(new_comp)
        merged["offers"] = unique
        return merged

    def _update_fw_targets_from_comparison(
        self, comparison: dict, only_keys: set[str] | None = None
    ) -> None:
        if only_keys:
            offers = comparison.get("offers") or []
            for ent in self._fw_unified_cache:
                key = ent.get("key") or ""
                if key not in only_keys:
                    continue
                ent["_check_status"] = self._firmware_status_from_offers(
                    self._fw_offers_for_target(key, offers=offers)
                )
                if ent.get("_tier") != "culprit":
                    ent["_tier"] = (
                        "outdated"
                        if ent["_check_status"] == "newer"
                        else ent.get("_tier") or "normal"
                    )
        else:
            self._apply_fw_comparison_to_cache(comparison)
        self._resort_fw_unified_cache()
        if self._fw_unified_cache:
            self._apply_fw_filter()

    def _fw_offers_for_target(
        self, target_key: str, *, offers: list | None = None
    ) -> list:
        if offers is None:
            offers = (self._firmware_comparison or {}).get("offers") or []
        if target_key == "bios":
            return [o for o in offers if o.get("kind") == "bios"]
        if target_key.startswith("ssd:"):
            model = target_key[4:].strip().lower()
            if model == "none":
                return [o for o in offers if o.get("kind") == "ssd"]
            return [
                o
                for o in offers
                if o.get("kind") == "ssd"
                and (
                    (o.get("installed_model") or "").lower() == model
                    or model in (o.get("title") or "").lower()
                )
            ]
        if target_key.startswith("peripheral:") or target_key.startswith("winfw:"):
            return [
                o
                for o in offers
                if o.get("target_key") == target_key
            ]
        return offers

    def _fw_cache_row_for_key(self, target_key: str) -> dict | None:
        return next(
            (e for e in self._fw_unified_cache if (e.get("key") or "") == target_key),
            None,
        )

    def _fw_catalog_entry_for_key(self, target_key: str) -> dict | None:
        """Packages payload for a firmware target (session comparison + index merge)."""
        key = (target_key or "").strip()
        if not key or key == "ssd:loading":
            return None
        row = self._fw_cache_row_for_key(key)
        offers = self._fw_offers_for_target(key) if self._firmware_comparison else []
        if not offers and row and row.get("_index_package_offers"):
            offers = list(row["_index_package_offers"])
        installed = (row.get("installed") or "?").strip() if row else "?"
        status = (row.get("_check_status") or "none").strip() if row else "none"
        session: dict | None = None
        if offers or (row and row.get("_scan_verified")):
            session = {
                "target_key": key,
                "installed_version": installed,
                "offers": offers,
                "status": status,
            }
        if drvidx.is_index_enabled(self._settings):
            merged = drvidx.entry_with_index_firmware_packages(session, key)
            if merged:
                merged = dict(merged)
                merged.pop("_from_index", None)
                return merged
        return session

    def _on_fw_unified_selection(self) -> None:
        self._sync_fw_workflow_buttons()
        row = self.fw_unified_table.currentRow()
        if row < 0:
            self._update_fw_inspector_header(None)
            self._fill_driver_compare_table(self.fw_compare_table, [])
            self._set_catalog_hint(self.fw_hint, "")
            self.fw_btn_download.setEnabled(False)
            if hasattr(self, "fw_btn_set_installed"):
                self.fw_btn_set_installed.setEnabled(False)
            return
        item = self.fw_unified_table.item(row, FW_COL_COMPONENT)
        if not item:
            return
        key = str(item.data(QtCore.Qt.UserRole) or "")
        if key == "ssd:loading":
            self._sync_fw_workflow_buttons()
            self._update_fw_inspector_header(self._fw_cache_row_for_key(key))
            self._fill_driver_compare_table(self.fw_compare_table, [])
            self._set_fw_packages_section_visible(False)
            self._set_catalog_hint(self.fw_hint, "")
            self.fw_btn_download.setEnabled(False)
            if hasattr(self, "fw_btn_set_installed"):
                self.fw_btn_set_installed.setEnabled(False)
            return
        label = item.text()
        cache_row = self._fw_cache_row_for_key(key)
        entry = self._fw_catalog_entry_for_key(key)
        offers = (entry or {}).get("offers") or []
        self._update_fw_inspector_header(cache_row)
        status = (cache_row or {}).get("_check_status") or ""
        if offers:
            self._fill_driver_compare_table(self.fw_compare_table, offers)
            self._set_fw_packages_section_visible(True)
            self.fw_packages_heading.setText("Available packages")
            prof = self._hardware_profile or {}
            inst = (cache_row or {}).get("installed") or "?"
            kind = "bios" if key == "bios" else ("ssd" if key.startswith("ssd:") else "")
            if fwcat.offers_are_utility_only(offers):
                summary = fwcat.build_firmware_utility_inspector_summary(
                    offers,
                    component_label=label,
                    kind=kind,
                )
                brief = (
                    "Utility / support links only — compare versions in the vendor tool."
                )
                self._set_catalog_hint(self.fw_hint, brief, tooltip=summary)
            elif status in ("unknown", "uncertain"):
                drives = prof.get("ssd_firmware") or []
                focus = key[4:].strip() if key.startswith("ssd:") else ""
                if key == "bios":
                    summary = fwcat.build_bios_uncertain_inspector_summary(
                        offers,
                        inst,
                        status=status,
                        system_ctx=prof.get("system_ctx") or prof,
                    )
                elif key.startswith("ssd:"):
                    summary = fwcat.build_ssd_uncertain_inspector_summary(
                        offers,
                        drives,
                        status=status,
                        focus_model=focus,
                    )
                else:
                    summary = drvcat.build_uncertain_inspector_summary(
                        offers, inst, status=status
                    )
                brief = self._brief_package_compare_hint(status, offers)
                self._set_catalog_hint(
                    self.fw_hint,
                    brief or "Version compare is Unknown — verify on the vendor site.",
                    tooltip=summary,
                )
            else:
                self._set_catalog_hint(self.fw_hint, "")
        elif cache_row and cache_row.get("_scan_verified"):
            self._fill_driver_compare_table(self.fw_compare_table, [])
            self._set_fw_packages_section_visible(True)
            self.fw_packages_heading.setText("Available packages")
            self._set_catalog_hint(
                self.fw_hint,
                "No package rows saved — run Search for firmware updates.",
            )
        else:
            self._fill_driver_compare_table(self.fw_compare_table, [])
            self._set_fw_packages_section_visible(True)
            self.fw_packages_heading.setText("Available packages")
            if self._fw_needs_vendor_verify(cache_row or {}):
                self._set_catalog_hint(
                    self.fw_hint,
                    self._fw_vendor_verify_hint(cache_row or {}),
                )
            else:
                self._set_catalog_hint(
                    self.fw_hint,
                    "Run ② Search for updates to load catalog packages.",
                )
        self.fw_btn_download.setEnabled(False)
        if hasattr(self, "fw_btn_set_installed"):
            dev_id = (cache_row or {}).get("device_id") or ""
            needs_verify = self._fw_needs_vendor_verify(cache_row)
            self.fw_btn_set_installed.setText(
                "Confirm firmware version…"
                if needs_verify
                else "Set installed firmware…"
            )
            self.fw_btn_set_installed.setEnabled(
                key.startswith("peripheral:") and bool(dev_id)
            )
            tip = (
                "After checking in the vendor app/updater, save the MCU firmware "
                "version here so future scans can compare accurately."
                if needs_verify
                else (
                    "Save the MCU firmware version you confirmed in a vendor updater "
                    "(used for USB peripherals when Windows only reports the HID driver)."
                )
            )
            self.fw_btn_set_installed.setToolTip(tip)
