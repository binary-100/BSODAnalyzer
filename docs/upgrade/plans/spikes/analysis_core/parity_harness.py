"""D1 parity harness — compare native_stub vs CDB on a corpus directory.

Usage (from repo root):
  py -3 docs/upgrade/plans/spikes/analysis_core/parity_harness.py
  py -3 docs/upgrade/plans/spikes/analysis_core/parity_harness.py --corpus path/to/dumps
  py -3 docs/upgrade/plans/spikes/analysis_core/parity_harness.py --strict

Exit codes:
  0 — empty corpus, or all dumps matched under --strict rules
  1 — corpus non-empty and (--strict) any diff or native failed while CDB succeeded
  2 — argument / runtime error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_SPIKE_DIR = Path(__file__).resolve().parent
if str(_SPIKE_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SPIKE_DIR.parent))

from analysis_core.cdb_reference import (  # noqa: E402
    analyze_minidump_cdb_reference,
    apply_production_enrich,
    cdb_available,
)
from analysis_core.contract import parity_field_diff  # noqa: E402
from analysis_core.native_minimal import analyze_minidump_native_stub  # noqa: E402

DEFAULT_CORPUS = _SPIKE_DIR / "corpus"
FIXTURES = _SPIKE_DIR / "fixtures"


@dataclass
class DumpParityRow:
    path: str
    native_ok: bool
    cdb_ok: bool
    diffs: dict = field(default_factory=dict)
    native_source: str | None = None
    cdb_source: str | None = None


@dataclass
class ParityReport:
    corpus_dir: str
    cdb_available: bool
    enrich_applied: bool
    dumps: list[DumpParityRow] = field(default_factory=list)

    @property
    def matched(self) -> int:
        return sum(1 for d in self.dumps if d.native_ok and d.cdb_ok and not d.diffs)

    @property
    def with_diffs(self) -> int:
        return sum(1 for d in self.dumps if d.diffs)

    @property
    def native_failed_cdb_ok(self) -> int:
        return sum(1 for d in self.dumps if d.cdb_ok and not d.native_ok)


def _collect_dump_paths(corpus_dir: Path) -> list[Path]:
    seen: set[str] = set()
    paths: list[Path] = []
    for pattern in ("*.dmp", "*.DMP"):
        for p in sorted(corpus_dir.glob(pattern)):
            key = str(p.resolve()).lower()
            if key not in seen:
                seen.add(key)
                paths.append(p)
    return paths


def run_parity(
    corpus_dir: Path,
    *,
    apply_enrich: bool = True,
) -> ParityReport:
    report = ParityReport(
        corpus_dir=str(corpus_dir.resolve()),
        cdb_available=cdb_available(),
        enrich_applied=apply_enrich,
    )
    if not corpus_dir.is_dir():
        return report

    for dump_path in _collect_dump_paths(corpus_dir):
        native = analyze_minidump_native_stub(dump_path)
        if apply_enrich and native is not None:
            native = apply_production_enrich(native)
        cdb = (
            analyze_minidump_cdb_reference(dump_path, apply_enrich=apply_enrich)
            if report.cdb_available
            else None
        )
        diffs = parity_field_diff(native, cdb) if (native and cdb) else {}
        report.dumps.append(
            DumpParityRow(
                path=str(dump_path),
                native_ok=native is not None,
                cdb_ok=cdb is not None,
                diffs=diffs,
                native_source=(native or {}).get("analysis_source"),
                cdb_source=(cdb or {}).get("analysis_source"),
            )
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Native vs CDB dump parity (D1 spike)")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="Directory containing *.dmp files (gitignored samples)",
    )
    parser.add_argument(
        "--include-fixtures",
        action="store_true",
        help="Also scan spikes/analysis_core/fixtures/*.dmp (checked-in synthetics)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="Exit 0 even when corpus has diffs (default: strict when corpus non-empty)",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Compare without enrich_windbg_analysis on either side",
    )
    args = parser.parse_args(argv)
    apply_enrich = not args.no_enrich

    report = run_parity(args.corpus, apply_enrich=apply_enrich)
    if args.include_fixtures and FIXTURES.is_dir():
        fixture_report = run_parity(FIXTURES, apply_enrich=apply_enrich)
        report.dumps.extend(fixture_report.dumps)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(f"Corpus: {report.corpus_dir}")
        print(f"CDB available: {report.cdb_available}")
        print(f"Enrich applied: {report.enrich_applied}")
        print(f"Dumps scanned: {len(report.dumps)}")
        print(f"Matched (no field diffs): {report.matched}")
        print(f"With diffs: {report.with_diffs}")
        for row in report.dumps:
            status = "OK" if not row.diffs and row.native_ok else "DIFF" if row.diffs else "PARTIAL"
            print(f"  [{status}] {row.path}")
            if row.diffs:
                for field, vals in row.diffs.items():
                    print(f"       {field}: native={vals['native']!r} cdb={vals['cdb']!r}")

    if not report.dumps:
        print(
            "No .dmp files in corpus — add anonymized samples under "
            f"{DEFAULT_CORPUS} (see corpus/README.md and CORPUS_POLICY.md). Exit 0.",
            file=sys.stderr,
        )
        return 0

    strict = len(report.dumps) > 0 and not args.no_strict
    if strict:
        if report.with_diffs > 0 or report.native_failed_cdb_ok > 0:
            print(
                f"Strict parity failed: diffs={report.with_diffs}, "
                f"native_failed_cdb_ok={report.native_failed_cdb_ok}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
