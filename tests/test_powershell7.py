"""PowerShell 7 detection and optional PnP parent parallel lookup."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import bsod_runtime as rt


def test_powershell7_not_available_by_default_probe() -> None:
    rt.reset_powershell7_probe()
    with mock.patch("shutil.which", return_value=None), mock.patch(
        "os.path.isfile", return_value=False
    ):
        rt.reset_powershell7_probe()
        assert rt.powershell7_available() is False


def test_powershell7_detects_from_which() -> None:
    rt.reset_powershell7_probe()

    def fake_run(args, **kwargs):
        class R:
            returncode = 0
            stdout = "7.4.5\n"
            stderr = ""

        return R()

    with mock.patch("shutil.which", return_value=r"C:\Program Files\PowerShell\7\pwsh.exe"), mock.patch(
        "subprocess.run", side_effect=fake_run
    ):
        rt.reset_powershell7_probe()
        assert rt.powershell7_available() is True
        assert rt.powershell7_version() == "7.4.5"


def test_should_prompt_when_missing_and_not_dismissed() -> None:
    rt.reset_powershell7_probe()
    with mock.patch.object(rt, "powershell7_available", return_value=False):
        assert rt.should_prompt_powershell7_upgrade({}) is True
        assert (
            rt.should_prompt_powershell7_upgrade({"powershell7_upgrade_dismissed": True})
            is False
        )
        assert (
            rt.should_prompt_powershell7_upgrade({"powershell7_upgrade_prompt": False})
            is False
        )


def test_wait_for_powershell7_detects_after_reset() -> None:
    rt.reset_powershell7_probe()
    calls = {"n": 0}

    def fake_available() -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    with mock.patch.object(rt, "powershell7_available", side_effect=fake_available):
        with mock.patch.object(rt, "powershell7_version", return_value="7.5.0"):
            with mock.patch("time.sleep", return_value=None):
                ok, ver = rt.wait_for_powershell7_installed(timeout_sec=10, poll_sec=0.01)
    assert ok is True
    assert ver == "7.5.0"


def test_powershell7_install_script_path_dev_layout() -> None:
    path = rt.powershell7_install_script_path()
    assert path.endswith("install_powershell7.ps1")
    assert "scripts" in path.replace("\\", "/")


def test_powershell7_install_log_path_under_temp() -> None:
    path = rt.powershell7_install_log_path()
    assert path.endswith("BSODAnalyzer_pwsh7_install.log")
    temp = os.environ.get("TEMP", "")
    assert temp and path.startswith(temp)


def test_powershell7_driver_search_speedup_label() -> None:
    assert "5" in rt.PWSH7_DRIVER_SEARCH_SPEEDUP_LABEL
    assert "×" in rt.PWSH7_DRIVER_SEARCH_SPEEDUP_LABEL


def test_launch_powershell7_uses_open_when_admin() -> None:
    with mock.patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=True), mock.patch(
        "ctypes.windll.shell32.ShellExecuteW", return_value=42
    ) as shell_exec, mock.patch("os.path.isfile", return_value=True):
        ok, msg = rt.launch_powershell7_install_elevated()
    assert ok is True
    assert shell_exec.call_args[0][1] == "open"


def test_launch_powershell7_uses_runas_when_not_admin() -> None:
    with mock.patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=False), mock.patch(
        "ctypes.windll.shell32.ShellExecuteW", return_value=42
    ) as shell_exec, mock.patch("os.path.isfile", return_value=True):
        ok, _msg = rt.launch_powershell7_install_elevated()
    assert ok is True
    assert shell_exec.call_args[0][1] == "runas"


def test_powershell7_install_failure_message_mentions_admin_when_not_elevated() -> None:
    with mock.patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=False):
        text = rt.powershell7_install_failure_message("Install timed out.")
    assert "not running as administrator" in text


def test_powershell7_install_failure_message_skips_admin_when_elevated() -> None:
    with mock.patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=True):
        text = rt.powershell7_install_failure_message("Install timed out.")
    assert "not running as administrator" not in text


def test_install_powershell7_script_uses_direct_msi_first() -> None:
    script = Path(rt.powershell7_install_script_path())
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "Install-Pwsh7Msi" in text
    assert "3010" in text
    assert "BSODAnalyzer_pwsh7_install.log" in text
    assert "Get-Pwsh7MsiUrlFromWingetPkgs" in text
    assert text.index("Install-Pwsh7Msi") < text.index("Get-Pwsh7MsiUrlFromWingetPkgs")
    assert text.index("Get-Pwsh7MsiUrlFromWingetPkgs") < text.index("Install-Pwsh7Winget")


def test_windbg_install_failure_message_includes_log_path() -> None:
    msg = rt.windbg_install_failure_message("Install timed out.")
    assert "BSODAnalyzer_windbg_install.log" in msg
    assert "bundled CDB" in msg


def test_build_parallel_parent_script_uses_foreach_parallel() -> None:
    script = rt.build_pnp_parent_lookup_script("abc123", parallel=True)
    assert "ForEach-Object -Parallel" in script
    assert "ConvertFrom-Json -AsArray" not in script


def test_build_serial_parent_script_no_parallel() -> None:
    script = rt.build_pnp_parent_lookup_script("abc123", parallel=False)
    assert "ForEach-Object -Parallel" not in script
    assert "foreach ($id in $ids)" in script


if __name__ == "__main__":
    test_powershell7_not_available_by_default_probe()
    test_powershell7_detects_from_which()
    test_should_prompt_when_missing_and_not_dismissed()
    test_wait_for_powershell7_detects_after_reset()
    test_powershell7_install_script_path_dev_layout()
    test_powershell7_install_log_path_under_temp()
    test_powershell7_driver_search_speedup_label()
    test_launch_powershell7_uses_open_when_admin()
    test_launch_powershell7_uses_runas_when_not_admin()
    test_powershell7_install_failure_message_mentions_admin_when_not_elevated()
    test_powershell7_install_failure_message_skips_admin_when_elevated()
    test_install_powershell7_script_uses_direct_msi_first()
    test_windbg_install_failure_message_includes_log_path()
    test_build_parallel_parent_script_uses_foreach_parallel()
    test_build_serial_parent_script_no_parallel()
    print("PowerShell 7 tests OK")
