"""Audit live vendor/OEM API endpoints used by driver_catalog."""
from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc
import vendor_fetch as vf

# Strings that must not appear in docs/backlog as if they were still in use.
_RETIRED_API_DOC_MARKERS = tuple(
    getattr(dc, "_NVIDIA_RETIRED_API_MARKERS", ())
    + (
        "amd_release_notes.html",
        "release-notes.html/graphics",
        "support/chipsets.html",
        "chipset hub page",
    )
)
_HARDCODED_URL_SCAN_FILES = (
    "driver_catalog.py",
    "firmware_catalog.py",
    "vendor_endpoint_health.py",
)
_URL_EXTRACT_RE = re.compile(r"https://[^\s\"'\\)>\]]+")
_RETIRED_URL_MARKERS = (
    "support/chipsets.html",
    "resources/support-articles/release-notes.html",
    "release-notes.html/graphics",
)


_SKIP_URL_SUBSTRINGS = (
    "{",
    "example.com",
    "localhost",
    "127.0.0.1",
    "downloads.dell.com",
    "download.gigabyte.com",
    "support.hp.com/wcc-services/swd-v2/osVersionData?cc=us&lc=en&productOid=12345",
)


def scan_docs_for_retired_api_names(root: Path | None = None) -> list[str]:
    """Flag backlog lines that reference retired vendor APIs."""
    base = root or Path(__file__).resolve().parents[1]
    problems: list[str] = []
    backlog = base / "docs" / "IMPROVEMENT_BACKLOG.md"
    if not backlog.is_file():
        return problems
    text = backlog.read_text(encoding="utf-8")
    for marker in _RETIRED_API_DOC_MARKERS:
        if marker in text:
            problems.append(
                f"docs/IMPROVEMENT_BACKLOG.md: mentions retired API {marker!r}"
            )
    return problems


def collect_hardcoded_vendor_urls(root: Path | None = None) -> list[str]:
    """Unique https URLs from catalog modules (for live reachability probes)."""
    import urllib.parse

    base = root or Path(__file__).resolve().parents[1]
    seen: set[str] = set()
    urls: list[str] = []
    for rel in _HARDCODED_URL_SCAN_FILES:
        path = base / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for raw in _URL_EXTRACT_RE.findall(text):
            url = raw.rstrip(".,;")
            if any(skip in url for skip in _SKIP_URL_SUBSTRINGS):
                continue
            try:
                parsed = urllib.parse.urlparse(url)
            except ValueError:
                continue
            if parsed.scheme != "https" or not parsed.netloc or "." not in parsed.netloc:
                continue
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return sorted(urls)


def scan_code_for_retired_urls(root: Path | None = None) -> list[str]:
    """Flag catalog source files that still reference retired vendor URLs."""
    base = root or Path(__file__).resolve().parents[1]
    problems: list[str] = []
    for rel in _HARDCODED_URL_SCAN_FILES:
        path = base / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in _RETIRED_URL_MARKERS:
            if marker in text:
                problems.append(f"{rel}: references retired URL {marker!r}")
    return problems


def probe_hardcoded_urls(
    urls: list[str],
    *,
    already_probed: set[str] | None = None,
) -> list[dict]:
    """GET probe for hardcoded vendor URLs not covered by named probes (WARN on miss)."""
    done = {u.lower() for u in (already_probed or set())}
    rows: list[dict] = []
    for url in urls:
        if url.lower() in done:
            continue
        done.add(url.lower())
        slug = re.sub(r"[^a-z0-9]+", "_", url.split("//", 1)[-1].lower())[:48]
        row = probe(f"hardcoded_{slug}", url)
        if any(marker in url for marker in _RETIRED_URL_MARKERS):
            row["status"] = "FAIL (retired URL still in code)"
        elif row["status"].startswith("FAIL"):
            row["status"] = row["status"].replace("FAIL", "WARN", 1)
        rows.append(row)
    return rows


def _status(ok: bool, body: str, *, json_ok: bool = False, min_len: int = 40) -> str:
    if not ok:
        return f"FAIL ({str(body)[:80]})"
    if json_ok and not body.lstrip().startswith(("{", "[")):
        return f"FAIL (not JSON, len={len(body)})"
    if len(body) < min_len:
        return f"WARN (short {len(body)}: {body[:60]!r})"
    return f"OK (len={len(body)})"


def probe(name: str, url: str, *, headers: dict | None = None, json_ok: bool = False) -> dict:
    try:
        ok, body = dc._http_get(url, headers=headers)
    except ValueError as exc:
        return {"name": name, "url": url, "status": f"FAIL ({exc})", "detail": ""}
    st = _status(ok, body, json_ok=json_ok)
    detail = ""
    if ok and json_ok:
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                detail = f" keys={list(data.keys())[:6]}"
        except json.JSONDecodeError:
            st = "FAIL (invalid JSON)"
    return {"name": name, "url": url, "status": st, "detail": detail}


def probe_realtek(cate_id: str) -> dict:
    url = f"https://www.realtek.com/Download/ListAllDownloadItem?cate_id={cate_id}"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=dc._http_browser_headers())
    try:
        with urllib.request.urlopen(req, timeout=dc._HTTP_TIMEOUT, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        items = (data.get("Data") or {}).get("DownloadItems") or {}
        n = sum(len(v) for v in items.values() if isinstance(v, list))
        st = "OK" if data.get("Pass") and n else f"WARN (Pass={data.get('Pass')} items={n})"
        return {"name": f"realtek_cate_{cate_id}", "url": url, "status": st, "detail": ""}
    except Exception as exc:
        return {"name": f"realtek_cate_{cate_id}", "url": url, "status": f"FAIL ({exc})", "detail": ""}


def probe_catalog_scrapes() -> list[dict]:
    rows: list[dict] = []
    ctx = {"hw_category": "graphics", "device_label": "AMD Radeon RX 7900"}
    ver, _ = dc._scrape_amd_driver_version(ctx)
    rows.append({
        "name": "amd_scrape_graphics",
        "url": dc._amd_drivers_download_url(),
        "status": "OK" if ver else "FAIL (no version parsed)",
        "detail": f" ver={ver}" if ver else "",
    })
    ig, dg, ug = dc._scrape_intel_driver_version("graphics")
    rows.append({
        "name": "intel_scrape_graphics",
        "url": "intel product + DSA fallback",
        "status": "OK" if ig else "FAIL (no version parsed)",
        "detail": f" ver={ig}" if ig else "",
    })
    iw, _, _ = dc._scrape_intel_driver_version("wifi")
    rows.append({
        "name": "intel_scrape_wifi",
        "url": "intel wifi product page",
        "status": "OK" if iw else "WARN (no version parsed)",
        "detail": f" ver={iw}" if iw else "",
    })
    ic, _, _ = dc._scrape_intel_driver_version("chipset")
    rows.append({
        "name": "intel_scrape_chipset",
        "url": dc._intel_product_url("chipset"),
        "status": "OK" if ic else "FAIL (no version parsed)",
        "detail": f" ver={ic}" if ic else "",
    })
    ctx_chipset = {"hw_category": "chipset", "device_label": "AMD Chipset"}
    ver_amd_chip, _ = dc._scrape_amd_driver_version(ctx_chipset)
    rows.append({
        "name": "amd_scrape_chipset",
        "url": dc._amd_drivers_download_url() + " (hub + chipset leaf pages)",
        "status": "OK" if ver_amd_chip else "WARN (no version parsed)",
        "detail": f" ver={ver_amd_chip}" if ver_amd_chip else "",
    })
    hit, method = dc._nvidia_lookup_download_info({
        "pnp_class": "display",
        "device_label": "NVIDIA GeForce",
    })
    rows.append({
        "name": "nvidia_lookup_chain",
        "url": method or "none",
        "status": "OK" if hit and hit.get("Version") else "FAIL",
        "detail": f" ver={hit.get('Version')}" if hit else "",
    })
    diag = vf.last_fetch_diag("nvidia")
    if diag and diag.failures:
        rows.append({
            "name": "nvidia_fallback_chain",
            "url": "(diagnostics)",
            "status": "INFO",
            "detail": "; ".join(diag.failures[:4]),
        })
    return rows


def main() -> int:
    results: list[dict] = []
    results.append(probe(
        "nvidia_ajax",
        "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/"
        "AjaxDriverService.php?func=DriverManualLookup&psid=120&pfid=942"
        "&osID=135&languageCode=1033&isWHQL=1&dch=1&sort1=0&numberOfResults=1",
        json_ok=True,
    ))
    results.append(probe(
        "nvidia_processfind",
        "https://www.nvidia.com/Download/processFind.aspx?"
        "psid=120&pfid=942&osid=135&lid=1&dtcid=1&lang=en-us",
    ))
    results.append({
        "name": "nvidia_xml_retired",
        "url": "(removed from code)",
        "status": "RETIRED (404 expected — not used)",
        "detail": "",
    })
    results.append(probe(
        "amd_download_center",
        dc._amd_drivers_download_url(),
    ))
    results.append({
        "name": "amd_chipsets_html_retired",
        "url": "https://www.amd.com/en/support/chipsets.html",
        "status": "RETIRED (404 — use download center)",
        "detail": "",
    })
    results.append({
        "name": "nvidia_getbydeviceid_retired",
        "url": "(removed from code — was never in v6 hot path)",
        "status": "RETIRED (do not reference in backlog)",
        "detail": "",
    })
    results.append({
        "name": "amd_release_notes_retired",
        "url": "(removed from code)",
        "status": "RETIRED (404 expected — not used)",
        "detail": "",
    })
    results.append(probe(
        "intel_graphics_page",
        "https://www.intel.com/content/www/us/en/download/19344/"
        "intel-graphics-windows-dch-drivers.html",
    ))
    results.append(probe_realtek("584"))
    results.append(probe(
        "msi_support_api",
        "https://www.msi.com/api/v1/product/support/panel?"
        "product=MPG-Z790-CARBON-WIFI&type=driver&page=1&per_page=5",
        headers={"Accept": "application/json"},
        json_ok=True,
    ))
    results.append(probe(
        "hp_os_version_api",
        "https://support.hp.com/wcc-services/swd-v2/osVersionData?cc=us&lc=en&productOid=12345",
        headers={"Accept": "application/json"},
        json_ok=True,
    ))
    results.append(probe(
        "ms_catalog_search",
        "https://www.catalog.update.microsoft.com/Search.aspx?q=nvidia+display",
    ))
    results.extend(probe_catalog_scrapes())

    probed_urls = {r["url"] for r in results if r.get("url", "").startswith("http")}
    hardcoded = collect_hardcoded_vendor_urls()
    results.extend(probe_hardcoded_urls(hardcoded, already_probed=probed_urls))

    doc_problems = scan_docs_for_retired_api_names()
    for msg in doc_problems:
        results.append({
            "name": "doc_retired_api",
            "url": msg,
            "status": "FAIL",
            "detail": "",
        })

    code_problems = scan_code_for_retired_urls()
    for msg in code_problems:
        results.append({
            "name": "code_retired_url",
            "url": msg,
            "status": "FAIL",
            "detail": "",
        })

    fails = 0
    for r in results:
        line = f"{r['name']:26} {r['status']}{r.get('detail', '')}"
        print(line)
        if r["status"].startswith("FAIL"):
            fails += 1
    print(f"\n{len(results) - fails}/{len(results)} checks passed (FAIL = broken; WARN/INFO = partial)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
