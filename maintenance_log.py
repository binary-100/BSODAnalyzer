"""
Maintenance activity log for full-install mode (append-only JSONL).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app_settings as app_set

_LOG_NAME = "maintenance_log.jsonl"
_MAX_READ = 200


def _log_path() -> Path | None:
    if not app_set.allows_persistent_driver_data():
        return None
    d = app_set.full_install_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / _LOG_NAME


def append_event(kind: str, summary: str, *, detail: str = "", extra: dict | None = None) -> None:
    path = _log_path()
    if not path:
        return
    row: dict[str, Any] = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "local_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "kind": (kind or "event").strip(),
        "summary": (summary or "").strip(),
        "detail": (detail or "").strip()[:2000],
    }
    if extra:
        row["extra"] = extra
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_events(limit: int = 50) -> list[dict]:
    path = _log_path()
    if not path or not path.is_file():
        return []
    lines: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-max(1, min(limit, _MAX_READ)) :]:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                out.append(data)
        except json.JSONDecodeError:
            continue
    return list(reversed(out))


def format_events_plain(events: list[dict]) -> str:
    if not events:
        return "No maintenance activity logged yet."
    parts: list[str] = []
    for e in events:
        at = (e.get("local_at") or e.get("at") or "?")[:19].replace("T", " ")
        kind = e.get("kind") or "event"
        summary = e.get("summary") or ""
        parts.append(f"{at}  [{kind}]  {summary}")
        detail = (e.get("detail") or "").strip()
        if detail:
            for ln in detail.splitlines()[:6]:
                parts.append(f"    {ln}")
    return "\n".join(parts)
