#!/usr/bin/env py -3
"""Complete facade audit — static, import, runtime probes. Read-only except report."""
from __future__ import annotations

import ast
import importlib
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
BA = APP / "bsod_analyzer.py"
REPORT = APP / "docs" / "_FACADE_AUDIT_REPORT.txt"


def exports_and_locals() -> tuple[set[str], set[str]]:
    tree = ast.parse(BA.read_text(encoding="utf-8"))
    exports: set[str] = set()
    local: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            local.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                exports.add(a.asname or a.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "VERSION":
                    exports.add("VERSION")
    return exports, local


def scan_all_python() -> tuple[Counter[str], dict[str, set[str]], Counter[str]]:
    used: Counter[str] = Counter()
    detail: dict[str, set[str]] = defaultdict(set)
    core_refs: Counter[str] = Counter()

    def mark(sym: str, rel: str, how: str) -> None:
        used[sym] += 1
        detail[sym].add(f"{rel}:{how}")

    for path in sorted(APP.rglob("*.py")):
        if path.name == "bsod_analyzer.py":
            continue
        rel = path.relative_to(APP).as_posix()
        if "__pycache__" in rel or "audit_archive" in rel:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")

        for sym in re.findall(r"\bcore\.([A-Za-z_][A-Za-z0-9_]*)", text):
            mark(sym, rel, "core")
            core_refs[sym] += 1
        for sym in re.findall(r"\bba\.([A-Za-z_][A-Za-z0-9_]*)", text):
            mark(sym, rel, "ba")
        for sym in re.findall(r'["\']bsod_analyzer\.([A-Za-z_][A-Za-z0-9_]*)["\']', text):
            mark(sym, rel, "patch")
        for sym in re.findall(r'_ba\(["\']([A-Za-z_][A-Za-z0-9_]*)["\']', text):
            mark(sym, rel, "_ba")
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "bsod_analyzer":
                    for a in node.names:
                        if a.name != "*":
                            mark(a.asname or a.name, rel, "from_import")
        except SyntaxError:
            pass

    return used, detail, core_refs


def body_only_symbols(exports: set[str]) -> set[str]:
    tree = ast.parse(BA.read_text(encoding="utf-8"))
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            refs.add(node.id)
    return exports & refs


def hiddenimports_from_spec() -> list[str]:
    text = (APP / "BSODAnalyzer.spec").read_text(encoding="utf-8")
    block = text.split("hiddenimports=[", 1)[1].split("]", 1)[0]
    return [ln.strip().strip("',") for ln in block.splitlines() if ln.strip().startswith("'")]


def probe_imports(modules: list[str]) -> list[str]:
    sys.path.insert(0, str(APP))
    lines: list[str] = []
    for mod in modules:
        try:
            importlib.import_module(mod)
            lines.append(f"OK  {mod}")
        except Exception as exc:
            lines.append(f"FAIL {mod}: {exc}")
    return lines


SCRIPT_CORE_FALSE = frozenset({"find", "read_text", "write_text"})
PATCH_FALSE = frozenset({"py"})
ALIAS_OK = frozenset({"APP_VERSION"})  # driver_backup imports VERSION as APP_VERSION


def probe_all_symbols() -> tuple[list[str], list[str]]:
    """Runtime-resolve every _ba('…') and core.* against bsod_analyzer."""
    sys.path.insert(0, str(APP))
    import bsod_analyzer as core  # noqa: E402

    ba_syms: set[str] = set()
    core_syms: set[str] = set()
    skip_files = frozenset({"probe_ba_symbols.py", "audit_facade_complete.py"})

    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        if "__pycache__" in rel or path.name == "bsod_analyzer.py" or path.name in skip_files:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for sym in re.findall(r"""_ba\(['"]([A-Za-z_][A-Za-z0-9_]*)['"]""", text):
            ba_syms.add(sym)
        for sym in re.findall(r"\bcore\.([A-Za-z_][A-Za-z0-9_]*)", text):
            core_syms.add(sym)

    ba_broken = sorted(s for s in ba_syms if not hasattr(core, s))
    core_broken = sorted(s for s in core_syms - SCRIPT_CORE_FALSE if not hasattr(core, s))
    return ba_broken, core_broken


def runtime_core_checks() -> list[str]:
    sys.path.insert(0, str(APP))
    import bsod_analyzer as core  # noqa: E402

    lines: list[str] = []
    checks = [
        ("de (intentionally not on facade; workers use device_enrichment)", not hasattr(core, "de")),
        ("gather_report_data", callable(getattr(core, "gather_report_data", None))),
        ("device_inventory_for_matching", callable(getattr(core, "device_inventory_for_matching", None))),
        ("find_cdb", callable(getattr(core, "find_cdb", None))),
        ("_parse_event_time (_ba in bsod_minidump)", callable(getattr(core, "_parse_event_time", None))),
    ]
    for name, ok in checks:
        lines.append(f"{'OK' if ok else 'FAIL'}  core.{name}")
    ba_broken, core_broken = probe_all_symbols()
    lines.append(f"probe _ba: {len(ba_broken)} broken")
    for s in ba_broken:
        lines.append(f"FAIL  _ba('{s}')")
    lines.append(f"probe core.*: {len(core_broken)} broken (excl script Path locals)")
    for s in core_broken:
        lines.append(f"FAIL  core.{s}")
    if not ba_broken and not core_broken:
        lines.append("OK  all _ba and core.* symbols resolve on bsod_analyzer")
    return lines


def import_time_ms() -> str:
    import importlib

    sys.path.insert(0, str(APP))
    # Cold-ish import: drop cached module when run standalone repeatedly in dev
    for mod in ("bsod_analyzer",):
        sys.modules.pop(mod, None)
    t0 = time.perf_counter()
    importlib.import_module("bsod_analyzer")
    return f"import bsod_analyzer: {(time.perf_counter() - t0) * 1000:.1f}ms"


def symbol_owners() -> dict[str, str]:
    """Map re-exported symbol → owning module (from bsod_analyzer import blocks)."""
    owners: dict[str, str] = {}
    tree = ast.parse(BA.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            for a in node.names:
                owners[a.asname or a.name] = mod
    return owners


def decouple_scan() -> list[str]:
    """Production modules with lazy/direct bsod_analyzer imports (retarget candidates)."""
    skip = {
        "bsod_analyzer.py",
        "gui_app_context.py",
        "bsod_gui_qt.py",
        "bsod_gui_workers.py",
        "analyzer_gather.py",
        "analyzer_hardware.py",
        "bsod_minidump.py",
        "bsod_crash_report.py",
        "crash_report_narrative.py",
    }
    lines: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        if (
            "__pycache__" in rel
            or rel.startswith("tests/")
            or rel.startswith("scripts/")
            or path.name in skip
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "bsod_analyzer" not in text:
            continue
        syms: set[str] = set()
        if "import bsod_analyzer as core" in text or "import bsod_analyzer as ba" in text:
            syms.add("(module alias core/ba)")
        for m in re.finditer(r"from bsod_analyzer import \(([^)]*)\)", text, re.S):
            for part in m.group(1).split(","):
                part = part.strip()
                if not part:
                    continue
                if " as " in part:
                    syms.add(part.split(" as ")[0].strip())
                else:
                    syms.add(part)
        for m in re.finditer(r"from bsod_analyzer import (\w+(?: as \w+)?)", text):
            part = m.group(1).strip()
            syms.add(part.split(" as ")[0].strip())
        if syms:
            lines.append(f"  {rel}: {', '.join(sorted(syms))}")
    return lines


def usage_channels(used: Counter[str], detail: dict[str, set[str]]) -> list[str]:
    lines: list[str] = []
    channels = Counter()
    for sym, hits in used.items():
        for loc in detail[sym]:
            ch = loc.rsplit(":", 1)[-1]
            channels[ch] += hits
    lines.append("usage by channel (hits):")
    for ch, cnt in channels.most_common():
        lines.append(f"  {cnt:4d}  {ch}")
    return lines


def prune_by_owner(prune: list[str], owners: dict[str, str]) -> list[str]:
    lines: list[str] = []
    by_mod: dict[str, list[str]] = defaultdict(list)
    for sym in prune:
        by_mod[owners.get(sym, "?")].append(sym)
    for mod in sorted(by_mod):
        lines.append(f"  [{mod}] ({len(by_mod[mod])})")
        lines.append("    " + ", ".join(sorted(by_mod[mod])))
    return lines


def benchmark_ba() -> str:
    sys.path.insert(0, str(APP))
    import analyzer_gather as ag  # noqa: E402
    import bsod_analyzer as core  # noqa: E402

    n = 5000

    def ms(fn):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        return (time.perf_counter() - t0) * 1000

    ba_ms = ms(lambda: ag._ba("find_cdb"))
    direct_ms = ms(core.find_cdb)
    return f"_ba x{n}: {ba_ms:.1f}ms  direct x{n}: {direct_ms:.1f}ms  ratio {ba_ms/max(direct_ms,0.001):.1f}x"


def main() -> int:
    exports, local = exports_and_locals()
    used, detail, core_refs = scan_all_python()
    body_only = body_only_symbols(exports)
    prune_candidates = sorted(exports - set(used.keys()) - local - body_only)
    missing_exports = sorted(
        s
        for s in (set(used.keys()) - exports - local)
        if s not in PATCH_FALSE
        and s not in ALIAS_OK
        and s not in SCRIPT_CORE_FALSE
        and s != "sym"
    )

    lines: list[str] = []
    w = lines.append
    w("BSOD Analyzer — complete facade audit")
    w(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    w("")
    w("=== STATIC ===")
    w(f"exports={len(exports)} local_defs={len(local)} facade_symbols_used={len(used)}")
    w(f"core_refs_total={sum(core_refs.values())} unique_core_symbols={len(core_refs)}")
    w(f"body_only_imports={len(body_only)} prune_candidates={len(prune_candidates)}")
    w(f"missing_exports (used but not on ba)={missing_exports}")
    w("")
    w("--- body_only ---")
    w(", ".join(sorted(body_only)))
    w("")
    w("--- prune_candidates ---")
    w("\n".join(prune_candidates))
    w("")
    w("--- missing_exports detail ---")
    for sym in missing_exports:
        w(f"  {sym}: {sorted(detail[sym])[:8]}")
    w("")
    w("--- top core.* ---")
    for sym, cnt in core_refs.most_common(40):
        w(f"  {cnt:3d}  {sym}")
    w("")
    owners = symbol_owners()
    w("")
    w("=== USAGE CHANNELS ===")
    w("\n".join(usage_channels(used, detail)))
    w("")
    w("=== PRUNE BY OWNER (verified unused only) ===")
    w("\n".join(prune_by_owner(prune_candidates, owners)))
    w("")
    w("=== DECOUPLE CANDIDATES (production, not GUI shell) ===")
    w("\n".join(decouple_scan()) or "  (none)")
    w("")
    w("=== IMPORT TIME ===")
    w(import_time_ms())
    w("")
    w("=== RUNTIME core checks ===")
    w("\n".join(runtime_core_checks()))
    w("")
    w("=== _ba benchmark ===")
    w(benchmark_ba())
    w("")
    w("=== PyInstaller hiddenimports ===")
    w("\n".join(probe_imports(hiddenimports_from_spec())))
    w("")
    w("=== Key module import chain ===")
    key = [
        "bsod_analyzer",
        "bsod_crash_report",
        "analyzer_gather",
        "analyzer_hardware",
        "crash_report_narrative",
        "driver_catalog",
        "driver_verification",
        "driver_list_build",
        "gui_app_context",
        "bsod_gui_workers",
        "bsod_gui_qt",
        "catalog_device_context",
        "firmware_catalog",
    ]
    w("\n".join(probe_imports(key)))

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT.read_text(encoding="utf-8"))
    ba_broken, core_broken = probe_all_symbols()
    return 1 if missing_exports or ba_broken or core_broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
