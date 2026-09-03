"""One-shot: split gui_mixin_shell.py into focused mixins."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SHELL = APP / "gui_mixin_shell.py"
GUI = APP / "bsod_gui_qt.py"

SLICES: list[tuple[str, str, str, list[tuple[int, int]]]] = [
    (
        "gui_mixin_task_progress.py",
        "GuiTaskProgressMixin",
        "Task progress bar, catalog-tab mirroring, session progress UI.",
        [(1224, 1407)],
    ),
    (
        "gui_mixin_catalog_layout.py",
        "GuiCatalogLayoutMixin",
        "Catalog tab layout presets, splitters, table chrome, column persist.",
        [(1409, 2005)],
    ),
    (
        "gui_mixin_settings.py",
        "GuiSettingsMixin",
        "App settings, menu bar, theme, preferences, install mode.",
        [(226, 260), (2007, 2390)],
    ),
]

MIXIN_HEADER = '''"""{doc}"""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class {cls}:
'''

SHELL_HEADER = '''"""Main window shell: init, tabs layout, toolbar, placeholders."""
from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiShellMixin:
'''


def _extract_ranges(lines: list[str], ranges: list[tuple[int, int]]) -> str:
    chunks: list[str] = []
    for start, end in ranges:
        block = "".join(lines[start - 1 : end])
        if not block.startswith("    def ") and not block.startswith("    @"):
            raise SystemExit(f"Expected method block at {start}-{end}, got:\n{block[:80]!r}")
        chunks.append(block.rstrip("\n"))
    return "\n\n".join(chunks) + "\n"


def main() -> None:
    lines = SHELL.read_text(encoding="utf-8").splitlines(keepends=True)

    # Validate we still have the expected class header
    text = "".join(lines)
    if "class GuiShellMixin:" not in text:
        raise SystemExit("GuiShellMixin anchor missing")

    all_ranges: list[tuple[int, int]] = []
    for filename, cls, doc, ranges in SLICES:
        all_ranges.extend(ranges)
        body = _extract_ranges(lines, ranges)
        out = APP / filename
        out.write_text(MIXIN_HEADER.format(doc=doc, cls=cls) + body, encoding="utf-8")
        print(f"Wrote {out} ({len(body.splitlines())} lines)")

    for start, end in sorted(all_ranges, reverse=True):
        del lines[start - 1 : end]

    # Rewrite shell: keep module docstring + imports + class with remaining methods
    remaining = "".join(lines)
    if not remaining.lstrip().startswith('"""Main window shell'):
        raise SystemExit("Unexpected shell file shape after extraction")

    # Ensure single class body (init + remaining methods already in lines)
    SHELL.write_text(remaining, encoding="utf-8")
    print(f"Updated {SHELL} ({len(remaining.splitlines())} lines)")

    gui = GUI.read_text(encoding="utf-8")
    imports = """
from gui_mixin_catalog_layout import GuiCatalogLayoutMixin
from gui_mixin_settings import GuiSettingsMixin
from gui_mixin_task_progress import GuiTaskProgressMixin"""
    if "GuiCatalogLayoutMixin" not in gui:
        gui = gui.replace(
            "from gui_mixin_shell import GuiShellMixin\n",
            "from gui_mixin_shell import GuiShellMixin\n"
            "from gui_mixin_catalog_layout import GuiCatalogLayoutMixin\n"
            "from gui_mixin_settings import GuiSettingsMixin\n"
            "from gui_mixin_task_progress import GuiTaskProgressMixin\n",
        )
    mro_old = """class MainWindow(
    GuiShellMixin,
    GuiVendorHealthMixin,"""
    mro_new = """class MainWindow(
    GuiShellMixin,
    GuiSettingsMixin,
    GuiCatalogLayoutMixin,
    GuiTaskProgressMixin,
    GuiVendorHealthMixin,"""
    if mro_new not in gui:
        if mro_old not in gui:
            raise SystemExit("MainWindow MRO anchor not found")
        gui = gui.replace(mro_old, mro_new)
    GUI.write_text(gui, encoding="utf-8")
    print(f"Updated {GUI}")


if __name__ == "__main__":
    main()
