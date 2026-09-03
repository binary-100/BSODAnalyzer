"""One-shot probe for interactive GUI bootstrap (agent/dev diagnostic)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui_qt_bootstrap import prepare_interactive_gui, probe_qt_platform, read_qt_platform_log

if __name__ == "__main__":
    print("before:", repr(os.environ.get("QT_QPA_PLATFORM")))
    prepare_interactive_gui()
    print("after:", repr(os.environ.get("QT_QPA_PLATFORM")))
    ok = probe_qt_platform(mode="interactive_script")
    print("probe_ok:", ok)
    tail = read_qt_platform_log(tail_lines=15)
    if tail:
        print("--- log tail ---")
        print(tail)
