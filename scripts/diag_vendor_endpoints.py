"""Quick vendor endpoint probe — see scripts/audit_vendor_apis.py for the full audit."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    runpy.run_path(str(Path(__file__).resolve().parent / "audit_vendor_apis.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
