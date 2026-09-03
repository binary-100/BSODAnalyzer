"""Extract drivers unified-table UI from gui_mixin_drivers.py."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "gui_mixin_drivers.py"
GUI = APP / "bsod_gui_qt.py"

HEADER = '''"""Drivers tab unified table: row styling, populate, filter, selection."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiDriversTableMixin:
'''

# Row styling through unified-table selection handler.
RANGE = (1289, 2617)

MRO_ANCHOR = "    GuiAnalysisMixin,\n    GuiDriversMixin,"
MRO_INSERT = "    GuiDriversTableMixin,\n"


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = RANGE
    body = "".join(lines[start - 1 : end])
    if not body.startswith("    def _set_device_row_status"):
        raise SystemExit(f"Unexpected block: {body[:80]!r}")
    out = APP / "gui_mixin_drivers_table.py"
    out.write_text(HEADER + body, encoding="utf-8")
    print(f"Wrote {out} ({len(body.splitlines())} lines)")

    del lines[start - 1 : end]
    SRC.write_text("".join(lines), encoding="utf-8")
    print(f"Updated {SRC} ({len(lines)} lines)")

    gui = GUI.read_text(encoding="utf-8")
    if "GuiDriversTableMixin" not in gui:
        gui = gui.replace(
            "from gui_mixin_drivers import GuiDriversMixin\n",
            "from gui_mixin_drivers import GuiDriversMixin\n"
            "from gui_mixin_drivers_table import GuiDriversTableMixin\n",
        )
        gui = gui.replace(MRO_ANCHOR, "    GuiAnalysisMixin,\n" + MRO_INSERT + "    GuiDriversMixin,")
    GUI.write_text(gui, encoding="utf-8")
    print(f"Updated {GUI}")


if __name__ == "__main__":
    main()
