"""Dump analysis dict contract — parity target for native vs CDB (D1/D2b).

Production reference: bsod_minidump.analyze_minidump_with_cdb → enrich_windbg_analysis.
See docs/upgrade/plans/ANALYSIS_CORE_PLAN.md § Dump analysis contract.
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

ANALYSIS_SOURCES = frozenset({"native", "cdb", "native_stub", "none"})
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})

AnalysisSource = Literal["native", "cdb", "native_stub", "none"]
ConfidenceLevel = Literal["high", "medium", "low"]

# Production D2b targets native | cdb | none — native_stub is spike-only.
PRODUCTION_ANALYSIS_SOURCES = frozenset({"native", "cdb", "none"})


class DumpAnalysisResult(TypedDict, total=False):
    faulting_driver: str | None
    bugcheck_code: str | None
    bugcheck_p1: str | None
    bugcheck_str: str | None
    failure_bucket_id: str | None
    stack_frames: list[str]
    process_name: str | None
    symbol_name: str | None
    kernel_stack_top: str | None
    actionable_stack_frame: str | None
    raw: list[str]
    analysis_source: AnalysisSource
    analysis_confidence: ConfidenceLevel


PARITY_COMPARE_KEYS = (
    "faulting_driver",
    "bugcheck_code",
    "bugcheck_p1",
    "bugcheck_str",
    "failure_bucket_id",
    "process_name",
    "symbol_name",
    "stack_frames",
)


def empty_dump_analysis(
    *,
    source: AnalysisSource = "none",
    confidence: ConfidenceLevel = "low",
) -> dict[str, Any]:
    return {
        "faulting_driver": None,
        "bugcheck_code": None,
        "bugcheck_p1": None,
        "bugcheck_str": None,
        "failure_bucket_id": None,
        "stack_frames": [],
        "process_name": None,
        "symbol_name": None,
        "kernel_stack_top": None,
        "actionable_stack_frame": None,
        "raw": [],
        "analysis_source": source,
        "analysis_confidence": confidence,
    }


def normalize_dump_analysis(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Ensure list fields and metadata exist; return None if input is None."""
    if data is None:
        return None
    out = empty_dump_analysis(
        source=data.get("analysis_source") or "none",
        confidence=data.get("analysis_confidence") or "low",
    )
    out.update(data)
    frames = out.get("stack_frames")
    out["stack_frames"] = list(frames) if frames else []
    raw = out.get("raw")
    out["raw"] = list(raw) if raw else []
    return out


def parity_field_diff(
    native: dict[str, Any] | None,
    cdb: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Return {field: {native, cdb}} for fields that differ."""
    diffs: dict[str, dict[str, Any]] = {}
    n = normalize_dump_analysis(native) or {}
    c = normalize_dump_analysis(cdb) or {}
    for key in PARITY_COMPARE_KEYS:
        nv, cv = n.get(key), c.get(key)
        if key == "stack_frames":
            if _norm_frames(nv) != _norm_frames(cv):
                diffs[key] = {"native": nv, "cdb": cv}
            continue
        if _norm_val(nv, key=key) != _norm_val(cv, key=key):
            diffs[key] = {"native": nv, "cdb": cv}
    return diffs


def _norm_frames(val: Any) -> tuple[str, ...] | None:
    if not val:
        return None
    if not isinstance(val, (list, tuple)):
        return None
    return tuple(str(x).strip().lower() for x in val if str(x).strip())


def _norm_val(val: Any, *, key: str = "") -> str | None:
    if val is None:
        return None
    if key in ("bugcheck_code", "bugcheck_p1"):
        return _norm_hex(val, width=8 if key == "bugcheck_code" else 16)
    if isinstance(val, str):
        s = val.strip()
        return s.lower() if s else None
    return str(val).strip().lower()


def _norm_hex(val: Any, width: int = 8) -> str | None:
    if val is None:
        return None
    s = str(val).strip().lower()
    m = re.match(r"0x([0-9a-f]+)", s)
    if m:
        try:
            n = int(m.group(1), 16)
            return f"0x{n:0{width}x}"
        except ValueError:
            return s
    return s
