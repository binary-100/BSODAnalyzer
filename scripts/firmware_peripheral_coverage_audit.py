"""Audit peripheral firmware vendor support-site search (live or fixtures)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import firmware_peripheral_vendors as fpv


def main() -> int:
    parser = argparse.ArgumentParser(description="Peripheral firmware support-site coverage audit")
    parser.add_argument("--live", action="store_true", help="Fetch vendor sites over the network")
    parser.add_argument("--vendor", action="append", help="Limit to vendor key(s)")
    args = parser.parse_args()

    profiles = list(fpv.PERIPHERAL_REFERENCE_PROFILES)
    if args.vendor:
        allow = {v.strip().lower() for v in args.vendor}
        profiles = [p for p in profiles if p.vendor_key in allow]

    html_cache: dict[str, str] = {}
    fixtures = ROOT / "tests" / "fixtures"
    razer_art = fixtures / "razer_pro_type_ultra_firmware_article_snippet.html"
    if razer_art.is_file():
        url = "https://mysupport.razer.com/app/answers/detail/a_id/6217"
        html_cache[f"article:{fpv._cache_key(url)}"] = razer_art.read_text(encoding="utf-8")

    results = []
    for prof in profiles:
        row = fpv.audit_reference_profile(
            prof,
            live=args.live,
            html_cache=html_cache if not args.live else None,
        )
        vr = row.get("vendor_row") or {}
        results.append({
            "vendor": prof.vendor_key,
            "label": prof.label,
            "notes": prof.notes,
            "status": row.get("status"),
            "version_found": vr.get("version"),
            "url": vr.get("url"),
            "parse_method": vr.get("parse_method"),
            "coverage_reason": vr.get("coverage_reason"),
        })

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    print("=" * 72)
    print("Peripheral firmware support-site audit")
    print(f"Mode: {'live network' if args.live else 'fixtures where available'}")
    print("=" * 72)
    for r in results:
        print(
            f"[{r['status']}] {r['vendor']:12} {r['label'][:40]:40} "
            f"ver={r['version_found'] or '—'}"
        )
        if r.get("url"):
            print(f"         {r['url'][:90]}")
    print("\nSummary:", json.dumps(by_status, indent=2))

    out = ROOT / "firmware_peripheral_coverage_audit.json"
    out.write_text(json.dumps({"summary": by_status, "results": results}, indent=2), encoding="utf-8")
    print(f"\nJSON: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
