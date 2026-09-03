"""Remove installed-package helpers from driver_catalog.py after catalog_installed_packages extract."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
CATALOG = APP / "driver_catalog.py"

# Inclusive 1-based line ranges to drop (verify against current file before re-run).
DROP_RANGES = (
    (591, 594),
    (1224, 1277),
    (2772, 2842),
)


def main() -> int:
    lines = CATALOG.read_text(encoding="utf-8").splitlines(keepends=True)
    drop = set()
    for start, end in DROP_RANGES:
        drop.update(range(start, end + 1))
    kept = [line for i, line in enumerate(lines, start=1) if i not in drop]
    CATALOG.write_text("".join(kept), encoding="utf-8")
    print(f"Removed {len(drop)} lines from {CATALOG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
