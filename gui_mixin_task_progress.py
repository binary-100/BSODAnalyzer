"""Task progress bar, catalog-tab mirroring, session progress UI."""

from __future__ import annotations

import re

from gui_app_context import *  # noqa: F403

# Substrings that tie progress text to Drivers vs Firmware tab status lines.
_DRIVER_PROGRESS_HINTS = (
    "driver inventory",
    "driver list",
    "load devices",
    "loading full device",
    "device list",
    "hardware scan",
    "scanning hardware",
    "driver catalog",
    "driver update",
    "building device list",
    "enriching device",
    "signed-driver",
    "installed driver",
    "scanning devices",
    "coverage check",
    "scanning crash dumps and driver",
    "reading full driver",
    "driver inventory complete",
    "checking ",
    "checked ",
    " device(s)",
)
_FIRMWARE_PROGRESS_HINTS = (
    "firmware",
    "ssd firmware",
    "warming firmware",
    "firmware component",
)


class GuiTaskProgressMixin:
    def _build_task_progress_bar(self) -> QtWidgets.QWidget:
        frame = QtWidgets.QWidget()
        frame.setObjectName("TaskProgressFrame")
        frame.setVisible(False)
        frame.setFixedHeight(0)
        lay = QtWidgets.QVBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        label = QtWidgets.QLabel("")
        label.setObjectName("TaskProgressCaption")
        label.setWordWrap(True)
        label.setFixedHeight(TASK_PROGRESS_LABEL_LINE_HEIGHT)
        bar = QtWidgets.QProgressBar()
        bar.setObjectName("TaskProgressBar")
        bar.setMinimum(0)
        bar.setMaximum(100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(TASK_PROGRESS_BAR_HEIGHT)
        bar.setMinimumWidth(0)
        bar.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        lay.addWidget(label)
        lay.addWidget(bar)
        self._task_progress_label = label
        self._task_progress = bar
        self._task_progress_frame = frame
        return frame

    def _make_task_progress_widgets(
        self,
        parent: QtWidgets.QWidget,
        *,
        catalog_tab: bool = False,
    ) -> tuple[QtWidgets.QLabel, QtWidgets.QProgressBar]:
        lay = QtWidgets.QHBoxLayout(parent)
        lay.setContentsMargins(CATALOG_CHROME_H_INSET, 4, CATALOG_CHROME_H_INSET, 4)
        lay.setSpacing(8 if not catalog_tab else 0)
        label = QtWidgets.QLabel("")
        label.setObjectName("Muted")
        if catalog_tab:
            label.setVisible(False)
            label.setFixedWidth(0)
            label.setMaximumWidth(0)
        else:
            label.setMaximumWidth(TASK_PROGRESS_LABEL_MAX_WIDTH)
            label.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Ignored,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
        bar = QtWidgets.QProgressBar()
        bar.setMinimum(0)
        bar.setMaximum(100)
        bar.setValue(0)
        bar.setTextVisible(not catalog_tab)
        bar.setFixedHeight(TASK_PROGRESS_BAR_HEIGHT)
        if not catalog_tab:
            bar.setMinimumWidth(240)
        else:
            bar.setMinimumWidth(0)
        bar.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        if catalog_tab:
            lay.addWidget(bar, 1)
        else:
            lay.addWidget(label, 0)
            lay.addWidget(bar, 1)
        return label, bar

    def _build_catalog_tab_progress_row(self, attr_prefix: str) -> QtWidgets.QWidget:
        frame = QtWidgets.QWidget()
        frame.setVisible(False)
        frame.setFixedHeight(0)
        label, bar = self._make_task_progress_widgets(frame, catalog_tab=True)
        setattr(self, f"{attr_prefix}_tab_progress_label", label)
        setattr(self, f"{attr_prefix}_tab_progress_bar", bar)
        setattr(self, f"{attr_prefix}_tab_progress_frame", frame)
        return frame

    def _task_progress_active(self) -> bool:
        """True while a task holds the global progress bar (depth > 0)."""
        return getattr(self, "_task_progress_depth", 0) > 0

    def _task_progress_on_catalog_tab(self) -> bool:
        if not hasattr(self, "tabs"):
            return False
        idx = self.tabs.currentIndex()
        drv_idx = self._drivers_tab_index() if hasattr(self, "_drivers_tab_widget") else -1
        fw_idx = self._firmware_tab_index() if hasattr(self, "_firmware_tab_widget") else -1
        return idx in (drv_idx, fw_idx)

    def _header_progress_visible_on_current_tab(self, label: str | None = None) -> bool:
        """Banner tabs show header progress for log analysis only — not post-analysis catalog work."""
        if self._task_progress_on_catalog_tab():
            return True
        if getattr(self, "_analysis_run_active", False):
            return True
        text = label or ""
        if not text and hasattr(self, "_task_progress_label"):
            text = self._task_progress_label.text() or ""
        return self._progress_domain(text) is None

    def _header_progress_shown(self) -> bool:
        return (
            self._task_progress_active()
            and self._header_progress_visible_on_current_tab()
        )

    @staticmethod
    def _parse_driver_inventory_shard(msg: str) -> tuple[str, int | None, int | None]:
        """Parse 'Driver inventory 2/5 …' shard progress from inventory messages."""
        m = re.search(r"Driver inventory\s+(\d+)/(\d+)", msg or "", re.I)
        if not m:
            return (msg or "").strip(), None, None
        done, total = int(m.group(1)), int(m.group(2))
        if total <= 0:
            return (msg or "").strip(), None, None
        pct = int(100 * done / total)
        return (msg or "").strip(), pct, 100

    @classmethod
    def _progress_domain(cls, label: str) -> str | None:
        """Return 'drivers', 'firmware', or None for general progress."""
        low = (label or "").lower()
        if any(h in low for h in _FIRMWARE_PROGRESS_HINTS):
            if "device(s)" not in low or "firmware" in low:
                return "firmware"
        if any(h in low for h in _DRIVER_PROGRESS_HINTS):
            return "drivers"
        if re.search(r"driver inventory\s+\d+/\d+", low):
            return "drivers"
        return None

    def _format_task_progress_line(self, label: str | None = None) -> str:
        text = (label or self._task_progress_label.text() or "Working…").strip()
        bar = self._task_progress
        if bar.maximum() > 0 and bar.value() >= 0:
            pct = int(round(100 * bar.value() / bar.maximum()))
            return f"{text[:120]} ({pct}%)"
        return text[:200]

    def _refresh_task_progress_caption(self, label: str | None = None) -> None:
        if not hasattr(self, "_task_progress_label"):
            return
        self._task_progress_label.setText(self._format_task_progress_line(label)[:160])

    def _task_progress_frame_height(self, *, catalog: bool) -> int:
        if catalog:
            return TASK_PROGRESS_FRAME_HEIGHT
        return TASK_PROGRESS_BANNER_FRAME_HEIGHT

    def _catalog_status_display(self, label: str) -> str:
        """Status line for a catalog tab — prefer shard detail when present."""
        shard_label, shard_pct, _ = self._parse_driver_inventory_shard(label)
        if shard_pct is not None:
            return f"{shard_label[:160]} ({shard_pct}%)"
        return self._format_task_progress_line(label)

    def _mirror_task_progress_to_catalog_status(self, label: str | None = None) -> None:
        """Mirror global task progress to Drivers/Firmware tab status lines."""
        if not self._task_progress_active():
            return
        domain_label = (label or self._task_progress_label.text() or "Working…").strip()
        domain = self._progress_domain(domain_label)
        display = self._catalog_status_display(domain_label)
        cur = self.tabs.currentIndex() if hasattr(self, "tabs") else -1
        drv_idx = (
            self._drivers_tab_index() if hasattr(self, "_drivers_tab_widget") else -1
        )
        fw_idx = (
            self._firmware_tab_index() if hasattr(self, "_firmware_tab_widget") else -1
        )
        on_drv = cur == drv_idx and drv_idx >= 0
        on_fw = cur == fw_idx and fw_idx >= 0
        if on_drv and hasattr(self, "drv_scan_status"):
            self.drv_scan_status.setText(display[:240])
        elif domain == "drivers" and hasattr(self, "drv_scan_status"):
            self.drv_scan_status.setText(display[:240])
        if on_fw and hasattr(self, "fw_scan_status"):
            self.fw_scan_status.setText(display[:240])
        elif domain == "firmware" and hasattr(self, "fw_scan_status"):
            self.fw_scan_status.setText(display[:240])

    def _sync_task_progress_layout_for_tab(self, index: int | None = None) -> None:
        """Full-width pill bar; banner tabs stack caption above the bar."""
        if not hasattr(self, "_task_progress_label"):
            return
        idx = self.tabs.currentIndex() if index is None else index
        if idx < 0:
            return
        drv_idx = (
            self._drivers_tab_index() if hasattr(self, "_drivers_tab_widget") else -1
        )
        fw_idx = (
            self._firmware_tab_index() if hasattr(self, "_firmware_tab_widget") else -1
        )
        catalog = idx in (drv_idx, fw_idx)
        label = self._task_progress_label
        bar = self._task_progress
        frame = self._task_progress_frame
        if catalog:
            label.setVisible(False)
            label.setFixedHeight(0)
            frame.setProperty("catalogChrome", True)
        else:
            label.setVisible(True)
            label.setFixedHeight(TASK_PROGRESS_LABEL_LINE_HEIGHT)
            frame.setProperty("catalogChrome", False)
            self._refresh_task_progress_caption()
        bar.setMinimumWidth(0)
        bar.setTextVisible(False)
        frame.style().unpolish(frame)
        frame.style().polish(frame)
        self._sync_task_progress_frame_visibility()

    def _sync_task_progress_frame_visibility(self, label: str | None = None) -> None:
        frame = getattr(self, "_task_progress_frame", None)
        if frame is None:
            return
        show = self._header_progress_shown()
        if show:
            catalog = self._task_progress_on_catalog_tab()
            frame.setFixedHeight(self._task_progress_frame_height(catalog=catalog))
            frame.setVisible(True)
        else:
            frame.setFixedHeight(0)
            frame.setVisible(False)

    def _mirror_task_progress_to_catalog_tabs(self) -> None:
        """Keep catalog-tab duplicate progress rows hidden — use the global bar only."""
        for prefix in ("drv", "fw"):
            frame = getattr(self, f"{prefix}_tab_progress_frame", None)
            if frame is not None:
                frame.setVisible(False)
                frame.setFixedHeight(0)

    def _begin_task_progress(
        self,
        label: str,
        *,
        maximum: int = 0,
        value: int = 0,
    ) -> None:
        self._task_progress_depth = getattr(self, "_task_progress_depth", 0) + 1
        self._task_progress_label.setText(label)
        if maximum <= 0:
            self._task_progress.setRange(0, 0)
        else:
            self._task_progress.setRange(0, maximum)
            self._task_progress.setValue(value)
        self._mirror_task_progress_to_catalog_tabs()
        self._sync_task_progress_layout_for_tab()
        self._sync_tab_header_visibility()
        self._mirror_task_progress_to_catalog_status(label)

    def _set_task_progress(
        self,
        value: int | None = None,
        label: str | None = None,
        *,
        maximum: int | None = None,
    ) -> None:
        if getattr(self, "_task_progress_depth", 0) <= 0:
            return
        if label is not None:
            self._task_progress_label.setText(label)
        if maximum is not None:
            if maximum <= 0:
                self._task_progress.setRange(0, 0)
            else:
                self._task_progress.setRange(0, maximum)
        if value is not None and self._task_progress.maximum() > 0:
            self._task_progress.setValue(
                min(value, self._task_progress.maximum())
            )
        self._mirror_task_progress_to_catalog_tabs()
        status_text = (label or self._task_progress_label.text() or "Working…")[:120]
        self.statusBar().showMessage(status_text)
        self._sync_task_progress_layout_for_tab()
        self._sync_tab_header_visibility()
        self._mirror_task_progress_to_catalog_status(label or status_text)

    def _end_task_progress(self) -> None:
        depth = getattr(self, "_task_progress_depth", 0)
        if depth <= 0:
            return
        self._task_progress_depth = depth - 1
        if self._task_progress_depth > 0:
            self._mirror_task_progress_to_catalog_tabs()
            self._sync_task_progress_frame_visibility()
            return
        self._task_progress_frame.setVisible(False)
        self._task_progress_frame.setFixedHeight(0)
        self._task_progress.setRange(0, 100)
        self._task_progress.setValue(0)
        self._mirror_task_progress_to_catalog_tabs()
        self._sync_tab_header_visibility()
        if hasattr(self, "_update_drv_tab_summary_line"):
            self._update_drv_tab_summary_line()
        if hasattr(self, "_update_fw_tab_summary_line"):
            self._update_fw_tab_summary_line()
