"""Split gui_mixin_firmware.py into workflow, inventory, table, and scan mixins."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "gui_mixin_firmware.py"
GUI = APP / "bsod_gui_qt.py"

HEADER = '''"""{doc}"""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class {cls}:
'''

SLICES: list[tuple[str, str, str, list[tuple[int, int]]]] = [
    (
        "gui_mixin_firmware_workflow.py",
        "GuiFirmwareWorkflowMixin",
        "Firmware tab workflow buttons and component scan entry.",
        [(8, 93)],
    ),
    (
        "gui_mixin_firmware_inventory.py",
        "GuiFirmwareInventoryMixin",
        "SSD inventory workers and unified firmware list build.",
        [(94, 442)],
    ),
    (
        "gui_mixin_firmware_table.py",
        "GuiFirmwareTableMixin",
        "Firmware unified table fill, filter, selection, and comparison cache.",
        [(444, 1272)],
    ),
    (
        "gui_mixin_firmware_scan.py",
        "GuiFirmwareScanMixin",
        "Firmware catalog workers, user-installed MCU version, download.",
        [(1274, 1320), (1402, 1767)],
    ),
]

MRO_OLD = "    GuiFirmwareMixin,"
MRO_NEW = """    GuiFirmwareWorkflowMixin,
    GuiFirmwareInventoryMixin,
    GuiFirmwareTableMixin,
    GuiFirmwareScanMixin,
    GuiFirmwareMixin,"""


def _body(lines: list[str], ranges: list[tuple[int, int]]) -> str:
    chunks = []
    for start, end in ranges:
        block = "".join(lines[start - 1 : end])
        chunks.append(block.rstrip("\n"))
    return "\n\n".join(chunks) + "\n"


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)

    for filename, cls, doc, ranges in SLICES:
        body = _body(lines, ranges)
        (APP / filename).write_text(HEADER.format(doc=doc, cls=cls) + body, encoding="utf-8")
        print(f"Wrote {filename} ({len(body.splitlines())} lines)")

    all_ranges = [r for _f, _c, _d, rs in SLICES for r in rs]
    for start, end in sorted(all_ranges, reverse=True):
        del lines[start - 1 : end]

    SRC.write_text("".join(lines), encoding="utf-8")
    print(f"Updated gui_mixin_firmware.py ({len(lines)} lines)")

    gui = GUI.read_text(encoding="utf-8")
    imports = """
from gui_mixin_firmware_inventory import GuiFirmwareInventoryMixin
from gui_mixin_firmware_scan import GuiFirmwareScanMixin
from gui_mixin_firmware_table import GuiFirmwareTableMixin
from gui_mixin_firmware_workflow import GuiFirmwareWorkflowMixin"""
    if "GuiFirmwareWorkflowMixin" not in gui:
        gui = gui.replace(
            "from gui_mixin_firmware import GuiFirmwareMixin\n",
            "from gui_mixin_firmware import GuiFirmwareMixin\n" + imports.strip() + "\n",
        )
        gui = gui.replace(MRO_OLD, MRO_NEW)
    GUI.write_text(gui, encoding="utf-8")
    print("Updated bsod_gui_qt.py")


if __name__ == "__main__":
    main()
