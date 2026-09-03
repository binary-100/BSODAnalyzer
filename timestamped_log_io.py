"""Text IO helpers that prefix each line with a local timestamp."""

from __future__ import annotations

from datetime import datetime


class TimestampPrefixTextIO:
    """Wrap a text file so every new line starts with ``[YYYY-MM-DD HH:MM:SS] ``."""

    def __init__(self, fh) -> None:
        self._fh = fh
        self._at_line_start = True

    def write(self, data: str) -> int:
        if not data:
            return 0
        for chunk in data.splitlines(keepends=True):
            if self._at_line_start and chunk.strip():
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                chunk = f"[{ts}] {chunk}"
            self._fh.write(chunk)
            self._at_line_start = chunk.endswith("\n")
        return len(data)

    def flush(self) -> None:
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __getattr__(self, name: str):
        return getattr(self._fh, name)
