"""Remove extracted slices from driver_catalog.py (maintainability batch)."""
from __future__ import annotations

from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "driver_catalog.py"

# 1-based inclusive ranges (from the same snapshot of driver_catalog.py).
REMOVE = [
    (1334, 1401),  # catalog_realtek_queries
    (1903, 2428),  # catalog_offer_compare
    (3240, 3425),  # catalog_mscatalog_queries
]

if __name__ == "__main__":
    lines = CATALOG.read_text(encoding="utf-8").splitlines(keepends=True)
    drop = set()
    for start, end in REMOVE:
        drop.update(range(start, end + 1))
    kept = [line for i, line in enumerate(lines, start=1) if i not in drop]
    CATALOG.write_text("".join(kept), encoding="utf-8")
    print(f"Wrote {CATALOG.name} ({len(kept)} lines)")
