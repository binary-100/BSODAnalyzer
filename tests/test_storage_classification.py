"""Storage drive classification for firmware inventory."""

from __future__ import annotations

from bsod_hardware_wmi import _classify_storage_drive


def test_hybrid_sshd_classified() -> None:
    assert _classify_storage_drive("ST2000LX001-1RG174", "SCSI", 2000.0) == "hybrid_hdd"


def test_sandisk_ultra_usb_removable() -> None:
    assert (
        _classify_storage_drive("SanDisk Ultra USB 3.0", "USB", 64.0, bus_type=7)
        == "usb_removable"
    )


def test_nvme_ssd_classified() -> None:
    assert (
        _classify_storage_drive("Samsung SSD 970 EVO Plus 500GB NVMe", "SSD", 500.0, media_type=4)
        == "nvme_ssd"
    )
    assert (
        _classify_storage_drive("WDS500G3X0C-00SJG0", "SSD", 500.0, media_type=4)
        == "ssd"
    )


def test_internal_hdd() -> None:
    assert _classify_storage_drive("WDC WD10EZEX", "IDE", 1000.0, media_type=3) == "hdd"


if __name__ == "__main__":
    test_hybrid_sshd_classified()
    test_sandisk_ultra_usb_removable()
    test_nvme_ssd_classified()
    test_internal_hdd()
    print("storage classification tests OK")
