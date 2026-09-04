"""Quarantined analysis-core spike — do not import from production source."""

from .contract import (
    ANALYSIS_SOURCES,
    CONFIDENCE_LEVELS,
    empty_dump_analysis,
    normalize_dump_analysis,
)

__all__ = [
    "ANALYSIS_SOURCES",
    "CONFIDENCE_LEVELS",
    "empty_dump_analysis",
    "normalize_dump_analysis",
]
