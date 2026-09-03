"""GUI tests — Action Plan mixin step filtering (`gui_mixin_action_plan.py`)."""

from __future__ import annotations

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui_test_harness import offscreen_main_window  # noqa: E402


def test_action_plan_source_steps_skips_numbered_prefix_rows() -> None:
    model = {
        "fix_plan": {
            "steps": [
                "1) Old numbered header",
                "Update the AMD chipset driver package.",
                "2) Another header",
                "Run Windows Update optional updates.",
            ]
        },
        "driver": {},
    }
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            rows = win._action_plan_source_steps(model)
    assert "Update the AMD chipset driver package." in rows
    assert "Run Windows Update optional updates." in rows
    assert not any(r.startswith("1)") or r.startswith("2)") for r in rows)
