"""Run tests/test_*.py with Qt offscreen plugin paths configured before any PySide6 import.

Discovery is delegated to pytest so every `test_*` function in the file runs, not only the
subset an `if __name__ == "__main__":` block happened to list. One process per file keeps the
isolation the suite was written against (module-level caches, monkeypatched globals).

`--legacy` restores the old runpy behaviour for a single file when a test genuinely needs its
`__main__` block (documented per file in docs/TEST_HARNESS_PLAN.md).
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import gui_qt_bootstrap as _qt_boot  # noqa: E402

_qt_boot.install_pyside6_import_guard()
_qt_boot.ensure_offscreen_for_tests(probe=False)


def _run_legacy(path: Path, extra: list[str]) -> int:
    sys.argv = [str(path), *extra]
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _run_pytest(path: Path, extra: list[str]) -> int:
    import pytest

    args = [str(path), "-q", "--no-header", "-p", "no:cacheprovider", *extra]
    return int(pytest.main(args))


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print("usage: run_test_module.py [--legacy] tests/test_foo.py", file=sys.stderr)
        return 2
    legacy = False
    if argv[0] == "--legacy":
        legacy = True
        argv = argv[1:]
    if not argv:
        print("usage: run_test_module.py [--legacy] tests/test_foo.py", file=sys.stderr)
        return 2
    path = Path(argv[0]).resolve()
    if not path.is_file():
        print(f"not found: {path}", file=sys.stderr)
        return 2
    extra = argv[1:]
    return _run_legacy(path, extra) if legacy else _run_pytest(path, extra)


if __name__ == "__main__":
    raise SystemExit(main())
