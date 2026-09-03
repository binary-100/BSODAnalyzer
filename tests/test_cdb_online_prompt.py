"""WinDbg online-install prompt and CDB search order policy."""

from __future__ import annotations

import os
import sys
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import bsod_analyzer as core
import bsod_minidump as md


def test_should_prompt_cdb_online_when_no_windbg_app() -> None:
    with mock.patch.object(md, "_is_online", return_value=True), mock.patch.object(
        md, "_find_windbg_app_engine_dir", return_value=None
    ):
        assert core.should_prompt_cdb_online_install({}) is True
        assert core.should_prompt_cdb_online_install({"cdb_online_install_dismissed": True}) is False
        assert core.should_prompt_cdb_online_install({"cdb_online_install_prompt": False}) is False


def test_should_not_prompt_cdb_when_offline() -> None:
    with mock.patch.object(md, "_is_online", return_value=False), mock.patch.object(
        md, "_find_windbg_app_engine_dir", return_value=None
    ):
        assert core.should_prompt_cdb_online_install({}) is False


def test_should_not_prompt_cdb_when_windbg_app_present() -> None:
    with mock.patch.object(md, "_is_online", return_value=True), mock.patch.object(
        md, "_find_windbg_app_engine_dir", return_value=r"C:\Program Files\WindowsApps\WinDbg"
    ):
        assert core.should_prompt_cdb_online_install({}) is False


def test_cdb_search_paths_online_prefers_windbg_app_before_bundled() -> None:
    bundled = r"C:\app\_internal\DebuggingTools\x64\cdb.exe"
    app_cdb = r"C:\Program Files\WindowsApps\WinDbg\amd64\cdb.exe"
    with mock.patch.object(md, "_get_local_cdb_path", return_value=r"C:\app\DebuggingTools\x64\cdb.exe"), mock.patch.object(
        md, "_get_bundled_cdb_path", return_value=bundled
    ), mock.patch.object(md, "_get_windbg_app_cdb_path", return_value=app_cdb), mock.patch.object(
        md, "_is_online", return_value=True
    ), mock.patch.object(md, "_cdb_engine_usable", return_value=True), mock.patch(
        "os.path.isfile", return_value=True
    ):
        paths = md._get_cdb_search_paths()
    assert paths.index(app_cdb) < paths.index(bundled)


def test_cdb_search_paths_offline_prefers_bundled_before_windbg_app() -> None:
    bundled = r"C:\app\_internal\DebuggingTools\x64\cdb.exe"
    app_cdb = r"C:\Program Files\WindowsApps\WinDbg\amd64\cdb.exe"
    with mock.patch.object(md, "_get_local_cdb_path", return_value=r"C:\app\DebuggingTools\x64\cdb.exe"), mock.patch.object(
        md, "_get_bundled_cdb_path", return_value=bundled
    ), mock.patch.object(md, "_get_windbg_app_cdb_path", return_value=app_cdb), mock.patch.object(
        md, "_is_online", return_value=False
    ), mock.patch.object(md, "_cdb_engine_usable", return_value=True), mock.patch(
        "os.path.isfile", return_value=True
    ):
        paths = md._get_cdb_search_paths()
    assert paths.index(bundled) < paths.index(app_cdb)


def test_windbg_msix_url_parsed_from_winget_show() -> None:
    sample = """
Found WinDbg [Microsoft.WinDbg]
Version: 1.2606.22001.0
Installer:
  Installer Url: https://windbg.download.prss.microsoft.com/dbazure/prod/windbg.msixbundle
"""
    with mock.patch("subprocess.run") as run:
        run.return_value = mock.Mock(returncode=0, stdout=sample, stderr="")
        url = md._windbg_msix_download_url()
    assert url and url.startswith("https://windbg.download")


def test_resolve_windbg_url_uses_github_then_fallback() -> None:
    with mock.patch.object(md, "_windbg_msix_download_url", return_value=None), mock.patch.object(
        md, "_windbg_msix_url_from_github_manifest",
        return_value="https://windbg.download.prss.microsoft.com/from-github",
    ):
        assert md._resolve_windbg_msix_url().endswith("from-github")
    with mock.patch.object(md, "_windbg_msix_download_url", return_value=None), mock.patch.object(
        md, "_windbg_msix_url_from_github_manifest", return_value=None
    ):
        assert md._resolve_windbg_msix_url() == md.WINDDBG_MSIX_FALLBACK_URL


def test_install_cdb_online_uses_direct_msix_not_winget_install() -> None:
    with mock.patch.object(md, "_is_online", return_value=True), mock.patch.object(
        md, "find_cdb", return_value=None
    ), mock.patch.object(md, "_find_windbg_app_engine_dir", return_value=None), mock.patch.object(
        md, "_install_windbg_online", return_value=(True, "ok")
    ) as online, mock.patch.object(
        md, "_finalize_online_windbg_install", return_value=(True, "done")
    ):
        ok, msg = md.install_cdb()
    assert ok is True
    online.assert_called_once()


def test_install_cdb_online_installs_windbg_even_when_bundled_present() -> None:
    with mock.patch.object(md, "_is_online", return_value=True), mock.patch.object(
        md, "find_cdb", return_value=r"C:\app\_internal\DebuggingTools\x64\cdb.exe"
    ), mock.patch.object(md, "_find_windbg_app_engine_dir", return_value=None), mock.patch.object(
        md, "_install_windbg_online", return_value=(True, "ok")
    ) as online, mock.patch.object(
        md, "_finalize_online_windbg_install", return_value=(True, "done")
    ):
        ok, msg = md.install_cdb()
    assert ok is True
    online.assert_called_once()


def test_windbg_msix_fallback_not_stale_vs_github() -> None:
    """Fails when winget-pkgs has a newer WinDbg than WINDDBG_MSIX_FALLBACK_VERSION."""
    latest = md._windbg_latest_version_label()
    if not latest:
        return
    fb = md.WINDDBG_MSIX_FALLBACK_VERSION
    assert md._version_sort_key(fb) >= md._version_sort_key(latest), (
        f"Run: py -3 scripts/sync_install_fallbacks.py — "
        f"GitHub manifest {latest} is newer than fallback {fb}"
    )


def test_windbg_install_logs_on_online_install() -> None:
    with mock.patch.object(md, "_reset_windbg_install_log") as reset, mock.patch.object(
        md, "_resolve_windbg_msix_url", return_value="https://example/msix"
    ), mock.patch.object(md, "_download_windbg_msix_bundle", return_value=(False, "network test")):
        md._install_windbg_online(lambda _m: None)
    reset.assert_called_once()


if __name__ == "__main__":
    test_should_prompt_cdb_online_when_no_windbg_app()
    test_should_not_prompt_cdb_when_offline()
    test_should_not_prompt_cdb_when_windbg_app_present()
    test_cdb_search_paths_online_prefers_windbg_app_before_bundled()
    test_cdb_search_paths_offline_prefers_bundled_before_windbg_app()
    test_windbg_msix_url_parsed_from_winget_show()
    test_resolve_windbg_url_uses_github_then_fallback()
    test_install_cdb_online_uses_direct_msix_not_winget_install()
    test_install_cdb_online_installs_windbg_even_when_bundled_present()
    test_windbg_msix_fallback_not_stale_vs_github()
    test_windbg_install_logs_on_online_install()
    print("CDB online prompt tests OK")
