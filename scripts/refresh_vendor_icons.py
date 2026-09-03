#!/usr/bin/env py
"""Refresh bundled vendor SVGs from Simple Icons + known manufacturer sources."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "assets" / "vendor_icons"

# Simple Icons filename slug -> our vendor_key
SIMPLE_ICONS: dict[str, str] = {
    "amd": "amd",
    "intel": "intel",
    "nvidia": "nvidia",
    "dell": "dell",
    "hp": "hp",
    "lenovo": "lenovo",
    "samsung": "samsung",
    "westerndigital": "western_digital",
    "asus": "asus",
    "acer": "acer",
    "msi": "msi",
    "qualcomm": "qualcomm",
    "broadcom": "broadcom",
    "logitech": "logitech",
    "corsair": "corsair",
    "razer": "razer",
    "apple": "apple",
    "seagate": "seagate",
    "sandisk": "sandisk",
    "kingstontechnology": "kingston",
    "alienware": "alienware",
    "mediatek": "mediatek",
    "lg": "lg",
    "vmware": "vmware",
    "virtualbox": "virtualbox",
}

# Keys refreshed from non-Simple-Icons sources (do not overwrite here).
PRESERVE_KEYS = frozenset(
    {"amd", "microsoft", "crucial", "gigabyte", "sk_hynix", "marvell", "synaptics", "realtek"}
)

# Prefer well-known trademark colors over Simple Icons hex where they differ.
COLOR_OVERRIDES: dict[str, str] = {
    "razer": "#44D62C",
    "alienware": "#00AEEF",
    "kingston": "#CC0000",
}

# Light fills for black wordmarks on the app dark theme.
DARK_THEME_FILL: dict[str, str] = {
    "asus": "#E8E8EC",
    "corsair": "#F9E900",
    "apple": "#D0D0D6",
}

SI_JSON = (
    "https://raw.githubusercontent.com/simple-icons/simple-icons/14.0.0/_data/simple-icons.json"
)
SI_SVG = "https://cdn.jsdelivr.net/npm/simple-icons@14.0.0/icons/{slug}.svg"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "BSODAnalyzer-icon-refresh/1.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read()


def slug_to_title(slug: str) -> str:
    special = {
        "westerndigital": "Western Digital",
        "kingstontechnology": "Kingston Technology",
    }
    if slug in special:
        return special[slug]
    return slug.replace("_", " ").title()


def hex_for_slug(slug: str, by_title: dict[str, dict]) -> str | None:
    title = slug_to_title(slug)
    entry = by_title.get(title.lower())
    return entry["hex"] if entry else None


def apply_brand_color(svg: str, hex_color: str, key: str) -> str:
    color = COLOR_OVERRIDES.get(key, f"#{hex_color.lstrip('#')}")
    if key in DARK_THEME_FILL:
        color = DARK_THEME_FILL[key]
    svg = re.sub(r'fill="currentColor"', f'fill="{color}"', svg)
    svg = re.sub(r'fill="#000000"', f'fill="{color}"', svg)
    svg = re.sub(r'fill="#000"', f'fill="{color}"', svg)
    svg = re.sub(
        r"<path(?![^>]*\bfill=)([^>]*)>",
        f'<path fill="{color}"\\1>',
        svg,
    )
    return svg


def main() -> int:
    icons = json.loads(fetch(SI_JSON).decode("utf-8"))
    by_title = {item["title"].lower(): item for item in icons}
    updated: list[str] = []
    skipped: list[str] = []

    for slug, key in SIMPLE_ICONS.items():
        if key in PRESERVE_KEYS:
            skipped.append(f"{key} (preserve)")
            continue
        hex_color = hex_for_slug(slug, by_title)
        if not hex_color:
            skipped.append(f"{key} (no Simple Icons entry for slug: {slug})")
            continue
        try:
            raw = fetch(SI_SVG.format(slug=slug)).decode("utf-8")
        except Exception as exc:
            skipped.append(f"{key} (fetch failed: {exc})")
            continue
        svg = apply_brand_color(raw, hex_color, key)
        out = ICON_DIR / f"{key}.svg"
        out.write_text(svg, encoding="utf-8")
        src = by_title.get(slug_to_title(slug).lower(), {}).get("source", "")
        updated.append(f"{key} <- simple-icons/{slug} ({src})")

    print("Updated:")
    for line in updated:
        print(f"  {line}")
    print("Skipped:")
    for line in skipped:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
