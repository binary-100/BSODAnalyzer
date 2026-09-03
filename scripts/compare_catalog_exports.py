"""Compare two BSOD Analyzer catalog scan JSON exports (cross-machine or before/after).

Usage:
  py -3 scripts/compare_catalog_exports.py path\\to\\scan_a.json path\\to\\scan_b.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import catalog_export as cexp  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip())
        return 2
    path_a = Path(sys.argv[1])
    path_b = Path(sys.argv[2])
    if not path_a.is_file() or not path_b.is_file():
        print("Both arguments must be existing JSON export files.")
        return 1
    payload_a = json.loads(path_a.read_text(encoding="utf-8"))
    payload_b = json.loads(path_b.read_text(encoding="utf-8"))
    print(cexp.compare_catalog_exports(payload_a, payload_b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
