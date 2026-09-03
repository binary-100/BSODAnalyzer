"""One-shot: extract hardware profile scan from bsod_analyzer.py."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "bsod_analyzer.py"
OUT = APP / "analyzer_hardware.py"

# After gather extract, re-measure FUNC_RANGE on bsod_analyzer.py before running this script.
FUNC_RANGE = (250, 358)


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT.name} already exists — remove or rename before re-running.")

    if "def gather_hardware_profile" not in SRC.read_text(encoding="utf-8"):
        raise SystemExit(f"{SRC.name} has no gather_hardware_profile — already extracted?")

    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = FUNC_RANGE
    body = "".join(lines[start - 1 : end])

    header = '''"""Drivers-tab hardware scan without event logs (extracted from bsod_analyzer)."""

from __future__ import annotations

from bsod_hardware_wmi import (
    get_bios_and_driver_versions,
    get_devices_with_driver_problems,
    get_devices_with_generic_driver,
    get_hardware_profile_wmi_bundle,
    get_pnp_entities_for_analysis,
    get_storage_and_system_context,
)
from bsod_crash_report import (
    build_hardware_enrichment_bundle,
    device_inventory_for_matching,
    enrich_bios_driver_info,
    get_wmi_monitor_edid_by_device_id,
)


'''

    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len((header + body).splitlines())} lines approx)")

    del lines[start - 1 : end]
    text = "".join(lines)

    import_block = """from analyzer_hardware import gather_hardware_profile

"""
    needle = "from analyzer_gather import"
    if needle not in text:
        raise SystemExit("analyzer_gather import anchor not found")
    idx = text.index(needle)
    end_idx = text.index("\n", idx) + 1
    text = text[:end_idx] + import_block + text[end_idx:]

    SRC.write_text(text, encoding="utf-8")
    print(f"Updated {SRC}")


if __name__ == "__main__":
    main()
