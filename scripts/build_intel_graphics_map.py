"""Build bundled data/intel_graphics_products.json — generation buckets for Intel iGPU pages."""
from __future__ import annotations

import json
from pathlib import Path

# Curated Intel download pages (product-page-only version compare).
_BUCKETS = [
    {
        "id": "arc_modern",
        "title": "Intel Arc / Core Ultra graphics (unified WHQL)",
        "download_id": 785597,
        "url": (
            "https://www.intel.com/content/www/us/en/download/785597/"
            "intel-arc-iris-xe-graphics-windows.html"
        ),
        "label_patterns": [
            r"\bArc\s*[AB]\d",
            r"\bArc\s*Graphics\b",
            r"\bCore\s*Ultra\b",
            r"\bUHD\s*Graphics\s*7[67]0\b",
            r"\bIris\s*Xe\b",
        ],
        "pci_dev": [
            "56A0", "56A1", "56A2", "56A5", "56A6", "56B0", "56B1", "56B2",
            "56B3", "56B5", "56B6", "56C0", "56C1", "56C2",
            "7D45", "7D55", "7D60", "7D67", "A780", "A781", "A788", "A789",
            "BGA0", "BGA1", "BGA2",
        ],
    },
    {
        "id": "xe_11_14",
        "title": "Intel 11th–14th Gen processor graphics",
        "download_id": 864990,
        "url": (
            "https://www.intel.com/content/www/us/en/download/864990/"
            "intel-uhd-iris-xe-graphics-windows.html"
        ),
        "label_patterns": [
            r"\bUHD\s*Graphics\s*7[0-5]\d\b",
            r"\bIris\s*Plus\b",
            r"\bIris\s*Xe\b",
            r"\bHD\s*Graphics\s*6[3-5]\d\b",
        ],
        "pci_dev": [
            "9A49", "9A78", "9A70", "9A60", "9A68", "9A59", "9A40",
            "4680", "4688", "4690", "4693", "4626", "4628",
            "A7A0", "A7A1", "A7A8", "A7AA", "A7AC",
            "8A52", "8A53", "8A5A", "8A5B", "8A71", "8A72",
        ],
    },
    {
        "id": "legacy_dch",
        "title": "Intel Graphics DCH (6th–10th Gen floor)",
        "download_id": 19344,
        "url": (
            "https://www.intel.com/content/www/us/en/download/19344/"
            "intel-graphics-windows-dch-drivers.html"
        ),
        "label_patterns": [
            r"\bHD\s*Graphics\s*(5[3-9]\d|6[0-2]\d|630)\b",
            r"\bUHD\s*Graphics\s*6[0-2]\d\b",
            r"\bIris\s*(540|550|650)\b",
        ],
        "pci_dev": [
            "1912", "1916", "191B", "1921", "1926", "1927", "192B", "1932",
            "5912", "5916", "591B", "5921", "5926", "5927",
            "3E90", "3E91", "3E92", "3E93", "3E98", "3E99", "3E9A", "3E9B",
            "9BC4", "9BC5", "9BC6", "9BC8", "9BCA", "9BCC",
        ],
    },
    {
        "id": "arc_pro",
        "title": "Intel Arc Pro graphics",
        "download_id": 741626,
        "url": (
            "https://www.intel.com/content/www/us/en/download/741626/"
            "intel-arc-pro-graphics-windows.html"
        ),
        "label_patterns": [
            r"\bArc\s*Pro\b",
            r"\bArc\s*Pro\s*[AB]\d",
        ],
        "pci_dev": ["56A0", "56A5", "56B0", "56B5"],
    },
]


def main() -> None:
    out_path = Path(__file__).resolve().parents[1] / "data" / "intel_graphics_products.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"bucket_count": len(_BUCKETS), "buckets": _BUCKETS}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(_BUCKETS)} Intel graphics buckets -> {out_path}")
    for b in _BUCKETS:
        print(f"  {b['id']:14}  {b['download_id']}  {b['title']}")


if __name__ == "__main__":
    main()
