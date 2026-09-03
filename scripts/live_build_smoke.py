"""Post-build smoke tests — frozen exe probes + live API checks.

Usage:
  py -3 scripts/live_build_smoke.py --quick
  py -3 scripts/live_build_smoke.py --skip-cli --max-devices 2
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_EXE = ROOT / "BSODAnalyzer_v6" / "BSODAnalyzer.exe"
_SUBPROC_ENV = {**os.environ, "BSOD_NO_PAUSE": "1"}


def _emit(report: dict, path: Path | None) -> None:
    text = json.dumps(report, indent=2)
    print(text, flush=True)
    if path:
        path.write_text(text, encoding="utf-8")


def _gui_launch_smoke(exe: Path, *, wait_sec: float = 6.0) -> dict:
    """Default frozen entry is GUI — verify process starts and survives briefly."""
    try:
        proc = subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_SUBPROC_ENV,
        )
    except OSError as exc:
        return {"exit_code": -1, "error": str(exc)}
    time.sleep(wait_sec)
    code = proc.poll()
    if code is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        return {"exit_code": 0, "note": f"GUI process alive after {wait_sec}s"}
    return {"exit_code": code, "error": f"GUI exited early with code {code}"}


def _run_exe(exe: Path, args: list[str], *, stdin: str = "", timeout: int = 180) -> dict:
    cmd = [str(exe), *args]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(exe.parent),
            env=_SUBPROC_ENV,
        )
        elapsed = round(time.monotonic() - t0, 2)
        return {
            "cmd": " ".join(cmd),
            "exit_code": proc.returncode,
            "elapsed_sec": elapsed,
            "stdout": (proc.stdout or "").strip()[:4000],
            "stderr": (proc.stderr or "").strip()[:2000],
        }
    except subprocess.TimeoutExpired:
        return {
            "cmd": " ".join(cmd),
            "exit_code": -1,
            "elapsed_sec": timeout,
            "error": "timeout",
        }
    except OSError as exc:
        return {"cmd": " ".join(cmd), "exit_code": -1, "error": str(exc)}


def _live_api_report(*, fast: bool, run_scan: bool, max_devices: int) -> dict:
    import importlib.util

    path = ROOT / "scripts" / "live_machine_probe.py"
    spec = importlib.util.spec_from_file_location("live_machine_probe", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_report(
        run_scan=run_scan and not fast,
        max_devices=max_devices,
        fast=fast,
        network_timeout_sec=20.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="BSOD Analyzer post-build smoke tests")
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--skip-cli", action="store_true")
    parser.add_argument("--skip-api", action="store_true", help="Skip network live API probe")
    parser.add_argument("--skip-gui", action="store_true")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Probes + vendor health only (no full driver scan, no CLI analysis)",
    )
    parser.add_argument("--max-devices", type=int, default=2, help="Devices for --scan (default 2)")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "live_smoke_report.json",
        help="Write incremental JSON report here",
    )
    args = parser.parse_args()
    exe: Path = args.exe.resolve()
    out_path: Path = args.out.resolve()

    report: dict = {"exe": str(exe), "exists": exe.is_file(), "probes": {}, "failures": []}
    _emit(report, out_path)

    if not exe.is_file():
        report["failures"].append(f"Missing executable: {exe}")
        report["pass"] = False
        _emit(report, out_path)
        return 1

    report["probes"]["cdb"] = _run_exe(exe, ["--probe-cdb"], timeout=60)
    if report["probes"]["cdb"].get("exit_code") != 0:
        report["failures"].append("CDB probe failed")
    _emit(report, out_path)

    report["probes"]["mscatalog"] = _run_exe(exe, ["--probe-mscatalog"], timeout=60)
    if report["probes"]["mscatalog"].get("exit_code") != 0:
        report["failures"].append("MSCatalog module probe failed")
    _emit(report, out_path)

    if not args.skip_gui:
        report["probes"]["gui_launch"] = _gui_launch_smoke(exe)
        if report["probes"]["gui_launch"].get("exit_code") != 0:
            report["failures"].append("GUI failed to stay running for smoke window")
        _emit(report, out_path)

    run_cli = not args.skip_cli and not args.quick
    if run_cli:
        # Frozen CLI shows a MessageBox on exit unless BSOD_NO_PAUSE=1 (set in env).
        report["probes"]["cli_analysis"] = _run_exe(
            exe,
            ["--cli"],
            stdin="N\nN\n",
            timeout=120,
        )
        cli = report["probes"]["cli_analysis"]
        if cli.get("error") == "timeout":
            report["failures"].append(
                "CLI analysis timed out (UAC relaunch or blocking dialog — run smoke as admin or use --skip-cli)"
            )
        else:
            out = (cli.get("stdout") or "").lower()
            if cli.get("exit_code") != 0:
                report["failures"].append("CLI analysis exited non-zero")
            elif "bsod analyzer" not in out and "analyzing" not in out:
                report["failures"].append("CLI analysis produced unexpected output")
        _emit(report, out_path)

    if not args.skip_api:
        try:
            report["live_api"] = _live_api_report(
                fast=args.quick,
                run_scan=not args.quick,
                max_devices=max(1, args.max_devices),
            )
            if args.quick:
                probes = (report["live_api"] or {}).get("vendor_probes") or {}
                for name, row in probes.items():
                    if (row or {}).get("skipped"):
                        continue
                    if not (row or {}).get("ok"):
                        err = (row or {}).get("error") or "no version"
                        report["failures"].append(f"{name} probe failed: {err}")
                report["live_api_summary"] = report["live_api"]
            else:
                scan = (report["live_api"] or {}).get("scan_simulation") or {}
                vendor = (report["live_api"] or {}).get("vendor_health") or []
                broken = [r for r in vendor if not r.get("ok")]
                if broken:
                    report["failures"].append(
                        f"Vendor health broken: {', '.join(r['vendor'] for r in broken)}"
                    )
                nvidia_probe = (report["live_api"] or {}).get("vendor_probes", {}).get("nvidia") or {}
                if not nvidia_probe.get("skipped") and not nvidia_probe.get("ok") and "error" not in nvidia_probe:
                    report["failures"].append("NVIDIA lookup returned no version")
                report["live_api_summary"] = {
                    "scan_elapsed_sec": scan.get("elapsed_sec"),
                    "devices_checked": scan.get("checked_count"),
                    "updates_found": scan.get("update_count"),
                    "chipset": (report["live_api"] or {}).get("chipset_quick"),
                    "vendor_health": vendor,
                    "vendor_probes": (report["live_api"] or {}).get("vendor_probes"),
                    "fix_progress": (report["live_api"] or {}).get("fix_progress"),
                }
        except Exception as exc:
            report["live_api_error"] = str(exc)
            report["failures"].append(f"Live API probe error: {exc}")
        _emit(report, out_path)

    report["pass"] = not report["failures"]
    _emit(report, out_path)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
