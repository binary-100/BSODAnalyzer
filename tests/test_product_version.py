"""Product line gating tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bsod_analyzer as core
import product_version as pv


def test_dev_default_is_v6() -> None:
    assert core.VERSION.startswith("6.")
    assert pv.is_v6_line()


if __name__ == "__main__":
    test_dev_default_is_v6()
    print("OK")
