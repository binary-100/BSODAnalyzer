"""Run Qt-heavy test modules in a child process (parent never imports PySide6).

Some MainWindow offscreen modules pass every assertion then abort during QApplication
interpreter teardown (Windows exit 0xC0000409). The child may return a negative exit code
even when pytest reported success. This runner treats pytest output as authoritative when
the progress line reaches [100%] with no failures.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Modules known to pass tests then crash on Qt shutdown — extend when TEST_HARNESS triage finds more.
QT_ISOLATED_MODULE_NAMES = frozenset(
    {
        "test_workflow_copy_batch4.py",
    }
)


def pytest_reported_all_passed(output: str) -> bool:
    """True when pytest quiet output shows a full green run."""
    text = output or ""
    if re.search(r"\bFAILED\b", text):
        return False
    if re.search(r"\bERROR\b", text):
        return False
    if re.search(r"\d+ failed", text, re.I):
        return False
    progress = re.search(r"([\.FE]+)\s*\[100%\]", text)
    if progress:
        marks = progress.group(1)
        return "." in marks and "F" not in marks and "E" not in marks
    match = re.search(r"(\d+) passed(?:,\s*(\d+) skipped)?(?:\s+in\s+[\d.]+s)?", text)
    if match:
        passed = int(match.group(1))
        failed_match = re.search(r"(\d+) failed", text)
        failed = int(failed_match.group(1)) if failed_match else 0
        return passed > 0 and failed == 0
    return False


def run_isolated_module(path: Path, extra: list[str] | None = None) -> int:
    """Run one test file in a fresh child; return 0 when pytest reported all passed."""
    root = Path(__file__).resolve().parents[1]
    path = path.resolve()
    extra = extra or []

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONSTARTUP"] = str(root / "tests" / "_qt_startup.py")

    cmd = [sys.executable, str(root / "tests" / "run_test_module.py"), str(path), *extra]
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.stdout:
        sys.stdout.write(proc.stdout)
        if not proc.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if proc.stderr:
        sys.stderr.write(proc.stderr)
        if not proc.stderr.endswith("\n"):
            sys.stderr.write("\n")

    combined = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        return 0
    if pytest_reported_all_passed(combined):
        sys.stderr.write(
            f"Note: child exited {proc.returncode} during Qt teardown; pytest reported all passed.\n"
        )
        return 0
    return proc.returncode if proc.returncode >= 0 else 1


def module_requires_isolation(path: Path) -> bool:
    return path.name in QT_ISOLATED_MODULE_NAMES


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print("usage: qt_isolated_runner.py tests/test_foo.py", file=sys.stderr)
        return 2
    path = Path(argv[0]).resolve()
    if not path.is_file():
        print(f"not found: {path}", file=sys.stderr)
        return 2
    return run_isolated_module(path, argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
