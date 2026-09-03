"""Capture pre/post driver-update baseline for Realtek audio + NIC comparison.

Usage:
  py -3 scripts/capture_driver_update_baseline.py --label pre_update
  py -3 scripts/capture_driver_update_baseline.py --label post_update
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_settings as app_set
import bsod_analyzer as core
import bsod_runtime as rt
import driver_catalog as dc


TARGET_DEVICES = (
    "Realtek Audio",
    "Realtek Gaming 2.5GbE Family Controller",
)

THIRD_PARTY_OFFERS = {
    "Realtek Audio": {
        "source": "third_party_update_tool",
        "version": "6.0.9998.1",
        "note": "Reported by user's other driver update tool before this baseline.",
    },
    "Realtek Gaming 2.5GbE Family Controller": {
        "source": "third_party_update_tool",
        "version": "1125.30.50.508",
        "note": "Reported by user's other driver update tool before this baseline.",
    },
}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _powershell_signed_drivers() -> list[dict[str, str]]:
    ps = r"""
Get-CimInstance Win32_PnPSignedDriver |
  Where-Object { $_.DeviceName -match 'Realtek|Gaming 2\.5' } |
  Select-Object DeviceName, DriverVersion, DriverDate, InfName, Manufacturer, DeviceID |
  ConvertTo-Json -Compress
"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = (out.stdout or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError, subprocess.TimeoutExpired):
        pass
    return []


def _pnp_rows_for_devices(pnp_list: list, names: set[str]) -> list[dict]:
    rows: list[dict] = []
    for row in pnp_list or []:
        name = (row.get("name") or row.get("friendly_name") or "").strip()
        if name in names:
            rows.append(_json_safe(row))
    return rows


def _inventory_rows(prof: dict, names: set[str]) -> list[dict]:
    inv = core.device_inventory_for_matching(prof.get("bios_driver_info"))
    out: list[dict] = []
    for row in inv or []:
        name = (row.get("name") or row.get("display_name") or "").strip()
        if name in names:
            out.append(_json_safe(row))
    return out


def _format_text(payload: dict) -> str:
    lines = [
        "BSOD Analyzer — driver update baseline",
        "=" * 60,
        f"Label: {payload.get('label')}",
        f"Captured: {payload.get('captured_at_local')}",
        f"Machine: {payload.get('machine')}",
        "",
        "Third-party tool offers (reference — not installed by BSOD Analyzer):",
    ]
    for dev, offer in (payload.get("third_party_reference") or {}).items():
        lines.append(f"  • {dev}: v{offer.get('version')} ({offer.get('source')})")
    lines.extend(["", "Installed drivers (WMI signed-driver query):", ""])
    for row in payload.get("wmi_signed_drivers") or []:
        lines.append(f"  {row.get('DeviceName')}")
        lines.append(f"    Version: {row.get('DriverVersion')}  Date: {row.get('DriverDate')}")
        lines.append(f"    INF: {row.get('InfName')}  Mfg: {row.get('Manufacturer')}")
        lines.append("")
    lines.append("BSOD Analyzer catalog comparison (live Search simulation):")
    lines.append("")
    for entry in payload.get("catalog_comparison", {}).get("devices") or []:
        name = entry.get("device_name") or "?"
        lines.append(f"  Device: {name}")
        lines.append(f"    Installed: {entry.get('installed_version') or '?'}")
        lines.append(f"    Status: {entry.get('status') or '?'}")
        for offer in entry.get("offers") or []:
            ver = offer.get("version") or "?"
            src = offer.get("source_label") or offer.get("source") or "?"
            vs = offer.get("vs_installed") or "?"
            title = (offer.get("title") or "")[:80]
            lines.append(f"    • [{vs}] {src}: v{ver} — {title}")
        lines.append("")
    lines.extend(
        [
            "Compare after install:",
            "  py -3 scripts/capture_driver_update_baseline.py --label post_update",
            "  py -3 scripts/compare_driver_update_baselines.py pre post",
            "",
        ]
    )
    return "\n".join(lines)


def capture(*, label: str, include_third_party_ref: bool) -> dict:
    print("Gathering hardware profile (WMI + PnP)…")
    prof = core.gather_hardware_profile()
    ctx = dict(prof.get("system_ctx") or {})
    ctx["_gui_driver_catalog"] = True
    pnp = prof.get("pnp_list") or []
    bios = prof.get("bios_driver_info")
    inv = core.device_inventory_for_matching(bios)
    names = set(TARGET_DEVICES)

    print("Running catalog comparison for Realtek Audio + 2.5GbE NIC…")
    dc.set_gui_catalog_session(True)
    try:
        catalog = dc.build_multi_device_driver_comparison(
            list(TARGET_DEVICES),
            pnp,
            inv,
            ctx,
            progress=lambda msg: print(f"  catalog: {str(msg).encode('ascii', 'replace').decode()}"),
        )
    finally:
        dc.set_gui_catalog_session(False)

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "schema": "bsod_analyzer_driver_update_baseline_v1",
        "label": label,
        "captured_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "captured_at_local": now.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "machine": ctx.get("machine_label") or ctx.get("computer_name") or "",
        "target_devices": list(TARGET_DEVICES),
        "third_party_reference": THIRD_PARTY_OFFERS if include_third_party_ref else {},
        "wmi_signed_drivers": _powershell_signed_drivers(),
        "pnp_entities": _pnp_rows_for_devices(pnp, names),
        "inventory_rows": _inventory_rows(prof, names),
        "system_ctx_summary": {
            "gpu_vendor": ctx.get("gpu_vendor"),
            "service_tag": ctx.get("service_tag") or ctx.get("dell_service_tag"),
            "model": ctx.get("model") or ctx.get("system_model"),
        },
        "catalog_comparison": _json_safe(catalog),
        "hardware_profile_elapsed_note": "See catalog_comparison.elapsed_ms",
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--label",
        default="pre_update",
        help="Baseline label (pre_update | post_update | custom)",
    )
    parser.add_argument(
        "--no-third-party-ref",
        action="store_true",
        help="Omit third-party tool version reference block",
    )
    args = parser.parse_args()
    include_ref = not args.no_third_party_ref and args.label == "pre_update"

    payload = capture(label=args.label, include_third_party_ref=include_ref)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = app_set.local_export_directory()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"BSODAnalyzer_driver_baseline_{args.label}_{stamp}.json"
    txt_path = out_dir / f"BSODAnalyzer_driver_baseline_{args.label}_{stamp}.txt"
    latest_json = out_dir / f"BSODAnalyzer_driver_baseline_{args.label}_latest.json"
    latest_txt = out_dir / f"BSODAnalyzer_driver_baseline_{args.label}_latest.txt"

    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    text = _format_text(payload)
    rt.write_text_file_sync(json_path, body)
    rt.write_text_file_sync(txt_path, text)
    rt.write_text_file_sync(latest_json, body)
    rt.write_text_file_sync(latest_txt, text)

    print("")
    print(f"Saved JSON: {json_path}")
    print(f"Saved text: {txt_path}")
    print(f"Latest copies: {latest_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
