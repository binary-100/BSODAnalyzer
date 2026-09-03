"""Audit SSD firmware vendor coverage for reference drives (live or fixture)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import firmware_ssd_vendors as fsv


def main() -> int:
    parser = argparse.ArgumentParser(description="SSD firmware vendor coverage audit")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch vendor pages over the network (slow)",
    )
    parser.add_argument(
        "--vendor",
        action="append",
        help="Limit to vendor key(s), e.g. samsung wd",
    )
    args = parser.parse_args()

    profiles = list(fsv.SSD_REFERENCE_PROFILES)
    if args.vendor:
        allow = {v.strip().lower() for v in args.vendor}
        profiles = [p for p in profiles if p.vendor_key in allow]

    html_cache: dict[str, str] = {}
    fixture = ROOT / "tests" / "fixtures" / "samsung_tools_ssd_snippet.html"
    if fixture.is_file():
        html_cache["samsung"] = fixture.read_text(encoding="utf-8")

    results = []
    for prof in profiles:
        row = fsv.audit_reference_profile(
            prof,
            live=args.live,
            html_cache=html_cache if not args.live else None,
        )
        results.append({
            "vendor": prof.vendor_key,
            "model": prof.model,
            "example_installed": prof.example_installed,
            "notes": prof.notes,
            "status": row.get("status"),
            "vs_installed": row.get("vs_installed"),
            "parse_method": row.get("parse_method"),
            "version_found": (row.get("vendor_row") or {}).get("version"),
            "coverage_reason": (row.get("vendor_row") or {}).get("coverage_reason"),
            "url": (row.get("vendor_row") or {}).get("url"),
        })

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    print("=" * 72)
    print("SSD firmware vendor coverage audit")
    print(f"Mode: {'live network' if args.live else 'fixtures + utility stubs'}")
    print("=" * 72)
    for r in results:
        print(
            f"[{r['status']}] {r['vendor']:12} {r['model'][:45]:45} "
            f"installed={r['example_installed'] or '—':12} "
            f"catalog={r['version_found'] or '—'}"
        )
        if r.get("coverage_reason"):
            print(f"         reason: {r['coverage_reason']}")
    print()
    print("Summary:", json.dumps(by_status, indent=2))

    out = ROOT / "firmware_ssd_coverage_audit.json"
    out.write_text(json.dumps({"summary": by_status, "results": results}, indent=2), encoding="utf-8")
    print(f"\nJSON: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
