"""Run ordered vendor HTTP fetch steps; record failures for diagnostics.

This module does **not** modify the application or download new endpoint configs.
When a step fails, the next predefined step runs in the same session only.
Updating which steps exist requires a normal software release (see scripts/audit_vendor_apis.py).

Also tracks **parser rot**: page/response was obtained but no version could be
extracted (T1). That signal feeds ``session_vendor_failures`` so the existing
post-scan Repair prompt fires even when the HTTP fetch itself "succeeded."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class FetchStep(Generic[T]):
    name: str
    run: Callable[[], T | None]


@dataclass
class FetchResult(Generic[T]):
    value: T | None
    method: str = ""
    failures: list[str] = field(default_factory=list)


_LAST_FETCH_DIAG: dict[str, FetchResult] = {}
# vendor → detail strings for "got content / applicable, but no version"
_EMPTY_EXTRACTION: dict[str, list[str]] = {}


def last_fetch_diag(vendor: str) -> FetchResult | None:
    return _LAST_FETCH_DIAG.get((vendor or "").lower())


def record_empty_extraction(vendor: str, detail: str = "") -> None:
    """Mark that a vendor page/response loaded but yielded no version (parser rot)."""
    key = (vendor or "").strip().lower()
    if not key:
        return
    msg = (detail or "page loaded but no version extracted").strip()
    bucket = _EMPTY_EXTRACTION.setdefault(key, [])
    if msg not in bucket:
        bucket.append(msg)


def empty_extraction_details(vendor: str | None = None) -> dict[str, list[str]]:
    """Return empty-extraction details; optionally filter to one vendor."""
    if vendor:
        key = vendor.lower()
        return {key: list(_EMPTY_EXTRACTION.get(key) or [])} if key in _EMPTY_EXTRACTION else {}
    return {k: list(v) for k, v in _EMPTY_EXTRACTION.items()}


def clear_session_diagnostics() -> None:
    """Reset fetch + empty-extraction session state (tests / new scan)."""
    _LAST_FETCH_DIAG.clear()
    _EMPTY_EXTRACTION.clear()


def run_steps(steps: list[FetchStep[T]], *, vendor: str = "") -> FetchResult[T]:
    """Try steps in order; return first non-None result and record failed attempts."""
    failures: list[str] = []
    for step in steps:
        try:
            val = step.run()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{step.name}: {exc}")
            continue
        if val is not None:
            result = FetchResult(value=val, method=step.name, failures=failures)
            if vendor:
                _LAST_FETCH_DIAG[vendor.lower()] = result
            return result
        failures.append(f"{step.name}: no data")
    # Every step failed. Report that, rather than reusing this vendor's last successful
    # value: the cache key is only the vendor name, so a second device of the same vendor
    # (AMD GPU + AMD chipset, Intel graphics + Intel Wi-Fi) would inherit an unrelated
    # device's version. It also made vendor_endpoint_health call a dead endpoint healthy,
    # since it derives `ok` from the returned version.
    result = FetchResult(value=None, failures=failures)
    if vendor:
        _LAST_FETCH_DIAG[vendor.lower()] = result
    return result
