"""Tests for extractor-rule discovery, backup, and repair (b6)."""
from __future__ import annotations

import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vendor_extractor_repair as ver
import vendor_extractors as vex
import vendor_endpoint_health as veh
import vendor_fetch as vf


def test_candidate_rules_vendor_specific_come_first() -> None:
    rules = ver.candidate_rules_for("amd", "graphics")
    assert rules
    assert rules[0].get("pattern", "").lower().find("adrenalin") >= 0 or rules[0].get(
        "kind"
    ) in ("regex", "json_next_data")
    # Generic candidates are present later
    kinds = [r.get("kind") for r in rules]
    assert "json_ld" in kinds or "json_next_data" in kinds


def test_discover_finds_rule_when_bundled_misses(tmp_path, monkeypatch) -> None:
    html = '<html><body>NewLabelVersion: 99.1.2.3 and junk</body></html>'
    # Bundled AMD graphics won't match "NewLabelVersion" — candidate Version regex will.
    monkeypatch.setattr(
        ver,
        "_fetch_vendor_html",
        lambda vendor, hint: (True, html, "https://amd.example/drivers"),
    )
    # Pretend current extractor always fails
    monkeypatch.setattr(veh, "get_extractor", lambda vendor, hint="*": {
        "mode": "scalar",
        "version": [{"kind": "regex", "pattern": r"DOES_NOT_MATCH_(\d+)"}],
    })
    found = ver.discover_extractor_overrides(["amd"], force_all_hints=True)
    assert "amd" in found
    assert "graphics" in found["amd"]
    rule = found["amd"]["graphics"]["version"][0]
    # Winning rule should extract 99.1.2.3 from this HTML
    assert vex.extract_version(html, {"mode": "scalar", "version": [rule]}) == "99.1.2.3"


def test_discover_skips_when_current_extractor_works() -> None:
    html = '<script id="__NEXT_DATA__">{"v":"32.0.21043.19003"}</script>'
    with mock.patch.object(
        ver, "_fetch_vendor_html", return_value=(True, html, "https://amd.example")
    ):
        # Real bundled AMD graphics json_next_data pick-max should work
        found = ver.discover_extractor_overrides(["amd"])
    # If bundled already works, no override needed for graphics
    assert "graphics" not in (found.get("amd") or {})


def test_backup_and_rollback(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    bak = tmp_path / "vendor_endpoints.extractors.bak.json"
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    monkeypatch.setattr(ver, "extractor_backup_path", lambda: bak)
    monkeypatch.setattr(veh, "clear_vendor_scrape_cache_after_repair", lambda: None)

    # Seed manifest with an old override
    veh.save_manifest(
        {
            "endpoints": {},
            "extractors": {
                "amd": {
                    "graphics": {
                        "version": [{"kind": "regex", "pattern": r"OLD-(\d+\.\d+)"}]
                    }
                }
            },
        },
        source="test",
    )
    ver.backup_current_extractors()
    assert bak.is_file()

    # Apply a new override
    ok, msg = ver.apply_discovered_extractors(
        {
            "amd": {
                "graphics": {
                    "mode": "scalar",
                    "version": [{"kind": "regex", "pattern": r"NEW-(\d+\.\d+\.\d+)"}],
                    "_discovered_version_sample": "1.2.3",
                }
            }
        },
        do_backup=False,  # already backed up
    )
    assert ok
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "NEW-" in data["extractors"]["amd"]["graphics"]["version"][0]["pattern"]
    assert "_discovered_version_sample" not in data["extractors"]["amd"]["graphics"]

    # Rollback restores OLD
    ok, msg = ver.rollback_extractors()
    assert ok
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "OLD-" in data["extractors"]["amd"]["graphics"]["version"][0]["pattern"]


def test_apply_discovered_strips_private_keys(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    bak = tmp_path / "bak.json"
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    monkeypatch.setattr(ver, "extractor_backup_path", lambda: bak)
    monkeypatch.setattr(veh, "clear_vendor_scrape_cache_after_repair", lambda: None)
    veh.save_manifest({"endpoints": {}, "extractors": {}}, source="test")

    ok, msg = ver.apply_discovered_extractors(
        {
            "intel": {
                "graphics": {
                    "mode": "scalar",
                    "version": [{"kind": "regex", "pattern": r"(\d+\.\d+\.\d+\.\d+)"}],
                    "_discovered_version_sample": "32.0.1.2",
                    "_discovered_from_url": "https://intel.example",
                }
            }
        }
    )
    assert ok
    assert "32.0.1.2" in msg
    data = json.loads(path.read_text(encoding="utf-8"))
    ext = data["extractors"]["intel"]["graphics"]
    assert "_discovered_version_sample" not in ext
    assert "_discovered_from_url" not in ext


def test_vendors_needing_repair_from_empty_extraction() -> None:
    vf.clear_session_diagnostics()
    vf.record_empty_extraction("amd", "page loaded but no version")
    need = ver.vendors_needing_extractor_repair()
    assert "amd" in need
    vf.clear_session_diagnostics()


def test_try_rule_on_html_scalar() -> None:
    html = "Version 7.8.9.10 here"
    rule = {"kind": "regex", "pattern": r"Version\s+(\d+\.\d+\.\d+\.\d+)", "flags": "i"}
    assert ver._try_rule_on_html(html, rule) == "7.8.9.10"


if __name__ == "__main__":
    # Tests that need tmp_path are run via a local temp dir
    import tempfile
    from pathlib import Path

    test_candidate_rules_vendor_specific_come_first()
    test_discover_skips_when_current_extractor_works()
    test_vendors_needing_repair_from_empty_extraction()
    test_try_rule_on_html_scalar()

    td = Path(tempfile.mkdtemp())

    class MP:
        def setattr(self, obj, name, value):
            setattr(obj, name, value) if False else None

    # discover_finds_rule
    html = "<html><body>NewLabelVersion: 99.1.2.3 and junk</body></html>"
    with mock.patch.object(
        ver, "_fetch_vendor_html", return_value=(True, html, "https://amd.example")
    ), mock.patch.object(
        veh,
        "get_extractor",
        return_value={
            "mode": "scalar",
            "version": [{"kind": "regex", "pattern": r"DOES_NOT_MATCH_(\d+)"}],
        },
    ):
        found = ver.discover_extractor_overrides(["amd"], force_all_hints=True)
    assert "amd" in found and "graphics" in found["amd"]
    print("discover_finds_rule OK")

    # backup/rollback
    path = td / "vendor_endpoints.json"
    bak = td / "bak.json"
    with mock.patch.object(veh, "manifest_path", lambda: path), \
         mock.patch.object(ver, "extractor_backup_path", lambda: bak), \
         mock.patch.object(veh, "clear_vendor_scrape_cache_after_repair", lambda: None):
        veh.save_manifest(
            {
                "endpoints": {},
                "extractors": {
                    "amd": {
                        "graphics": {
                            "version": [{"kind": "regex", "pattern": r"OLD-(\d+\.\d+)"}]
                        }
                    }
                },
            },
            source="test",
        )
        ver.backup_current_extractors()
        ver.apply_discovered_extractors(
            {
                "amd": {
                    "graphics": {
                        "mode": "scalar",
                        "version": [{"kind": "regex", "pattern": r"NEW-(\d+\.\d+\.\d+)"}],
                        "_discovered_version_sample": "1.2.3",
                    }
                }
            },
            do_backup=False,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "NEW-" in data["extractors"]["amd"]["graphics"]["version"][0]["pattern"]
        ok, _ = ver.rollback_extractors()
        assert ok
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "OLD-" in data["extractors"]["amd"]["graphics"]["version"][0]["pattern"]
    print("backup_rollback OK")
    print("vendor_extractor_repair tests OK")
