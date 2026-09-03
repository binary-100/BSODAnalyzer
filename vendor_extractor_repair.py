"""Discover and persist version-extractor rules when manufacturer pages change.

Used by ``vendor_endpoint_health.run_user_repair``: when a vendor page loads but
bundled extractors find no version (parser rot / T1), try a library of candidate
rules against the live HTML, keep the first that yields a version-shaped string,
back up the previous extractor overrides, and write the winner into
``vendor_endpoints.json`` (config only — never modifies the .exe).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import app_settings as app_set
import vendor_endpoint_health as veh
import vendor_extractors as vex

# ---------------------------------------------------------------------------
# Candidate rule library (tried in order when bundled extractors miss)
# ---------------------------------------------------------------------------
_GENERIC_SCALAR_CANDIDATES: list[dict] = [
    {
        "kind": "json_next_data",
        "pattern": r"(\d+\.\d+\.\d+\.\d+)",
        "pick": "max",
    },
    {
        "kind": "json_next_data",
        "pattern": (
            r'"(?:version|driverVersion|fileVersion|packageVersion|softwareVersion)"'
            r'\s*:\s*"(\d+\.\d+\.\d+(?:\.\d+)?)"'
        ),
        "flags": "i",
        "pick": "max",
    },
    {"kind": "json_ld", "path": "softwareVersion"},
    {
        "kind": "regex",
        "pattern": r'"softwareVersion"\s*:\s*"([\d.]+)"',
        "flags": "i",
        "pick": "max",
    },
    {
        "kind": "regex",
        "pattern": r'"driverVersion"\s*:\s*"([\d.]+)"',
        "flags": "i",
        "pick": "max",
    },
    {
        "kind": "regex",
        "pattern": r'"fileVersion"\s*:\s*"([\d.]+)"',
        "flags": "i",
        "pick": "max",
    },
    {
        "kind": "regex",
        "pattern": r'"packageVersion"\s*:\s*"([\d.]+)"',
        "flags": "i",
        "pick": "max",
    },
    {
        "kind": "regex",
        "pattern": r'"version"\s*:\s*"(\d+\.\d+\.\d+(?:\.\d+)?)"',
        "flags": "i",
        "pick": "max",
    },
    {
        "kind": "regex",
        "pattern": r"(\d{2}\.\d+\.\d+\.\d+)\s*\(Latest\)",
        "flags": "i",
    },
    {
        "kind": "regex",
        "pattern": r"Version\s*[:=]?\s*(\d+\.\d+\.\d+(?:\.\d+)?)",
        "flags": "i",
        "pick": "max",
    },
    {
        "kind": "regex",
        "pattern": r"\b(\d+\.\d+\.\d+\.\d+)\b",
        "pick": "max",
    },
]

_VENDOR_HINT_CANDIDATES: dict[str, dict[str, list[dict]]] = {
    "amd": {
        "graphics": [
            {
                "kind": "regex",
                "pattern": r"Adrenalin.*?(\d+\.\d+\.\d+(?:\.\d+)?)",
                "flags": "is",
                "pick": "max",
            },
            {
                "kind": "regex",
                "pattern": r"Radeon.*?Software.*?(\d+\.\d+\.\d+(?:\.\d+)?)",
                "flags": "is",
                "pick": "max",
            },
            {
                "kind": "regex",
                "pattern": r"driverPackageVersion.*?(\d+\.\d+\.\d+(?:\.\d+)?)",
                "flags": "is",
            },
        ],
        "chipset": [
            {
                "kind": "regex",
                "pattern": r"chipset[^\"]{0,160}(\d+\.\d+\.\d+\.\d+)",
                "flags": "i",
                "pick": "max",
            },
            {
                "kind": "regex",
                "pattern": r"\b([67]\.\d+\.\d+\.\d+)\b",
                "pick": "max",
            },
        ],
    },
    "intel": {
        "graphics": [
            {
                "kind": "regex",
                "pattern": r"32\.0\.\d+\.\d+",
                "group": 0,
                "pick": "max",
            },
            {
                "kind": "regex",
                "pattern": r"31\.0\.\d+\.\d+",
                "group": 0,
                "pick": "max",
            },
        ],
        "wifi": [
            {
                "kind": "regex",
                "pattern": r"24\.\d+\.\d+\.\d+",
                "group": 0,
                "pick": "max",
            },
        ],
        "chipset": [
            {
                "kind": "regex",
                "pattern": r"10\.\d+\.\d+\.\d+",
                "group": 0,
                "pick": "max",
            },
        ],
    },
}


def candidate_rules_for(vendor: str, hint: str) -> list[dict]:
    """Ordered candidate rules: vendor/hint-specific first, then generic."""
    v = (vendor or "").lower()
    h = (hint or "*").lower()
    specific = list((_VENDOR_HINT_CANDIDATES.get(v) or {}).get(h) or [])
    # Dedup by (kind, pattern, path) while preserving order.
    seen: set[tuple] = set()
    out: list[dict] = []
    for rule in specific + list(_GENERIC_SCALAR_CANDIDATES):
        key = (
            rule.get("kind"),
            rule.get("pattern"),
            rule.get("path"),
            rule.get("group"),
            rule.get("pick"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(rule))
    return out


# ---------------------------------------------------------------------------
# Backup / rollback
# ---------------------------------------------------------------------------
def extractor_backup_path() -> Path:
    return app_set._ensure_dir() / "vendor_endpoints.extractors.bak.json"


def backup_current_extractors() -> Path:
    """Snapshot current extractor overrides before a repair write."""
    manifest = veh.load_manifest()
    payload = {
        "backed_up_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "extractors": dict(manifest.get("extractors") or {}),
    }
    path = extractor_backup_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def rollback_extractors() -> tuple[bool, str]:
    """Restore extractor overrides from the last repair backup."""
    path = extractor_backup_path()
    if not path.is_file():
        return False, "No extractor backup found."
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"Could not read extractor backup: {exc}"
    extractors = data.get("extractors")
    if not isinstance(extractors, dict):
        return False, "Extractor backup is missing a valid extractors map."
    manifest = veh.load_manifest()
    manifest["extractors"] = extractors
    veh.save_manifest(manifest, source="extractor_rollback")
    veh.clear_vendor_scrape_cache_after_repair()
    when = data.get("backed_up_at") or "unknown time"
    return True, f"Restored extractor rules from backup ({when}). Program files were not modified."


# ---------------------------------------------------------------------------
# Live HTML fetch for discovery
# ---------------------------------------------------------------------------
def _fetch_vendor_html(vendor: str, hint: str) -> tuple[bool, str, str]:
    """Return ``(ok, html, url)`` for the vendor/hint download page."""
    v = (vendor or "").lower()
    h = (hint or "graphics").lower()
    try:
        import driver_catalog as dc
    except ImportError:
        return False, "", ""

    if v == "amd":
        url = veh.get_endpoint(
            "amd",
            "download_page",
            (veh.BUNDLED_ENDPOINTS.get("amd") or {}).get("download_page", ""),
        )
        if not url:
            return False, "", ""
        ok, html = dc._vendor_http_get_robust(url)
        return ok, html if ok else "", url

    if v == "intel":
        key_map = {
            "graphics": "graphics_product",
            "chipset": "chipset_product",
            "wifi": "wifi_product",
        }
        ep_key = key_map.get(h, "graphics_product")
        default = (veh.BUNDLED_ENDPOINTS.get("intel") or {}).get(ep_key, "")
        url = veh.get_endpoint("intel", ep_key, default)
        if not url:
            return False, "", ""
        ok, html = dc._vendor_http_get_robust(
            url,
            referer="https://www.intel.com/content/www/us/en/download-center/home.html",
            insecure_fallback=True,
        )
        return ok, html if ok else "", url

    if v == "mediatek":
        url = "https://www.mediatek.com/products/broadband-wifi"
        ok, html = dc._vendor_http_get_robust(url, insecure_fallback=True)
        return ok, html if ok else "", url

    if v == "marvell":
        url = "https://www.marvell.com/support/downloads.html"
        ok, html = dc._vendor_http_get_robust(url, referer="https://www.marvell.com/")
        return ok, html if ok else "", url

    if v == "gigabyte":
        # No single stable product page without a model slug — skip live discovery.
        return False, "", ""

    return False, "", ""


def _strip_private_keys(extractor: dict) -> dict:
    return {k: v for k, v in extractor.items() if not str(k).startswith("_")}


def _try_rule_on_html(html: str, rule: dict, *, mode: str = "scalar") -> str:
    trial = {"mode": mode, "version": [dict(rule)]}
    if mode == "rows":
        rows = vex.extract_rows(html, trial)
        vers = [r.get("version") or "" for r in rows if r.get("version")]
        valid = [v for v in vers if vex.is_version_shaped(v)]
        if not valid:
            return ""
        return max(valid, key=lambda v: vex._parse_version(v) or ())
    return vex.extract_version(html, trial)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def vendors_needing_extractor_repair(
    system_ctx: dict | None = None,
) -> list[str]:
    """Vendors that showed empty-extraction / health failure this session."""
    need: set[str] = set()
    try:
        import vendor_fetch as vf

        for vendor, details in vf.empty_extraction_details().items():
            if details and vendor in vex.BUNDLED_EXTRACTORS:
                need.add(vendor)
    except ImportError:
        pass
    for row in veh.broken_vendors(veh.run_health_check(system_ctx)):
        if row.vendor in vex.BUNDLED_EXTRACTORS:
            need.add(row.vendor)
    # HTML scrapers only (NVIDIA is API-driven).
    return sorted(v for v in need if v != "nvidia")


def discover_extractor_overrides(
    vendors: list[str] | None = None,
    *,
    progress: Callable[[str], None] | None = None,
    force_all_hints: bool = False,
) -> dict[str, dict[str, dict]]:
    """Try candidate rules on live pages; return overrides that yield a version.

    Skips a vendor/hint when the *current* merged extractor already works.
    Does not write anything — caller backs up + applies.
    """

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    targets = [v.lower() for v in (vendors or list(vex.BUNDLED_EXTRACTORS.keys()))]
    targets = [v for v in targets if v in vex.BUNDLED_EXTRACTORS and v != "nvidia"]
    found: dict[str, dict[str, dict]] = {}

    for vendor in targets:
        hints = list((vex.BUNDLED_EXTRACTORS.get(vendor) or {}).keys())
        # Prefer concrete hints; include "*" only when it's the sole entry.
        concrete = [h for h in hints if h != "*"]
        to_try = concrete if concrete else hints
        if not force_all_hints and vendor in ("amd", "intel"):
            # During repair, probe the primary product class first.
            preferred = {
                "amd": ["graphics", "chipset"],
                "intel": ["graphics", "chipset", "wifi"],
            }.get(vendor, to_try)
            to_try = [h for h in preferred if h in (vex.BUNDLED_EXTRACTORS.get(vendor) or {})]

        for hint in to_try:
            bundled = vex.get_bundled_extractor(vendor, hint)
            mode = (bundled or {}).get("mode") or "scalar"
            prog(f"Checking {vendor} / {hint} version extractors…")
            ok, html, url = _fetch_vendor_html(vendor, hint)
            if not ok or not html:
                prog(f"  {vendor}/{hint}: could not fetch page")
                continue

            current = veh.get_extractor(vendor, hint)
            if current:
                if mode == "rows":
                    if vex.extract_rows(html, current):
                        prog(f"  {vendor}/{hint}: current extractor OK")
                        continue
                elif vex.extract_version(html, current):
                    prog(f"  {vendor}/{hint}: current extractor OK")
                    continue

            for rule in candidate_rules_for(vendor, hint):
                ver = _try_rule_on_html(html, rule, mode=mode)
                if not ver:
                    continue
                extractor = {
                    "mode": mode,
                    "version": [dict(rule)],
                    "_discovered_version_sample": ver,
                    "_discovered_from_url": url,
                }
                found.setdefault(vendor, {})[hint] = extractor
                prog(f"  {vendor}/{hint}: found working rule → {ver}")
                break
            else:
                prog(f"  {vendor}/{hint}: no candidate rule produced a version")

    return found


def apply_discovered_extractors(
    discovered: dict[str, dict[str, dict]],
    *,
    source: str = "user_repair",
    do_backup: bool = True,
) -> tuple[bool, str]:
    """Backup (optional) then persist discovered extractor overrides."""
    if not discovered:
        return False, "No extractor overrides to apply."
    cleaned: dict[str, dict[str, dict]] = {}
    samples: list[str] = []
    for vendor, hints in discovered.items():
        if not isinstance(hints, dict):
            continue
        slot: dict[str, dict] = {}
        for hint, ext in hints.items():
            if not isinstance(ext, dict):
                continue
            sample = (ext.get("_discovered_version_sample") or "").strip()
            if sample:
                samples.append(f"{vendor}/{hint}→{sample}")
            slot[hint] = _strip_private_keys(ext)
        if slot:
            cleaned[vendor] = slot
    if not cleaned:
        return False, "No valid extractor overrides to apply."
    if do_backup:
        backup_current_extractors()
    ok, msg = veh.apply_extractor_overrides(cleaned, source=source)
    if ok and samples:
        msg = f"{msg}\nSample versions read: {', '.join(samples)}."
        msg += "\nPrevious extractor rules were backed up (can be restored if needed)."
    return ok, msg
