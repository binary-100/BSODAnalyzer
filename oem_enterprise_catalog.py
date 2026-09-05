"""Enterprise OEM driver manifests (Dell / HP / Lenovo Phase A).

Official deployment catalogs supplement consumer OEM APIs. Manifests are
downloaded once per TTL, parsed locally, and merged into OEM row warmers.
No per-device network calls and no MSCatalog queries.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import app_settings as app_set

_DELL_CAB_URL = "https://downloads.dell.com/catalog/DriverPackCatalog.cab"
_HP_CAB_URL = "https://ftp.hp.com/pub/caps-softpaq/cmit/HPClientDriverPackCatalog.cab"
_LENOVO_XML_URL = "https://download.lenovo.com/cdrt/td/catalogv2.xml"

_DELL_XML_MEMBER = "DriverPackCatalog.xml"
_HP_XML_MEMBER = "HPClientDriverPackCatalog.xml"

_MANIFEST_TTL_DAYS = 7
_DELL_METADATA_MAX_BYTES = 2_000_000
_DELL_NS = "{openmanage/cm/dm}"

_SESSION: dict[str, list[dict]] = {}


def clear_session_cache() -> None:
    _SESSION.clear()


def merge_oem_row_lists(primary: list[dict], supplemental: list[dict]) -> list[dict]:
    """Append supplemental OEM rows; enrich ``inner_versions`` when title+version match."""
    if not supplemental:
        return list(primary)
    out = list(primary)
    index: dict[tuple[str, str], int] = {}
    for i, row in enumerate(out):
        index[_row_dedupe_key(row)] = i
    for row in supplemental:
        key = _row_dedupe_key(row)
        if key in index:
            i = index[key]
            if not out[i].get("inner_versions") and row.get("inner_versions"):
                merged = dict(out[i])
                merged["inner_versions"] = row["inner_versions"]
                out[i] = merged
            continue
        out.append(row)
        index[key] = len(out) - 1
    return out


def _row_dedupe_key(row: dict) -> tuple[str, str]:
    return (
        (row.get("title") or "").strip().lower(),
        (row.get("version") or "").strip(),
    )


def dell_enterprise_rows(system_ctx: dict | None) -> list[dict]:
    key = f"dell:{_machine_key(system_ctx)}"
    if key in _SESSION:
        return _SESSION[key]
    rows = _dell_enterprise_rows_impl(system_ctx)
    _SESSION[key] = rows
    return rows


def hp_enterprise_rows(system_ctx: dict | None) -> list[dict]:
    key = f"hp:{_machine_key(system_ctx)}"
    if key in _SESSION:
        return _SESSION[key]
    rows = _hp_enterprise_rows_impl(system_ctx)
    _SESSION[key] = rows
    return rows


def lenovo_enterprise_rows(system_ctx: dict | None) -> list[dict]:
    key = f"lenovo:{_machine_key(system_ctx)}"
    if key in _SESSION:
        return _SESSION[key]
    rows = _lenovo_enterprise_rows_impl(system_ctx)
    _SESSION[key] = rows
    return rows


def _machine_key(system_ctx: dict | None) -> str:
    ctx = system_ctx or {}
    parts = [
        (ctx.get("system_manufacturer") or "").strip().lower(),
        (ctx.get("system_model") or "").strip().lower(),
        (ctx.get("system_sku") or "").strip().upper(),
        (ctx.get("baseboard_product") or "").strip().upper(),
        (ctx.get("machine_type") or "").strip().upper(),
    ]
    return "|".join(parts)


def _manifest_cache_dir() -> Path:
    return app_set.enterprise_manifest_cache_dir()


def _manifest_fresh(path: Path) -> bool:
    if not path.is_file():
        return False
    age_days = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 86400.0
    return age_days < _MANIFEST_TTL_DAYS


def _http_get_bytes(url: str, *, timeout: int = 90) -> bytes | None:
    try:
        import driver_catalog as dc
    except ImportError:
        ua = "BSODAnalyzer/6.4"
    else:
        ua = dc.catalog_user_agent()
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _extract_cab_member(cab_bytes: bytes, member_name: str) -> bytes | None:
    if not cab_bytes:
        return None
    member_base = member_name.rsplit("/", 1)[-1].lower()
    with tempfile.TemporaryDirectory(prefix="bsod_cab_") as td:
        cab_path = Path(td) / "catalog.cab"
        cab_path.write_bytes(cab_bytes)
        try:
            subprocess.run(
                ["tar", "-xf", str(cab_path), "-C", td],
                check=False,
                capture_output=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        for path in Path(td).rglob("*"):
            if path.is_file() and path.name.lower() == member_base:
                try:
                    return path.read_bytes()
                except OSError:
                    return None
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["expand", str(cab_path), f"-F:{member_name}", td],
                    check=False,
                    capture_output=True,
                    timeout=120,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
            for path in Path(td).rglob("*"):
                if path.is_file() and path.name.lower() == member_base:
                    try:
                        return path.read_bytes()
                    except OSError:
                        return None
    return None


def _load_cached_xml(vendor: str, url: str, cab_member: str | None) -> bytes | None:
    cache_dir = _manifest_cache_dir()
    xml_cache = cache_dir / f"{vendor}.xml"
    if _manifest_fresh(xml_cache):
        try:
            return xml_cache.read_bytes()
        except OSError:
            pass
    raw = _http_get_bytes(url)
    if not raw:
        return None
    if cab_member:
        xml_bytes = _extract_cab_member(raw, cab_member)
    else:
        xml_bytes = raw
    if not xml_bytes:
        return None
    try:
        xml_cache.write_bytes(xml_bytes)
        meta = {
            "cached_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_url": url,
            "bytes": len(xml_bytes),
        }
        (cache_dir / f"{vendor}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except OSError:
        pass
    return xml_bytes


def _windows_os_tokens() -> tuple[bool, bool]:
    win11 = False
    if sys.platform == "win32":
        try:
            win11 = sys.getwindowsversion().build >= 22000  # type: ignore[attr-defined]
        except AttributeError:
            win11 = False
    return win11, not win11


def _model_match_score(system_model: str, candidate: str) -> int:
    sm = re.sub(r"[^a-z0-9]+", " ", (system_model or "").lower()).split()
    cm = re.sub(r"[^a-z0-9]+", " ", (candidate or "").lower()).split()
    if not sm or not cm:
        return 0
    sm_set = {t for t in sm if len(t) >= 2}
    cm_set = {t for t in cm if len(t) >= 2}
    if not sm_set or not cm_set:
        return 0
    overlap = sm_set.intersection(cm_set)
    if not overlap:
        if (system_model or "").lower() in (candidate or "").lower():
            return 5
        if (candidate or "").lower() in (system_model or "").lower():
            return 4
        return 0
    return min(20, 3 * len(overlap))


def _hp_system_ids(system_ctx: dict | None) -> set[str]:
    ctx = system_ctx or {}
    ids: set[str] = set()
    for raw in (
        ctx.get("baseboard_product"),
        ctx.get("system_sku"),
        ctx.get("machine_type"),
    ):
        text = str(raw or "").strip().lower()
        for tok in re.findall(r"[0-9a-f]{4}", text):
            ids.add(tok)
    return ids


def _lenovo_mtm(system_ctx: dict | None) -> str:
    ctx = system_ctx or {}
    mtm = (ctx.get("machine_type") or ctx.get("baseboard_product") or ctx.get("system_sku") or "")
    mtm = re.sub(r"[^A-Z0-9]", "", mtm.upper())
    if len(mtm) >= 10:
        return mtm[:10]
    if len(mtm) >= 7:
        return mtm[:7]
    return mtm


def _parse_dell_driver_archive_manifest(text: str | bytes) -> list[dict]:
    """Parse Dell driver-pack metadata XML (Release / DeviceDescription rows)."""
    blob = text
    if isinstance(text, bytes):
        for enc in ("utf-8", "utf-16"):
            try:
                blob = text.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            blob = text.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return []
    best: dict[tuple[str, str], dict] = {}
    for rel in root.findall(".//Release"):
        title = (rel.get("DeviceDescription") or "").strip()
        if not title:
            continue
        ver = (rel.get("VendorVersion") or rel.get("DellVersion") or "").strip()
        cat = (rel.get("Category") or "driver").strip()
        rid = (rel.get("ReleaseID") or "").split("_")[0].strip()
        url = ""
        if rid:
            url = (
                "https://www.dell.com/support/home/us/en/19/Drivers/"
                f"DriversDetails?driverId={rid}"
            )
        row = {"title": title, "version": ver, "date": "", "url": url, "category": cat}
        key = (title.lower(), cat.lower())
        prev = best.get(key)
        if not prev:
            best[key] = row
            continue
        try:
            import driver_catalog as dc
            if dc.compare_versions(prev.get("version") or "", ver) in ("older", "unknown"):
                best[key] = row
        except ImportError:
            best[key] = row
    return list(best.values())


def _parse_dell_software_manifest_text(text: str | bytes) -> list[dict]:
    try:
        import driver_catalog as dc
    except ImportError:
        return []
    if not hasattr(dc, "parse_dell_software_manifest_root"):
        return []
    blob = text
    if isinstance(text, bytes):
        for enc in ("utf-16", "utf-8"):
            try:
                blob = text.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            blob = text.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return []
    return dc.parse_dell_software_manifest_root(root)


def _dell_os_supported(pkg: ET.Element, *, want_win11: bool, want_win10: bool) -> bool:
    for os_el in pkg.findall(f".//{_DELL_NS}OperatingSystem"):
        disp = ""
        for d in os_el.findall(f"{_DELL_NS}Display"):
            disp = (d.text or "").strip().lower()
            if disp:
                break
        os_code = (os_el.get("osCode") or "").lower()
        arch = (os_el.get("osArch") or "").lower()
        if arch and arch not in ("x64", "amd64"):
            continue
        blob = f"{disp} {os_code}"
        if want_win11 and ("windows 11" in blob or "win11" in blob):
            return True
        if want_win10 and ("windows 10" in blob or "windows10" in os_code or "win10" in blob):
            return True
    return False


def _dell_model_score(pkg: ET.Element, system_model: str, system_sku: str) -> int:
    best = 0
    sku_u = (system_sku or "").upper()
    for model in pkg.findall(f".//{_DELL_NS}Model"):
        name = (model.get("name") or "").strip()
        disp = ""
        for d in model.findall(f"{_DELL_NS}Display"):
            disp = (d.text or "").strip()
            if disp:
                break
        sid = (model.get("systemID") or "").upper()
        score = max(_model_match_score(system_model, name), _model_match_score(system_model, disp))
        if sku_u and sid and sku_u.endswith(sid):
            score += 8
        if score > best:
            best = score
    return best


def _dell_enterprise_rows_impl(system_ctx: dict | None) -> list[dict]:
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").lower()
    if "dell" not in mfr and "alienware" not in mfr:
        return []
    xml_bytes = _load_cached_xml("dell", _DELL_CAB_URL, _DELL_XML_MEMBER)
    if not xml_bytes:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    want_win11, want_win10 = _windows_os_tokens()
    system_model = (ctx.get("system_model") or "").strip()
    system_sku = (ctx.get("system_sku") or "").strip()
    candidates: list[tuple[int, ET.Element, str]] = []
    base_loc = (root.get("baseLocation") or "downloads.dell.com").strip("/")
    for pkg in root.findall(f"{_DELL_NS}DriverPackage"):
        if not _dell_os_supported(pkg, want_win11=want_win11, want_win10=want_win10):
            continue
        score = _dell_model_score(pkg, system_model, system_sku)
        if score < 4:
            continue
        dt = (pkg.get("dateTime") or "")[:10]
        candidates.append((score, pkg, dt))
    if not candidates:
        return []
    candidates.sort(key=lambda t: (t[0], t[2]), reverse=True)
    _score, best_pkg, _ = candidates[0]
    meta = best_pkg.find(f"{_DELL_NS}DriverPackMetadataInfo")
    if meta is None:
        return _dell_pack_summary_rows(best_pkg, base_loc)
    try:
        meta_size = int((meta.findtext("Size") or meta.get("Size") or "0").strip())
    except ValueError:
        meta_size = 0
    meta_path = (meta.findtext("path") or meta.get("path") or "").strip()
    if not meta_path or meta_size <= 0 or meta_size > _DELL_METADATA_MAX_BYTES:
        return _dell_pack_summary_rows(best_pkg, base_loc)
    meta_url = f"https://{base_loc}/{meta_path.lstrip('/')}"
    meta_bytes = _http_get_bytes(meta_url, timeout=60)
    if not meta_bytes:
        return _dell_pack_summary_rows(best_pkg, base_loc)
    for enc in ("utf-16", "utf-8"):
        try:
            text = meta_bytes.decode(enc)
            rows = _parse_dell_software_manifest_text(text)
            if not rows:
                rows = _parse_dell_driver_archive_manifest(text)
            if rows:
                for row in rows:
                    row.setdefault("category", row.get("category") or "Dell enterprise catalog")
                return rows
        except UnicodeDecodeError:
            continue
    return _dell_pack_summary_rows(best_pkg, base_loc)


def _dell_pack_summary_rows(pkg: ET.Element, base_loc: str) -> list[dict]:
    title = ""
    for name_el in pkg.findall(f".//{_DELL_NS}Name"):
        for disp in name_el.findall(f"{_DELL_NS}Display"):
            title = (disp.text or "").strip()
            if title:
                break
    if not title:
        title = "Dell System Driver Pack"
    ver = (pkg.get("dellVersion") or pkg.get("vendorVersion") or "").strip()
    date_s = (pkg.get("dateTime") or "")[:10]
    url = ""
    info = pkg.find(f"{_DELL_NS}ImportantInfo")
    if info is not None and info.get("URL"):
        url = info.get("URL") or ""
    rel = (pkg.get("path") or "").strip()
    if not url and rel:
        url = f"https://{base_loc}/{rel.lstrip('/')}"
    return [{
        "title": title,
        "version": ver,
        "date": date_s,
        "url": url,
        "category": "Dell enterprise driver pack",
    }]


def _hp_enterprise_rows_impl(system_ctx: dict | None) -> list[dict]:
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").lower()
    if "hp" not in mfr and "hewlett" not in mfr:
        return []
    xml_bytes = _load_cached_xml("hp", _HP_CAB_URL, _HP_XML_MEMBER)
    if not xml_bytes:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    want_win11, want_win10 = _windows_os_tokens()
    system_model = (ctx.get("system_model") or "").strip()
    hp_ids = _hp_system_ids(ctx)
    softpaqs: dict[str, dict] = {}
    for sp in root.findall(".//SoftPaq"):
        sp_id = (sp.findtext("Id") or "").strip().lower()
        if not sp_id:
            continue
        softpaqs[sp_id] = {
            "title": (sp.findtext("Name") or sp.findtext("CvaTitle") or sp_id).strip(),
            "version": (sp.findtext("Version") or "").strip(),
            "date": _normalize_date(sp.findtext("DateReleased") or ""),
            "url": (sp.findtext("Url") or "").strip(),
            "category": (sp.findtext("Category") or "HP SoftPaq").strip(),
        }
    rows: list[dict] = []
    seen: set[str] = set()
    for link in root.findall(".//ProductOSDriverPack"):
        os_name = (link.findtext("OSName") or "").lower()
        if want_win11 and "windows 11" not in os_name:
            if not (want_win10 and "windows 10" in os_name):
                continue
        elif want_win10 and "windows 10" not in os_name and not want_win11:
            continue
        sys_name = (link.findtext("SystemName") or "").strip()
        score = _model_match_score(system_model, sys_name)
        sys_id_raw = (link.findtext("SystemId") or "").lower()
        sys_ids = {s.strip() for s in sys_id_raw.replace(" ", "").split(",") if s.strip()}
        if hp_ids and sys_ids.intersection(hp_ids):
            score += 10
        if score < 4:
            continue
        sp_id = (link.findtext("SoftPaqId") or "").strip().lower()
        sp = softpaqs.get(sp_id)
        if not sp or sp_id in seen:
            continue
        seen.add(sp_id)
        rows.append(dict(sp))
    rows.sort(key=lambda r: (r.get("date") or "", r.get("version") or ""), reverse=True)
    return rows[:12]


def _lenovo_enterprise_rows_impl(system_ctx: dict | None) -> list[dict]:
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").lower()
    if "lenovo" not in mfr and "thinkpad" not in mfr and "ideapad" not in mfr:
        return []
    mtm = _lenovo_mtm(ctx)
    if not mtm:
        return []
    xml_bytes = _load_cached_xml("lenovo", _LENOVO_XML_URL, None)
    if not xml_bytes:
        return []
    text = xml_bytes.decode("utf-8", errors="replace").lstrip("\ufeff")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    want_win11, want_win10 = _windows_os_tokens()
    rows: list[dict] = []
    for model in root.findall(".//Model"):
        types = {((t.text or "").strip().upper()) for t in model.findall(".//Type")}
        if mtm not in types and mtm[:7] not in types:
            continue
        model_name = (model.get("name") or "Lenovo system").strip()
        best: dict | None = None
        best_key = ""
        for sccm in model.findall("SCCM"):
            os_attr = (sccm.get("os") or "").lower()
            ver_attr = (sccm.get("version") or "").lower()
            if want_win11 and "win11" not in os_attr and os_attr != "win10":
                if not (want_win10 and os_attr == "win10"):
                    continue
            elif want_win10 and os_attr not in ("win10", "win11", "*") and not want_win11:
                continue
            url = (sccm.text or "").strip()
            if not url:
                continue
            date_s = (sccm.get("date") or "").strip()
            key = f"{os_attr}|{ver_attr}|{date_s}"
            if key > best_key:
                best_key = key
                best = {
                    "title": f"{model_name} Driver Pack ({os_attr or 'windows'})",
                    "version": ver_attr if ver_attr and ver_attr != "*" else date_s,
                    "date": date_s,
                    "url": url,
                    "category": "Lenovo SCCM driver pack",
                }
        if best:
            rows.append(best)
    return rows


def _normalize_date(raw: str) -> str:
    try:
        import driver_catalog as dc
    except ImportError:
        return (raw or "").strip()[:10]
    return dc._normalize_oem_date(raw)


def parse_dell_driver_pack_catalog_xml(xml_bytes: bytes, system_ctx: dict | None) -> list[dict]:
    """Test helper: parse DriverPackCatalog.xml bytes for this machine."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    want_win11, want_win10 = _windows_os_tokens()
    ctx = system_ctx or {}
    system_model = (ctx.get("system_model") or "").strip()
    system_sku = (ctx.get("system_sku") or "").strip()
    base_loc = (root.get("baseLocation") or "downloads.dell.com").strip("/")
    out: list[dict] = []
    for pkg in root.findall(f"{_DELL_NS}DriverPackage"):
        if not _dell_os_supported(pkg, want_win11=want_win11, want_win10=want_win10):
            continue
        if _dell_model_score(pkg, system_model, system_sku) < 4:
            continue
        out.extend(_dell_pack_summary_rows(pkg, base_loc))
    return out
