"""Shared pyflakes plumbing for the static gates in `test_static_analysis.py`.

Kept out of `test_*.py` so pytest does not try to collect it, and importable by
`scripts/` if a maintainer wants the same file list the gate uses.

pyflakes runs in-process through its API rather than the CLI: the app has ~350 source
files and a `py -3 -m pyflakes <every file>` command line exceeds the Windows 32k limit.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

# Trees that are not our source: build output, shipped bundles, vendored runtimes.
_SKIP_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "build",
        "dist",
        "BSODAnalyzer_v6",
        "BSODAnalyzer_portable",
        "DebuggingTools",
        "PowerShellModules",
        "appdata",
        "data",
        "Minidump",
    }
)

# Directories that hold first-party Python, relative to the app root. The root itself
# contributes its top-level modules only (no recursion).
_SOURCE_SUBDIRS = ("tests", "scripts", "runtime_hooks", "maint")


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str
    # pyflakes message class name (e.g. "UndefinedName"), or "SyntaxError"/"UnexpectedError".
    code: str = ""

    def location(self, root: Path) -> str:
        try:
            rel = self.path.relative_to(root)
        except ValueError:
            rel = self.path
        return f"{rel}:{self.line}"

    def render(self, root: Path) -> str:
        return f"{self.location(root)}: {self.message}"


def iter_source_files(root: Path) -> Iterator[Path]:
    """Every first-party `.py` file, deduplicated and in a stable order."""
    seen: set[Path] = set()
    candidates: list[Path] = sorted(root.glob("*.py"))
    for sub in _SOURCE_SUBDIRS:
        base = root / sub
        if not base.is_dir():
            continue
        candidates.extend(sorted(base.rglob("*.py")))
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        if any(part in _SKIP_DIRS for part in resolved.parts):
            continue
        seen.add(resolved)
        yield resolved


class _Collector:
    """pyflakes reporter that accumulates findings instead of printing them."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def unexpectedError(self, filename: str, msg: str) -> None:  # noqa: N802 - pyflakes API
        self.findings.append(
            Finding(Path(filename), 0, f"unexpected error: {msg}", "UnexpectedError")
        )

    def syntaxError(  # noqa: N802 - pyflakes API
        self,
        filename: str,
        msg: str,
        lineno: int | None,
        offset: int | None,
        text: str | None,
    ) -> None:
        self.findings.append(
            Finding(Path(filename), lineno or 0, f"syntax error: {msg}", "SyntaxError")
        )

    def flake(self, message: object) -> None:
        # str(message) prefixes a Windows path whose drive colon defeats naive splitting.
        template = getattr(message, "message", "%r")
        args = getattr(message, "message_args", ())
        try:
            text = template % args
        except TypeError:
            text = str(template)
        self.findings.append(
            Finding(
                Path(getattr(message, "filename", "<unknown>")),
                int(getattr(message, "lineno", 0) or 0),
                text,
                type(message).__name__,
            )
        )


def pyflakes_findings(paths: Iterable[Path]) -> list[Finding]:
    from pyflakes import api as pyflakes_api

    collector = _Collector()
    for path in paths:
        source = path.read_text(encoding="utf-8", errors="replace")
        pyflakes_api.check(source, str(path), collector)
    return collector.findings


# pyflakes message classes that mean the interpreter would raise on that line.
# Matched by class name rather than message text: "local variable 'x' is assigned to but
# never used" (cosmetic) and "local variable 'x' ... referenced before assignment" (fatal)
# both start with the same words.
FATAL_CODES = frozenset(
    {
        "UndefinedName",
        "UndefinedLocal",
        "UndefinedExport",
        "SyntaxError",
        "UnexpectedError",
    }
)


def undefined_name_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Findings where a name lookup fails at runtime."""
    return [f for f in findings if f.code in FATAL_CODES]


def module_docstring_names(path: Path) -> set[str]:
    """Names an `__all__` re-export list advertises, if the module declares one."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if "__all__" not in targets:
            continue
        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            return {
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }
    return set()
