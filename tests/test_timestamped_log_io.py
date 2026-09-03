"""Tests for timestamp-prefixed log file wrapper."""

from __future__ import annotations

import io

from timestamped_log_io import TimestampPrefixTextIO


def test_timestamp_prefix_on_each_line() -> None:
    base = io.StringIO()
    wrapped = TimestampPrefixTextIO(base)
    wrapped.write("first line\nsecond")
    wrapped.write(" part\n")
    out = base.getvalue()
    assert out.count("[") >= 2
    assert "first line" in out
    assert "second part" in out


if __name__ == "__main__":
    test_timestamp_prefix_on_each_line()
    print("OK")
