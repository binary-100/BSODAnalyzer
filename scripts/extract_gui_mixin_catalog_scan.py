"""Extract catalog scan workers from gui_mixin_catalog.py."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "gui_mixin_catalog.py"
GUI = APP / "bsod_gui_qt.py"

HEADER = '''"""Driver catalog scan workers, batch merge, and progress handlers."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiCatalogScanMixin:
'''

RANGES = [
    (27, 273),  # thread busy through device row selected (excl. package format helpers)
    (618, 1462),  # scan progress through catalog failed (excl. compare table fill)
]

MRO_ANCHOR = "    GuiFirmwareMixin,\n    GuiCatalogMixin,"
MRO_INSERT = "    GuiCatalogScanMixin,\n"


def _extract(lines: list[str], ranges: list[tuple[int, int]]) -> str:
    chunks: list[str] = []
    for start, end in ranges:
        block = "".join(lines[start - 1 : end])
        if not block.startswith("    def "):
            raise SystemExit(f"Expected methods at {start}-{end}, got {block[:60]!r}")
        chunks.append(block.rstrip("\n"))
    return "\n\n".join(chunks) + "\n"


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    body = _extract(lines, RANGES)
    out = APP / "gui_mixin_catalog_scan.py"
    out.write_text(HEADER + body, encoding="utf-8")
    print(f"Wrote {out} ({len(body.splitlines())} lines)")

    for start, end in sorted(RANGES, reverse=True):
        del lines[start - 1 : end]

    SRC.write_text("".join(lines), encoding="utf-8")
    print(f"Updated {SRC} ({len(lines)} lines)")

    gui = GUI.read_text(encoding="utf-8")
    if "GuiCatalogScanMixin" not in gui:
        gui = gui.replace(
            "from gui_mixin_catalog import GuiCatalogMixin\n",
            "from gui_mixin_catalog import GuiCatalogMixin\n"
            "from gui_mixin_catalog_scan import GuiCatalogScanMixin\n",
        )
        gui = gui.replace(MRO_ANCHOR, "    GuiFirmwareMixin,\n" + MRO_INSERT + "    GuiCatalogMixin,")
    GUI.write_text(gui, encoding="utf-8")
    print(f"Updated {GUI}")


if __name__ == "__main__":
    main()
