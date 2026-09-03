"""Import smoke for scripts/firmware_peripheral_coverage_audit.py (domain map §H)."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def test_firmware_peripheral_coverage_audit_has_main() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "firmware_peripheral_coverage_audit.py"
    spec = importlib.util.spec_from_file_location("firmware_peripheral_coverage_audit", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(getattr(mod, "main", None))
