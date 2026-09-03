"""GUI: flag broken vendor lookups and user-approved repair (settings file only)."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

import vendor_endpoint_audit as vea
import vendor_endpoint_health as veh


class GuiVendorHealthMixin:
    _vendor_health_prompted: bool

    def _repair_intro_text(self) -> str:
        lines = [
            "BSOD Analyzer will automatically test NVIDIA, AMD, and Intel driver "
            "lookup sites on the internet, and refresh OEM BIOS/firmware catalog "
            "cache for your PC manufacturer.",
            "",
            "If working page addresses or version-reading rules are found, they are "
            "saved to your settings folder only (vendor_endpoints.json). "
            "The program .exe is not modified.",
        ]
        if (veh.remote_manifest_enabled()):
            lines.extend(
                [
                    "",
                    "This repair may also download an updated lookup catalog from the developer.",
                ]
            )
        lines.extend(["", "Continue?"])
        return "\n".join(lines)

    def _vendor_health_system_ctx(self) -> dict:
        if hasattr(self, "_catalog_system_ctx_from_profile"):
            return self._catalog_system_ctx_from_profile()
        prof = getattr(self, "_hardware_profile", None) or {}
        return dict(prof.get("system_ctx") or {})

    def _show_vendor_health_report(self) -> None:
        ctx = self._vendor_health_system_ctx()
        rows = veh.run_health_check(ctx)
        text = veh.format_health_report(rows)
        broken = veh.broken_vendors(rows)
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Manufacturer lookup health")
        box.setText(text)
        box.setIcon(
            QtWidgets.QMessageBox.Icon.Warning
            if broken
            else QtWidgets.QMessageBox.Icon.Information
        )
        if broken:
            repair = box.addButton(
                "Repair automatically…",
                QtWidgets.QMessageBox.ButtonRole.ActionRole,
            )
            box.addButton(QtWidgets.QMessageBox.StandardButton.Close)
            box.exec()
            if box.clickedButton() == repair:
                self._run_vendor_endpoint_repair()
        else:
            box.exec()

    def _run_vendor_lookup_audit(self) -> None:
        intro = QtWidgets.QMessageBox(self)
        intro.setWindowTitle("Audit manufacturer lookup pages")
        intro.setIcon(QtWidgets.QMessageBox.Icon.Information)
        intro.setText(
            "BSOD Analyzer will test NVIDIA, AMD, and Intel driver lookup pages "
            "against known alternates.\n\n"
            "If a better address is found, you can apply it with one click. "
            "Changes are saved to your settings folder only (vendor_endpoints.json). "
            "The program .exe is not modified.\n\n"
            "Continue?"
        )
        intro.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No
        )
        if intro.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        progress = QtWidgets.QProgressDialog(
            "Auditing manufacturer lookup pages…",
            "",
            0,
            0,
            self,
        )
        progress.setWindowTitle("Audit manufacturer lookup pages")
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        QtWidgets.QApplication.processEvents()

        status_lines: list[str] = []

        def on_progress(msg: str) -> None:
            status_lines.append(msg)
            progress.setLabelText("\n".join(status_lines[-5:]))
            QtWidgets.QApplication.processEvents()

        ctx = self._vendor_health_system_ctx()
        rows = vea.run_lookup_address_audit(ctx, progress=on_progress)
        progress.close()

        text = vea.format_audit_report(rows)
        patches = vea.recommended_patches(rows)
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Lookup page audit")
        box.setText(text)
        broken = any(r.status == "broken" for r in rows)
        box.setIcon(
            QtWidgets.QMessageBox.Icon.Warning
            if broken or patches
            else QtWidgets.QMessageBox.Icon.Information
        )
        apply_btn = None
        if patches:
            apply_btn = box.addButton(
                "Apply recommended updates…",
                QtWidgets.QMessageBox.ButtonRole.ActionRole,
            )
        box.addButton(QtWidgets.QMessageBox.StandardButton.Close)
        box.exec()
        if apply_btn and box.clickedButton() == apply_btn:
            confirm = QtWidgets.QMessageBox.question(
                self,
                "Apply lookup updates",
                f"Save {sum(len(v) for v in patches.values())} recommended lookup address update(s) "
                f"to your settings folder?\n\n"
                "The program .exe will not be modified.",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
            )
            if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
                ok, msg = vea.apply_audit_patches(rows)
                if ok:
                    QtWidgets.QMessageBox.information(self, "Updates applied", msg)
                    self.statusBar().showMessage(msg.split("\n")[0], 10000)
                else:
                    QtWidgets.QMessageBox.warning(self, "Updates not applied", msg)

    def _run_vendor_endpoint_repair(self) -> None:
        intro = QtWidgets.QMessageBox(self)
        intro.setWindowTitle("Repair manufacturer lookups")
        intro.setIcon(QtWidgets.QMessageBox.Icon.Question)
        intro.setText(self._repair_intro_text())
        intro.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No
        )
        if intro.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        progress = QtWidgets.QProgressDialog(
            "Repairing manufacturer lookups…",
            "",
            0,
            0,
            self,
        )
        progress.setWindowTitle("Repair manufacturer lookups")
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        QtWidgets.QApplication.processEvents()

        status_lines: list[str] = []

        def on_progress(msg: str) -> None:
            status_lines.append(msg)
            progress.setLabelText("\n".join(status_lines[-5:]))
            QtWidgets.QApplication.processEvents()

        ok, msg = veh.run_user_repair(progress=on_progress)
        progress.close()

        if ok:
            QtWidgets.QMessageBox.information(self, "Repair complete", msg)
            self.statusBar().showMessage(msg.split("\n")[0], 10000)
        else:
            QtWidgets.QMessageBox.warning(self, "Repair failed", msg)

    def _maybe_warn_vendor_health_after_scan(
        self, *, firmware_scan: bool = False
    ) -> None:
        if getattr(self, "_vendor_health_prompted", False):
            return
        batch = getattr(self, "_driver_batch_comparison", None) or {}
        driver_rows = list(batch.get("devices") or batch.get("drivers") or [])
        fw_comp = getattr(self, "_firmware_comparison", None) or {}
        firmware_offers = list(fw_comp.get("offers") or [])
        failed = set(
            veh.session_vendor_failures(
                self._vendor_health_system_ctx(),
                driver_rows=driver_rows if not firmware_scan else None,
                firmware_offers=firmware_offers if firmware_scan else None,
            )
        )
        if not failed:
            return
        self._vendor_health_prompted = True
        names = ", ".join(sorted(failed))
        # Distinguish reachability failures from parser-rot (page OK, no version).
        try:
            import vendor_fetch as vf

            empty = {
                v for v in failed if (vf.empty_extraction_details(v).get(v) or [])
            }
        except ImportError:
            empty = set()
        scan_label = "Firmware search" if firmware_scan else "Driver search"
        waf_blocked: set[str] = set()
        try:
            import vendor_fetch as vf

            for vendor in failed:
                diag = vf.last_fetch_diag(vendor)
                if not diag or not diag.failures:
                    continue
                blob = " ".join(diag.failures).lower()
                if any(k in blob for k in ("403", "forbidden", "waf", "cloudflare", "captcha")):
                    waf_blocked.add(vendor)
        except ImportError:
            waf_blocked = set()
        if empty and empty == failed:
            body = (
                f"{scan_label} reached one or more manufacturer sites ({names}) but "
                f"could not read a version from the page "
                f"(the site layout may have changed).\n\n"
                "Would you like BSOD Analyzer to repair this automatically now? "
                "(Requires internet; saves settings only — does not modify the program.)"
            )
        elif empty:
            waf_note = ""
            if waf_blocked:
                waf_names = ", ".join(sorted(waf_blocked))
                waf_note = (
                    f"\n\nSome sites ({waf_names}) blocked automated access (bot/WAF) — "
                    "repair may not help until you open the vendor page in a browser."
                )
            body = (
                f"{scan_label} had manufacturer lookup issues ({names}).\n\n"
                "Some sites could not be reached; others loaded but no version could be "
                "read (possible page-layout change)."
                f"{waf_note}\n\n"
                "Would you like BSOD Analyzer to repair this automatically now? "
                "(Requires internet; saves settings only — does not modify the program.)"
            )
        else:
            waf_note = ""
            if waf_blocked:
                waf_names = ", ".join(sorted(waf_blocked))
                waf_note = (
                    f"\n\nBlocked by site protection (WAF/bot check): {waf_names}. "
                    "Automatic repair cannot bypass this — use the vendor site manually."
                )
            body = (
                f"{scan_label} could not reach one or more manufacturer lookup sources "
                f"({names}).\n\n"
                "Version numbers from those sources may be missing or unreliable."
                f"{waf_note}\n\n"
                "Would you like BSOD Analyzer to repair this automatically now? "
                "(Requires internet; saves settings only — does not modify the program.)"
            )
        r = QtWidgets.QMessageBox.warning(
            self,
            "Manufacturer lookup issue",
            body,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        )
        if r == QtWidgets.QMessageBox.StandardButton.Yes:
            self._run_vendor_endpoint_repair()
