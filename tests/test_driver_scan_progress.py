"""Per-device driver scan progress lines."""

from __future__ import annotations

import driver_catalog as dc


def test_format_device_check_progress_newer() -> None:
    line = dc.format_device_check_progress(
        "NVIDIA GeForce RTX",
        {
            "installed_version": "31.0.15.100",
            "status": "newer",
            "offers": [
                {
                    "source_label": "OEM (Dell / Alienware)",
                    "version": "32.0.15.200",
                    "vs_installed": "newer",
                }
            ],
        },
        done=2,
        total=5,
    )
    assert "31.0.15.100" in line
    assert "32.0.15.200" in line
    assert "Dell" in line
    assert line.startswith("Checked 2/5")


def test_format_device_check_progress_batch_counter() -> None:
    line = dc.format_device_check_progress(
        "Realtek Audio",
        {"installed_version": "6.0.1", "status": "none", "offers": []},
        done=3,
        total=10,
    )
    assert line.startswith("Checked 3/10")
    assert "WU/OEM" in line


def test_format_device_check_progress_no_match() -> None:
    line = dc.format_device_check_progress(
        "Realtek Audio",
        {"installed_version": "6.0.1", "status": "none", "offers": []},
    )
    assert line.startswith("Checked Realtek")
    assert "WU/OEM" in line


if __name__ == "__main__":
    test_format_device_check_progress_newer()
    test_format_device_check_progress_batch_counter()
    test_format_device_check_progress_no_match()
    print("OK")
