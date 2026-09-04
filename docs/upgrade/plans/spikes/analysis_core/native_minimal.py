"""Minimal native dump reader (spike) — PAGE triage + limited MDMP.

Windows BSOD minidumps in C:\\Windows\\Minidump are typically **PAGE** (kernel
DUMP_HEADER64 / triage), not classic user-mode **MDMP**. Full D2 should evaluate
kdmp-parser / kdmp-parser-rs; this spike reads only stable header fields.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .contract import empty_dump_analysis, normalize_dump_analysis

# DUMP_HEADER64.Signature — little-endian u32 spells 'PAGE'
_PAGE_SIGNATURE = 0x45474150
_MDMP_SIGNATURE = b"MDMP"

# Standard DUMP_HEADER64 field offsets (see Windows DUMP_HEADER64 / kdmp-parser Header64)
_OFF_BUGCHECK_CODE = 0x38
_OFF_BUGCHECK_P1 = 0x40
_OFF_BUGCHECK_P2 = 0x48
_OFF_BUGCHECK_P3 = 0x50
_OFF_BUGCHECK_P4 = 0x58

# MINIDUMP_HEADER (32 bytes)
_MDMP_HEADER_FMT = "<4sIIIIIQ"
_MDMP_DIR_ENTRY_FMT = "<III"
_STREAM_EXCEPTION = 6
_STREAM_MISC_INFO = 15


def analyze_minidump_native_stub(path: str | Path) -> dict[str, Any] | None:
    """Return partial dict from dump bytes, or None if unrecognized."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = p.read_bytes()
    except OSError:
        return None
    if len(data) < 32:
        return None

    sig_le = struct.unpack_from("<I", data, 0)[0]
    if sig_le == _PAGE_SIGNATURE or data[:4] == b"PAGE":
        return _parse_page_triage(data)
    if data[:4] == _MDMP_SIGNATURE:
        return _parse_mdmp(data)
    return None


def _parse_page_triage(data: bytes) -> dict[str, Any]:
    """Kernel triage dump — BugCheckCode in DUMP_HEADER64."""
    if len(data) < _OFF_BUGCHECK_P4 + 8:
        out = empty_dump_analysis(source="native_stub", confidence="low")
        out["raw"] = ["native_stub: PAGE dump too small for header fields"]
        return normalize_dump_analysis(out)

    code = struct.unpack_from("<I", data, _OFF_BUGCHECK_CODE)[0]
    p1, p2, p3, p4 = struct.unpack_from("<4Q", data, _OFF_BUGCHECK_P1)
    out = empty_dump_analysis(source="native_stub", confidence="medium")
    out["bugcheck_code"] = f"0x{code:08X}"
    out["bugcheck_p1"] = f"0x{p1:016X}"
    out["bugcheck_str"] = _derive_bugcheck_str(out["bugcheck_code"])
    out["raw"] = [
        f"native_stub: PAGE triage header code=0x{code:08X} p1=0x{p1:016X}",
        f"native_stub: p2=0x{p2:016X} p3=0x{p3:016X} p4=0x{p4:016X}",
        "native_stub: faulting_driver requires TRIAGE driver list (D2)",
    ]
    return normalize_dump_analysis(out)


def _parse_mdmp(data: bytes) -> dict[str, Any] | None:
    """Classic MDMP — scan Exception/MiscInfo streams; no fake BugCheck stream."""
    if len(data) < 32:
        return None
    try:
        _, _, nstreams, dir_rva, _, _, _ = struct.unpack_from(_MDMP_HEADER_FMT, data, 0)
    except struct.error:
        return None
    if nstreams == 0 or dir_rva + nstreams * 12 > len(data):
        return None

    streams_found: list[int] = []
    bugcheck_code: int | None = None
    offset = dir_rva
    for _ in range(nstreams):
        if offset + 12 > len(data):
            break
        stream_type, data_size, rva = struct.unpack_from(_MDMP_DIR_ENTRY_FMT, data, offset)
        offset += 12
        streams_found.append(stream_type)
        if stream_type == _STREAM_EXCEPTION and rva + 4 <= len(data):
            # MINIDUMP_EXCEPTION_STREAM: ThreadId then ExceptionRecord; code often at +8
            if rva + 12 <= len(data):
                exc_code = struct.unpack_from("<I", data, rva + 8)[0]
                if bugcheck_code is None:
                    bugcheck_code = exc_code
        elif stream_type == _STREAM_MISC_INFO and rva + 8 <= len(data):
            # MINIDUMP_MISC_INFO may carry Flags1; full bugcheck parse deferred to D2
            pass

    out = empty_dump_analysis(source="native_stub", confidence="low")
    out["raw"] = [
        f"native_stub: MDMP streams present: {streams_found}",
        "native_stub: MDMP kernel attribution deferred to D2 (use PAGE path for BSOD minidumps)",
    ]
    if bugcheck_code is not None:
        out["bugcheck_code"] = f"0x{bugcheck_code:08X}"
        out["bugcheck_str"] = _derive_bugcheck_str(out["bugcheck_code"])
        out["analysis_confidence"] = "low"
    return normalize_dump_analysis(out)


def _derive_bugcheck_str(code_hex: str | None) -> str | None:
    if not code_hex:
        return None
    try:
        import sys
        from pathlib import Path as _Path

        root = _Path(__file__).resolve().parents[5]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from bsod_crash_report import get_bugcheck_info

        code_int = int(code_hex, 16)
        name, _desc = get_bugcheck_info(code_int)
        if name.lower().startswith("0x"):
            return name
        return f"{name} (0x{code_int:08X})"
    except Exception:
        return None
