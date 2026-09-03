"""Unit tests for the data-driven vendor version extraction engine (b2)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vendor_extractors as ve


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_AMD_NEXT = (
    '<html><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{"version":"26.6.4","driverPackageVersion":"32.0.21043.19003"}}}'
    "</script></html>"
)
_INTEL_HTML = (
    "<html><body>Version: 32.0.101.6790 (Latest) "
    "also older 31.0.101.1000 junk 26</body></html>"
)
_GIGABYTE_HTML = (
    '{"fileTitle":"AMD Chipset Drivers","fileVersion":"6.02.22.027"}'
    # JSON-style escaped slash in the raw page text (one backslash + slash).
    '{"fileTitle":"Realtek LAN\\/Ethernet","fileVersion":"10.73.822.2025"}'
)
_MEDIATEK_HTML = (
    '<a href="https://cdn.example.com/drivers/mt7922_1.2.3.4.exe">dl</a>'
    '<a href="https://cdn.example.com/other/readme.txt">skip</a>'
    '<a href="https://cdn.example.com/wifi/mt7921_2.0.1.zip">dl2</a>'
)
_JSON_LD = (
    '<script type="application/ld+json">'
    '{"@type":"SoftwareApplication","softwareVersion":"24.0.1.2"}'
    "</script>"
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_is_version_shaped_requires_min_parts() -> None:
    assert ve.is_version_shaped("26.6.4") is True
    assert ve.is_version_shaped("32.0.101.6790") is True
    assert ve.is_version_shaped("26") is False  # min_parts default 2
    assert ve.is_version_shaped("26", min_parts=1) is True
    assert ve.is_version_shaped("") is False
    assert ve.is_version_shaped("not-a-version") is False


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------
def test_transforms() -> None:
    assert ve.apply_transforms("  1.2.3  ", ["strip"]) == "1.2.3"
    assert ve.apply_transforms("a\\/b", ["unescape_slashes"]) == "a/b"
    assert ve.apply_transforms("ABC", ["lower"]) == "abc"
    assert ve.apply_transforms("  X\\/Y  ", ["strip", "unescape_slashes", "lower"]) == "x/y"
    # Unknown transform ignored (fail-open)
    assert ve.apply_transforms("1.2", ["bogus", "strip"]) == "1.2"


# ---------------------------------------------------------------------------
# regex kind
# ---------------------------------------------------------------------------
def test_regex_first_match() -> None:
    ext = {
        "mode": "scalar",
        "version": [
            {"kind": "regex", "pattern": r"(\d+\.\d+\.\d+\.\d+)\s*\(Latest\)"},
        ],
    }
    assert ve.extract_version(_INTEL_HTML, ext) == "32.0.101.6790"


def test_regex_pick_max() -> None:
    ext = {
        "mode": "scalar",
        "version": [
            {"kind": "regex", "pattern": r"\d+\.\d+\.\d+\.\d+", "group": 0, "pick": "max"},
        ],
    }
    # 32.0… > 31.0…
    assert ve.extract_version(_INTEL_HTML, ext) == "32.0.101.6790"


def test_regex_rejects_single_digit_by_default() -> None:
    html = "<p>build 26 is here and also 1.2.3</p>"
    ext = {
        "mode": "scalar",
        "version": [
            {"kind": "regex", "pattern": r"\b(\d+)\b", "pick": "first"},
            {"kind": "regex", "pattern": r"(\d+\.\d+\.\d+)"},
        ],
    }
    # First rule matches "26" but min_parts=2 rejects it; second rule wins.
    assert ve.extract_version(html, ext) == "1.2.3"


def test_regex_param_substitution_is_escaped() -> None:
    html = "Product RX-7900 version 24.5.1 and RX version 1.0.0"
    ext = {
        "mode": "scalar",
        "version": [
            {
                "kind": "regex",
                "pattern": r"{family}[^\d]{0,40}(\d+\.\d+\.\d+)",
                "pick": "max",
            },
        ],
    }
    assert ve.extract_version(html, ext, params={"family": "RX-7900"}) == "24.5.1"


def test_ordered_rules_first_valid_wins() -> None:
    html = "fallback 9.9.9 primary 1.2.3"
    ext = {
        "mode": "scalar",
        "version": [
            {"kind": "regex", "pattern": r"primary\s+(\d+\.\d+\.\d+)"},
            {"kind": "regex", "pattern": r"fallback\s+(\d+\.\d+\.\d+)"},
        ],
    }
    assert ve.extract_version(html, ext) == "1.2.3"


def test_bad_rule_skipped_fail_open() -> None:
    ext = {
        "mode": "scalar",
        "version": [
            {"kind": "nope"},  # unknown kind
            {"kind": "regex", "pattern": "x" * 500},  # over length cap
            {"kind": "regex", "pattern": r"(\d+\.\d+\.\d+)"},
        ],
    }
    assert ve.extract_version("ver 3.4.5", ext) == "3.4.5"


# ---------------------------------------------------------------------------
# json_next_data
# ---------------------------------------------------------------------------
def test_json_next_data_path() -> None:
    ext = {
        "mode": "scalar",
        "version": [
            {
                "kind": "json_next_data",
                "path": "props.pageProps.driverPackageVersion",
            },
        ],
    }
    assert ve.extract_version(_AMD_NEXT, ext) == "32.0.21043.19003"


def test_json_next_data_blob_pick_max() -> None:
    ext = {
        "mode": "scalar",
        "version": [
            {
                "kind": "json_next_data",
                "pattern": r"(\d+\.\d+\.\d+(?:\.\d+)?)",
                "pick": "max",
            },
        ],
    }
    # 32.0… > 26.6.4
    assert ve.extract_version(_AMD_NEXT, ext) == "32.0.21043.19003"


# ---------------------------------------------------------------------------
# json_ld
# ---------------------------------------------------------------------------
def test_json_ld_path() -> None:
    ext = {
        "mode": "scalar",
        "version": [{"kind": "json_ld", "path": "softwareVersion"}],
    }
    assert ve.extract_version(_JSON_LD, ext) == "24.0.1.2"


# ---------------------------------------------------------------------------
# rows_pair / link_filename
# ---------------------------------------------------------------------------
def test_rows_pair_gigabyte_shape() -> None:
    ext = {
        "mode": "rows",
        "version": [
            {
                "kind": "rows_pair",
                "pattern": (
                    r'"fileTitle"\s*:\s*"(?P<title>(?:[^"\\]|\\.)+)"\s*,\s*'
                    r'"fileVersion"\s*:\s*"(?P<version>[^"]+)"'
                ),
                "transforms_title": ["unescape_slashes", "strip"],
            }
        ],
    }
    rows = ve.extract_rows(_GIGABYTE_HTML, ext)
    assert len(rows) == 2
    assert rows[0]["version"] == "6.02.22.027"
    assert rows[1]["title"] == "Realtek LAN/Ethernet"
    assert rows[1]["version"] == "10.73.822.2025"


def test_link_filename_mediatek_shape() -> None:
    ext = {
        "mode": "rows",
        "version": [
            {
                "kind": "link_filename",
                "link_pattern": r"https://[^\"'\s<>]+\.(?:exe|zip|cab|msi)",
                "version_pattern": r"(\d+\.\d+\.\d+(?:\.\d+)?)",
            }
        ],
    }
    rows = ve.extract_rows(_MEDIATEK_HTML, ext)
    vers = {r["version"] for r in rows}
    assert vers == {"1.2.3.4", "2.0.1"}


# ---------------------------------------------------------------------------
# date + dispatch
# ---------------------------------------------------------------------------
def test_extract_date() -> None:
    html = "Released: 2026-05-20 Version 1.2.3"
    ext = {
        "mode": "scalar",
        "version": [{"kind": "regex", "pattern": r"(\d+\.\d+\.\d+)"}],
        "date": [{"kind": "regex", "pattern": r"Released:\s*(\d{4}-\d{2}-\d{2})"}],
    }
    assert ve.extract_version(html, ext) == "1.2.3"
    assert ve.extract_date(html, ext) == "2026-05-20"


def test_run_extractor_dispatches_mode() -> None:
    scalar = {
        "mode": "scalar",
        "version": [{"kind": "regex", "pattern": r"(\d+\.\d+\.\d+)"}],
    }
    assert ve.run_extractor("v 1.2.3", scalar) == "1.2.3"
    rows_ext = {
        "mode": "rows",
        "version": [
            {
                "kind": "rows_pair",
                "pattern": r'title="(?P<title>[^"]+)"\s+ver="(?P<version>[^"]+)"',
            }
        ],
    }
    out = ve.run_extractor('title="A" ver="4.5.6"', rows_ext)
    assert isinstance(out, list) and out[0]["version"] == "4.5.6"


# ---------------------------------------------------------------------------
# Merge (prepend) — needed by b4 but tested here as part of the engine contract
# ---------------------------------------------------------------------------
def test_merge_prepends_override_rules() -> None:
    bundled = {
        "mode": "scalar",
        "version": [{"kind": "regex", "pattern": r"bundled-(\d+\.\d+\.\d+)", "id": "b"}],
    }
    override = {
        "version": [{"kind": "regex", "pattern": r"override-(\d+\.\d+\.\d+)", "id": "o"}],
    }
    merged = ve.merge_extractor_rules(bundled, override)
    assert merged["mode"] == "scalar"
    assert [r.get("id") for r in merged["version"]] == ["o", "b"]


def test_merge_replace_flag() -> None:
    bundled = {
        "mode": "scalar",
        "version": [{"kind": "regex", "pattern": r"bundled-(\d+\.\d+)"}],
    }
    override = {
        "replace": True,
        "version": [{"kind": "regex", "pattern": r"only-(\d+\.\d+)"}],
    }
    merged = ve.merge_extractor_rules(bundled, override)
    assert "replace" not in merged
    assert len(merged["version"]) == 1
    assert "only-" in merged["version"][0]["pattern"]


def test_merge_empty_override_returns_bundled() -> None:
    bundled = {"mode": "scalar", "version": [{"kind": "regex", "pattern": r"(\d+\.\d+)"}]}
    assert ve.merge_extractor_rules(bundled, None) == bundled
    assert ve.merge_extractor_rules(bundled, {}) == bundled


def test_merge_replace_with_invalid_rules_fails_open() -> None:
    bundled = {
        "mode": "scalar",
        "version": [{"kind": "regex", "pattern": r"bundled-(\d+\.\d+)", "id": "b"}],
    }
    override = {
        "replace": True,
        "version": [{"kind": "regex", "pattern": "x" * 500}],
    }
    merged = ve.merge_extractor_rules(bundled, override)
    assert [r.get("id") for r in merged["version"]] == ["b"]


def test_sanitize_rule_rejects_nested_quant() -> None:
    assert ve.sanitize_rule({"kind": "regex", "pattern": r"(a+)+"}) is None
    assert ve.sanitize_rule({"kind": "regex", "pattern": r"(\d+\.\d+\.\d+)"}) is not None


def test_sanitize_extractor_keeps_valid_subset() -> None:
    cleaned = ve.sanitize_extractor(
        {
            "mode": "scalar",
            "version": [
                {"kind": "nope"},
                {"kind": "regex", "pattern": r"(\d+\.\d+\.\d+)", "id": "ok"},
            ],
            "extra_ignored": True,
        }
    )
    assert cleaned is not None
    assert cleaned["mode"] == "scalar"
    assert len(cleaned["version"]) == 1
    assert cleaned["version"][0]["id"] == "ok"
    assert "extra_ignored" not in cleaned


def test_bundled_extractors_sanitize_clean() -> None:
    """Shipped defaults must survive the same sanitizer used for overrides."""
    for vendor, hints in ve.BUNDLED_EXTRACTORS.items():
        for hint, ext in hints.items():
            cleaned = ve.sanitize_extractor(ext)
            assert cleaned is not None, f"{vendor}/{hint} failed sanitize"
            assert len(cleaned.get("version") or []) == len(ext.get("version") or [])


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------
def test_input_clipped_to_max() -> None:
    # Engine must not crash / hang on oversized input.
    huge = "x" * (ve.MAX_INPUT_CHARS + 50_000) + " Version 7.8.9 "
    # Version is past the clip point — should NOT match (clip drops the tail).
    ext = {
        "mode": "scalar",
        "version": [{"kind": "regex", "pattern": r"Version\s+(\d+\.\d+\.\d+)"}],
    }
    assert ve.extract_version(huge, ext) == ""
    # Version inside the window still works.
    ok = " Version 7.8.9 " + ("x" * 1000)
    assert ve.extract_version(ok, ext) == "7.8.9"


def test_empty_inputs() -> None:
    assert ve.extract_version("", {"version": []}) == ""
    assert ve.extract_version("hi", None) == ""
    assert ve.extract_rows("", {"mode": "rows", "version": []}) == []


if __name__ == "__main__":
    test_is_version_shaped_requires_min_parts()
    test_transforms()
    test_regex_first_match()
    test_regex_pick_max()
    test_regex_rejects_single_digit_by_default()
    test_regex_param_substitution_is_escaped()
    test_ordered_rules_first_valid_wins()
    test_bad_rule_skipped_fail_open()
    test_json_next_data_path()
    test_json_next_data_blob_pick_max()
    test_json_ld_path()
    test_rows_pair_gigabyte_shape()
    test_link_filename_mediatek_shape()
    test_extract_date()
    test_run_extractor_dispatches_mode()
    test_merge_prepends_override_rules()
    test_merge_replace_flag()
    test_merge_empty_override_returns_bundled()
    test_merge_replace_with_invalid_rules_fails_open()
    test_sanitize_rule_rejects_nested_quant()
    test_sanitize_extractor_keeps_valid_subset()
    test_bundled_extractors_sanitize_clean()
    test_input_clipped_to_max()
    test_empty_inputs()
    print("vendor_extractors tests OK")
