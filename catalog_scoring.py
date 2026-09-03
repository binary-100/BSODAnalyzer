"""Driver/firmware version parsing and numeric comparison (extracted from driver_catalog)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

# Microsoft/OEM often stamp inbox or republished drivers with placeholder dates.
_DRIVER_DATE_SENTINEL_YMD = frozenset({
    (1970, 1, 1),
    (1980, 1, 1),
    (2005, 1, 1),
    (2006, 6, 21),
    (2006, 6, 22),
    (2007, 7, 7),
})


def parse_driver_version(version: str) -> tuple[int, ...]:
    """Normalize version strings for comparison (e.g. 32.0.15.7688)."""
    if not version:
        return ()
    s = str(version).strip()
    m = re.search(r"(\d+(?:\.\d+){1,6})", s)
    if not m:
        return ()
    parts = []
    for p in m.group(1).split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts)


def compare_versions(installed: str, candidate: str) -> str:
    """Return newer | same | older | unknown (numeric version segments only)."""
    a = parse_driver_version(installed)
    b = parse_driver_version(candidate)
    if not a or not b:
        return "unknown"
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    if b > a:
        return "newer"
    if b < a:
        return "older"
    return "same"


def parse_driver_package_date(raw: str) -> date | None:
    """Parse WMI / catalog / JSON driver dates to a calendar date."""
    if not raw:
        return None
    try:
        from bsod_hardware_wmi import _parse_json_date
    except ImportError:
        _parse_json_date = lambda s: s or ""  # type: ignore[assignment, misc]
    s = str(_parse_json_date(str(raw).strip()) or "").strip()
    if not s:
        s = str(raw).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        except ValueError:
            pass
    return None


def driver_date_is_trustworthy(d: date | None) -> bool:
    """False for Microsoft placeholder dates and unusable values."""
    if d is None:
        return False
    if (d.year, d.month, d.day) in _DRIVER_DATE_SENTINEL_YMD:
        return False
    if d.year < 2012:
        return False
    if d > date.today() + timedelta(days=90):
        return False
    return True
import driver_version_identity as dvi


def _catalog_loader(name: str) -> str:
    """Installed-version loaders live here but resolve via driver_catalog for test mocks."""
    import driver_catalog as _dc

    return getattr(_dc, name)()


def _load_installed_package_versions() -> dict[str, str]:
    import driver_catalog as _dc
    return _dc._load_installed_package_versions()


def _ctx_device_label(ctx: dict) -> str:
    return (
        ctx.get("device_label")
        or ctx.get("device_name")
        or ctx.get("target_device_name")
        or ""
    ).strip()


_MS_INBOX_VERSION_RE = re.compile(r"^10\.0\.\d{4,}")

def _looks_like_amd_chipset_package_version(version: str) -> bool:
    """AMD Chipset Software suite versioning (e.g. 7.12.x, 8.05.x) — not per-INF lines."""
    parts = parse_driver_version(version)
    if not parts or len(parts) < 2:
        return False
    major, minor = parts[0], parts[1]
    if major == 8:
        # 8.05.04.516 suite vs 8.0.0.62 provisioning component
        return minor >= 1
    if major == 7:
        return True
    if major == 5 and len(parts) >= 4:
        # Legacy suite builds like 5.11.02.217 — not PSP 5.44.0.0 or SMBUS 5.12.0.44.
        return parts[3] >= 100
    return False

def _looks_like_intel_chipset_package_version(version: str) -> bool:
    """Intel Chipset INF / platform package versioning (e.g. 10.1.19900.8770)."""
    parts = parse_driver_version(version)
    if not parts or len(parts) < 2:
        return False
    major, minor = parts[0], parts[1]
    if major == 10 and minor >= 1:
        return True
    if major == 11 and minor <= 9:
        return True
    return False

def _intel_chipset_suite_build(version: str) -> int | None:
    """Suite INF uses a large third segment (e.g. 10.1.20398.8776); component INFs use small builds."""
    parts = parse_driver_version(version)
    if not parts or len(parts) < 3:
        return None
    if parts[0] != 10 or parts[1] != 1:
        return None
    return int(parts[2])

def _intel_suite_vs_component_version_mismatch(installed: str, candidate: str) -> bool:
    """True when comparing chipset suite package to per-device component INF numbering."""
    ib = _intel_chipset_suite_build(installed)
    cb = _intel_chipset_suite_build(candidate)
    if ib is None or cb is None:
        return False
    suite_floor = 1000
    inst_is_suite = ib >= suite_floor
    cand_is_suite = cb >= suite_floor
    return inst_is_suite != cand_is_suite

def _looks_like_amd_adrenalin_version(version: str) -> bool:
    """AMD Software: Adrenalin marketing version (e.g. 26.6.2)."""
    parts = parse_driver_version(version)
    return bool(
        parts
        and 20 <= parts[0] < 30
        and len(parts) >= 2
        and parts[1] >= 1
    )

def _looks_like_amd_display_driver_version(version: str) -> bool:
    """AMD Windows display driver package version (32.0.x.x)."""
    parts = parse_driver_version(version)
    return bool(parts and parts[0] == 32 and len(parts) >= 3)

def _load_amd_chipset_suite_installed_version() -> str:
    """AMD Chipset Software suite from Add/Remove Programs (e.g. 8.05.04.516)."""
    pkg = _load_installed_package_versions()
    ver = (pkg.get("amd_chipset") or "").strip()
    if ver and _looks_like_amd_chipset_package_version(ver):
        return ver
    return ""

def _load_intel_chipset_suite_installed_version() -> str:
    """Intel Chipset INF package from Add/Remove Programs (e.g. 10.1.19900.8770)."""
    pkg = _load_installed_package_versions()
    ver = (pkg.get("intel_chipset") or "").strip()
    if ver and _looks_like_intel_chipset_package_version(ver):
        return ver
    return ""

def _load_amd_adrenalin_installed_version() -> str:
    """Adrenalin edition from Add/Remove Programs (AMD Software 26.x)."""
    pkg = _load_installed_package_versions()
    ver = (pkg.get("amd_adrenalin") or "").strip()
    if ver and _looks_like_amd_adrenalin_version(ver):
        return ver
    return ""

def _load_nvidia_branch_installed_version() -> str:
    """Game Ready branch from Add/Remove Programs (e.g. 581.42)."""
    pkg = _load_installed_package_versions()
    ver = (pkg.get("nvidia_branch") or "").strip()
    if ver and _looks_like_nvidia_branch_version(ver):
        return ver
    return ""

def _looks_like_realtek_nic_driver_version(version: str) -> bool:
    parts = parse_driver_version(version)
    if len(parts) < 2:
        return False
    if parts[0] >= 1000:
        return True
    return len(parts) >= 4 and parts[0] >= 100

def _ctx_is_wifi_radio_device(ctx: dict) -> bool:
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx).lower()
    if "bluetooth" in label and pnp == "bluetooth":
        return False
    if pnp == "net":
        return True
    return any(k in label for k in ("wi-fi", "wifi", "wireless", "wlan", "802.11"))

def _ctx_is_bluetooth_radio_device(ctx: dict) -> bool:
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx).lower()
    return pnp == "bluetooth" or ("bluetooth" in label and "wi-fi" not in label and "wifi" not in label)

def _looks_like_mediatek_uwd_version(version: str) -> bool:
    """MediaTek UWD Wi-Fi/BT driver versions (e.g. 3.5.0.1392, 1.930.3.287)."""
    parts = parse_driver_version(version)
    return bool(parts and 1 <= parts[0] <= 9 and len(parts) >= 3)

def _ctx_skip_amd_adrenalin_compare_gate(ctx: dict | None) -> bool:
    """Do not treat MSCatalog 26.x as AMD Adrenalin on third-party radio/network devices."""
    if not ctx:
        return False
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    if vk in ("mediatek", "qualcomm", "killer", "broadcom"):
        return True
    if vk == "intel" and pnp == "net":
        return True
    inst = (ctx.get("primary_version") or "").strip()
    if inst and _looks_like_mediatek_uwd_version(inst):
        return True
    return False

def _looks_like_realtek_wdm_version(version: str) -> bool:
    parts = parse_driver_version(version)
    return len(parts) >= 2 and parts[0] == 6 and parts[1] == 0

def _looks_like_realtek_apo_version(version: str) -> bool:
    parts = parse_driver_version(version)
    return bool(parts and parts[0] == 13)

def _realtek_net_version_major(version: str) -> str:
    parts = parse_driver_version(version)
    return str(parts[0]) if parts else ""

def _realtek_nic_cross_scheme_equivalent(installed: str, candidate: str) -> bool:
    """True when Realtek.com 11.x.y matches OEM 1125.x.y.z (shared build suffix)."""
    return dvi.realtek_nic_versions_equivalent(installed, candidate)

def _realtek_nic_version_tail(version: str) -> tuple[int, ...]:
    """Realtek NIC suffix after the OEM-specific first segment (e.g. 1125.28.1224.2025 → 28…)."""
    parts = parse_driver_version(version)
    if len(parts) < 2:
        return ()
    return parts[1:]

def _realtek_nic_same_oem_family(installed: str, candidate: str) -> bool:
    """True when Dell/Realtek NIC builds share the same base suffix (1125 vs 1168 revision bump)."""
    it = _realtek_nic_version_tail(installed)
    ct = _realtek_nic_version_tail(candidate)
    return bool(it and ct and it == ct)

def _looks_like_windows_inbox_driver_version(version: str) -> bool:
    v = (version or "").strip()
    if not v:
        return False
    if _MS_INBOX_VERSION_RE.match(v):
        return True
    parts = parse_driver_version(v)
    return bool(len(parts) >= 3 and parts[0] == 10 and parts[1] == 0 and parts[2] >= 10240)

def _version_prefix_family(parts: tuple[int, ...]) -> str:
    if not parts:
        return ""
    if parts[0] == 6 and len(parts) >= 2 and parts[1] == 0:
        return "wdm_6"
    if parts[0] == 10 and len(parts) >= 2 and parts[1] == 0:
        return "inbox_10"
    if parts[0] == 32:
        return "gpu_32"
    if 20 <= parts[0] < 30 and len(parts) >= 2 and parts[1] >= 1:
        return "amd_pkg"
    if parts[0] <= 2:
        return "low_major"
    return f"m{parts[0]}"

def _version_schemes_compatible(installed: str, candidate: str) -> bool:
    """False when inbox, Realtek WDM/APO, or other unlike numbering is compared."""
    inst_inbox = _looks_like_windows_inbox_driver_version(installed)
    cand_inbox = _looks_like_windows_inbox_driver_version(candidate)
    if inst_inbox != cand_inbox:
        return False
    inst_rt_wdm = _looks_like_realtek_wdm_version(installed)
    cand_rt_apo = _looks_like_realtek_apo_version(candidate)
    cand_rt_wdm = _looks_like_realtek_wdm_version(candidate)
    inst_rt_apo = _looks_like_realtek_apo_version(installed)
    if (inst_rt_wdm and cand_rt_apo) or (inst_rt_apo and cand_rt_wdm):
        return False
    inst_p = parse_driver_version(installed)
    cand_p = parse_driver_version(candidate)
    if inst_p and cand_p:
        fi = _version_prefix_family(inst_p)
        fc = _version_prefix_family(cand_p)
        if fi and fc and fi != fc:
            incompatible = {
                ("wdm_6", "gpu_32"),
                ("wdm_6", "amd_pkg"),
                ("wdm_6", "inbox_10"),
                ("inbox_10", "gpu_32"),
                ("inbox_10", "amd_pkg"),
                ("gpu_32", "amd_pkg"),
                ("low_major", "gpu_32"),
                ("low_major", "amd_pkg"),
                ("low_major", "inbox_10"),
                ("low_major", "m10"),
            }
            if (fi, fc) in incompatible or (fc, fi) in incompatible:
                return False
    return True

def compare_driver_to_installed(
    installed_version: str,
    candidate_version: str,
    *,
    installed_date: str = "",
    candidate_date: str = "",
    candidate_windows_version: str = "",
    wu_offered: bool = False,
    source: str = "",
    hwid_verified: bool = False,
    device_ctx: dict | None = None,
) -> tuple[str, str]:
    """
    Decide newer | same | older | uncertain | unknown using multiple signals.

    Priority:
    1) Windows Update optional driver list (OS already selected this package)
    2) Numeric driver version (primary when parseable)
    3) Driver package dates when both are trustworthy (not MS sentinels)
    4) uncertain when version and date disagree (vendor re-numbering)
    """
    inst = (installed_version or "").strip()
    cand = (candidate_version or "").strip()
    inst_known = inst and inst not in ("?", "—", "N/A", "unknown")
    cand_known = bool(cand)

    if not inst_known and cand_known:
        return (
            "unknown",
            "Installed driver version was not read from Windows — cannot compare automatically.",
        )

    if wu_offered and cand_known and inst_known:
        ver = compare_versions(inst, cand)
        if ver == "older":
            return (
                "uncertain",
                "Windows Update offers this package but its version string is lower "
                "than installed — possible numbering change; verify before installing.",
            )
        if ver == "newer":
            return (
                "newer",
                "Offered as an optional driver update in Windows Update.",
            )
        if ver == "same":
            return (
                "same",
                "Optional Windows Update package matches the installed version string.",
            )

    inst_branch = _looks_like_nvidia_branch_version(inst)
    cand_branch = _looks_like_nvidia_branch_version(cand)
    inst_internal = _looks_like_nvidia_internal_version(inst)
    cand_internal = _looks_like_nvidia_internal_version(cand)
    nvidia_mixed = (
        inst_known
        and cand_known
        and (
            (inst_branch and cand_internal)
            or (inst_internal and cand_branch)
        )
    )
    if nvidia_mixed:
        if inst_internal and cand_branch:
            branch_installed = _catalog_loader("_load_nvidia_branch_installed_version")
            if branch_installed:
                nvidia_ver = compare_versions(branch_installed, cand)
                notes = {
                    "newer": (
                        f"NVIDIA branch {cand} is newer than installed "
                        f"{branch_installed} (Windows reports {inst})."
                    ),
                    "older": (
                        f"NVIDIA branch {cand} is older than installed {branch_installed}."
                    ),
                    "same": (
                        f"NVIDIA Game Ready branch {branch_installed} matches catalog "
                        f"{cand} (Windows internal {inst})."
                    ),
                    "unknown": "Could not compare NVIDIA branch version numbers.",
                }
                return nvidia_ver, notes.get(nvidia_ver, notes["unknown"])
            win_cand = (candidate_windows_version or "").strip()
            if win_cand and _looks_like_nvidia_internal_version(win_cand):
                internal_ver = compare_versions(inst, win_cand)
                notes = {
                    "newer": (
                        f"Catalog Windows package {win_cand} (branch {cand}) is newer than "
                        f"installed {inst}."
                    ),
                    "older": (
                        f"Installed {inst} is newer than catalog Windows package "
                        f"{win_cand} (branch {cand})."
                    ),
                    "same": (
                        f"Installed {inst} matches catalog Windows package for branch {cand}."
                    ),
                    "unknown": "Could not compare NVIDIA internal version numbers.",
                }
                return internal_ver, notes.get(internal_ver, notes["unknown"])
        inst_d = parse_driver_package_date(installed_date)
        cand_d = parse_driver_package_date(candidate_date)
        inst_dt = driver_date_is_trustworthy(inst_d)
        cand_dt = driver_date_is_trustworthy(cand_d)
        if inst_dt and cand_dt:
            if cand_d > inst_d:
                return (
                    "newer",
                    "NVIDIA package date is newer (branch vs internal version formats).",
                )
            if cand_d < inst_d:
                return (
                    "older",
                    "NVIDIA package date is older (branch vs internal version formats).",
                )
            return (
                "same",
                "NVIDIA package dates match (branch vs internal version formats).",
            )
        if inst_branch and cand_branch:
            pass
        else:
            return (
                "uncertain",
                "NVIDIA branch (610.xx) vs internal (32.0.x.x) version strings — "
                "confirm on the NVIDIA site or compare driver dates.",
            )

    inst_adrenalin = _looks_like_amd_adrenalin_version(inst)
    cand_adrenalin = _looks_like_amd_adrenalin_version(cand)
    inst_amd_display = _looks_like_amd_display_driver_version(inst)
    cand_amd_display = _looks_like_amd_display_driver_version(cand)
    amd_mixed = (
        inst_known
        and cand_known
        and (
            (inst_amd_display and cand_adrenalin)
            or (inst_adrenalin and cand_amd_display)
        )
    )
    if amd_mixed:
        adrenalin_installed = _catalog_loader("_load_amd_adrenalin_installed_version")
        if adrenalin_installed and cand_adrenalin:
            amd_ver = compare_versions(adrenalin_installed, cand)
            notes = {
                "newer": (
                    f"Adrenalin {cand} is newer than installed {adrenalin_installed} "
                    f"(Windows reports display driver {inst})."
                ),
                "older": (
                    f"Adrenalin {cand} is older than installed {adrenalin_installed}."
                ),
                "same": f"Adrenalin version matches installed {adrenalin_installed}.",
                "unknown": "Could not compare Adrenalin version numbers.",
            }
            return amd_ver, notes.get(amd_ver, notes["unknown"])
        inst_d = parse_driver_package_date(installed_date)
        cand_d = parse_driver_package_date(candidate_date)
        inst_dt = driver_date_is_trustworthy(inst_d)
        cand_dt = driver_date_is_trustworthy(cand_d)
        if inst_dt and cand_dt:
            if cand_d > inst_d:
                return (
                    "newer",
                    "AMD package date is newer (Adrenalin 26.x vs 32.0.x display formats).",
                )
            if cand_d < inst_d:
                return (
                    "older",
                    "AMD package date is older (Adrenalin 26.x vs 32.0.x display formats).",
                )
            return (
                "same",
                "AMD package dates match (Adrenalin vs display driver version formats).",
            )
        return (
            "uncertain",
            "AMD Adrenalin (26.x) vs Windows display driver (32.0.x) — compare in "
            "AMD Software or match release dates on AMD's site.",
        )

    # AMD Adrenalin/graphics suite version (26.x) attached to a per-component INF
    # device (e.g. PSP 5.44.0.0, SMBUS 2.0.0.26) is apples-to-oranges: the vendor
    # scraper reports the suite number, but the component INF version is a
    # different scheme. A naive compare reads 26 > 5 as "newer" and re-surfaces a
    # device the user is already current on. Treat as uncertain and point at the
    # proper suite rows — matching how the other AMD chipset components behave.
    # Gate on a large major-version gap so genuine same-family bumps that merely
    # look Adrenalin-like (e.g. Intel Wi-Fi 22.x → 23.x) are unaffected.
    _inst_parts = parse_driver_version(inst)
    _cand_parts = parse_driver_version(cand)
    if (
        inst_known
        and cand_known
        and cand_adrenalin
        and not inst_adrenalin
        and not inst_amd_display
        and _inst_parts
        and _cand_parts
        and _inst_parts[0] + 3 < _cand_parts[0]
        and not _ctx_skip_amd_adrenalin_compare_gate(device_ctx)
    ):
        return (
            "uncertain",
            "AMD Adrenalin/graphics suite version vs component INF version — use the "
            "AMD Radeon graphics or AMD Chipset / Platform drivers row for suite updates.",
        )

    if inst_known and cand_known:
        if _intel_suite_vs_component_version_mismatch(inst, cand):
            return (
                "uncertain",
                "Intel Chipset INF suite version vs component INF version — use "
                "Intel Chipset / Platform drivers for suite updates.",
            )
        if (
            _looks_like_realtek_wdm_version(inst)
            and _looks_like_realtek_wdm_version(cand)
            and (source or "").lower() == "microsoft"
            and not hwid_verified
        ):
            pre_ver = compare_versions(inst, cand)
            if pre_ver == "newer":
                return (
                    "uncertain",
                    "Microsoft Realtek MEDIA package — hardware ID not confirmed for this "
                    "codec. Open Update Catalog → Package Details before installing.",
                )
        if _realtek_nic_cross_scheme_equivalent(inst, cand):
            _eq, eq_note = dvi.versions_equivalent(
                inst,
                cand,
                device_ctx={"vendor_key": "realtek", "pnp_class": "net"},
            )
            return "same", eq_note or dvi.realtek_nic_equivalence_note(inst, cand)
        if (
            _looks_like_realtek_nic_driver_version(inst)
            and _looks_like_realtek_nic_driver_version(cand)
            and _realtek_net_version_major(inst) != _realtek_net_version_major(cand)
            # A shared build suffix (1125.28.1224.2025 → 1168.28.1224.2025) is an OEM
            # revision bump, not a different family, so it stays comparable. The reject
            # filter already treats it that way via _realtek_nic_same_oem_family.
            and not _realtek_nic_same_oem_family(inst, cand)
        ):
            pre_ver = compare_versions(inst, cand)
            fam_notes = {
                "newer": (
                    "OEM Realtek NIC package uses a different version family "
                    f"(e.g. {_realtek_net_version_major(cand)}.x vs installed "
                    f"{_realtek_net_version_major(inst)}.x) — verify on Dell/OEM support "
                    "before installing."
                ),
                "older": (
                    "Package version family differs from installed Realtek NIC driver."
                ),
                "same": (
                    "Version families differ but numeric strings match — verify manually."
                ),
            }
            return "uncertain", fam_notes.get(pre_ver, fam_notes["older"])

    ver = compare_versions(inst, cand) if (inst_known and cand_known) else "unknown"
    inst_chipset_suite = (
        _looks_like_amd_chipset_package_version(inst)
        or _looks_like_intel_chipset_package_version(inst)
    )
    cand_chipset_suite = (
        _looks_like_amd_chipset_package_version(cand)
        or _looks_like_intel_chipset_package_version(cand)
    )
    if inst_chipset_suite and _looks_like_amd_adrenalin_version(cand):
        return (
            "unknown",
            "AMD Software marketing version — not comparable to AMD Chipset Software suite.",
        )
    if (
        inst_known
        and cand_known
        and ver == "newer"
        and not inst_chipset_suite
        and cand_chipset_suite
    ):
        return (
            "uncertain",
            "AMD chipset package version vs component INF version — use the "
            "AMD Chipset / Platform drivers row for suite updates.",
        )
    if (
        inst_known
        and cand_known
        and ver in ("newer", "older")
        and not _version_schemes_compatible(inst, cand)
        and not wu_offered
        and not hwid_verified
        and not (inst_branch or cand_branch)
    ):
        return (
            "uncertain",
            "Installed driver uses Windows inbox version format (10.0.x…) while the "
            "catalog package uses a different numbering scheme — confirm hardware ID "
            "match before treating as an update.",
        )
    inst_d = parse_driver_package_date(installed_date)
    cand_d = parse_driver_package_date(candidate_date)
    inst_dt = driver_date_is_trustworthy(inst_d)
    cand_dt = driver_date_is_trustworthy(cand_d)

    if ver == "unknown":
        if (
            inst_known
            and not cand_known
            and _looks_like_realtek_wdm_version(inst)
            and cand_dt
        ):
            return (
                "uncertain",
                "Realtek legacy/vendor page date is not comparable to installed UAD (6.0.x) — "
                "use Microsoft Catalog UAD packages.",
            )
        if inst_dt and cand_dt:
            if cand_d > inst_d:
                return "newer", "Package date is newer (version strings not comparable)."
            if cand_d < inst_d:
                return "older", "Package date is older (version strings not comparable)."
            return "same", "Package dates match (version strings not comparable)."
        return "unknown", "Could not compare version numbers or trustworthy package dates."

    if not inst_dt or not cand_dt:
        notes = {
            "newer": "Version number is higher than installed.",
            "older": "Version number is lower than installed.",
            "same": "Version string matches installed.",
        }
        extra = (
            " Driver dates ignored (missing or Microsoft/OEM placeholder dates)."
            if source == "microsoft" or not (inst_dt and cand_dt)
            else " Driver dates were not available for a second check."
        )
        return ver, notes.get(ver, "") + extra

    if ver == "newer":
        if cand_d < inst_d:
            return (
                "newer",
                f"Version {cand} is higher than {inst}; package date is older "
                f"({candidate_date} vs {installed_date}) — trusting version "
                "(common when Microsoft uses a default driver date).",
            )
        return "newer", "Version and driver package date are both newer than installed."

    if ver == "same":
        if cand_d > inst_d:
            if device_ctx and (
                _ctx_is_wifi_radio_device(device_ctx)
                or _ctx_is_bluetooth_radio_device(device_ctx)
            ):
                return (
                    "same",
                    f"Same version string ({cand}); package date is newer "
                    f"({candidate_date} vs {installed_date}) — no version change.",
                )
            return (
                "newer",
                f"Same version string ({cand}); driver package date is newer "
                f"({candidate_date} vs {installed_date}).",
            )
        return "same", "Version string and driver package date match installed."

    # ver == "older"
    if cand_d > inst_d:
        days = (cand_d - inst_d).days
        if days >= 14:
            return (
                "uncertain",
                f"Version {cand} is lower than installed {inst}, but package date is "
                f"{days} days newer — possible vendor re-numbering; verify on the "
                "manufacturer site before installing.",
            )
    return "older", "Version and driver package date are both older than installed."

def extract_version_from_text(text: str) -> str:
    """Pull a version token from a BIOS/SSD package title or filename."""
    s = (text or "").strip()
    if not s:
        return ""
    for pat in (
        r"\b(\d+\.\d+\.\d+(?:\.\d+)?)\b",
        r"\b([A-Z]{1,3}\d{2,}[A-Z]?\d*)\b",
        r"\b(v?\d{4,6}[A-Z]?)\b",
        r"\b(\d{2}[A-Z]\d{2,})\b",
    ):
        m = re.search(pat, s, re.I)
        if m:
            return m.group(1).upper().lstrip("V")
    return ""

def _firmware_version_compact(version: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (version or "").upper())

def compare_firmware_versions(
    installed: str,
    candidate: str,
    *,
    title: str = "",
) -> str:
    """
    BIOS/SSD version compare — handles unlike formats (SMBIOS vs OEM package names).
    Falls back to numeric compare_versions when possible.
    """
    cand = (candidate or "").strip() or extract_version_from_text(title)
    inst = (installed or "").strip()
    if not cand or not inst or inst in ("?", "—", "N/A"):
        return "unknown"
    inst_c = _firmware_version_compact(inst)
    cand_c = _firmware_version_compact(cand)
    if inst_c == cand_c:
        return "same"
    if len(cand_c) >= 4 and len(inst_c) >= 4:
        if cand_c in inst_c:
            return "older"
        if inst_c in cand_c:
            return "newer"
    numeric = compare_versions(inst, cand)
    if numeric != "unknown":
        return numeric
    inst_toks = set(re.findall(r"[A-Z]{0,3}\d{2,}[A-Z]?\d*", inst.upper()))
    cand_toks = set(re.findall(r"[A-Z]{0,3}\d{2,}[A-Z]?\d*", cand.upper()))
    shared = inst_toks & cand_toks
    if shared:
        inst_nums = [int(x) for x in re.findall(r"\d+", inst) if x.isdigit()]
        cand_nums = [int(x) for x in re.findall(r"\d+", cand) if x.isdigit()]
        if inst_nums and cand_nums and max(cand_nums) > max(inst_nums):
            return "newer"
        if inst_nums and cand_nums and max(cand_nums) < max(inst_nums):
            return "older"
        return "same"
    if len(cand_c) >= 6 and len(inst_c) >= 6:
        if cand_c[:4] == inst_c[:4] and cand_c > inst_c:
            return "newer"
        if cand_c[:4] == inst_c[:4] and cand_c < inst_c:
            return "older"
    return "unknown"

def _normalize_oem_date(raw: str) -> str:
    """Normalize OEM/API release dates to ``YYYY-MM-DD`` or ``\"\"``.

    Dell/HP JSON often uses ``\"February 02, 2026\"`` — never slice those with
    ``[:10]`` (that produced strings like ``\"February 0\"``).
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        from bsod_hardware_wmi import _parse_json_date
    except ImportError:
        _parse_json_date = lambda x: x or ""  # type: ignore[assignment, misc]
    s = str(_parse_json_date(s) or s).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d").date()
            if 1 <= dt.month <= 12 and 1 <= dt.day <= 31:
                return dt.isoformat()
        except ValueError:
            pass
    parsed = parse_driver_package_date(s)
    if parsed and driver_date_is_trustworthy(parsed):
        return parsed.isoformat()
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if m:
        month_name, day_s, year_s = m.group(1), m.group(2), m.group(3)
        try:
            day = int(day_s)
            if day < 1 or day > 31:
                return ""
            for fmt in ("%B %d %Y", "%b %d %Y"):
                try:
                    dt = datetime.strptime(f"{month_name} {day} {year_s}", fmt).date()
                    if driver_date_is_trustworthy(dt):
                        return dt.isoformat()
                except ValueError:
                    continue
        except ValueError:
            pass
    return ""


def _looks_like_nvidia_branch_version(version: str) -> bool:
    v = (version or "").strip()
    return bool(re.match(r"^\d{3}\.\d{2,3}$", v))

def _looks_like_nvidia_internal_version(version: str) -> bool:
    v = (version or "").strip()
    return bool(re.match(r"^32\.0\.\d+\.\d+", v))
