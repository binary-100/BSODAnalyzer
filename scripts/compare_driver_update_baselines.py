"""Compare two driver-update baseline captures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_settings as app_set


def _load(label: str) -> dict:
    out_dir = app_set.local_export_directory()
    path = out_dir / f"BSODAnalyzer_driver_baseline_{label}_latest.json"
    if not path.is_file():
        raise FileNotFoundError(f"No baseline for label {label!r}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _device_map(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for entry in (payload.get("catalog_comparison") or {}).get("devices") or []:
        name = (entry.get("device_name") or "").strip()
        if not name:
            continue
        prev = out.get(name)
        if prev is None:
            out[name] = entry
            continue
        # Prefer successful entries over error stubs when duplicates exist.
        if (prev.get("status") or "") == "error" and (entry.get("status") or "") != "error":
            out[name] = entry
    return out


def compare(before: dict, after: dict) -> str:
    lines = [
        "BSOD Analyzer - driver baseline comparison",
        "=" * 60,
        f"Before: {before.get('label')} @ {before.get('captured_at_local')}",
        f"After:  {after.get('label')} @ {after.get('captured_at_local')}",
        "",
    ]
    before_wmi = {
        (r.get("DeviceName") or ""): r for r in before.get("wmi_signed_drivers") or []
    }
    after_wmi = {
        (r.get("DeviceName") or ""): r for r in after.get("wmi_signed_drivers") or []
    }
    all_names = sorted(set(before_wmi) | set(after_wmi))
    lines.append("WMI signed-driver versions:")
    for name in all_names:
        bv = (before_wmi.get(name) or {}).get("DriverVersion") or "-"
        av = (after_wmi.get(name) or {}).get("DriverVersion") or "-"
        mark = "  (changed)" if bv != av else ""
        lines.append(f"  {name}: {bv} -> {av}{mark}")
    lines.append("")

    ref = before.get("third_party_reference") or {}
    if ref:
        lines.append("Third-party tool reference (from pre-update baseline):")
        for dev, offer in ref.items():
            lines.append(f"  {dev}: v{offer.get('version')}")
        lines.append("")

    bd = _device_map(before)
    ad = _device_map(after)
    lines.append("BSOD Analyzer catalog installed version:")
    for dev in sorted(set(bd) | set(ad)):
        bver = (bd.get(dev) or {}).get("installed_version") or "-"
        aver = (ad.get(dev) or {}).get("installed_version") or "-"
        mark = "  (changed)" if bver != aver else ""
        lines.append(f"  {dev}: {bver} -> {aver}{mark}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: py -3 scripts/compare_driver_update_baselines.py pre_update post_update")
        return 2
    before = _load(sys.argv[1])
    after = _load(sys.argv[2])
    print(compare(before, after))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
