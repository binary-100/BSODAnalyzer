"""Extract hardware profile + driver inventory workers from gui_mixin_drivers.py."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "gui_mixin_drivers.py"
GUI = APP / "bsod_gui_qt.py"

HEADER = '''"""Hardware profile scan and full driver inventory loading."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiDriversInventoryMixin:
'''

RANGES = [
    (8, 316),
    (925, 1111),
    (1314, 1598),
]

MRO_ANCHOR = "    GuiDriversTableMixin,\n    GuiDriversMixin,"
MRO_INSERT = "    GuiDriversInventoryMixin,\n"


def _body(lines: list[str], ranges: list[tuple[int, int]]) -> str:
    chunks = []
    for start, end in ranges:
        block = "".join(lines[start - 1 : end])
        chunks.append(block.rstrip("\n"))
    return "\n\n".join(chunks) + "\n"


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    body = _body(lines, RANGES)
    (APP / "gui_mixin_drivers_inventory.py").write_text(HEADER + body, encoding="utf-8")
    print(f"Wrote gui_mixin_drivers_inventory.py ({len(body.splitlines())} lines)")

    for start, end in sorted(RANGES, reverse=True):
        del lines[start - 1 : end]

    SRC.write_text("".join(lines), encoding="utf-8")
    print(f"Updated gui_mixin_drivers.py ({len(lines)} lines)")

    gui = GUI.read_text(encoding="utf-8")
    if "GuiDriversInventoryMixin" not in gui:
        gui = gui.replace(
            "from gui_mixin_drivers_table import GuiDriversTableMixin\n",
            "from gui_mixin_drivers_table import GuiDriversTableMixin\n"
            "from gui_mixin_drivers_inventory import GuiDriversInventoryMixin\n",
        )
        gui = gui.replace(MRO_ANCHOR, "    GuiDriversTableMixin,\n" + MRO_INSERT + "    GuiDriversMixin,")
    GUI.write_text(gui, encoding="utf-8")
    print("Updated bsod_gui_qt.py")


if __name__ == "__main__":
    main()
