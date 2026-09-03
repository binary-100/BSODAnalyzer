"""Static gates: a name that cannot resolve must fail the suite, not a user's session.

The suite runs code paths, and the paths it never runs are exactly where `NameError`
lives. pyflakes reads every line regardless, so it catches the import that was dropped
during a module split, the helper that moved, the loop variable that was renamed.

Two gates, because the first one has a blind spot the codebase actually falls into:

  * `test_no_undefined_names` — pyflakes' own undefined-name/syntax findings.
  * `test_star_import_names_resolve_in_shared_context` — the 20-odd GUI mixins do
    `from gui_app_context import *`, which makes pyflakes give up and report every
    unresolved name as "may be undefined". That downgrade hid `mlog` (the maintenance
    log alias) in two mixins for as long as the star import existed: the activity-history
    dialog raised `NameError` before it could show. Resolving those names against the
    real `gui_app_context` namespace turns the guess back into an assertion.

Deliberately not gated here: unused imports (~980, cosmetic and churn-prone) and
assigned-but-unused locals (~44, often intentional unpacking).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
APP_ROOT = TESTS_DIR.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tests.static_analysis import (  # noqa: E402
    Finding,
    iter_source_files,
    pyflakes_findings,
    undefined_name_findings,
)

# A literal dict with the same key twice keeps only the last value. In a vendor alias
# map that silently discards a mapping, and deleting the "duplicate" flips canonical
# values for whoever survives — KNOWN_VENDORS had six such pairs.
_LOST_MAPPING_CODES = frozenset({"MultiValueRepeatedKeyLiteral"})

pytest.importorskip("pyflakes", reason="static gate needs pyflakes installed")

# Star-import re-export hubs, keyed by the module pyflakes names in its message.
_STAR_IMPORT_HUBS = ("gui_app_context",)

_STAR_MESSAGE = re.compile(
    r"^'(?P<name>[^']+)' may be undefined, or defined from star imports: (?P<hubs>.+)$"
)


def _findings() -> list[Finding]:
    return pyflakes_findings(iter_source_files(APP_ROOT))


def test_no_undefined_names() -> None:
    """Every name reference resolves — no `NameError` waiting on an unrun branch."""
    offenders = undefined_name_findings(_findings())
    assert not offenders, "names that cannot resolve at runtime:\n  " + "\n  ".join(
        f.render(APP_ROOT) for f in offenders
    )


def test_star_import_names_resolve_in_shared_context() -> None:
    """Names pyflakes could not resolve past a star import must exist in the hub.

    Without this, `from gui_app_context import *` silently exempts the GUI mixins —
    ~1400 name references — from the gate above.
    """
    namespaces: dict[str, set[str]] = {}
    for hub in _STAR_IMPORT_HUBS:
        namespaces[hub] = set(dir(__import__(hub)))

    offenders: list[str] = []
    for finding in _findings():
        match = _STAR_MESSAGE.match(finding.message)
        if not match:
            continue
        name = match.group("name")
        hubs = [h.strip() for h in match.group("hubs").split(",")]
        known = {h for h in hubs if h in namespaces}
        if len(known) != len(hubs):
            # A hub we do not import here; do not guess about its exports.
            continue
        if any(name in namespaces[h] for h in known):
            continue
        offenders.append(f"{finding.render(APP_ROOT)} (not exported by {', '.join(hubs)})")

    assert not offenders, (
        "names hidden behind a star import do not exist in the shared context:\n  "
        + "\n  ".join(offenders)
    )


def test_no_dict_literal_silently_drops_a_mapping() -> None:
    """Repeated keys with different values mean one mapping never takes effect."""
    offenders = [f for f in _findings() if f.code in _LOST_MAPPING_CODES]
    assert not offenders, "dict literals whose keys shadow each other:\n  " + "\n  ".join(
        f.render(APP_ROOT) for f in offenders
    )


def test_gate_covers_the_whole_first_party_tree() -> None:
    """A shrinking file list would make the gates above pass by looking away."""
    files = list(iter_source_files(APP_ROOT))
    names = {p.name for p in files}
    assert len(files) > 300, f"static gate only sees {len(files)} files"
    for expected in ("bsod_analyzer.py", "driver_catalog.py", "gui_app_context.py"):
        assert expected in names, f"{expected} missing from the static gate's file list"
    assert any(p.parent.name == "tests" for p in files), "tests/ not covered"
    assert any(p.parent.name == "scripts" for p in files), "scripts/ not covered"
