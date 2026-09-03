"""Phase 2: split gui_mixin_catalog.py into packages, install, export mixins."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "gui_mixin_catalog.py"
GUI = APP / "bsod_gui_qt.py"

EXPORT_HEADER = '''"""Catalog scan export payloads and session file writes."""

from __future__ import annotations

from dataclasses import dataclass

from gui_app_context import *  # noqa: F403


@dataclass
class ExportFileChoices:
    include_crash_report: bool = False
    include_catalog_summary: bool = False
    include_catalog_json: bool = False

    def any_selected(self) -> bool:
        return (
            self.include_crash_report
            or self.include_catalog_summary
            or self.include_catalog_json
        )

    def needs_catalog_payload(self) -> bool:
        return self.include_catalog_summary or self.include_catalog_json


class GuiCatalogExportMixin:
'''

PACKAGES_HEADER = '''"""Compare/package table formatting and catalog hint helpers."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiCatalogPackagesMixin:
'''

INSTALL_HEADER = '''"""Driver install, backup, restore, and System Restore actions."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiCatalogInstallMixin:
'''

CATALOG_STUB = '''"""Catalog UI composition anchor and stable re-exports."""

from __future__ import annotations

from gui_mixin_catalog_export import ExportFileChoices


class GuiCatalogMixin:
    """Behavior lives in gui_mixin_catalog_* mixins; kept for import/MRO compatibility."""
'''

SLICES: list[tuple[str, str, list[tuple[int, int]]]] = [
    ("gui_mixin_catalog_packages.py", PACKAGES_HEADER, [(27, 370)]),
    ("gui_mixin_catalog_install.py", INSTALL_HEADER, [(371, 1082)]),
    ("gui_mixin_catalog_export.py", EXPORT_HEADER, [(1083, 1963)]),
]

MRO_OLD = """    GuiCatalogScanMixin,
    GuiCatalogMixin,"""
MRO_NEW = """    GuiCatalogScanMixin,
    GuiCatalogPackagesMixin,
    GuiCatalogInstallMixin,
    GuiCatalogExportMixin,
    GuiCatalogMixin,"""


def _body(lines: list[str], ranges: list[tuple[int, int]]) -> str:
    chunks = []
    for start, end in ranges:
        block = "".join(lines[start - 1 : end])
        chunks.append(block.rstrip("\n"))
    return "\n\n".join(chunks) + "\n"


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)

    # ExportFileChoices lives at top — export slice is methods only; prepend dataclass via header.
    for filename, header, ranges in SLICES:
        body = _body(lines, ranges)
        (APP / filename).write_text(header + body, encoding="utf-8")
        print(f"Wrote {filename} ({len(body.splitlines())} lines)")

    all_ranges = [r for _f, _h, ranges in SLICES for r in ranges]
    for start, end in sorted(all_ranges, reverse=True):
        del lines[start - 1 : end]

    # Replace file with stub (remove old dataclass + empty class body)
    SRC.write_text(CATALOG_STUB, encoding="utf-8")
    print(f"Updated gui_mixin_catalog.py (stub)")

    gui = GUI.read_text(encoding="utf-8")
    for mod, cls in (
        ("gui_mixin_catalog_packages", "GuiCatalogPackagesMixin"),
        ("gui_mixin_catalog_install", "GuiCatalogInstallMixin"),
        ("gui_mixin_catalog_export", "GuiCatalogExportMixin"),
    ):
        imp = f"from {mod} import {cls}\n"
        if cls not in gui:
            gui = gui.replace(
                "from gui_mixin_catalog_scan import GuiCatalogScanMixin\n",
                "from gui_mixin_catalog_scan import GuiCatalogScanMixin\n" + imp,
            )
    if MRO_NEW not in gui:
        gui = gui.replace(MRO_OLD, MRO_NEW)
    GUI.write_text(gui, encoding="utf-8")
    print("Updated bsod_gui_qt.py")


if __name__ == "__main__":
    main()
