"""Compare driver catalog scan timings from session_log.jsonl (read-only).

Does not modify the app or run scans. Parses existing GUI session logs written
during normal **Search for driver updates** runs.

Usage (from app/):
  py -3 scripts/compare_catalog_scan_timings.py
  py -3 scripts/compare_catalog_scan_timings.py --last 10
  py -3 scripts/compare_catalog_scan_timings.py --before 2026-07-21 --after 2026-07-21
  py -3 scripts/compare_catalog_scan_timings.py --json --out catalog_timing_report.json

Windows default log: %%TEMP%%\\BSODAnalyzer\\session_log.jsonl
Full-install log: session_log.log_path() under LOCALAPPDATA.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import session_log as slog


@dataclass(frozen=True)
class ScanRun:
    local_at: str
    devices: int
    elapsed_ms: int
    status: str
    updates: int | None

    @property
    def elapsed_min(self) -> float:
        return self.elapsed_ms / 60_000.0


def _parse_local_date(local_at: str) -> str:
    """YYYY-MM-DD from session log local_at (date portion)."""
    return local_at[:10]


def _device_count(message: str) -> int | None:
    m = re.search(r"Checked (\d+) device", message or "")
    return int(m.group(1)) if m else None


def _update_count(message: str) -> int | None:
    m = re.search(r"(\d+) update\(s\) available", message or "")
    return int(m.group(1)) if m else None


def load_full_scans(
    log_path: Path,
    *,
    min_devices: int = 140,
) -> list[ScanRun]:
    if not log_path.is_file():
        return []
    runs: list[ScanRun] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("kind") != "driver_catalog" or o.get("phase") != "end":
            continue
        elapsed = o.get("elapsed_ms")
        if not isinstance(elapsed, int):
            continue
        msg = o.get("message") or ""
        devices = _device_count(msg)
        if devices is None or devices < min_devices:
            continue
        runs.append(
            ScanRun(
                local_at=o.get("local_at") or o.get("at") or "",
                devices=devices,
                elapsed_ms=elapsed,
                status=str(o.get("status") or ""),
                updates=_update_count(msg),
            )
        )
    return runs


def _percentile(sorted_vals: list[int], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    idx = max(0, min(len(sorted_vals) - 1, int(round(pct * (len(sorted_vals) - 1)))))
    return float(sorted_vals[idx])


@dataclass(frozen=True)
class TimingStats:
    count: int
    min_ms: int
    p50_ms: float
    mean_ms: float
    p95_ms: float
    max_ms: int

    @classmethod
    def from_runs(cls, runs: list[ScanRun]) -> TimingStats | None:
        if not runs:
            return None
        ms = sorted(r.elapsed_ms for r in runs)
        return cls(
            count=len(ms),
            min_ms=ms[0],
            p50_ms=_percentile(ms, 0.50),
            mean_ms=float(statistics.mean(ms)),
            p95_ms=_percentile(ms, 0.95),
            max_ms=ms[-1],
        )

    def as_dict(self) -> dict:
        return {
            "count": self.count,
            "min_min": round(self.min_ms / 60_000, 2),
            "p50_min": round(self.p50_ms / 60_000, 2),
            "mean_min": round(self.mean_ms / 60_000, 2),
            "p95_min": round(self.p95_ms / 60_000, 2),
            "max_min": round(self.max_ms / 60_000, 2),
        }


def filter_runs(
    runs: list[ScanRun],
    *,
    before: str | None = None,
    after: str | None = None,
    last: int | None = None,
) -> list[ScanRun]:
    out = runs
    if before:
        out = [r for r in out if _parse_local_date(r.local_at) < before]
    if after:
        out = [r for r in out if _parse_local_date(r.local_at) >= after]
    if last is not None and last > 0:
        out = out[-last:]
    return out


def format_stats(label: str, stats: TimingStats | None) -> list[str]:
    if stats is None:
        return [f"{label}: (no matching scans)"]
    d = stats.as_dict()
    return [
        f"{label}: n={d['count']}  "
        f"min={d['min_min']:.2f}  p50={d['p50_min']:.2f}  "
        f"mean={d['mean_min']:.2f}  p95={d['p95_min']:.2f}  max={d['max_min']:.2f} min"
    ]


def build_report(
    runs: list[ScanRun],
    *,
    before: str | None,
    after: str | None,
    last: int | None,
    min_devices: int,
    log_path: Path,
) -> dict:
    all_stats = TimingStats.from_runs(runs)
    window = filter_runs(runs, before=before, after=after, last=last)
    window_stats = TimingStats.from_runs(window)
    report: dict = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "log_path": str(log_path),
        "min_devices": min_devices,
        "all_full_scans": all_stats.as_dict() if all_stats else None,
        "filter": {
            "before": before,
            "after": after,
            "last": last,
        },
        "filtered": window_stats.as_dict() if window_stats else None,
        "recent_runs": [
            {
                "local_at": r.local_at,
                "devices": r.devices,
                "elapsed_min": round(r.elapsed_min, 2),
                "updates": r.updates,
                "status": r.status,
            }
            for r in window[-20:]
        ],
    }
    if before and after is None:
        after_runs = filter_runs(runs, after=before)
        after_stats = TimingStats.from_runs(after_runs)
        report["compare"] = {
            "before_date": before,
            "before": TimingStats.from_runs(filter_runs(runs, before=before)).as_dict()
            if runs
            else None,
            "on_or_after": after_stats.as_dict() if after_stats else None,
        }
        if report["compare"]["before"] and after_stats:
            b_p50 = report["compare"]["before"]["p50_min"]
            a_p50 = after_stats.as_dict()["p50_min"]
            report["compare"]["p50_delta_min"] = round(a_p50 - b_p50, 2)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare driver catalog scan timings from session_log.jsonl (read-only).",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Session log path (default: session_log.log_path())",
    )
    parser.add_argument(
        "--min-devices",
        type=int,
        default=140,
        help="Minimum device count to count as a full scan (default: 140)",
    )
    parser.add_argument(
        "--before",
        metavar="YYYY-MM-DD",
        help="Split compare: stats before this date vs on/after (also use with --after to filter a window)",
    )
    parser.add_argument(
        "--after",
        metavar="YYYY-MM-DD",
        help="Only scans on/after this local date",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="After other filters, keep only the last N scans",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON report to stdout",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to this file",
    )
    args = parser.parse_args(argv)

    log_path = args.log or slog.log_path()
    runs = load_full_scans(log_path, min_devices=args.min_devices)
    report = build_report(
        runs,
        before=args.before,
        after=args.after,
        last=args.last,
        min_devices=args.min_devices,
        log_path=log_path,
    )

    if args.json:
        text = json.dumps(report, indent=2)
        print(text)
    else:
        print(f"Session log: {log_path}")
        print(f"Full scans (>={args.min_devices} devices): {len(runs)}")
        for line in format_stats("All time", TimingStats.from_runs(runs)):
            print(line)
        cmp = report.get("compare")
        if args.before and not args.after and cmp and cmp.get("before") and cmp.get("on_or_after"):
            print(
                f"Compare p50: before {cmp['before']['p50_min']:.2f} min  "
                f"-> on/after {cmp['on_or_after']['p50_min']:.2f} min  "
                f"(delta {cmp.get('p50_delta_min', 0):+.2f} min)"
            )
        elif args.after or args.last:
            window = filter_runs(
                runs, before=args.before, after=args.after, last=args.last
            )
            label = "Filtered"
            if args.last:
                label += f" (last {args.last})"
            for line in format_stats(label, TimingStats.from_runs(window)):
                print(line)
        recent = report.get("recent_runs") or []
        if args.after or args.last:
            pass  # recent_runs already reflects filter in build_report
        elif not args.before:
            recent = report.get("recent_runs") or []
        elif cmp and cmp.get("on_or_after"):
            recent = filter_runs(runs, after=args.before)[-20:]
            recent = [
                {
                    "local_at": r.local_at,
                    "devices": r.devices,
                    "elapsed_min": round(r.elapsed_min, 2),
                    "updates": r.updates,
                    "status": r.status,
                }
                for r in recent
            ]
        if recent:
            print("\nRecent runs (up to 20):")
            for row in recent:
                upd = row["updates"]
                upd_s = f", {upd} update(s)" if upd is not None else ""
                print(
                    f"  {row['local_at']}  {row['devices']} devices  "
                    f"{row['elapsed_min']:.2f} min{upd_s}"
                )

    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if not args.json:
            print(f"\nWrote {args.out}")

    return 0 if runs else 1


if __name__ == "__main__":
    raise SystemExit(main())
