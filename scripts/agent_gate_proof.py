#!/usr/bin/env py -3
"""Machine-readable proof that agent validation gates ran (not just claimed)."""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[1]
PROOF_PATH = APP / "docs" / ".agent_gate_proof.json"
PROOF_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def git_head() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=APP,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def load_proof() -> dict[str, Any]:
    if not PROOF_PATH.is_file():
        return {"version": PROOF_VERSION, "updated": "", "git_head": "", "gates": {}}
    try:
        data = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": PROOF_VERSION, "updated": "", "git_head": "", "gates": {}}
    data.setdefault("gates", {})
    return data


def save_proof(data: dict[str, Any]) -> None:
    data["version"] = PROOF_VERSION
    data["updated"] = _utc_now_iso()
    data["git_head"] = git_head()
    PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROOF_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def record_gate(gate_id: str, **fields: Any) -> None:
    """Merge a successful gate run into the proof file."""
    data = load_proof()
    entry: dict[str, Any] = {
        "at": _utc_now_iso(),
        "exit": 0,
        **fields,
    }
    data["gates"][gate_id] = entry
    save_proof(data)


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _age_minutes(at_iso: str) -> float | None:
    dt = _parse_iso(at_iso)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 60.0


def verify_gates(
    required: list[str],
    *,
    max_age_minutes: float = 720.0,
    require_git_match: bool = True,
    allow_stale_git: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    """Return (errors, proof_snapshot)."""
    errors: list[str] = []
    if not PROOF_PATH.is_file():
        return [f"missing proof file: {PROOF_PATH.relative_to(APP)}"], {}

    try:
        proof = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"unreadable proof file: {exc}"], {}

    gates: dict[str, Any] = proof.get("gates") or {}
    current = git_head()
    recorded = (proof.get("git_head") or "").strip()

    if require_git_match and recorded and current and recorded != current:
        if not allow_stale_git:
            errors.append(
                f"git HEAD mismatch: proof={recorded[:12]} current={current[:12]} "
                "(re-run gates on this tree or pass --allow-stale-git)"
            )

    for gate_id in required:
        if gate_id not in gates:
            errors.append(f"gate not recorded: {gate_id}")
            continue
        entry = gates[gate_id]
        if entry.get("exit", 1) != 0:
            errors.append(f"gate {gate_id}: recorded exit {entry.get('exit')}")
        at = entry.get("at") or ""
        age = _age_minutes(at)
        if age is None:
            errors.append(f"gate {gate_id}: invalid timestamp {at!r}")
        elif age > max_age_minutes:
            errors.append(
                f"gate {gate_id}: stale ({age:.0f}m old; max {max_age_minutes:.0f}m)"
            )

    # Facade-specific artifact cross-check
    if "facade" in required and "facade" in gates and not errors:
        report = APP / "docs" / "_FACADE_AUDIT_REPORT.txt"
        if not report.is_file():
            errors.append("facade gate recorded but docs/_FACADE_AUDIT_REPORT.txt missing")
        else:
            facade_at = gates["facade"].get("at", "")
            rep_age = _age_minutes(facade_at)
            if rep_age is not None and (time.time() - report.stat().st_mtime) / 60.0 > max_age_minutes + 5:
                errors.append("_FACADE_AUDIT_REPORT.txt older than allowed window")

    return errors, proof
