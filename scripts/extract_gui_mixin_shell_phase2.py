"""Phase 2: further split gui_mixin_shell.py + move tab builds to drivers/firmware mixins."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SHELL = APP / "gui_mixin_shell.py"
GUI = APP / "bsod_gui_qt.py"
DRIVERS = APP / "gui_mixin_drivers.py"
FIRMWARE = APP / "gui_mixin_firmware.py"

MIXIN_HEADER = '''"""{doc}"""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class {cls}:
'''

NEW_SLICES: list[tuple[str, str, str, list[tuple[int, int]]]] = [
    (
        "gui_mixin_maintenance.py",
        "GuiMaintenanceMixin",
        "Session log hooks and full-install maintenance report/history.",
        [(550, 593), (1087, 1187)],
    ),
    (
        "gui_mixin_lifecycle.py",
        "GuiLifecycleMixin",
        "File-menu snapshots, shutdown, closeEvent, background task teardown.",
        [(1192, 1412)],
    ),
    (
        "gui_mixin_window_chrome.py",
        "GuiWindowChromeMixin",
        "Admin banner, severity dot, bottom toolbar, placeholder glance panel.",
        [(1414, 1468), (2420, 2565)],
    ),
    (
        "gui_mixin_tabs.py",
        "GuiTabsMixin",
        "Tab host wiring and Summary/Action/Details/System/Advanced tab layout.",
        [(1470, 1758), (2372, 2419)],
    ),
]

APPEND_SLICES: list[tuple[Path, str, tuple[int, int]]] = [
    (DRIVERS, "GuiDriversMixin", (1759, 2092)),
    (FIRMWARE, "GuiFirmwareMixin", (2094, 2370)),
]

MRO_INSERT = """    GuiMaintenanceMixin,
    GuiLifecycleMixin,
    GuiWindowChromeMixin,
    GuiTabsMixin,"""

IMPORT_LINES = """
from gui_mixin_lifecycle import GuiLifecycleMixin
from gui_mixin_maintenance import GuiMaintenanceMixin
from gui_mixin_tabs import GuiTabsMixin
from gui_mixin_window_chrome import GuiWindowChromeMixin"""


def _extract_ranges(lines: list[str], ranges: list[tuple[int, int]]) -> str:
    chunks: list[str] = []
    for start, end in ranges:
        block = "".join(lines[start - 1 : end])
        if not block.startswith("    def ") and not block.startswith("    @"):
            raise SystemExit(f"Expected method block at {start}-{end}, got:\n{block[:100]!r}")
        chunks.append(block.rstrip("\n"))
    return "\n\n".join(chunks) + "\n"


def _append_to_class(path: Path, body: str) -> None:
    text = path.read_text(encoding="utf-8").rstrip() + "\n\n" + body
    if not body.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def main() -> None:
    lines = SHELL.read_text(encoding="utf-8").splitlines(keepends=True)

    for filename, cls, doc, ranges in NEW_SLICES:
        body = _extract_ranges(lines, ranges)
        out = APP / filename
        out.write_text(MIXIN_HEADER.format(doc=doc, cls=cls) + body, encoding="utf-8")
        print(f"Wrote {out} ({len(body.splitlines())} lines)")

    for path, _cls, span in APPEND_SLICES:
        body = _extract_ranges(lines, [span])
        _append_to_class(path, body)
        print(f"Appended {len(body.splitlines())} lines to {path.name}")

    all_ranges: list[tuple[int, int]] = []
    for _f, _c, _d, ranges in NEW_SLICES:
        all_ranges.extend(ranges)
    for _p, _c, span in APPEND_SLICES:
        all_ranges.append(span)

    for start, end in sorted(all_ranges, reverse=True):
        del lines[start - 1 : end]

    remaining = "".join(lines)
    SHELL.write_text(remaining, encoding="utf-8")
    print(f"Updated {SHELL} ({len(remaining.splitlines())} lines)")

    gui = GUI.read_text(encoding="utf-8")
    if "GuiMaintenanceMixin" not in gui:
        gui = gui.replace(
            "from gui_mixin_task_progress import GuiTaskProgressMixin\n",
            "from gui_mixin_task_progress import GuiTaskProgressMixin\n"
            + IMPORT_LINES.strip()
            + "\n",
        )
    anchor = "    GuiTaskProgressMixin,\n    GuiVendorHealthMixin,"
    if MRO_INSERT not in gui:
        if anchor not in gui:
            raise SystemExit("MainWindow MRO anchor not found")
        gui = gui.replace(anchor, "    GuiTaskProgressMixin,\n" + MRO_INSERT + "\n    GuiVendorHealthMixin,")
    GUI.write_text(gui, encoding="utf-8")
    print(f"Updated {GUI}")


if __name__ == "__main__":
    main()
