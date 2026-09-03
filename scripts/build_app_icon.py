"""Extract C4 themed app icons from the approved gallery board PNG.

Source: docs/logo_concept_C4_lens_chip_bug_themes.png (Night / Day / Manly row).

    py -3 scripts/build_app_icon.py

Writes:
  assets/app_icon/app_icon_night.png  (and day, manly)
  assets/app_icon/BSODAnalyzer.ico      (multi-size; Night default for exe shell)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "assets" / "app_icon"
ICO_PATH = OUT_DIR / "BSODAnalyzer.ico"
GALLERY_BOARD = ROOT / "docs" / "logo_concept_C4_lens_chip_bug_themes.png"
PNG_SIZES = (256, 128, 64, 48, 32, 16)
THEMES = ("night", "day", "manly")


def extract_icons_from_gallery(
    board_path: Path,
    *,
    master_size: int = 256,
    canvas_pad: float = 0.10,
) -> dict[str, "Image.Image"]:
    """Crop the three themed icons from the gallery presentation board."""
    from PIL import Image

    board = Image.open(board_path).convert("RGBA")
    width, height = board.size
    col_w = width // 3
    icons: dict[str, Image.Image] = {}
    for index, theme_id in enumerate(THEMES):
        col = board.crop((index * col_w, 0, (index + 1) * col_w, height))
        cw, ch = col.size
        margin_top = int(ch * 0.20)
        margin_bottom = int(ch * 0.14)
        band = col.crop((0, margin_top, cw, ch - margin_bottom))
        bw, bh = band.size
        side = min(bw, bh) - 32
        cx, cy = bw // 2, bh // 2
        left, top = cx - side // 2, cy - side // 2
        icon = band.crop((left, top, left + side, top + side))
        icons[theme_id] = _fit_icon_to_square(icon, master_size, pad=canvas_pad)
    return icons


def _fit_icon_to_square(icon: "Image.Image", size: int, *, pad: float = 0.10) -> "Image.Image":
    """Scale artwork down with even padding so the lens handle is not clipped."""
    from PIL import Image

    inner = max(1, int(size * (1 - 2 * pad)))
    scaled = icon.resize((inner, inner), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = (size - inner) // 2
    canvas.paste(scaled, (offset, offset), scaled)
    return canvas


def main() -> int:
    if not GALLERY_BOARD.is_file():
        print(f"Missing gallery board: {GALLERY_BOARD}", file=sys.stderr)
        return 1

    try:
        from PIL import Image
    except ImportError:
        print("Pillow (PIL) is required to build app icons.", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    icons = extract_icons_from_gallery(GALLERY_BOARD)

    for theme_id, img in icons.items():
        png_path = OUT_DIR / f"app_icon_{theme_id}.png"
        img.save(png_path, format="PNG")
        print(f"Wrote {png_path}")

    night = icons["night"]
    ico_frames = [
        night.resize((size, size), Image.Resampling.LANCZOS) for size in PNG_SIZES
    ]
    ico_frames[0].save(
        ICO_PATH,
        format="ICO",
        sizes=[(im.width, im.height) for im in ico_frames],
        append_images=ico_frames[1:],
    )
    print(f"Wrote {ICO_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
