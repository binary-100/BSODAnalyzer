"""Tests for quarantined analysis_core spike (D1 scaffold).

Does not modify production behavior. Spike path is injected for imports only.
"""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

import pytest

_SPIKES = Path(__file__).resolve().parents[1] / "docs" / "upgrade" / "plans" / "spikes"
_FIXTURES = _SPIKES / "analysis_core" / "fixtures"
if str(_SPIKES) not in sys.path:
    sys.path.insert(0, str(_SPIKES))

from analysis_core.cdb_reference import cdb_available  # noqa: E402
from analysis_core.contract import (  # noqa: E402
    empty_dump_analysis,
    normalize_dump_analysis,
    parity_field_diff,
)
from analysis_core.native_minimal import analyze_minidump_native_stub  # noqa: E402
from analysis_core.parity_harness import main as parity_main, run_parity  # noqa: E402


def _make_page_header(code: int = 0x124, p1: int = 0) -> bytes:
    buf = bytearray(0x1000)
    struct.pack_into("<I", buf, 0, 0x45474150)  # PAGE
    struct.pack_into("<I", buf, 0x38, code)
    struct.pack_into("<Q", buf, 0x40, p1)
    return bytes(buf)


def _make_mdmp_with_exception(code: int = 0x50) -> bytes:
    """Minimal MDMP with 32-byte header + one ExceptionStream (type 6)."""
    sig = b"MDMP"
    ver = 0xA793
    nstreams = 1
    header_size = 32
    dir_rva = header_size
    exc_size = 16
    exc_rva = dir_rva + 12
    buf = bytearray(exc_rva + exc_size)
    struct.pack_into("<4sIIIIIQ", buf, 0, sig, ver, nstreams, dir_rva, 0, 0, 0)
    struct.pack_into("<III", buf, dir_rva, 6, exc_size, exc_rva)
    struct.pack_into("<II", buf, exc_rva, 0, 0)  # thread id + padding
    struct.pack_into("<I", buf, exc_rva + 8, code)
    return bytes(buf)


def test_empty_dump_analysis_has_required_keys():
    d = empty_dump_analysis(source="native_stub", confidence="low")
    assert d["analysis_source"] == "native_stub"
    assert d["analysis_confidence"] == "low"
    assert d["stack_frames"] == []
    assert d["raw"] == []


def test_parity_field_diff_detects_mismatch():
    native = {"faulting_driver": "foo.sys", "bugcheck_code": "0x00000050"}
    cdb = {"faulting_driver": "bar.sys", "bugcheck_code": "0x00000050"}
    diffs = parity_field_diff(native, cdb)
    assert "faulting_driver" in diffs
    assert "bugcheck_code" not in diffs


def test_parity_hex_normalization():
    native = {"bugcheck_code": "0x50"}
    cdb = {"bugcheck_code": "0x00000050"}
    assert parity_field_diff(native, cdb) == {}


def test_page_stub_reads_bugcheck_from_header():
    data = _make_page_header(0x124, 0x1234)
    with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        result = analyze_minidump_native_stub(path)
        assert result is not None
        assert result["bugcheck_code"] == "0x00000124"
        assert result["bugcheck_p1"] == "0x0000000000001234"
        assert result["analysis_source"] == "native_stub"
        assert result.get("bugcheck_str")
    finally:
        Path(path).unlink(missing_ok=True)


def test_checked_in_page_fixture():
    fixture = _FIXTURES / "page_minimal.dmp"
    assert fixture.is_file(), "fixtures/page_minimal.dmp must be committed"
    result = analyze_minidump_native_stub(fixture)
    assert result is not None
    assert result["bugcheck_code"] == "0x00000124"


def test_mdmp_reads_exception_stream_not_module_list():
    data = _make_mdmp_with_exception(0x50)
    with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        result = analyze_minidump_native_stub(path)
        assert result is not None
        assert result["bugcheck_code"] == "0x00000050"
        assert any("MDMP" in line for line in result.get("raw", []))
    finally:
        Path(path).unlink(missing_ok=True)


def test_native_stub_rejects_non_dump():
    with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
        f.write(b"NOTADUMP")
        path = f.name
    try:
        assert analyze_minidump_native_stub(path) is None
    finally:
        Path(path).unlink(missing_ok=True)


def test_parity_harness_empty_corpus_exits_clean():
    with tempfile.TemporaryDirectory() as tmp:
        report = run_parity(Path(tmp))
        assert report.dumps == []
        assert isinstance(report.cdb_available, bool)
        assert parity_main(["--corpus", tmp]) == 0


def test_parity_harness_fixtures_no_strict():
    if not (_FIXTURES / "page_minimal.dmp").is_file():
        pytest.skip("fixture missing")
    with tempfile.TemporaryDirectory() as tmp:
        # fixtures-only via include-fixtures; empty corpus + fixtures
        code = parity_main(["--corpus", tmp, "--include-fixtures", "--no-strict"])
        assert code == 0


def test_cdb_available_uses_find_cdb():
    # When CDB is bundled, this should be True on the maintainer host.
    assert isinstance(cdb_available(), bool)


def test_normalize_dump_analysis_coerces_lists():
    d = normalize_dump_analysis({"stack_frames": ("a",), "raw": None})
    assert d is not None
    assert d["stack_frames"] == ["a"]
    assert d["raw"] == []
