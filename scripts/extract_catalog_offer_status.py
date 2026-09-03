"""Extract offer status helpers from driver_catalog.py → catalog_offer_status.py."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
CATALOG = APP / "driver_catalog.py"

# Inclusive ranges before extraction (offer status + intel chipset inf helper).
RANGES = [(1097, 1100), (2497, 2678)]
