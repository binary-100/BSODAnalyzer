"""
Timestamped session log for timing long GUI operations (append-only JSONL).

Written in full-install mode under the app data folder; portable mode uses
%TEMP%\\BSODAnalyzer\\session_log.jsonl (same folder as gui_crash.log).
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import app_settings as app_set

_LOG_NAME = "session_log.jsonl"
_MAX_READ = 500
_lock = threading.Lock()
_active: dict[str, float] = {}
_active_kind: dict[str, tuple[str, float]] = {}


def _log_dir() -> Path:
    if app_set.allows_persistent_driver_data():
        d = app_set.full_install_data_dir()
    else:
        d = Path(os.environ.get("TEMP", ".")) / "BSODAnalyzer"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path() -> Path:
    return _log_dir() / _LOG_NAME


def _timestamp_fields() -> tuple[str, str, int]:
    utc = datetime.now(timezone.utc)
    at = (
        utc.strftime("%Y-%m-%dT%H:%M:%S.")
        + f"{utc.microsecond // 1000:03d}Z"
    )
    local = utc.astimezone()
    local_at = local.strftime("%Y-%m-%d %H:%M:%S.") + f"{local.microsecond // 1000:03d}"
    unix_ms = int(utc.timestamp() * 1000)
    return at, local_at, unix_ms


def _append_row(row: dict[str, Any]) -> None:
    at, local_at, unix_ms = _timestamp_fields()
    row.setdefault("at", at)
    row.setdefault("local_at", local_at)
    row.setdefault("unix_ms", unix_ms)
    try:
        with log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def begin(kind: str, summary: str, *, extra: dict | None = None) -> str:
    """Record operation start; returns a token for :func:`end`."""
    token = uuid4().hex[:12]
    row: dict[str, Any] = {
        "kind": (kind or "operation").strip(),
        "phase": "start",
        "message": (summary or "").strip(),
    }
    if extra:
        row["extra"] = extra
    _append_row(row)
    started = time.monotonic()
    with _lock:
        _active[token] = started
        _active_kind[(kind or "operation").strip()] = (token, started)
    return token


def end(
    token: str | None,
    kind: str,
    summary: str,
    *,
    status: str = "ok",
    extra: dict | None = None,
) -> int | None:
    """Record operation end and elapsed time when *token* came from :func:`begin`.

    Returns elapsed milliseconds when timing was captured, else ``None``.
    """
    elapsed_ms: int | None = None
    if token:
        with _lock:
            start = _active.pop(token, None)
            kind_key = (kind or "operation").strip()
            active = _active_kind.get(kind_key)
            if active and active[0] == token:
                _active_kind.pop(kind_key, None)
        if start is not None:
            elapsed_ms = int((time.monotonic() - start) * 1000)
    row: dict[str, Any] = {
        "kind": (kind or "operation").strip(),
        "phase": "end",
        "message": (summary or "").strip(),
        "status": (status or "ok").strip(),
    }
    if elapsed_ms is not None:
        row["elapsed_ms"] = elapsed_ms
    if extra:
        row["extra"] = extra
    _append_row(row)
    return elapsed_ms


def progress(
    kind: str,
    message: str,
    *,
    extra: dict | None = None,
) -> None:
    """Record a progress milestone during an operation."""
    row: dict[str, Any] = {
        "kind": (kind or "progress").strip(),
        "phase": "progress",
        "message": (message or "").strip()[:2000],
    }
    kind_key = row["kind"]
    with _lock:
        active = _active_kind.get(kind_key)
    if active:
        row["since_start_ms"] = int((time.monotonic() - active[1]) * 1000)
    if extra:
        row["extra"] = extra
    _append_row(row)


def read_events(limit: int = 80) -> list[dict]:
    path = log_path()
    if not path.is_file():
        return []
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
        return "No session activity logged yet."
    parts: list[str] = []
    for e in events:
        at = (e.get("local_at") or e.get("at") or "?")[:23]
        kind = e.get("kind") or "event"
        phase = e.get("phase") or ""
        summary = e.get("message") or ""
        elapsed = e.get("elapsed_ms")
        since = e.get("since_start_ms")
        tag = f"[{kind}]"
        if phase:
            tag = f"[{kind}/{phase}]"
        line = f"{at}  {tag}  {summary}"
        if elapsed is not None:
            if elapsed >= 60_000:
                line += f"  ({elapsed / 60_000:.1f} min)"
            elif elapsed >= 1000:
                line += f"  ({elapsed / 1000:.1f} s)"
            else:
                line += f"  ({elapsed} ms)"
        elif since is not None:
            if since >= 60_000:
                line += f"  (+{since / 60_000:.1f} min)"
            elif since >= 1000:
                line += f"  (+{since / 1000:.1f} s)"
            else:
                line += f"  (+{since} ms)"
        parts.append(line)
    return "\n".join(parts)
