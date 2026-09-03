"""Phase 3: catalog tab bridge helpers from gui_mixin_shell.py."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SHELL = APP / "gui_mixin_shell.py"
GUI = APP / "bsod_gui_qt.py"

HEADER = '''"""Catalog tab chrome bridge: include columns, summary lines, stale refresh prompts."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiCatalogShellMixin:
'''

RANGE = (474, 961)
MRO_ANCHOR = "    GuiTabsMixin,\n    GuiVendorHealthMixin,"
MRO_INSERT = "    GuiCatalogShellMixin,\n"


def main() -> None:
    lines = SHELL.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = RANGE
    body = "".join(lines[start - 1 : end])
    if not body.startswith("    def _apply_catalog_tab_accessibility"):
        raise SystemExit(f"Unexpected block at {start}: {body[:80]!r}")
    (APP / "gui_mixin_catalog_shell.py").write_text(HEADER + body, encoding="utf-8")
    print(f"Wrote gui_mixin_catalog_shell.py ({len(body.splitlines())} lines)")

    del lines[start - 1 : end]
    SHELL.write_text("".join(lines), encoding="utf-8")
    print(f"Updated gui_mixin_shell.py ({len(lines)} lines)")

    gui = GUI.read_text(encoding="utf-8")
    if "GuiCatalogShellMixin" not in gui:
        gui = gui.replace(
            "from gui_mixin_tabs import GuiTabsMixin\n",
            "from gui_mixin_tabs import GuiTabsMixin\n"
            "from gui_mixin_catalog_shell import GuiCatalogShellMixin\n",
        )
        gui = gui.replace(MRO_ANCHOR, "    GuiTabsMixin,\n" + MRO_INSERT + "    GuiVendorHealthMixin,")
    GUI.write_text(gui, encoding="utf-8")
    print("Updated bsod_gui_qt.py")


if __name__ == "__main__":
    main()
