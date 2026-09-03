"""Run manufacturer lookup health + page audit (CLI mirror of Tools menu checks)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import vendor_endpoint_audit as vea
import vendor_endpoint_health as veh


def _load_system_ctx(use_hardware: bool) -> dict:
    if not use_hardware:
        return {}
    try:
        import bsod_analyzer as core

        prof = core.gather_hardware_profile()
        return dict(prof.get("system_ctx") or {})
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: could not gather hardware profile: {exc}")
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Manufacturer lookup health + page audit")
    parser.add_argument(
        "--no-hardware",
        action="store_true",
        help="Probe all vendors without WMI hardware gating (not recommended)",
    )
    parser.add_argument(
        "--hardware",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text report",
    )
    args = parser.parse_args()
    use_hardware = not args.no_hardware
    if args.hardware:
        use_hardware = True
    ctx = _load_system_ctx(use_hardware)

    health_rows = veh.run_health_check(ctx)
    audit_rows = vea.run_lookup_address_audit(ctx)

    if args.json:
        payload = {
            "hardware_gated": use_hardware,
            "system_ctx": {
                "manufacturer": ctx.get("system_manufacturer"),
                "model": ctx.get("system_model"),
            },
            "health": [
                {
                    "vendor": r.vendor,
                    "label": r.label,
                    "ok": r.ok,
                    "version_sample": r.version_sample,
                    "method": r.method,
                    "detail": r.detail,
                    "failures": r.failures,
                }
                for r in health_rows
            ],
            "audit": [
                {
                    "vendor": r.vendor,
                    "endpoint_key": r.endpoint_key,
                    "label": r.label,
                    "status": r.status,
                    "current_url": r.current_url,
                    "recommended_url": r.recommended_url,
                    "version_sample": r.version_sample,
                    "detail": r.detail,
                }
                for r in audit_rows
            ],
            "recommended_patches": vea.recommended_patches(audit_rows),
        }
        print(json.dumps(payload, indent=2))
    else:
        if ctx:
            print(
                f"Machine: {ctx.get('system_manufacturer')} / {ctx.get('system_model')}\n"
            )
        print("=" * 60)
        print("MANUFACTURER LOOKUP HEALTH (live probe)")
        print("=" * 60)
        for row in health_rows:
            st = "OK" if row.ok else "FAILED"
            print(f"{row.label}: {st}")
            if row.version_sample:
                print(f"  Sample version: {row.version_sample}")
            if row.method:
                print(f"  Method: {row.method}")
            if row.detail:
                print(f"  {row.detail}")
            if row.failures and not row.ok:
                print(f"  Failed steps: {'; '.join(row.failures[:6])}")
            print()

        print("=" * 60)
        print("MANUFACTURER LOOKUP PAGE AUDIT")
        print("=" * 60)
        print(vea.format_audit_report(audit_rows))
        patches = vea.recommended_patches(audit_rows)
        if patches:
            print()
            print("Recommended patches (not applied — use Tools → Audit → Apply in GUI):")
            for vendor, patch in patches.items():
                for key, url in patch.items():
                    print(f"  {vendor}.{key}: {url}")

    health_fails = sum(1 for r in health_rows if not r.ok)
    broken = sum(1 for r in audit_rows if r.status == "broken")
    return 1 if health_fails or broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
