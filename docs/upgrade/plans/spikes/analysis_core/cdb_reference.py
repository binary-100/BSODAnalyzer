"""CDB reference path for D1 parity — calls production parser when CDB is available."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def cdb_available() -> bool:
    """True when production find_cdb() resolves a CDB binary."""
    try:
        from bsod_minidump import find_cdb

        return bool(find_cdb())
    except ImportError:
        return False


def analyze_minidump_cdb_reference(
    path: str | Path,
    *,
    apply_enrich: bool = True,
) -> dict[str, Any] | None:
    """Run production CDB parse; tag analysis_source for parity reports."""
    try:
        from bsod_minidump import analyze_minidump_with_cdb
    except ImportError:
        return None
    result = analyze_minidump_with_cdb(str(path))
    if result is None:
        return None
    result = dict(result)
    result["analysis_source"] = "cdb"
    result.setdefault("analysis_confidence", "high")
    if apply_enrich:
        result = apply_production_enrich(result) or result
    return result


def apply_production_enrich(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Apply the same post-parse normalization production uses today."""
    if data is None:
        return None
    try:
        from bsod_minidump import enrich_windbg_analysis

        return enrich_windbg_analysis(dict(data))
    except ImportError:
        return data
