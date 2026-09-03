"""Vendor driver lookup health, user-approved endpoint repairs, optional remote manifest."""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import app_settings as app_set

MANIFEST_VERSION = 1

# When you host a lookup manifest, set this in a release build. End users never paste URLs.
BUNDLED_LOOKUP_MANIFEST_URL = ""

# HMAC-SHA256 key for remote manifest authenticity (same secret used by
# scripts/sign_vendor_manifest.py). Empty = signatures not required (https +
# allowlist + sanitize still apply). Non-empty = signature field mandatory.
# Keep the key aligned with the hosted file's signer; rotate by shipping a new build.
BUNDLED_MANIFEST_HMAC_KEY = ""

# Max body size for a remote lookup catalog (DoS guard).
MAX_REMOTE_MANIFEST_BYTES = 512_000

# Shipped defaults — updated in normal app releases.
BUNDLED_ENDPOINTS: dict[str, dict[str, str]] = {
    "nvidia": {
        "ajax_base": (
            "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/"
            "AjaxDriverService.php"
        ),
        "processfind_base": "https://www.nvidia.com/Download/processFind.aspx",
    },
    "amd": {
        "download_page": "https://www.amd.com/en/support/download/drivers.html",
    },
    "intel": {
        "graphics_product": (
            "https://www.intel.com/content/www/us/en/download/19344/"
            "intel-graphics-windows-dch-drivers.html"
        ),
        "chipset_product": (
            "https://www.intel.com/content/www/us/en/download/19347/"
            "chipset-inf-utility.html"
        ),
        "wifi_product": (
            "https://www.intel.com/content/www/us/en/download/19351/"
            "intel-wireless-wi-fi-drivers.html"
        ),
        "dsa_fallback": (
            "https://www.intel.com/content/www/us/en/download/785597/"
            "intel-driver-and-support-assistant.html"
        ),
    },
}

# https host suffixes allowed in endpoint overrides (manifest / repair / remote).
# Suffix match: host == suffix OR host.endswith("." + suffix).
ALLOWED_ENDPOINT_HOST_SUFFIXES: dict[str, tuple[str, ...]] = {
    "nvidia": ("nvidia.com", "geforce.com"),
    "amd": ("amd.com",),
    "intel": ("intel.com",),
}


@dataclass
class VendorHealthRow:
    vendor: str
    label: str
    ok: bool
    detail: str = ""
    method: str = ""
    failures: list[str] = field(default_factory=list)
    version_sample: str = ""


def manifest_path() -> Any:
    return app_set._ensure_dir() / "vendor_endpoints.json"


def load_manifest() -> dict:
    empty = {
        "manifest_version": MANIFEST_VERSION,
        "source": "bundled",
        "updated_at": "",
        "endpoints": {},
        "extractors": {},
        "candidates": {},
    }
    path = manifest_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if not isinstance(data.get("endpoints"), dict):
                    data["endpoints"] = {}
                if not isinstance(data.get("extractors"), dict):
                    data["extractors"] = {}
                if not isinstance(data.get("candidates"), dict):
                    data["candidates"] = {}
                # Sanitize at load so corrupt/hostile disk state cannot poison runtime.
                data["endpoints"] = sanitize_endpoints_map(data.get("endpoints") or {})
                data["extractors"] = sanitize_extractors_map(data.get("extractors") or {})
                data["candidates"] = sanitize_candidates_map(data.get("candidates") or {})
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return empty


def save_manifest(manifest: dict, *, source: str) -> None:
    manifest = dict(manifest)
    manifest["manifest_version"] = MANIFEST_VERSION
    manifest["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    manifest["source"] = source
    if not isinstance(manifest.get("endpoints"), dict):
        manifest["endpoints"] = {}
    if not isinstance(manifest.get("extractors"), dict):
        manifest["extractors"] = {}
    if not isinstance(manifest.get("candidates"), dict):
        manifest["candidates"] = {}
    manifest["endpoints"] = sanitize_endpoints_map(manifest.get("endpoints") or {})
    manifest["extractors"] = sanitize_extractors_map(manifest.get("extractors") or {})
    manifest["candidates"] = sanitize_candidates_map(manifest.get("candidates") or {})
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def endpoint_url_allowed(vendor: str, url: str) -> bool:
    """True when ``url`` is https and its host is on the vendor allowlist."""
    url = (url or "").strip()
    if not url.lower().startswith("https://"):
        return False
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if parsed.scheme.lower() != "https":
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or ":" in host:
        return False
    # Reject raw IPv4 hosts — vendor lookups are name-based.
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host):
        return False
    suffixes = ALLOWED_ENDPOINT_HOST_SUFFIXES.get((vendor or "").strip().lower()) or ()
    if not suffixes:
        return False
    return any(host == s or host.endswith("." + s) for s in suffixes)


def sanitize_endpoints_map(endpoints: dict) -> dict[str, dict[str, str]]:
    """Drop non-https / non-allowlisted endpoint overrides."""
    if not isinstance(endpoints, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for vendor, patch in endpoints.items():
        if not isinstance(patch, dict):
            continue
        vk = (vendor or "").strip().lower()
        if not vk:
            continue
        cleaned: dict[str, str] = {}
        for key, val in patch.items():
            url = str(val or "").strip()
            if not url or not endpoint_url_allowed(vk, url):
                continue
            kk = str(key or "").strip()
            if kk:
                cleaned[kk] = url
        if cleaned:
            out[vk] = cleaned
    return out


def sanitize_extractors_map(extractors: dict) -> dict[str, dict[str, dict]]:
    """Drop invalid extractor overrides (schema / ReDoS caps); fail-open per hint."""
    import vendor_extractors as vex

    if not isinstance(extractors, dict):
        return {}
    out: dict[str, dict[str, dict]] = {}
    for vendor, hints in extractors.items():
        if not isinstance(hints, dict):
            continue
        vk = (vendor or "").strip().lower()
        if not vk:
            continue
        slot: dict[str, dict] = {}
        for hint, extractor in hints.items():
            cleaned = vex.sanitize_extractor(extractor)
            if cleaned is None:
                continue
            hk = (hint or "*").strip().lower() or "*"
            slot[hk] = cleaned
        if slot:
            out[vk] = slot
    return out


def sanitize_candidates_map(
    candidates: dict,
) -> dict[str, dict[str, list[str]]]:
    """Allowlisted https alternate URLs: ``{vendor: {endpoint_key: [url,…]}}``."""
    if not isinstance(candidates, dict):
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    for vendor, keys in candidates.items():
        if not isinstance(keys, dict):
            continue
        vk = (vendor or "").strip().lower()
        if not vk:
            continue
        slot: dict[str, list[str]] = {}
        for key, urls in keys.items():
            if isinstance(urls, str):
                urls = [urls]
            if not isinstance(urls, list):
                continue
            kk = str(key or "").strip()
            if not kk:
                continue
            cleaned: list[str] = []
            seen: set[str] = set()
            for raw in urls[:32]:
                url = str(raw or "").strip()
                if not url or url in seen:
                    continue
                if not endpoint_url_allowed(vk, url):
                    continue
                seen.add(url)
                cleaned.append(url)
            if cleaned:
                slot[kk] = cleaned
        if slot:
            out[vk] = slot
    return out


def get_app_version() -> str:
    """Canonical app version string."""
    try:
        from product_version import product_version

        return str(product_version() or "").strip()
    except ImportError:
        return "0"


def version_tuple(version: str) -> tuple[int, ...]:
    """Parse ``major.minor.patch…`` into ints (non-numeric segments → 0)."""
    parts: list[int] = []
    for seg in re.split(r"[^\d]+", (version or "").strip()):
        if not seg:
            continue
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(0)
        if len(parts) >= 6:
            break
    return tuple(parts) if parts else (0,)


def app_meets_min_version(min_required: str, *, app_version: str | None = None) -> bool:
    """True when the running app is >= ``min_required`` (missing min → True)."""
    need = (min_required or "").strip()
    if not need:
        return True
    have = (app_version if app_version is not None else get_app_version()).strip()
    return version_tuple(have) >= version_tuple(need)


def _manifest_hmac_key_bytes() -> bytes:
    raw = BUNDLED_MANIFEST_HMAC_KEY
    if isinstance(raw, bytes):
        return raw
    return str(raw or "").encode("utf-8")


def canonical_manifest_payload(data: dict) -> bytes:
    """Stable UTF-8 bytes of the manifest with ``signature`` removed (for HMAC)."""
    payload = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign_manifest(data: dict, *, key: bytes | str | None = None) -> str:
    """Return hex HMAC-SHA256 for ``data`` (excluding any existing signature)."""
    import hashlib
    import hmac as hmac_mod

    if key is None:
        key_b = _manifest_hmac_key_bytes()
    elif isinstance(key, bytes):
        key_b = key
    else:
        key_b = str(key).encode("utf-8")
    if not key_b:
        raise ValueError("HMAC key is empty — set BUNDLED_MANIFEST_HMAC_KEY or pass key=")
    digest = hmac_mod.new(key_b, canonical_manifest_payload(data), hashlib.sha256).hexdigest()
    return digest


def verify_manifest_signature(data: dict, *, key: bytes | str | None = None) -> tuple[bool, str]:
    """Verify ``data['signature']`` when a key is configured.

    Returns ``(True, \"\")`` when:
      * no key is configured (signatures optional), or
      * signature matches.
    Fail-closed when a key is set but signature is missing/wrong.
    """
    import hashlib
    import hmac as hmac_mod

    if key is None:
        key_b = _manifest_hmac_key_bytes()
    elif isinstance(key, bytes):
        key_b = key
    else:
        key_b = str(key).encode("utf-8")
    if not key_b:
        return True, ""  # signing not enabled in this build
    sig = str(data.get("signature") or "").strip().lower()
    if sig.startswith("sha256="):
        sig = sig[7:].strip()
    if not sig or not re.fullmatch(r"[0-9a-f]{64}", sig):
        return False, "Remote lookup catalog is missing a valid signature."
    expected = hmac_mod.new(
        key_b, canonical_manifest_payload(data), hashlib.sha256
    ).hexdigest()
    if not hmac_mod.compare_digest(sig, expected):
        return False, "Remote lookup catalog signature mismatch."
    return True, ""


def validate_remote_manifest(
    data: dict,
    *,
    app_version: str | None = None,
) -> tuple[dict | None, str]:
    """Schema + min_app_version + HMAC + sanitize. Fail-open caller should ignore on error."""
    if not isinstance(data, dict):
        return None, "Downloaded file is not a valid vendor endpoint manifest."
    try:
        mv = int(data.get("manifest_version") or 0)
    except (TypeError, ValueError):
        return None, "Downloaded file is not a valid vendor endpoint manifest."
    if mv > MANIFEST_VERSION:
        return None, "Manifest requires a newer BSOD Analyzer version."
    if mv < 1:
        return None, "Downloaded file is not a valid vendor endpoint manifest."

    min_ver = str(data.get("min_app_version") or "").strip()
    if min_ver and not app_meets_min_version(min_ver, app_version=app_version):
        have = (app_version if app_version is not None else get_app_version()).strip()
        return (
            None,
            f"Lookup catalog requires BSOD Analyzer {min_ver} or newer "
            f"(this build is {have or 'unknown'}).",
        )

    ok_sig, sig_err = verify_manifest_signature(data)
    if not ok_sig:
        return None, sig_err

    endpoints = data.get("endpoints") if isinstance(data.get("endpoints"), dict) else {}
    extractors = data.get("extractors") if isinstance(data.get("extractors"), dict) else {}
    candidates = data.get("candidates") if isinstance(data.get("candidates"), dict) else {}
    # candidates-only catalogs are valid (audit alternates without changing endpoints).
    if not endpoints and not extractors and not candidates:
        return None, "Downloaded file is not a valid vendor endpoint manifest."

    cleaned: dict[str, Any] = {
        "manifest_version": mv,
        "endpoints": sanitize_endpoints_map(endpoints),
        "extractors": sanitize_extractors_map(extractors),
        "candidates": sanitize_candidates_map(candidates),
    }
    if min_ver:
        cleaned["min_app_version"] = min_ver
    # Do not copy signature onto the cleaned view — sanitize may drop URLs, which
    # would invalidate HMAC if merge re-verified. Fetch verifies; merge trusts
    # a fetch-validated dict via trust_validated=True.
    if (
        not cleaned["endpoints"]
        and not cleaned["extractors"]
        and not cleaned["candidates"]
    ):
        return None, "Remote lookup catalog had no usable allowlisted entries."
    return cleaned, ""


def get_endpoint(vendor: str, key: str, default: str = "") -> str:
    """User-approved override (allowlisted https), else bundled default."""
    manifest = load_manifest()
    overrides = (manifest.get("endpoints") or {}).get(vendor.lower()) or {}
    val = (overrides.get(key) or "").strip()
    if val and endpoint_url_allowed(vendor, val):
        return val
    bundled = (BUNDLED_ENDPOINTS.get(vendor.lower()) or {}).get(key) or ""
    return bundled or default


def _extractor_override_shape_ok(ext: dict) -> bool:
    """Deprecated shape gate — prefer ``vendor_extractors.sanitize_extractor``."""
    import vendor_extractors as vex

    return vex.sanitize_extractor(ext) is not None


def get_extractor_override(vendor: str, hint: str = "*") -> dict | None:
    """Sanitized extractor override from ``vendor_endpoints.json``, or ``None``."""
    import vendor_extractors as vex

    manifest = load_manifest()
    by_vendor = (manifest.get("extractors") or {}).get((vendor or "").lower()) or {}
    if not isinstance(by_vendor, dict):
        return None
    h = (hint or "*").strip().lower() or "*"
    for key in (h, "*"):
        cand = by_vendor.get(key)
        cleaned = vex.sanitize_extractor(cand) if isinstance(cand, dict) else None
        if cleaned is not None:
            return cleaned
    return None


def get_extractor(vendor: str, hint: str = "*") -> dict | None:
    """Merged extractor for ``vendor``/``hint``.

    Manifest overrides are PREPENDED onto bundled defaults (additive) so a bad
    override cannot wipe known-good extraction. Returns ``None`` only when
    neither bundled nor override rules exist for the vendor.
    """
    import vendor_extractors as vex

    bundled = vex.get_bundled_extractor(vendor, hint)
    override = get_extractor_override(vendor, hint)
    if not bundled and not override:
        return None
    return vex.merge_extractor_rules(bundled, override)


def apply_extractor_overrides(
    extractors: dict[str, dict[str, dict]],
    *,
    source: str = "user_repair",
) -> tuple[bool, str]:
    """Save extractor-rule overrides into ``vendor_endpoints.json`` (config only).

    Shape: ``{vendor: {hint: extractor_dict}}``. Each extractor is sanitized
    before save. Does not modify the program .exe.
    """
    import vendor_extractors as vex

    if not extractors or not isinstance(extractors, dict):
        return False, "No extractor overrides to save."
    manifest = load_manifest()
    current = dict(manifest.get("extractors") or {})
    saved: list[str] = []
    for vendor, hints in extractors.items():
        if not isinstance(hints, dict):
            continue
        vk = (vendor or "").strip().lower()
        if not vk:
            continue
        slot = dict(current.get(vk) or {})
        for hint, extractor in hints.items():
            cleaned = vex.sanitize_extractor(extractor)
            if cleaned is None:
                continue
            hk = (hint or "*").strip().lower() or "*"
            slot[hk] = cleaned
            saved.append(f"{vk}/{hk}")
        if slot:
            current[vk] = slot
    if not saved:
        return False, "No valid extractor overrides to save."
    manifest["extractors"] = current
    save_manifest(manifest, source=source)
    clear_vendor_scrape_cache_after_repair()
    return (
        True,
        f"Saved extractor rules for: {', '.join(sorted(saved))}. "
        "Program files were not modified.",
    )


def clear_vendor_scrape_cache_after_repair() -> None:
    try:
        import driver_catalog as dc

        dc.clear_vendor_scrape_cache()
    except ImportError:
        pass


def _http_probe(url: str, *, accept: str = "*/*") -> tuple[bool, str, int]:
    try:
        import driver_catalog as dc

        ok, body = dc._http_get(url, headers={"Accept": accept})
        return ok, body if ok else str(body), len(body) if ok else 0
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), 0


def _probe_nvidia() -> VendorHealthRow:
    import driver_catalog as dc

    ctx = {"pnp_class": "display", "device_label": "NVIDIA GeForce"}
    hit, method = dc._nvidia_lookup_download_info(ctx)
    try:
        import vendor_fetch as vf

        diag = vf.last_fetch_diag("nvidia")
        failures = list(diag.failures) if diag else []
    except ImportError:
        failures = []
    ver = (hit or {}).get("Version") or ""
    return VendorHealthRow(
        vendor="nvidia",
        label="NVIDIA",
        ok=bool(ver),
        detail="Game Ready lookup" if ver else "No version returned",
        method=method or "",
        failures=failures,
        version_sample=ver,
    )


def _probe_amd() -> VendorHealthRow:
    import driver_catalog as dc

    ver, _ = dc._scrape_amd_driver_version(
        {"hw_category": "graphics", "device_label": "AMD Radeon"}
    )
    try:
        import vendor_fetch as vf

        diag = vf.last_fetch_diag("amd")
        failures = list(diag.failures) if diag else []
    except ImportError:
        failures = []
    return VendorHealthRow(
        vendor="amd",
        label="AMD",
        ok=bool(ver),
        detail=f"Download center scrape" if ver else "Could not read a version",
        method="amd_download_center" if ver else "",
        failures=failures,
        version_sample=ver,
    )


def _probe_intel() -> VendorHealthRow:
    import driver_catalog as dc

    ver, _, _ = dc._scrape_intel_driver_version("graphics")
    try:
        import vendor_fetch as vf

        diag = vf.last_fetch_diag("intel")
        failures = list(diag.failures) if diag else []
    except ImportError:
        failures = []
    return VendorHealthRow(
        vendor="intel",
        label="Intel",
        ok=bool(ver),
        detail="Graphics lookup chain" if ver else "Could not read a version",
        method="intel_scrape" if ver else "",
        failures=failures,
        version_sample=ver,
    )


def _oem_firmware_catalog_probes(ctx: dict) -> list[tuple[str, str, Callable]]:
    """Live OEM BIOS/firmware catalog probes for this PC's manufacturer."""
    import driver_catalog as dc

    mfr = (ctx.get("system_manufacturer") or "").lower()
    bb_mfr = (ctx.get("baseboard_manufacturer") or "").lower()
    probes: list[tuple[str, str, Callable]] = []

    if "dell" in mfr or "alienware" in mfr:
        probes.append(
            ("oem_dell", "OEM BIOS catalog (Dell)", dc._fetch_dell_oem_rows_live)
        )
    if any(x in mfr for x in ("lenovo", "thinkpad", "ideapad")):
        probes.append(
            ("oem_lenovo", "OEM BIOS catalog (Lenovo)", dc._fetch_lenovo_oem_rows_live)
        )
    if "hp" in mfr or "hewlett" in mfr:
        probes.append(("oem_hp", "OEM BIOS catalog (HP)", dc._fetch_hp_oem_rows_live))
    if dc._manufacturer_matches(mfr, "asus", "rog") or dc._manufacturer_matches(
        bb_mfr, "asus"
    ):
        probes.append(
            ("oem_asus", "OEM BIOS catalog (ASUS)", dc._fetch_asus_oem_rows_live)
        )
    if dc._manufacturer_matches(mfr, "msi", "micro-star") or dc._manufacturer_matches(
        bb_mfr, "msi"
    ):
        probes.append(
            (
                "oem_msi",
                "OEM BIOS catalog (MSI)",
                lambda c: dc._fetch_msi_oem_rows_live(c, catalog_type="bios"),
            )
        )
    if dc._manufacturer_matches(mfr, "gigabyte") or dc._manufacturer_matches(
        bb_mfr, "gigabyte"
    ):
        probes.append(
            ("oem_gigabyte", "OEM BIOS catalog (Gigabyte)", dc.get_gigabyte_bios_rows)
        )
    if dc._manufacturer_matches(mfr, "acer"):
        probes.append(("oem_acer", "OEM BIOS catalog (Acer)", dc.get_acer_bios_rows))
    return probes


def _probe_oem_firmware_catalog(
    vendor_key: str,
    label: str,
    fetch_fn: Callable,
    ctx: dict,
) -> VendorHealthRow:
    try:
        rows, fallback = fetch_fn(ctx)
        ok = bool(rows)
        detail = f"{len(rows)} package(s)" if ok else "Empty or unreachable catalog"
        if not ok and fallback:
            detail = f"No packages parsed — {fallback[:120]}"
        return VendorHealthRow(
            vendor=vendor_key,
            label=label,
            ok=ok,
            detail=detail,
            method="oem_catalog",
        )
    except Exception as exc:
        return VendorHealthRow(
            vendor=vendor_key,
            label=label,
            ok=False,
            detail=str(exc)[:240],
            method="oem_catalog",
        )


def run_oem_firmware_health_probes(ctx: dict | None) -> list[VendorHealthRow]:
    ctx = ctx or {}
    return [
        _probe_oem_firmware_catalog(key, label, fn, ctx)
        for key, label, fn in _oem_firmware_catalog_probes(ctx)
    ]


def run_health_check(system_ctx: dict | None = None) -> list[VendorHealthRow]:
    ctx = system_ctx or {}
    rows: list[VendorHealthRow] = []
    try:
        from bsod_hardware_wmi import (
            amd_driver_lookup_applicable,
            intel_driver_lookup_applicable,
            nvidia_driver_lookup_applicable,
        )
    except ImportError:
        nvidia_driver_lookup_applicable = lambda _c: True  # noqa: E731
        amd_driver_lookup_applicable = lambda _c: True  # noqa: E731
        intel_driver_lookup_applicable = lambda _c: True  # noqa: E731

    if nvidia_driver_lookup_applicable(ctx):
        rows.append(_probe_nvidia())
    if amd_driver_lookup_applicable(ctx):
        rows.append(_probe_amd())
    if intel_driver_lookup_applicable(ctx):
        rows.append(_probe_intel())
    rows.extend(run_oem_firmware_health_probes(ctx))
    return rows


def broken_vendors(rows: list[VendorHealthRow] | None = None) -> list[VendorHealthRow]:
    rows = rows if rows is not None else run_health_check()
    return [r for r in rows if not r.ok]


def session_vendor_failures(
    system_ctx: dict | None = None,
    *,
    driver_rows: list[dict] | None = None,
    firmware_offers: list[dict] | None = None,
) -> list[str]:
    """Vendors with a broken lookup this session (hardware-gated).

    Includes:
      * all fetch steps failed (could not reach / no usable response), and
      * parser rot: page loaded (or device was version-applicable) but no version
        was extracted — recorded via ``vendor_fetch.record_empty_extraction`` or
        ``coverage_check_failed`` offers in ``driver_rows`` / ``firmware_offers``, and
      * OEM BIOS catalog probes that returned no packages for this PC.
    """
    failed: list[str] = []
    try:
        import vendor_fetch as vf
        from bsod_hardware_wmi import (
            amd_driver_lookup_applicable,
            intel_driver_lookup_applicable,
            nvidia_driver_lookup_applicable,
        )
    except ImportError:
        return failed
    ctx = system_ctx or {}
    checks = (
        ("nvidia", nvidia_driver_lookup_applicable(ctx)),
        ("amd", amd_driver_lookup_applicable(ctx)),
        ("intel", intel_driver_lookup_applicable(ctx)),
    )

    def _cache_has_version(vendor: str) -> bool:
        try:
            import driver_catalog as dc

            prefix = f"{vendor}:"
            for key, val in (getattr(dc, "_VENDOR_SCRAPE_CACHE", {}) or {}).items():
                if not str(key).startswith(prefix):
                    continue
                if isinstance(val, tuple) and val and val[0]:
                    return True
                if isinstance(val, dict) and (val.get("version") or ""):
                    return True
        except ImportError:
            pass
        return False

    for vendor, applicable in checks:
        if not applicable:
            continue
        if _cache_has_version(vendor):
            continue
        diag = vf.last_fetch_diag(vendor)
        if diag and diag.value is not None:
            continue  # at least one step returned a version this session
        empties = vf.empty_extraction_details(vendor).get(vendor) or []
        if empties:
            failed.append(vendor)
            continue
        if diag and diag.value is None and diag.failures:
            failed.append(vendor)

    # Honest-degradation rows from this scan (coverage_check_failed) → same prompt.
    for row in driver_rows or []:
        for offer in row.get("offers") or []:
            if not offer.get("coverage_check_failed"):
                continue
            vk = _vendor_key_from_coverage_offer(offer)
            if not vk or vk in failed:
                continue
            # Only surface vendors that apply to this PC.
            applicable = next((a for v, a in checks if v == vk), False)
            if applicable and not _cache_has_version(vk):
                failed.append(vk)

    for offer in firmware_offers or []:
        if not offer.get("coverage_check_failed"):
            continue
        src = (offer.get("source") or "").lower()
        if src == "ssd_vendor":
            tag = f"ssd:{(offer.get('source_label') or 'vendor').lower()}"
            if tag not in failed:
                failed.append(tag)

    if firmware_offers is not None:
        for row in run_oem_firmware_health_probes(ctx):
            if row.ok or row.vendor in failed:
                continue
            failed.append(row.vendor)
    return failed


def _vendor_key_from_coverage_offer(offer: dict) -> str:
    """Map a coverage-gap offer back to nvidia/amd/intel for health prompts."""
    label = (
        f"{offer.get('source_label') or ''} {offer.get('title') or ''}"
    ).lower()
    if "nvidia" in label:
        return "nvidia"
    if "amd" in label:
        return "amd"
    if "intel" in label or "killer" in label:
        return "intel"
    return ""


def discover_working_endpoints(
    progress: Callable[[str], None] | None = None,
) -> dict[str, dict[str, str]]:
    """Probe live sites and return endpoint overrides that respond (no exe changes)."""
    found: dict[str, dict[str, str]] = {}

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    prog("Checking NVIDIA…")
    nvidia = _probe_nvidia()
    if nvidia.ok:
        found["nvidia"] = dict(BUNDLED_ENDPOINTS.get("nvidia") or {})

    prog("Checking AMD download center…")
    amd_url = get_endpoint("amd", "download_page", BUNDLED_ENDPOINTS["amd"]["download_page"])
    ok, _body, size = _http_probe(amd_url)
    if ok and size > 10_000:
        found["amd"] = {"download_page": amd_url}

    if "amd" not in found:
        alt = "https://www.amd.com/en/support/download/drivers.html"
        ok, _body, size = _http_probe(alt)
        if ok and size > 10_000:
            found["amd"] = {"download_page": alt}

    prog("Checking Intel pages…")
    intel = _probe_intel()
    if intel.ok:
        found["intel"] = dict(BUNDLED_ENDPOINTS.get("intel") or {})

    return found


def run_user_repair(
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """
    One user consent covers everything: optional bundled manifest fetch, live
    endpoint probes, and version-extractor discovery when pages load but rules
    miss. Saves vendor_endpoints.json only — never modifies the program .exe.
    """
    merged: dict[str, dict[str, str]] = {}
    notes: list[str] = []
    extractor_msg = ""
    extractor_saved = False

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    prog("Refreshing OEM catalog cache…")
    try:
        import driver_catalog as dc

        dc.clear_oem_cache()
        notes.append(
            "Cleared OEM BIOS/driver catalog cache — next search will re-fetch packages."
        )
    except ImportError:
        pass

    url = (BUNDLED_LOOKUP_MANIFEST_URL or "").strip()
    if url:
        prog("Downloading latest lookup catalog…")
        data, err = fetch_remote_manifest(url)
        if data:
            try:
                import vendor_extractor_repair as ver

                if data.get("extractors"):
                    ver.backup_current_extractors()
            except ImportError:
                pass
            ok_remote, msg_remote = merge_remote_manifest(
                data, source="remote_manifest", trust_validated=True
            )
            if ok_remote:
                notes.append(msg_remote)
                if data.get("extractors"):
                    extractor_saved = True
            else:
                notes.append(f"Lookup catalog not applied ({msg_remote}).")
        elif err:
            notes.append(f"Lookup catalog download skipped ({err}).")

    discovered = discover_working_endpoints(progress=prog)
    for vendor, patch in discovered.items():
        merged[vendor] = {**(merged.get(vendor) or {}), **patch}

    try:
        import vendor_endpoint_audit as vea

        prog("Auditing lookup pages for better addresses…")
        audit_rows = vea.run_lookup_address_audit(progress=prog)
        audit_patches = vea.recommended_patches(audit_rows)
        for vendor, patch in audit_patches.items():
            merged[vendor] = {**(merged.get(vendor) or {}), **patch}
        if audit_patches:
            notes.append(
                "Applied lookup page updates from audit: "
                + ", ".join(sorted(audit_patches))
            )
    except ImportError:
        pass

    # Parser-rot repair: discover working extractor rules on live pages.
    try:
        import vendor_extractor_repair as ver

        prog("Checking version extractors…")
        need = ver.vendors_needing_extractor_repair()
        # Always probe AMD/Intel during repair — covers silent rot.
        targets = sorted(set(need) | {"amd", "intel"})
        ex_found = ver.discover_extractor_overrides(targets, progress=prog)
        if ex_found:
            ok_ex, extractor_msg = ver.apply_discovered_extractors(
                ex_found, source="user_repair"
            )
            if ok_ex:
                extractor_saved = True
                notes.append("Updated version-reading rules for changed manufacturer pages.")
            else:
                extractor_msg = ""
                notes.append("Extractor discovery found candidates but could not save them.")
        else:
            prog("Version extractors: no new rules needed (or pages unreachable).")
    except ImportError:
        pass

    if not merged and not extractor_saved:
        detail = (
            "Could not find working manufacturer lookup endpoints or version extractors.\n\n"
            "Check your internet connection and try again later, or install a newer "
            "BSOD Analyzer build when one is available."
        )
        failed_vendors: list[str] = []
        for row in run_health_check():
            if row.ok:
                continue
            fail_txt = "; ".join(row.failures[:3]) if row.failures else (row.detail or "")
            failed_vendors.append(f"{row.label}: {fail_txt or 'no response'}")
        if failed_vendors:
            detail += "\n\nProbe details:\n" + "\n".join(f"• {line}" for line in failed_vendors)
        if notes:
            detail += "\n\n" + "\n".join(notes)
        return False, detail

    parts: list[str] = []
    if merged:
        ok, msg = apply_repair_manifest(merged)
        if ok:
            parts.append(msg)
        else:
            notes.append(msg)
    if extractor_msg:
        parts.append(extractor_msg)
    if notes:
        parts.extend(notes)
    if not parts:
        return False, "Repair completed with no changes saved."
    return True, "\n\n".join(parts)


def apply_repair_manifest(
    discovered: dict[str, dict[str, str]],
    *,
    source: str = "user_repair",
) -> tuple[bool, str]:
    if not discovered:
        return False, "No working manufacturer lookup endpoints were found."
    cleaned = sanitize_endpoints_map(discovered)
    if not cleaned:
        return False, "No allowlisted https manufacturer lookup endpoints to save."
    manifest = load_manifest()
    endpoints = dict(manifest.get("endpoints") or {})
    for vendor, patch in cleaned.items():
        endpoints[vendor] = {**(endpoints.get(vendor) or {}), **patch}
    manifest["endpoints"] = endpoints
    save_manifest(manifest, source=source)
    clear_vendor_scrape_cache_after_repair()
    names = ", ".join(sorted(cleaned))
    return True, f"Saved lookup settings for: {names}. Program files were not modified."


def fetch_remote_manifest(url: str) -> tuple[dict | None, str]:
    """Download and validate the bundled lookup catalog URL (https only).

    Trust anchor is ``BUNDLED_LOOKUP_MANIFEST_URL`` (build-time) — end users never
    paste URLs. Validation: manifest_version, min_app_version, optional HMAC,
    then allowlist/sanitize. Any failure → ``(None, reason)`` (fail-open caller).
    """
    url = (url or "").strip()
    if not url:
        return None, "No lookup update URL is configured."
    if not url.startswith("https://"):
        return None, "Only https:// URLs are allowed for lookup updates."
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "BSODAnalyzer/vendor-manifest",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(MAX_REMOTE_MANIFEST_BYTES + 1)
        if len(raw) > MAX_REMOTE_MANIFEST_BYTES:
            return None, "Remote lookup catalog is too large."
        body = raw.decode("utf-8", errors="replace")
        data = json.loads(body)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, f"Could not download manifest: {exc}"
    return validate_remote_manifest(data)


def merge_remote_manifest(
    data: dict,
    *,
    source: str = "remote_manifest",
    trust_validated: bool = False,
) -> tuple[bool, str]:
    """Merge a remote catalog into local ``vendor_endpoints.json``.

    Pass ``trust_validated=True`` for the already-sanitized dict returned by
    ``fetch_remote_manifest`` / ``validate_remote_manifest`` (avoids re-checking
    HMAC after allowlist stripping). Other callers get a full validation pass.
    """
    if trust_validated and isinstance(data, dict):
        cleaned = {
            "manifest_version": int(data.get("manifest_version") or MANIFEST_VERSION),
            "endpoints": sanitize_endpoints_map(data.get("endpoints") or {}),
            "extractors": sanitize_extractors_map(data.get("extractors") or {}),
            "candidates": sanitize_candidates_map(data.get("candidates") or {}),
        }
        if data.get("min_app_version"):
            cleaned["min_app_version"] = str(data["min_app_version"])
        if (
            not cleaned["endpoints"]
            and not cleaned["extractors"]
            and not cleaned["candidates"]
        ):
            return (
                False,
                "Remote manifest contained no usable endpoints, extractors, or candidates.",
            )
    else:
        cleaned, err = validate_remote_manifest(data)
        if cleaned is None:
            return False, err or "Remote manifest failed validation."
    endpoints = cleaned.get("endpoints") or {}
    extractors = cleaned.get("extractors") or {}
    candidates = cleaned.get("candidates") or {}
    if not endpoints and not extractors and not candidates:
        return False, "Remote manifest contained no usable endpoints, extractors, or candidates."
    manifest = load_manifest()
    parts: list[str] = []
    if endpoints:
        merged_ep = dict(manifest.get("endpoints") or {})
        for vendor, patch in endpoints.items():
            merged_ep[vendor] = {**(merged_ep.get(vendor) or {}), **patch}
        manifest["endpoints"] = merged_ep
        parts.append("endpoints: " + ", ".join(sorted(endpoints)))
    if extractors:
        merged_ex = dict(manifest.get("extractors") or {})
        saved_hints: list[str] = []
        for vendor, hints in extractors.items():
            slot = dict(merged_ex.get(vendor) or {})
            for hint, extractor in hints.items():
                slot[hint] = dict(extractor)
                saved_hints.append(f"{vendor}/{hint}")
            if slot:
                merged_ex[vendor] = slot
        if saved_hints:
            manifest["extractors"] = merged_ex
            parts.append("extractors: " + ", ".join(sorted(saved_hints)))
    if candidates:
        merged_c = dict(manifest.get("candidates") or {})
        for vendor, keys in candidates.items():
            slot = dict(merged_c.get(vendor) or {})
            for key, urls in keys.items():
                prev = list(slot.get(key) or [])
                seen = set(prev)
                for u in urls:
                    if u not in seen:
                        prev.append(u)
                        seen.add(u)
                slot[key] = prev
            merged_c[vendor] = slot
        manifest["candidates"] = merged_c
        parts.append("candidates: " + ", ".join(sorted(candidates)))
    if not parts:
        return False, "Remote manifest contained no usable endpoints, extractors, or candidates."
    if cleaned.get("min_app_version"):
        manifest["min_app_version"] = cleaned["min_app_version"]
    save_manifest(manifest, source=source)
    clear_vendor_scrape_cache_after_repair()
    return True, "Applied remote lookup settings (" + "; ".join(parts) + ")."


def remote_manifest_enabled() -> bool:
    """True when this build has a developer lookup catalog URL configured."""
    return bool((BUNDLED_LOOKUP_MANIFEST_URL or "").strip())


def build_export_lookup_health(
    system_ctx: dict | None,
    scan_mode: dict | None = None,
    *,
    driver_rows: list[dict] | None = None,
    firmware_rows: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Snapshot of catalog sources, vendor API/scrape status, and configured lookup URLs
    for catalog scan exports (session diagnostics — no live HTTP during export).
    """
    ctx = system_ctx or {}
    scan = dict(scan_mode or {})
    manifest = load_manifest()

    offer_sources: set[str] = set()
    for row in list(driver_rows or []) + list(firmware_rows or []):
        for offer in row.get("offers") or []:
            label = (offer.get("source_label") or offer.get("source") or "").strip()
            if label:
                offer_sources.add(label)

    vendor_rows: list[dict[str, Any]] = []
    try:
        import vendor_fetch as vf
        from bsod_hardware_wmi import (
            amd_driver_lookup_applicable,
            intel_driver_lookup_applicable,
            nvidia_driver_lookup_applicable,
        )

        applicability = {
            "nvidia": nvidia_driver_lookup_applicable(ctx),
            "amd": amd_driver_lookup_applicable(ctx),
            "intel": intel_driver_lookup_applicable(ctx),
        }
    except ImportError:
        vf = None  # type: ignore[assignment]
        applicability = {"nvidia": False, "amd": False, "intel": False}

    labels = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel"}
    import_error = vf is None and not any(applicability.values())
    for vendor, applicable in applicability.items():
        diag = vf.last_fetch_diag(vendor) if vf else None
        if not applicable:
            session_status = "not_applicable"
        elif vf is None:
            session_status = "unknown"
        elif diag is None:
            session_status = "not_checked"
        elif diag.value is not None:
            session_status = "ok"
        else:
            session_status = "failed"
        endpoints: dict[str, str] = {}
        for key, default in (BUNDLED_ENDPOINTS.get(vendor) or {}).items():
            url = get_endpoint(vendor, key, default)
            if url:
                endpoints[key] = url
        vendor_rows.append(
            {
                "vendor": vendor,
                "label": labels.get(vendor, vendor),
                "applicable_to_this_pc": bool(applicable),
                "session_status": session_status,
                "working_method": (diag.method if diag else "") or "",
                "failed_steps": list(diag.failures) if diag and diag.failures else [],
                "configured_endpoints": endpoints,
            }
        )

    ex_map = manifest.get("extractors") or {}
    extractor_hints: list[str] = []
    if isinstance(ex_map, dict):
        for vk, hints in ex_map.items():
            if not isinstance(hints, dict):
                continue
            for hk in hints:
                extractor_hints.append(f"{vk}/{hk}")

    return {
        "catalog_scan": {
            "mode": scan.get("mode") or "",
            "active_sources": list(scan.get("active_list") or []),
            "skipped_sources": list(scan.get("skipped_list") or []),
            "detail": scan.get("detail") or "",
        },
        "offer_sources_in_export": sorted(offer_sources),
        "vendor_lookups": vendor_rows,
        "session_vendor_failures": session_vendor_failures(
            ctx, driver_rows=list(driver_rows or [])
        ),
        "endpoint_manifest": {
            "source": manifest.get("source") or "bundled",
            "updated_at": manifest.get("updated_at") or "",
            "extractor_overrides": sorted(extractor_hints),
        },
        "note": (
            "Vendor API/scrape status reflects the last driver catalog search in this "
            "session. Use Tools → Check manufacturer lookup health for a live probe."
            + (
                " Hardware applicability could not be determined for this export."
                if import_error
                else ""
            )
        ),
    }


def format_health_report(rows: list[VendorHealthRow]) -> str:
    lines = ["Manufacturer driver & firmware lookup health:", ""]
    for row in rows:
        status = "OK" if row.ok else "NEEDS ATTENTION"
        lines.append(f"• {row.label}: {status}")
        if row.version_sample:
            lines.append(f"    Sample version: {row.version_sample}")
        if row.detail:
            lines.append(f"    {row.detail}")
        if row.failures and not row.ok:
            lines.append(f"    Failed steps: {'; '.join(row.failures[:4])}")
        lines.append("")
    broken = broken_vendors(rows)
    if broken:
        lines.append(
            "Use Tools → Audit manufacturer lookup pages or Repair manufacturer lookups "
            "(one click — saves settings only, does not modify the program)."
        )
    else:
        lines.append("All checked manufacturer lookups responded.")
    return "\n".join(lines)
