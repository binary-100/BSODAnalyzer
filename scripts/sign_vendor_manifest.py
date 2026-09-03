#!/usr/bin/env python3
"""Sign a vendor lookup manifest (HMAC-SHA256) for hosting.

Usage:
  py -3 scripts/sign_vendor_manifest.py path/to/lookup_manifest.json
  py -3 scripts/sign_vendor_manifest.py path/to/lookup_manifest.json --key SECRET
  py -3 scripts/sign_vendor_manifest.py path/to/lookup_manifest.json --print-only

Writes ``signature`` into the JSON (in place unless --print-only). The key must
match ``BUNDLED_MANIFEST_HMAC_KEY`` in the release that will fetch the file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import vendor_endpoint_health as veh


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", help="Path to lookup_manifest.json")
    ap.add_argument(
        "--key",
        default="",
        help="HMAC key (default: BUNDLED_MANIFEST_HMAC_KEY or env BSOD_MANIFEST_HMAC_KEY)",
    )
    ap.add_argument(
        "--print-only",
        action="store_true",
        help="Print signed JSON to stdout; do not overwrite the file",
    )
    args = ap.parse_args()
    path = args.manifest
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        print("Manifest must be a JSON object.", file=sys.stderr)
        return 1
    key = (
        args.key
        or os.environ.get("BSOD_MANIFEST_HMAC_KEY")
        or veh.BUNDLED_MANIFEST_HMAC_KEY
        or ""
    )
    if not key:
        print(
            "No HMAC key: pass --key, set BSOD_MANIFEST_HMAC_KEY, or set "
            "BUNDLED_MANIFEST_HMAC_KEY in vendor_endpoint_health.py.",
            file=sys.stderr,
        )
        return 1
    data.pop("signature", None)
    data["signature"] = veh.sign_manifest(data, key=key)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.print_only:
        sys.stdout.write(text)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Signed {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
