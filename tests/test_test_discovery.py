"""Guard: every test function defined in tests/ is actually collected and run.

The suite previously ran via runpy + `if __name__ == "__main__":` blocks, so a test that
nobody remembered to list never executed while the runner still printed OK. 139 of 1037
test functions were dead that way. pytest fixed discovery; this test keeps it fixed.

Failure modes it catches:
  * a test file whose module-level `test_*` function pytest cannot collect
  * duplicate `test_*` names in one module (the later def silently replaces the earlier)
  * a test file that fails to import (collection error) — zero tests, previously silent
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import Counter
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
APP_ROOT = TESTS_DIR.parent

# Fixtures/params pytest can legitimately supply to a test signature.
_ALLOWED_PARAMS = {
    "tmp_path",
    "tmp_path_factory",
    "monkeypatch",
    "capsys",
    "capfd",
    "caplog",
    "request",
    "recwarn",
    "qtbot",
}


def _module_test_functions(tree: ast.Module) -> list[str]:
    """Module-level `test_*` functions — what pytest collects from a plain module."""
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _test_files() -> list[Path]:
    return sorted(p for p in TESTS_DIR.glob("test_*.py"))


def test_no_duplicate_test_names_within_a_module() -> None:
    """A redefined test name silently discards the earlier body."""
    offenders: list[str] = []
    for path in _test_files():
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        dupes = [n for n, c in Counter(_module_test_functions(tree)).items() if c > 1]
        for name in sorted(dupes):
            offenders.append(f"{path.name}::{name}")
    assert not offenders, "duplicate test names shadow earlier definitions: " + ", ".join(
        offenders
    )


def test_every_test_signature_is_collectible() -> None:
    """Required positional args that are not fixtures make pytest error instead of run."""
    offenders: list[str] = []
    for path in _test_files():
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            if any(
                d
                for d in node.decorator_list
                if "parametrize" in ast.dump(d) or "fixture" in ast.dump(d)
            ):
                continue
            args = node.args
            required = args.posonlyargs + args.args
            defaults_count = len(args.defaults)
            if defaults_count:
                required = required[:-defaults_count]
            bad = [a.arg for a in required if a.arg not in _ALLOWED_PARAMS]
            if bad:
                offenders.append(f"{path.name}::{node.name}({', '.join(bad)})")
    assert not offenders, (
        "tests take non-fixture arguments and cannot be collected: " + ", ".join(offenders)
    )


def test_pytest_collects_every_defined_test() -> None:
    """Cross-check AST-defined counts against what pytest actually collects."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(TESTS_DIR),
            "--collect-only",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "--ignore",
            str(Path(__file__).resolve()),
        ],
        cwd=str(APP_ROOT),
        capture_output=True,
        text=True,
        timeout=900,
    )
    collected: Counter[str] = Counter()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("test") or ".py" not in line:
            continue
        if "::" in line:
            # verbose node-id form: tests/test_foo.py::test_bar
            collected[Path(line.split("::", 1)[0]).name] += 1
        elif ": " in line:
            # quiet per-file summary form: tests/test_foo.py: 8
            file_part, _, count = line.rpartition(": ")
            if count.strip().isdigit():
                collected[Path(file_part).name] += int(count)

    assert collected, (
        "pytest collected nothing — discovery is broken.\n"
        f"stdout tail:\n{proc.stdout[-2000:]}\nstderr tail:\n{proc.stderr[-2000:]}"
    )

    missing: list[str] = []
    for path in _test_files():
        if path.resolve() == Path(__file__).resolve():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        defined = set(_module_test_functions(tree))
        if not defined:
            continue
        got = collected.get(path.name, 0)
        if got < len(defined):
            missing.append(f"{path.name}: defined {len(defined)}, collected {got}")

    assert not missing, "tests defined but not collected:\n  " + "\n  ".join(missing)


def test_collection_reports_no_import_errors() -> None:
    """A test module that cannot import contributes zero tests — never silently."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(TESTS_DIR),
            "--collect-only",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(APP_ROOT),
        capture_output=True,
        text=True,
        timeout=900,
    )
    out = proc.stdout
    assert "error" not in out.lower().split("short test summary")[-1] or "errors" not in out, (
        f"collection errors present:\n{out[-3000:]}"
    )
