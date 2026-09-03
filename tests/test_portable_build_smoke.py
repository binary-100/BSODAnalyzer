"""Smoke checks for the portable build.

End users launch BSODAnalyzer.exe and use the GUI (Run Analysis). Frozen-exe checks
run post-build only. CLI (--cli) is developer/automation smoke only.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import bsod_analyzer as core
import device_enrichment as de
import driver_catalog as drvcat

ROOT = Path(__file__).resolve().parents[1]
import product_version as pv

_major = str(pv.product_major())
DIST = ROOT / f"BSODAnalyzer_v{_major}"
EXE = DIST / "BSODAnalyzer.exe"


def _postbuild_exe_tests() -> bool:
    """Frozen-exe checks run after deploy only (not against a stale pre-build binary)."""
    return os.environ.get("BSOD_PORTABLE_POSTBUILD") == "1"


def test_distrib_version_files():
    if not _postbuild_exe_tests():
        return
    assert EXE.is_file(), f"Missing portable exe: {EXE}"
    internal = DIST / "_internal"
    assert internal.is_dir(), f"Missing onedir bundle: {internal}"
    assert any(internal.iterdir()), f"Empty onedir bundle: {internal}"
    root_ver = (ROOT / "VERSION.txt").read_text(encoding="utf-8")
    dist_ver = (DIST / "VERSION.txt").read_text(encoding="utf-8")
    readme = (DIST / "README.txt").read_text(encoding="utf-8")
    ver = core.VERSION
    assert ver in root_ver
    assert ver in dist_ver
    assert ver in readme
    assert core.VERSION == ver


def test_portable_gui_exe_starts():
    """GUI exe should stay alive for several seconds (no instant crash)."""
    if not _postbuild_exe_tests():
        return
    proc = subprocess.Popen(
        [str(EXE)],
        cwd=str(DIST),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(6)
        assert proc.poll() is None, "Portable exe exited immediately (startup crash?)"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_portable_cli_version_banner():
    """Frozen --cli must finish analysis and print the report (no UnicodeEncodeError)."""
    if not _postbuild_exe_tests() or not EXE.is_file():
        return
    env = os.environ.copy()
    env["BSOD_NO_PAUSE"] = "1"
    # Match a legacy Windows console so Unicode report text cannot slip through via UTF-8 pipes.
    env["PYTHONIOENCODING"] = "cp1252:replace"
    proc = subprocess.run(
        [str(EXE), "--cli"],
        cwd=str(DIST),
        input="N\nN\n\n",
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    ver = core.VERSION
    assert ver in out or "BSOD Analyzer" in out
    assert "Traceback" not in out, f"CLI crashed:\n{out[-2000:]}"
    assert "UnicodeEncodeError" not in out
    assert proc.returncode == 0, f"CLI exit {proc.returncode}:\n{out[-2000:]}"


def test_probe_cdb_dev_python() -> None:
    """Dev smoke: --probe-cdb resolves a cdb.exe path (SDK, bundled tree, or WinDbg app)."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "bsod_analyzer.py"), "--probe-cdb"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 and "CDB_NOT_FOUND" in out:
        return
    assert proc.returncode == 0, f"probe-cdb failed: {proc.stderr or out}"
    assert "cdb.exe" in out.lower()


def test_frozen_probe_cdb_path() -> None:
    """Post-build: frozen exe resolves bundled or local CDB via --probe-cdb."""
    if not _postbuild_exe_tests() or not EXE.is_file():
        return
    env = os.environ.copy()
    env["BSOD_NO_PAUSE"] = "1"
    proc = subprocess.run(
        [str(EXE), "--probe-cdb"],
        cwd=str(DIST),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    out = (proc.stdout or "").strip()
    assert proc.returncode == 0, f"--probe-cdb failed: {proc.stderr or out}"
    assert "cdb.exe" in out.lower(), out
    assert Path(out).is_file(), out


def test_distrib_debugging_tools_folder() -> None:
    """Bundled CDB lives under _internal (no duplicate root DebuggingTools folder)."""
    if not _postbuild_exe_tests():
        return
    cdb = DIST / "_internal" / "DebuggingTools" / "x64" / "cdb.exe"
    assert cdb.is_file(), f"Missing {cdb} — bundle DebuggingTools in PyInstaller spec"
    root_cdb = DIST / "DebuggingTools" / "x64" / "cdb.exe"
    assert not root_cdb.is_file(), (
        f"Unexpected duplicate {root_cdb} — finalize_portable_dist should remove root copy"
    )


def test_distrib_powershell_modules_folder() -> None:
    """MSCatalogLTS is bundled under _internal."""
    if not _postbuild_exe_tests():
        return
    psd1 = (
        DIST / "_internal" / "PowerShellModules" / "MSCatalogLTS" / "2.1.0.2" / "MSCatalogLTS.psd1"
    )
    assert psd1.is_file(), f"Missing bundled {psd1}"
    root_psd1 = DIST / "PowerShellModules" / "MSCatalogLTS" / "2.1.0.2" / "MSCatalogLTS.psd1"
    assert not root_psd1.is_file(), (
        f"Unexpected duplicate {root_psd1} — finalize_portable_dist should remove root copy"
    )


def test_distrib_portable_user_layout() -> None:
    """Launcher exists; stick-side data folder is not seeded (Maintenance USB model)."""
    if not _postbuild_exe_tests():
        return
    assert (DIST / "README.txt").is_file()
    assert (DIST / "Run BSODAnalyzer as Administrator.bat").is_file()
    assert not (DIST / "BSODAnalyzer_portable").is_dir()


def test_frozen_probe_mscatalog_module() -> None:
    if not _postbuild_exe_tests() or not EXE.is_file():
        return
    env = os.environ.copy()
    env["BSOD_NO_PAUSE"] = "1"
    proc = subprocess.run(
        [str(EXE), "--probe-mscatalog"],
        cwd=str(DIST),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    out = (proc.stdout or "").strip()
    assert proc.returncode == 0, f"--probe-mscatalog failed: {proc.stderr or out}"
    assert "MSCatalogLTS.psd1" in out or "PowerShellModules" in out, out


def test_system_restore_status_smoke():
    """Restore-point flow dependency: status query returns a dict."""
    st = drvcat.get_system_restore_status()
    assert isinstance(st, dict)
    assert "enabled" in st
    assert "drive" in st


def test_pnp_enrichment_at_scale():
    """Full device load path: indexed lookup stays fast on many rows."""
    index = {
        f"Device {i}": {
            "display_name": f"Display Device {i}",
            "vendor_key": "intel" if i % 2 == 0 else "realtek",
        }
        for i in range(120)
    }
    lu = de.PnpEnrichmentLookup(index)
    rows = [{"name": f"Device {i}"} for i in range(0, 120, 3)]
    enriched = de.enrich_driver_inventory_rows(rows, index, parallel=True)
    assert len(enriched) == len(rows)
    assert lu.match("Display Device 10") is not None


def test_find_cdb_and_clear_cache():
    core.clear_cdb_path_cache()
    p1 = core.find_cdb()
    p2 = core.find_cdb()
    assert p1 == p2
    core.clear_cdb_path_cache()


if __name__ == "__main__":
    postbuild = _postbuild_exe_tests()
    if postbuild:
        test_distrib_version_files()
        print("distrib OK")
    test_system_restore_status_smoke()
    print("restore status OK")
    test_pnp_enrichment_at_scale()
    print("pnp scale OK")
    test_find_cdb_and_clear_cache()
    print("find_cdb OK")
    test_probe_cdb_dev_python()
    print("probe-cdb dev OK")
    if postbuild:
        test_distrib_debugging_tools_folder()
        print("distrib DebuggingTools OK")
        test_distrib_portable_user_layout()
        print("distrib portable layout OK")
        test_distrib_powershell_modules_folder()
        print("distrib PowerShellModules OK")
        test_frozen_probe_cdb_path()
        print("frozen probe-cdb OK")
        test_portable_gui_exe_starts()
        print("gui launch OK")
        test_portable_cli_version_banner()
        print("cli banner OK")
        test_frozen_probe_mscatalog_module()
        print("frozen probe-mscatalog OK")
    print("Portable build smoke tests OK")
