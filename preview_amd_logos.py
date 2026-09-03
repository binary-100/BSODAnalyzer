"""Render AMD logo candidates on the app dark background for user review."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtCore, QtGui
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "preview_amd_logos"
BG = QtGui.QColor("#26262d")  # CARD background in app
RED = "#ED1C24"

CANDIDATES: dict[str, str] = {
    "A — current shipped (v5.4.12)": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 191 191">
  <path fill="#ED1C24" d="M1.597 0H190.803V189.21L138.828 137.235V51.981Z"/>
  <path fill="#ED1C24" d="M138.767 62.397L0 115.903V190.802H74.889L128.394 137.296H53.508Z"/>
</svg>""",
    "B — wiki single path": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 191 191">
  <path fill="#ED1C24" d="M1.597 0H190.803V189.21L138.828 137.235V51.981Zm-0.061 10.416L0 115.903v74.899h74.889l53.506-53.506H53.508Z"/>
</svg>""",
    "C — geometric (equal arms, square hole)": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path fill="#ED1C24" d="M0 0H100V100H72V28H28V72H0V0Z"/>
  <path fill="#ED1C24" d="M100 100H0V72H28V28H72V72H100V100Z"/>
</svg>""",
    "D — geometric bold (thicker arms)": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path fill="#ED1C24" d="M0 0H100V100H66V34H34V66H0V0Z"/>
  <path fill="#ED1C24" d="M100 100H0V66H34V34H66V66H100V100Z"/>
</svg>""",
    "E — classic chevron (45° cut, uniform)": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path fill="#ED1C24" d="M0 0H100V22H78V100H56V78H22V56H0V0Z"/>
  <path fill="#ED1C24" d="M100 100H22V78H44V0H66V22H100V100Z"/>
</svg>""",
    "G — wiki paths scaled to 100": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path fill="#ED1C24" d="M0.836 0H99.896V99.063L72.685 71.851V27.215Z"/>
  <path fill="#ED1C24" d="M72.653 32.668L0 60.682V99.896H39.209L67.221 71.883H28.015Z"/>
</svg>""",
}


def render_svg(svg: str, size: int, *, pad_ratio: float = 0.04) -> QtGui.QPixmap:
    renderer = QSvgRenderer(QtCore.QByteArray(svg.encode("utf-8")))
    pm = QtGui.QPixmap(size, size)
    pm.fill(BG)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pad = max(1, int(size * pad_ratio))
    target = QtCore.QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    renderer.render(p, target)
    p.end()
    return pm


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    sizes = (28, 44)
    for label, svg in CANDIDATES.items():
        key = label.split(" ")[0]
        for size in sizes:
            pm = render_svg(svg, size)
            pm.save(str(OUT / f"{key}_{size}px.png"))
    # Comparison sheet: 2 columns (28px | 44px) x 6 rows
    row_h = 72
    col_w = 220
    sheet = QtGui.QPixmap(col_w * 2 + 40, row_h * len(CANDIDATES) + 40)
    sheet.fill(QtGui.QColor("#1e1e23"))
    p = QtGui.QPainter(sheet)
    p.setPen(QtGui.QColor("#e7e7ec"))
    font = QtGui.QFont("Segoe UI", 10)
    p.setFont(font)
    y = 20
    for label, svg in CANDIDATES.items():
        key = label.split(" ")[0]
        p.drawText(12, y + 18, label)
        for i, size in enumerate(sizes):
            pm = render_svg(svg, size)
            x = 20 + i * (col_w + 20)
            p.drawPixmap(x, y + 24, pm)
            p.drawText(x, y + 20, f"{size}px")
        y += row_h
    p.end()
    sheet.save(str(OUT / "comparison_sheet.png"))
    print(f"Wrote {OUT / 'comparison_sheet.png'}")


if __name__ == "__main__":
    main()
