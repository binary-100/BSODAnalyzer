"""One-shot: move offer pipeline helpers from driver_catalog.py to catalog_offer_pipeline.py."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "driver_catalog.py"
PIPELINE = ROOT / "catalog_offer_pipeline.py"

NAMES = {
    "offer_source_sort_tier",
    "_installed_driver_date_from_ctx",
    "sort_catalog_offers",
    "_offer_installability_rank",
    "_append_compare_note",
    "resolve_uncertain_catalog_offers",
    "filter_offers_for_display",
    "annotate_offer_source_conflicts",
    "offer_source_conflict_summary",
    "enrich_offers_with_comparison",
    "_finalize_catalog_offers",
    "finalize_catalog_offers",
    "enrich_firmware_offers_with_comparison",
}

ASSIGN_NAMES = {
    "_STATUS_RANK",
    "_UNVERIFIED_NEWER_NOTE",
    "_SAME_WITHOUT_VERSION_NOTE",
}

MODULE_HEADER = '''\
"""Catalog offer enrich/sort/filter pipeline (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_scoring import compare_firmware_versions, compare_versions


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


'''

# Names resolved through _dc() inside moved bodies (replace direct calls).
_LAZY_DC_FUNCS = (
    "_offer_download_kind",
    "_offer_version_from_fields",
    "_offer_has_installable_package",
    "_recompare_offer_row",
    "_try_resolve_uncertain_offer",
    "_is_informational_catalog_offer",
)

_LAZY_DC_CONST = ("_DOWNLOAD_EXTENSIONS",)


def _patch_lazy_refs(source: str) -> str:
    for name in _LAZY_DC_FUNCS:
        source = source.replace(f"{name}(", f"_dc('{name}')(")
    for name in _LAZY_DC_CONST:
        source = source.replace(name, f"_dc('{name}')")
    return source


def main() -> int:
    src = CATALOG.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    extracted: list[tuple[int, str]] = []
    remove_ranges: list[tuple[int, int]] = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name not in NAMES:
                continue
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            chunk = _patch_lazy_refs("".join(lines[start:end]))
            extracted.append((start, chunk))
            remove_ranges.append((start, end))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ASSIGN_NAMES:
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    extracted.append((start, "".join(lines[start:end]) + "\n"))
                    remove_ranges.append((start, end))

    expected = len(NAMES) + len(ASSIGN_NAMES)
    if len(extracted) != expected:
        found = set(NAMES)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in NAMES:
                found.discard(node.name)
        print(f"Missing defs: {sorted(found)}", file=sys.stderr)
        print(f"Got {len(extracted)} expected {expected}", file=sys.stderr)
        return 1

    if PIPELINE.is_file() and "def sort_catalog_offers(" in PIPELINE.read_text(encoding="utf-8"):
        print("Already extracted — skip", file=sys.stderr)
        return 0

    extracted.sort(key=lambda x: x[0])
    body = "\n\n".join(c.rstrip() for _, c in extracted) + "\n"
    PIPELINE.write_text(MODULE_HEADER + body, encoding="utf-8")

    new_lines = list(lines)
    for start, end in sorted(remove_ranges, reverse=True):
        del new_lines[start:end]
    CATALOG.write_text("".join(new_lines), encoding="utf-8")

    import_block = """from catalog_offer_pipeline import (
    annotate_offer_source_conflicts,
    enrich_firmware_offers_with_comparison,
    enrich_offers_with_comparison,
    filter_offers_for_display,
    finalize_catalog_offers,
    offer_source_conflict_summary,
    offer_source_sort_tier,
    sort_catalog_offers,
    _finalize_catalog_offers,
)
"""
    cat = CATALOG.read_text(encoding="utf-8")
    anchor = "from catalog_scoring import ("
    if import_block.strip() not in cat:
        # Insert after catalog_scoring import block.
        end_idx = cat.find(")\n\n# Re-use project helpers")
        if end_idx == -1:
            print("Could not find insert point for pipeline imports", file=sys.stderr)
            return 1
        cat = cat[: end_idx + 2] + "\n" + import_block + cat[end_idx + 2 :]
        CATALOG.write_text(cat, encoding="utf-8")

    print(f"Extracted {len(extracted)} blocks into catalog_offer_pipeline.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
