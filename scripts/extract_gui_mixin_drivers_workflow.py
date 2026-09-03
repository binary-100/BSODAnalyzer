"""Extract driver workflow + summary UI from gui_mixin_drivers.py."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "gui_mixin_drivers.py"
GUI = APP / "bsod_gui_qt.py"

HEADER = '''"""Drivers tab search workflow, crash-linked catalog, summary/reliability UI."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiDriversWorkflowMixin:
'''

# Workflow, crash-auto-check, timeline/reliability blocks (after small table helpers).
RANGE = (115, 792)

MRO_ANCHOR = "    GuiDriversInventoryMixin,\n    GuiDriversMixin,"
MRO_INSERT = "    GuiDriversWorkflowMixin,\n"


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = RANGE
    body = "".join(lines[start - 1 : end])
    if not body.startswith("    def _apply_driver_only_view_defaults"):
        raise SystemExit(f"Unexpected block: {body[:80]!r}")
    (APP / "gui_mixin_drivers_workflow.py").write_text(HEADER + body, encoding="utf-8")
    print(f"Wrote gui_mixin_drivers_workflow.py ({len(body.splitlines())} lines)")

    del lines[start - 1 : end]
    SRC.write_text("".join(lines), encoding="utf-8")
    print(f"Updated gui_mixin_drivers.py ({len(lines)} lines)")

    gui = GUI.read_text(encoding="utf-8")
    if "GuiDriversWorkflowMixin" not in gui:
        gui = gui.replace(
            "from gui_mixin_drivers_inventory import GuiDriversInventoryMixin\n",
            "from gui_mixin_drivers_inventory import GuiDriversInventoryMixin\n"
            "from gui_mixin_drivers_workflow import GuiDriversWorkflowMixin\n",
        )
        gui = gui.replace(MRO_ANCHOR, "    GuiDriversInventoryMixin,\n" + MRO_INSERT + "    GuiDriversMixin,")
    GUI.write_text(gui, encoding="utf-8")
    print("Updated bsod_gui_qt.py")


if __name__ == "__main__":
    main()
