"""Global catalog PowerShell lock keeps concurrent subprocesses from freezing the GUI."""

from __future__ import annotations

import os
import sys
import threading
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bsod_runtime as rt


def test_run_catalog_powershell_serializes() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_run(_script: str, timeout: int = 30, *, prefer_pwsh: bool = False) -> tuple[bool, str]:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            import time
            time.sleep(0.05)
            return True, "ok"
        finally:
            with lock:
                active -= 1

    with mock.patch.object(rt, "run_powershell", side_effect=fake_run):
        threads = [
            threading.Thread(target=lambda: rt.run_catalog_powershell("1", timeout=5))
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
    assert peak == 1


if __name__ == "__main__":
    test_run_catalog_powershell_serializes()
    print("catalog powershell lock tests OK")
