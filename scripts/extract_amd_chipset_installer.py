"""Carve embedded 7z payload from AMD NSIS chipset installer and list INFs."""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

SEVEN_Z_SIG = bytes([0x37, 0x7A, 0xBC, 0xAF, 0x27, 0x1C])


def find_7z_offsets(data: bytes) -> list[int]:
    offsets: list[int] = []
    idx = 0
    while True:
        i = data.find(SEVEN_Z_SIG, idx)
        if i < 0:
            break
        offsets.append(i)
        idx = i + 1
    return offsets


def try_py7zr_extract(blob: bytes, dest: Path) -> bool:
    try:
        import py7zr
    except ImportError:
        return False
    tmp = dest.parent / "_carved.7z"
    tmp.write_bytes(blob)
    try:
        with py7zr.SevenZipFile(tmp, mode="r") as arc:
            arc.extractall(path=dest)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"py7zr failed: {exc}")
        return False
    finally:
        tmp.unlink(missing_ok=True)


def try_7zip_cli(archive: Path, dest: Path) -> bool:
    for exe in (
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ):
        if not exe.is_file():
            continue
        r = subprocess.run(
            [str(exe), "x", str(archive), f"-o{dest}", "-y"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return True
        print(r.stderr or r.stdout)
    return False


def list_infs(root: Path) -> list[dict]:
    rows: list[dict] = []
    for inf in sorted(root.rglob("*.inf")):
        text = inf.read_text(encoding="utf-8", errors="ignore")
        provider = ""
        m = re.search(r"Provider\s*=\s*\"([^\"]+)\"", text, re.I)
        if m:
            provider = m.group(1).strip()
        driver_ver = ""
        m = re.search(r"DriverVer\s*=\s*([^\n\r]+)", text, re.I)
        if m:
            driver_ver = m.group(1).strip()
        devices: list[str] = []
        for dm in re.finditer(r"^\s*\[%([^\]]+)\]", text, re.M):
            tag = dm.group(1).strip()
            if tag.lower().startswith(("version", "strings", "signature", "manufacturer")):
                continue
            if "." not in tag:
                continue
            devices.append(tag)
        rows.append(
            {
                "inf": str(inf.relative_to(root)),
                "provider": provider,
                "driver_ver": driver_ver,
                "sections": devices[:12],
                "section_count": len(devices),
            }
        )
    return rows


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"c:\Users\binar\Downloads\amd_chipset_software_8.05.04.516.exe"
    )
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        r"c:\Users\binar\OneDrive\Desktop\BSODAnalyzer\_tmp_chipset_extract"
    )
    if dest.exists():
        import shutil

        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    data = src.read_bytes()
    print(f"Installer: {src} ({len(data)} bytes)")
    offsets = find_7z_offsets(data)
    print(f"7z signatures found: {len(offsets)}")
    if not offsets:
        print("No embedded 7z archive — installer may use a different packer.")
        return 1

    # Prefer the largest trailing archive (NSIS usually embeds one main payload).
    best_off = max(offsets, key=lambda o: len(data) - o)
    blob = data[best_off:]
    print(f"Trying 7z carve at offset {best_off} ({len(blob)} bytes)")

    if try_py7zr_extract(blob, dest):
        print("Extracted via py7zr")
    else:
        carved = dest.parent / "_carved.7z"
        carved.write_bytes(blob)
        if try_7zip_cli(carved, dest):
            print("Extracted via 7-Zip CLI")
        else:
            print("Install py7zr (pip install py7zr) or 7-Zip to extract payload.")
            return 2

    infs = list_infs(dest)
    print(f"\nINF files: {len(infs)}")
    for row in infs:
        print(f"\n{row['inf']}")
        if row["provider"]:
            print(f"  Provider: {row['provider']}")
        if row["driver_ver"]:
            print(f"  DriverVer: {row['driver_ver']}")
        if row["sections"]:
            print(f"  Devices ({row['section_count']}): {', '.join(row['sections'][:8])}")
            if row["section_count"] > 8:
                print(f"    ... +{row['section_count'] - 8} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
