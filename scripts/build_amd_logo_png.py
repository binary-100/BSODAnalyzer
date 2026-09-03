"""Build assets/vendor_icons/amd.png from the approved clean AMD arrow vector.

The mark is drawn as crisp anti-aliased polygons (no bitmap tracing):
  * equal-thickness ARROWHEAD (top + right bars) whose 45 deg inner edges reach
    exactly to the hole's TL / BR corners (the arrowhead "makes" those corners);
  * a compact TAIL (left + bottom bars) whose tips sit back from the hole corners
    by SETBACK, so the two arrows come close but never touch across the notch;
  * a centred square negative space; symmetric about the TR->BL (anti) diagonal.

Records of all three background treatments (transparent / black / white) are
written to assets/vendor_icons/amd_variants/ so the shipped background can be
switched later with a single flag. By default the BLACK variant is installed as
the live icon (amd.png). The GUI strips the black matte when painting the icon
so the approved mark blends into table rows (see gui_vendor_icons.py).

    py -3 scripts/build_amd_logo_png.py                 # install black (default)
    py -3 scripts/build_amd_logo_png.py --background white
    py -3 scripts/build_amd_logo_png.py --background transparent
    py -3 scripts/build_amd_logo_png.py --skip-if-current
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "assets" / "vendor_icons"
OUT = ICON_DIR / "amd.png"
VARIANTS_DIR = ICON_DIR / "amd_variants"

AMD_RED = (0xED, 0x1C, 0x24)

# Approved v6.2.3+ geometry on black (user-reviewed Jul 2026). Builds must not drift.
AMD_PNG_MD5_BLACK = "13f64ac7a99b47b2dbc0131e4e78e3c7"

# --- geometry on a 100x100 box (y down) -------------------------------------
M = 8            # outer margin (transparent padding)
B = 100 - M      # far edge (92)
T_HEAD = 25      # arrowhead bar thickness
T_TAIL = 25      # tail bar thickness (equal => centred square hole)
G = 0            # arrowhead inner edge runs corner-to-corner (no set-back barb)
SETBACK = 3      # how far the tail tips sit back from the hole corners

# Backgrounds available for the installed icon; records are kept for all of them.
BACKGROUNDS: dict[str, tuple[int, int, int, int] | None] = {
    "transparent": None,
    "black": (0, 0, 0, 255),
    "white": (255, 255, 255, 255),
}


def _reflect_anti(pts):
    """Reflect across the anti-diagonal (top-right -> lower-left axis)."""
    return [(100 - y, 100 - x) for (x, y) in pts]


def draw_arrow(poly_scale: int = 8, size: int = 512):
    """Return the red-on-transparent AMD arrow as an anti-aliased RGBA image."""
    from PIL import Image, ImageDraw

    S = 100 * poly_scale
    img = Image.new("RGBA", (S, S), (*AMD_RED, 0))
    d = ImageDraw.Draw(img)

    def sc(pts):
        return [(x * poly_scale, y * poly_scale) for x, y in pts]

    top_bar = [(M + G, M), (B, M), (B, M + T_HEAD), (M + T_HEAD + G, M + T_HEAD)]
    right_bar = _reflect_anti(top_bar)

    h_top = M + T_HEAD
    h_left = M + T_TAIL
    h_bottom = B - T_TAIL

    tip = h_top + SETBACK
    left_arm = [
        (h_left, tip),
        (M, tip + (h_left - M)),
        (M, B),
        (h_left, h_bottom),
    ]
    bottom_arm = _reflect_anti(left_arm)

    for quad in (top_bar, right_bar, bottom_arm, left_arm):
        d.polygon(sc(quad), fill=(*AMD_RED, 255))

    return img.resize((size, size), Image.Resampling.LANCZOS)


def _file_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _composite(arrow, background):
    from PIL import Image

    if background is None:
        return arrow.copy()
    base = Image.new("RGBA", arrow.size, background)
    base.alpha_composite(arrow)
    return base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--background",
        choices=sorted(BACKGROUNDS),
        default="black",
        help="Background treatment to install as amd.png (default: black).",
    )
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument(
        "--skip-if-current",
        action="store_true",
        help="Exit 0 without rewriting amd.png when the installed file already matches "
        "the approved black-background hash (safe for CI builds).",
    )
    args = parser.parse_args()

    if (
        args.skip_if_current
        and args.background == "black"
        and OUT.is_file()
        and _file_md5(OUT) == AMD_PNG_MD5_BLACK
    ):
        print(f"amd.png already matches approved hash — skipping rebuild ({OUT})")
        return 0

    try:
        arrow = draw_arrow(size=args.size)
    except ImportError:
        print("Pillow (PIL) is required to build the AMD logo.", file=sys.stderr)
        return 1

    # Write records of every background treatment so we can switch later.
    VARIANTS_DIR.mkdir(parents=True, exist_ok=True)
    for name, bg in BACKGROUNDS.items():
        variant = _composite(arrow, bg)
        variant.save(VARIANTS_DIR / f"amd_{name}.png", format="PNG")

    # Install the selected background as the live icon; drop any stale .svg.
    svg = OUT.with_suffix(".svg")
    if svg.is_file():
        svg.unlink()
    _composite(arrow, BACKGROUNDS[args.background]).save(OUT, format="PNG")

    if args.background == "black" and _file_md5(OUT) != AMD_PNG_MD5_BLACK:
        print(
            f"ERROR: {OUT} MD5 {_file_md5(OUT)} != approved {AMD_PNG_MD5_BLACK}",
            file=sys.stderr,
        )
        return 1

    print(f"Wrote {OUT} (background={args.background})")
    print(f"Records in {VARIANTS_DIR}: " + ", ".join(f"amd_{n}.png" for n in BACKGROUNDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
