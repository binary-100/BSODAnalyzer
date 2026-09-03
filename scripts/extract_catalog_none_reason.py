"""Extract none-reason / coverage-gap helpers from driver_catalog.py → catalog_none_reason.py."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]

# Inclusive line range in driver_catalog.py (verify before re-run).
NONE_REASON_RANGE = (2681, 2856)
