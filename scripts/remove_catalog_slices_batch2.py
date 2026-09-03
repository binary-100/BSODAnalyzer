"""Remove batch-2 slices from driver_catalog.py (one-pass line drop)."""
from __future__ import annotations

from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "driver_catalog.py"

# 1-based inclusive ranges from driver_catalog.py snapshot before removal.
REMOVE = [
    (1147, 1156),  # chipset version helpers
    (1346, 1681),  # chipset platform comparison
    (5741, 5786),  # best_authoritative / best_versioned (now offer_status)
]

if __name__ == "__main__":
    lines = CATALOG.read_text(encoding="utf-8").splitlines(keepends=True)
    drop: set[int] = set()
    for start, end in REMOVE:
        drop.update(range(start, end + 1))
    kept = [line for i, line in enumerate(lines, start=1) if i not in drop]
    CATALOG.write_text("".join(kept), encoding="utf-8")
    print(f"Wrote {CATALOG.name} ({len(kept)} lines)")
