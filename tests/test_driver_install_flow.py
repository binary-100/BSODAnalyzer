"""Unified Install driver flow — capability, download routing, vendor launch."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import driver_install as drvinst


def test_offer_install_blocks_utility_rows() -> None:
    can, reason = drvinst.offer_install_capability(
        {
            "source": "utility",
            "title": "Intel Driver & Support Assistant",
            "url": "https://www.intel.com/content/www/us/en/support/detect.html",
            "download_kind": "url",
        }
    )
    assert can is False
    assert "detection" in reason.lower() or "tool" in reason.lower()


def test_offer_install_capability_catalog_without_update_id() -> None:
    offer = {
        "source": "microsoft",
        "download_kind": "catalog",
        "title": "Realtek MEDIA Driver Update (6.0.10001.1)",
        "version": "6.0.10001.1",
        "update_id": "",
    }
    can, reason = drvinst.offer_install_capability(offer)
    assert can
    assert "Catalog" in reason


def test_offer_install_capability_vendor_exe_path() -> None:
    can, reason = drvinst.offer_install_capability(
        {"downloaded_path": r"C:\Downloads\nvidia.exe"}
    )
    assert can
    assert "vendor installer" in reason.lower()


def test_offer_install_capability_direct_url() -> None:
    can, _reason = drvinst.offer_install_capability(
        {
            "download_kind": "url",
            "url": "https://example.com/driver.cab",
        }
    )
    assert can


def test_install_launches_vendor_exe() -> None:
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
        path = tmp.name
    try:
        with mock.patch("driver_install.os.startfile") as startfile, mock.patch(
            "driver_install.os.path.isfile", return_value=True
        ), mock.patch("driver_install.os.path.abspath", return_value=path):
            ok, msg = drvinst.launch_vendor_installer(path)
        assert ok
        assert "vendor installer" in msg.lower()
        startfile.assert_called_once_with(path)
    finally:
        os.unlink(path)


def test_install_driver_offer_downloads_then_pnputil() -> None:
    offer = {
        "download_kind": "url",
        "url": "https://example.com/pkg.cab",
    }
    progress: list[str] = []
    updated = {**offer, "downloaded_path": r"C:\x\pkg.cab"}

    with mock.patch.object(
        drvinst,
        "_ensure_package_downloaded",
        return_value=(True, "ok", updated),
    ), mock.patch.object(
        drvinst,
        "install_driver_via_pnputil",
        return_value=(True, "pnputil ok"),
    ) as mock_pnp:
        ok, msg, out_offer = drvinst.install_driver_offer(
            offer, device_name="Wi-Fi", progress_cb=progress.append
        )
    assert ok
    assert "pnputil ok" in msg
    assert "Wi-Fi" in msg
    assert out_offer.get("downloaded_path") == r"C:\x\pkg.cab"
    mock_pnp.assert_called_once_with(r"C:\x\pkg.cab", device_ctx=None)


def test_install_failure_still_returns_downloaded_offer() -> None:
    updated = {
        "download_kind": "url",
        "url": "https://example.com/pkg.cab",
        "downloaded_path": r"C:\x\pkg.cab",
    }
    with mock.patch.object(
        drvinst,
        "_ensure_package_downloaded",
        return_value=(True, "ok", updated),
    ), mock.patch.object(
        drvinst,
        "install_driver_via_pnputil",
        return_value=(False, "Access denied"),
    ):
        ok, msg, out_offer = drvinst.install_driver_offer(updated)
    assert not ok
    assert "Access denied" in msg
    assert out_offer.get("downloaded_path") == r"C:\x\pkg.cab"


def test_collect_pnputil_targets_cab_tries_expand_then_direct() -> None:
    with tempfile.NamedTemporaryFile(suffix=".cab", delete=False) as f:
        cab = f.name
    try:
        inf_root = tempfile.mkdtemp()
        inf_path = os.path.join(inf_root, "driver.inf")
        with open(inf_path, "w", encoding="utf-8") as fh:
            fh.write("; test\n")
        with mock.patch.object(
            drvinst,
            "_expand_cab_all",
            return_value=(True, ""),
        ), mock.patch.object(
            drvinst,
            "_find_inf_dir",
            return_value=inf_root,
        ):
            ok, err, targets = drvinst._collect_pnputil_targets(cab)
        assert ok, err
        assert targets == [(inf_root, True), (cab, False)]
    finally:
        os.unlink(cab)


def test_install_via_pnputil_falls_back_to_second_target() -> None:
    cab = r"C:\x\audio.cab"
    inf_root = r"C:\temp\bsod_cab_xyz"
    with mock.patch.object(
        drvinst,
        "_collect_pnputil_targets",
        return_value=(True, "", [(inf_root, True), (cab, False)]),
    ), mock.patch.object(
        drvinst,
        "_run_pnputil_once",
        side_effect=[(False, "folder install failed"), (True, "cab ok")],
    ) as pnp_mock:
        ok, msg = drvinst.install_driver_via_pnputil(cab)
    assert ok
    assert "cab ok" in msg
    assert "fallback method 2" in msg
    assert pnp_mock.call_count == 2


def test_expand_cab_all_tries_multiple_methods() -> None:
    calls: list[str] = []

    def _fail(_cab: str, _dest: str) -> tuple[bool, str]:
        calls.append("fail")
        return False, "nope"

    def _ok(_cab: str, dest: str) -> tuple[bool, str]:
        calls.append("ok")
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, "x.inf"), "w", encoding="utf-8") as fh:
            fh.write("; test\n")
        return True, ""

    with mock.patch.object(drvinst, "_expand_cab_star", side_effect=_fail), mock.patch.object(
        drvinst, "_expand_cab_legacy", side_effect=_ok
    ), mock.patch.object(drvinst, "_expand_cab_tar", side_effect=_fail):
        work = tempfile.mkdtemp()
        ok, err = drvinst._expand_cab_all("fake.cab", work)
    assert ok, err
    assert calls == ["fail", "ok"]


def test_collect_pnputil_targets_zip_falls_back_to_setup_exe() -> None:
    import tempfile
    import zipfile

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as zf:
        zip_path = zf.name
    work = tempfile.mkdtemp()
    setup = os.path.join(work, "Setup.exe")
    with open(setup, "wb") as fh:
        fh.write(b"MZ")
    try:
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(setup, "Setup.exe")
        ok, err, targets = drvinst._collect_pnputil_targets(zip_path)
        assert ok, err
        assert len(targets) == 1
        assert targets[0][0].lower().endswith("setup.exe")
    finally:
        os.unlink(zip_path)


def test_resolve_catalog_update_id_picks_version_match() -> None:
    import catalog_ps_module as cps

    rows = [
        {"title": "Other driver 1.0", "update_id": "11111111-1111-1111-1111-111111111111"},
        {
            "title": "Realtek MEDIA Driver Update (6.0.10001.1)",
            "version": "6.0.10001.1",
            "update_id": "22222222-2222-2222-2222-222222222222",
        },
    ]
    with mock.patch.object(cps, "search_mscatalog_updates", return_value=(rows, "")):
        uid, err = cps.resolve_catalog_update_id(
            {
                "title": "Realtek MEDIA Driver Update (6.0.10001.1)",
                "version": "6.0.10001.1",
            }
        )
    assert not err
    assert uid == "22222222-2222-2222-2222-222222222222"


def test_offer_install_blocks_uncertain_microsoft_without_hwid() -> None:
    offer = {
        "source": "microsoft",
        "update_id": "f2a9aa3b-54d6-4c00-ad13-d85a5d79fdf5",
        "title": "Realtek MEDIA Driver Update (6.0.10001.1)",
        "vs_installed": "uncertain",
        "hwid_matched": False,
    }
    can, reason = drvinst.offer_install_capability(offer)
    assert not can
    assert "Hardware ID" in reason


def test_classify_driver_install_outcome_windows_kept() -> None:
    msg = (
        "Microsoft PnP Utility\n"
        "Driver package added successfully.\n"
        "Published Name: oem42.inf\n"
        "Driver package is not a better match than the current driver."
    )
    assert drvinst.classify_driver_install_outcome(msg) == "windows_kept_driver"


if __name__ == "__main__":
    test_offer_install_blocks_utility_rows()
    test_offer_install_capability_catalog_without_update_id()
    test_offer_install_capability_vendor_exe_path()
    test_offer_install_capability_direct_url()
    test_install_launches_vendor_exe()
    test_install_driver_offer_downloads_then_pnputil()
    test_install_failure_still_returns_downloaded_offer()
    test_collect_pnputil_targets_cab_tries_expand_then_direct()
    test_install_via_pnputil_falls_back_to_second_target()
    test_expand_cab_all_tries_multiple_methods()
    test_collect_pnputil_targets_zip_falls_back_to_setup_exe()
    test_resolve_catalog_update_id_picks_version_match()
    test_offer_install_blocks_uncertain_microsoft_without_hwid()
    test_classify_driver_install_outcome_windows_kept()
    print("driver install flow tests OK")
