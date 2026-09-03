#!/usr/bin/env py -3
"""Verify machine-readable agent gate proof (AGENT_READINESS § Risk reporting)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPT_DIR))

from agent_gate_proof import PROOF_PATH, verify_gates  # noqa: E402

APP = SCRIPT_DIR.parent

KNOWN_GATES = ("facade", "t2", "t4", "t6")


def main() -> int:
    p = argparse.ArgumentParser(description="Verify agent validation gate proof file.")
    p.add_argument(
        "--require",
        default="",
        help=f"Comma-separated gates to require (known: {', '.join(KNOWN_GATES)})",
    )
    p.add_argument(
        "--max-age-minutes",
        type=float,
        default=720.0,
        help="Max age of recorded gates (default 720 = 12h)",
    )
    p.add_argument(
        "--allow-stale-git",
        action="store_true",
        help="Do not fail when proof git HEAD differs from current HEAD",
    )
    p.add_argument(
        "--no-git-check",
        action="store_true",
        help="Skip git HEAD match entirely",
    )
    p.add_argument("--print-proof", action="store_true", help="Print proof JSON on success")
    args = p.parse_args()

    required = [g.strip() for g in args.require.split(",") if g.strip()]
    if not required:
        print("verify_agent_report: specify --require facade,t2,t4,...", file=sys.stderr)
        return 2

    unknown = [g for g in required if g not in KNOWN_GATES]
    if unknown:
        print(f"verify_agent_report: unknown gate(s): {unknown}", file=sys.stderr)
        return 2

    errors, proof = verify_gates(
        required,
        max_age_minutes=args.max_age_minutes,
        require_git_match=not args.no_git_check,
        allow_stale_git=args.allow_stale_git,
    )
    if errors:
        print("Agent gate proof: FAIL")
        for err in errors:
            print(f"  - {err}")
        rel = PROOF_PATH.relative_to(APP)
        print(f"  proof file: {rel}")
        print("  Re-run the required gate(s) on this tree, then verify again.")
        return 1

    print("Agent gate proof: OK")
    for gate_id in required:
        entry = (proof.get("gates") or {}).get(gate_id, {})
        print(f"  {gate_id}: at={entry.get('at')} exit={entry.get('exit')}")
    if args.print_proof:
        import json

        print(json.dumps(proof, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
