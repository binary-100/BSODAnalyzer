"""PYTHONSTARTUP hook — register Qt plugins before any test imports PySide6.

Set by run_tests.bat. Safe to import manually when running a single test file:
  set QT_QPA_PLATFORM=offscreen
  set PYTHONSTARTUP=...\\tests\\_qt_startup.py
  py -3 tests\\test_foo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if os.environ.get("QT_QPA_PLATFORM", "").strip():
    _root = Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    import gui_qt_bootstrap as _qt_boot  # noqa: E402

    _qt_boot.install_pyside6_import_guard()
    _qt_boot.register_qt_plugins_for_import()
