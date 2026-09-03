"""Optional 7-Zip detection for .7z driver archives."""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bsod_runtime as rt
import driver_install as drvinst


def test_seven_zip_not_available_by_default_probe() -> None:
    rt.reset_seven_zip_probe()
    with mock.patch("shutil.which", return_value=None):
        with mock.patch("os.path.isfile", return_value=False):
            rt.reset_seven_zip_probe()
            assert rt.seven_zip_available() is False


def test_seven_zip_detects_from_program_files() -> None:
    rt.reset_seven_zip_probe()
    fake = r"C:\Program Files\7-Zip\7z.exe"

    def isfile(path: str) -> bool:
        return path == fake

    with mock.patch("shutil.which", return_value=None):
        with mock.patch("os.path.isfile", side_effect=isfile):
            with mock.patch(
                "subprocess.run",
                return_value=mock.Mock(returncode=0, stdout="7-Zip 24.08", stderr=""),
            ):
                rt.reset_seven_zip_probe()
                assert rt.seven_zip_available() is True
                assert rt.seven_zip_exe() == fake


def test_package_may_need_seven_zip() -> None:
    assert rt.package_may_need_seven_zip("https://x.com/pkg.7z")
    assert not rt.package_may_need_seven_zip("https://x.com/pkg.cab")


def test_find_vendor_setup_exe_prefers_shallow() -> None:
    import tempfile

    root = tempfile.mkdtemp()
    nested = os.path.join(root, "sub")
    os.makedirs(nested, exist_ok=True)
    deep = os.path.join(nested, "Setup.exe")
    shallow = os.path.join(root, "setup.exe")
    for p in (deep, shallow):
        with open(p, "wb") as fh:
            fh.write(b"")
    hit = drvinst._find_vendor_setup_exe(root)
    assert hit == shallow


def test_targets_from_extracted_zip_with_setup_only() -> None:
    import tempfile

    work = tempfile.mkdtemp()
    setup = os.path.join(work, "Setup.exe")
    with open(setup, "wb") as fh:
        fh.write(b"")
    ok, err, targets = drvinst._targets_from_extracted_tree(work)
    assert ok, err
    assert targets == [(setup, False)]


def test_needs_seven_zip_but_missing() -> None:
    rt.reset_seven_zip_probe()
    with mock.patch("shutil.which", return_value=None):
        with mock.patch("os.path.isfile", return_value=False):
            rt.reset_seven_zip_probe()
            assert drvinst.needs_seven_zip_but_missing(
                {"url": "https://example.com/chipset.7z"}
            )


if __name__ == "__main__":
    test_seven_zip_not_available_by_default_probe()
    test_seven_zip_detects_from_program_files()
    test_package_may_need_seven_zip()
    test_find_vendor_setup_exe_prefers_shallow()
    test_targets_from_extracted_zip_with_setup_only()
    test_needs_seven_zip_but_missing()
    print("seven zip runtime tests OK")
