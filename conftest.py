"""pytest bootstrap — Qt plugin paths must be set before the first PySide6 import.

Same contract as tests/run_test_module.py: without QT_PLUGIN_PATH, Windows shows a native
"no Qt platform plugin could be initialized" dialog even when QT_QPA_PLATFORM=offscreen.
pytest imports this file before collecting any test module, so the guard lands early enough.

See docs/AGENT_READINESS.md - Qt test bootstrap.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import gui_qt_bootstrap as _qt_boot  # noqa: E402

_qt_boot.install_pyside6_import_guard()
_qt_boot.ensure_offscreen_for_tests(probe=False)
