"""Tests for vendor endpoint health and user-approved repairs."""
from __future__ import annotations

import json
from unittest import mock

import vendor_endpoint_health as veh
import vendor_extractors as vex


def test_get_endpoint_uses_bundled_default() -> None:
    with mock.patch.object(veh, "load_manifest", return_value={"endpoints": {}}):
        url = veh.get_endpoint("amd", "download_page", "http://default.test")
    assert "amd.com" in url


def test_get_endpoint_prefers_user_manifest() -> None:
    manifest = {
        "endpoints": {
            "amd": {
                "download_page": "https://www.amd.com/en/support/download/drivers.html?v=2"
            }
        }
    }
    with mock.patch.object(veh, "load_manifest", return_value=manifest):
        assert (
            veh.get_endpoint("amd", "download_page", "")
            == "https://www.amd.com/en/support/download/drivers.html?v=2"
        )


def test_get_endpoint_rejects_non_allowlisted_host() -> None:
    manifest = {"endpoints": {"amd": {"download_page": "https://evil.example/amd"}}}
    with mock.patch.object(veh, "load_manifest", return_value=manifest):
        url = veh.get_endpoint("amd", "download_page", "")
    assert "amd.com" in url
    assert "evil.example" not in url


def test_endpoint_url_allowed() -> None:
    assert veh.endpoint_url_allowed(
        "amd", "https://www.amd.com/en/support/download/drivers.html"
    )
    assert veh.endpoint_url_allowed("nvidia", "https://gfwsl.geforce.com/x")
    assert not veh.endpoint_url_allowed("amd", "http://www.amd.com/x")
    assert not veh.endpoint_url_allowed("amd", "https://amd.com.evil.test/x")
    assert not veh.endpoint_url_allowed("amd", "https://evil.com/x")
    assert not veh.endpoint_url_allowed("amd", "https://user:pass@www.amd.com/x")


def test_apply_repair_rejects_non_allowlisted(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    monkeypatch.setattr(veh, "clear_vendor_scrape_cache_after_repair", lambda: None)
    ok, msg = veh.apply_repair_manifest(
        {"amd": {"download_page": "https://evil.example/amd"}}
    )
    assert ok is False
    assert "allowlisted" in msg.lower() or "https" in msg.lower()


def test_replace_with_only_bad_rules_fails_open_to_bundled() -> None:
    manifest = {
        "endpoints": {},
        "extractors": {
            "amd": {
                "graphics": {
                    "replace": True,
                    "mode": "scalar",
                    "version": [
                        {"kind": "nope"},
                        {"kind": "regex", "pattern": "x" * 500},
                    ],
                }
            }
        },
    }
    with mock.patch.object(veh, "load_manifest", return_value=manifest):
        ext = veh.get_extractor("amd", "graphics")
    bundled = vex.get_bundled_extractor("amd", "graphics")
    assert ext is not None and bundled is not None
    assert len(ext["version"]) == len(bundled["version"])


def test_sanitize_strips_invalid_rules_on_apply(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    monkeypatch.setattr(veh, "clear_vendor_scrape_cache_after_repair", lambda: None)
    ok, _msg = veh.apply_extractor_overrides(
        {
            "amd": {
                "graphics": {
                    "version": [
                        {"kind": "nope"},
                        {
                            "kind": "regex",
                            "pattern": r"SAFE-(\d+\.\d+\.\d+)",
                            "flags": "ix",  # x dropped
                            "id": "safe",
                        },
                    ]
                }
            }
        }
    )
    assert ok
    data = json.loads(path.read_text(encoding="utf-8"))
    rules = data["extractors"]["amd"]["graphics"]["version"]
    assert len(rules) == 1
    assert rules[0]["id"] == "safe"
    assert rules[0]["flags"] == "i"


def test_load_manifest_drops_bad_endpoint(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    path.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "endpoints": {
                    "amd": {
                        "download_page": "https://evil.example/x",
                        "ok_page": "https://www.amd.com/ok",
                    }
                },
                "extractors": {
                    "amd": {
                        "graphics": {
                            "version": [{"kind": "regex", "pattern": "x" * 500}]
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    data = veh.load_manifest()
    assert "evil.example" not in json.dumps(data)
    assert data["endpoints"]["amd"]["ok_page"] == "https://www.amd.com/ok"
    assert "amd" not in (data.get("extractors") or {})


def test_apply_repair_saves_manifest(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    monkeypatch.setattr(veh, "clear_vendor_scrape_cache_after_repair", lambda: None)
    ok, msg = veh.apply_repair_manifest(
        {"amd": {"download_page": "https://www.amd.com/en/support/download/drivers.html"}}
    )
    assert ok
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["endpoints"]["amd"]["download_page"].startswith("https://")
    assert "extractors" in data


def test_fetch_remote_manifest_requires_https() -> None:
    data, err = veh.fetch_remote_manifest("http://insecure.test/x.json")
    assert data is None
    assert "https" in err.lower()


def test_run_user_repair_local_only(monkeypatch) -> None:
    monkeypatch.setattr(veh, "BUNDLED_LOOKUP_MANIFEST_URL", "")
    monkeypatch.setattr(
        veh,
        "discover_working_endpoints",
        lambda progress=None: {
            "amd": {"download_page": "https://www.amd.com/en/support/download/drivers.html"}
        },
    )
    monkeypatch.setattr(
        veh,
        "apply_repair_manifest",
        lambda d: (True, "Saved lookup settings for: amd."),
    )
    ok, msg = veh.run_user_repair()
    assert ok
    assert "amd" in msg.lower()


# ---------------------------------------------------------------------------
# Extractor overrides (b4)
# ---------------------------------------------------------------------------
def test_get_extractor_falls_back_to_bundled() -> None:
    with mock.patch.object(
        veh, "load_manifest", return_value={"endpoints": {}, "extractors": {}}
    ):
        ext = veh.get_extractor("amd", "graphics")
    assert ext is not None
    assert ext.get("mode") == "scalar"
    assert isinstance(ext.get("version"), list) and ext["version"]
    bundled = vex.get_bundled_extractor("amd", "graphics")
    assert [r.get("kind") for r in ext["version"]] == [
        r.get("kind") for r in (bundled or {}).get("version") or []
    ]


def test_get_extractor_prepends_manifest_override() -> None:
    override_rule = {
        "kind": "regex",
        "pattern": r"OVERRIDE-(\d+\.\d+\.\d+)",
        "id": "override",
    }
    manifest = {
        "endpoints": {},
        "extractors": {
            "amd": {
                "graphics": {
                    "version": [override_rule],
                }
            }
        },
    }
    with mock.patch.object(veh, "load_manifest", return_value=manifest):
        ext = veh.get_extractor("amd", "graphics")
    assert ext is not None
    assert ext["version"][0].get("id") == "override"
    assert len(ext["version"]) > 1  # bundled rules still present after override


def test_get_extractor_replace_flag() -> None:
    manifest = {
        "endpoints": {},
        "extractors": {
            "amd": {
                "graphics": {
                    "replace": True,
                    "mode": "scalar",
                    "version": [
                        {"kind": "regex", "pattern": r"ONLY-(\d+\.\d+)", "id": "only"}
                    ],
                }
            }
        },
    }
    with mock.patch.object(veh, "load_manifest", return_value=manifest):
        ext = veh.get_extractor("amd", "graphics")
    assert ext is not None
    assert len(ext["version"]) == 1
    assert ext["version"][0].get("id") == "only"
    assert "replace" not in ext


def test_extract_bundled_version_honors_override() -> None:
    html = "OVERRIDE-9.8.7 and Adrenalin 26.6.4"
    manifest = {
        "endpoints": {},
        "extractors": {
            "amd": {
                "graphics": {
                    "version": [
                        {"kind": "regex", "pattern": r"OVERRIDE-(\d+\.\d+\.\d+)"}
                    ],
                }
            }
        },
    }
    with mock.patch.object(veh, "load_manifest", return_value=manifest):
        assert vex.extract_bundled_version("amd", html, hint="graphics") == "9.8.7"


def test_apply_extractor_overrides_persists(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    monkeypatch.setattr(veh, "clear_vendor_scrape_cache_after_repair", lambda: None)
    ok, msg = veh.apply_extractor_overrides(
        {
            "intel": {
                "graphics": {
                    "version": [
                        {"kind": "regex", "pattern": r"NEW-(\d+\.\d+\.\d+\.\d+)"}
                    ]
                }
            }
        }
    )
    assert ok
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "extractors" in data
    assert data["extractors"]["intel"]["graphics"]["version"][0]["kind"] == "regex"
    assert "intel/graphics" in msg


def test_apply_extractor_overrides_rejects_bad_shape() -> None:
    ok, msg = veh.apply_extractor_overrides(
        {"amd": {"graphics": {"version": "not-a-list"}}}  # type: ignore[dict-item]
    )
    assert ok is False
    assert "no valid" in msg.lower()


def test_merge_remote_manifest_extractors_only(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    monkeypatch.setattr(veh, "clear_vendor_scrape_cache_after_repair", lambda: None)
    ok, msg = veh.merge_remote_manifest(
        {
            "manifest_version": 1,
            "extractors": {
                "marvell": {
                    "*": {
                        "mode": "rows",
                        "version": [
                            {
                                "kind": "rows_pair",
                                "pattern": (
                                    r'"title"\s*:\s*"(?P<title>[^"]+)"[^}]*?'
                                    r'"version"\s*:\s*"(?P<version>[^"]+)"'
                                ),
                            }
                        ],
                    }
                }
            },
        }
    )
    assert ok
    assert "extractors" in msg.lower()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "marvell" in data["extractors"]


def test_app_meets_min_version() -> None:
    assert veh.app_meets_min_version("", app_version="6.2.4")
    assert veh.app_meets_min_version("6.2.4", app_version="6.2.4")
    assert veh.app_meets_min_version("6.2.0", app_version="6.2.4")
    assert not veh.app_meets_min_version("9.0.0", app_version="6.2.4")


def test_validate_rejects_high_min_app_version() -> None:
    data, err = veh.validate_remote_manifest(
        {
            "manifest_version": 1,
            "min_app_version": "99.0.0",
            "endpoints": {
                "amd": {
                    "download_page": "https://www.amd.com/en/support/download/drivers.html"
                }
            },
        },
        app_version="6.2.4",
    )
    assert data is None
    assert "99.0.0" in err


def test_validate_hmac_required_when_key_set(monkeypatch) -> None:
    monkeypatch.setattr(veh, "BUNDLED_MANIFEST_HMAC_KEY", "test-secret-key")
    unsigned = {
        "manifest_version": 1,
        "endpoints": {
            "amd": {
                "download_page": "https://www.amd.com/en/support/download/drivers.html"
            }
        },
    }
    data, err = veh.validate_remote_manifest(unsigned, app_version="6.2.4")
    assert data is None
    assert "signature" in err.lower()

    signed = dict(unsigned)
    signed["signature"] = veh.sign_manifest(signed, key="test-secret-key")
    data, err = veh.validate_remote_manifest(signed, app_version="6.2.4")
    assert err == ""
    assert data is not None
    assert "amd" in data["endpoints"]


def test_validate_hmac_rejects_tamper(monkeypatch) -> None:
    monkeypatch.setattr(veh, "BUNDLED_MANIFEST_HMAC_KEY", "test-secret-key")
    payload = {
        "manifest_version": 1,
        "endpoints": {
            "amd": {
                "download_page": "https://www.amd.com/en/support/download/drivers.html"
            }
        },
    }
    payload["signature"] = veh.sign_manifest(payload, key="test-secret-key")
    payload["endpoints"]["amd"]["download_page"] = (
        "https://www.amd.com/en/support/download/drivers.html?evil=1"
    )
    data, err = veh.validate_remote_manifest(payload, app_version="6.2.4")
    assert data is None
    assert "mismatch" in err.lower()


def test_merge_remote_candidates(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    monkeypatch.setattr(veh, "clear_vendor_scrape_cache_after_repair", lambda: None)
    ok, msg = veh.merge_remote_manifest(
        {
            "manifest_version": 1,
            "candidates": {
                "intel": {
                    "graphics_product": [
                        "https://www.intel.com/content/www/us/en/download/19344/"
                        "intel-graphics-windows-dch-drivers.html",
                        "https://evil.example/x",
                    ]
                }
            },
        }
    )
    assert ok
    assert "candidates" in msg.lower()
    data = json.loads(path.read_text(encoding="utf-8"))
    urls = data["candidates"]["intel"]["graphics_product"]
    assert len(urls) == 1
    assert "intel.com" in urls[0]
    assert "evil.example" not in json.dumps(data)


def test_example_manifest_validates() -> None:
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / "lookup_manifest.example.json"
    raw = json.loads(example.read_text(encoding="utf-8"))
    data, err = veh.validate_remote_manifest(raw, app_version="6.2.4")
    assert err == "", err
    assert data is not None
    assert data["extractors"] or data["endpoints"]


def test_load_manifest_normalizes_extractors_key(tmp_path, monkeypatch) -> None:
    path = tmp_path / "vendor_endpoints.json"
    path.write_text(
        json.dumps({"manifest_version": 1, "endpoints": {"amd": {}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(veh, "manifest_path", lambda: path)
    data = veh.load_manifest()
    assert data["extractors"] == {}


def test_oem_firmware_health_probe_dell(monkeypatch) -> None:
    ctx = {"system_manufacturer": "Dell Inc."}
    probes = veh._oem_firmware_catalog_probes(ctx)
    assert any(k == "oem_dell" for k, _l, _fn in probes)

    with mock.patch(
        "driver_catalog._fetch_dell_oem_rows_live",
        return_value=([{"title": "BIOS", "version": "1.0"}], "https://dell.com"),
    ):
        rows = veh.run_oem_firmware_health_probes(ctx)
    assert len(rows) == 1
    assert rows[0].vendor == "oem_dell"
    assert rows[0].ok is True

    with mock.patch(
        "driver_catalog._fetch_dell_oem_rows_live",
        return_value=([], "https://dell.com/support"),
    ):
        rows = veh.run_oem_firmware_health_probes(ctx)
    assert rows[0].ok is False


def test_run_health_check_includes_oem_for_dell(monkeypatch) -> None:
    ctx = {"system_manufacturer": "Dell Inc."}
    monkeypatch.setattr(veh, "_probe_nvidia", lambda: veh.VendorHealthRow("nvidia", "NVIDIA", True))
    monkeypatch.setattr(veh, "_probe_amd", lambda: veh.VendorHealthRow("amd", "AMD", True))
    monkeypatch.setattr(veh, "_probe_intel", lambda: veh.VendorHealthRow("intel", "Intel", True))
    with mock.patch(
        "bsod_hardware_wmi.nvidia_driver_lookup_applicable",
        return_value=False,
    ), mock.patch(
        "bsod_hardware_wmi.amd_driver_lookup_applicable",
        return_value=False,
    ), mock.patch(
        "bsod_hardware_wmi.intel_driver_lookup_applicable",
        return_value=False,
    ), mock.patch(
        "driver_catalog._fetch_dell_oem_rows_live",
        return_value=([{"title": "BIOS"}], "https://dell.com"),
    ):
        rows = veh.run_health_check(ctx)
    assert any(r.vendor == "oem_dell" for r in rows)


if __name__ == "__main__":
    test_get_endpoint_uses_bundled_default()
    test_get_endpoint_prefers_user_manifest()
    test_fetch_remote_manifest_requires_https()
    test_get_extractor_falls_back_to_bundled()
    test_get_extractor_prepends_manifest_override()
    test_get_extractor_replace_flag()
    test_extract_bundled_version_honors_override()
    test_apply_extractor_overrides_rejects_bad_shape()
    print("vendor_endpoint_health tests OK (run pytest for full suite)")
