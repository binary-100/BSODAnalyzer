#!/usr/bin/env py -3
"""T3 facade gate — audit + probe + machine proof record."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "scripts"))

from agent_gate_proof import record_gate  # noqa: E402


def _run(script: str) -> int:
    r = subprocess.run([sys.executable, str(APP / "scripts" / script)], cwd=APP)
    return int(r.returncode)


def _facade_metrics() -> dict:
    report = APP / "docs" / "_FACADE_AUDIT_REPORT.txt"
    metrics: dict = {"report": "docs/_FACADE_AUDIT_REPORT.txt"}
    if not report.is_file():
        return metrics
    text = report.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        if line.startswith("exports="):
            parts = line.split()
            for part in parts:
                if "=" in part:
                    k, _, v = part.partition("=")
                    if k in ("exports", "prune_candidates", "facade_symbols_used"):
                        try:
                            metrics[k] = int(v)
                        except ValueError:
                            pass
        if "probe _ba:" in line and "broken" in line:
            try:
                metrics["ba_broken"] = int(line.split("probe _ba:")[1].split("broken")[0].strip())
            except ValueError:
                pass
        if "probe core.*:" in line and "broken" in line:
            try:
                metrics["core_broken"] = int(line.split("probe core.*:")[1].split("broken")[0].strip())
            except ValueError:
                pass
    return metrics


def main() -> int:
    if _run("audit_facade_complete.py") != 0:
        return 1
    if _run("probe_ba_symbols.py") != 0:
        return 1
    record_gate(
        "facade",
        cmd="scripts/verify_facade_gate.py",
        **_facade_metrics(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
