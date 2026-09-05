"""Per-offer compare, verification, and uncertain-resolution (from driver_catalog)."""

from __future__ import annotations

import driver_version_identity as dvi
import oem_effective_version as oev

from catalog_device_context import (
    _ctx_device_label,
    _ctx_is_amd_chipset_platform_row,
    _ctx_is_intel_chipset_platform_row,
    _device_is_amd_chipset_plumbing,
    _device_is_intel_chipset_plumbing,
    _device_is_intel_me_device,
)
from catalog_device_profiles import (
    _load_intel_me_installed_version,
    _load_intel_wireless_installed_version,
    _load_realtek_ethernet_installed_version,
)
from catalog_mscatalog_session import _INSTALL_PROBE_CACHE, is_quick_check_mode
from catalog_oem_filters import _reject_oem_radio_wifi_bt_cross_mismatch
from catalog_offer_pipeline import (
    _SAME_WITHOUT_VERSION_NOTE,
    _UNVERIFIED_NEWER_NOTE,
    _append_compare_note,
    _offer_installability_rank,
    offer_source_sort_tier,
)
from catalog_offer_status import _offer_is_intel_chipset_inf
from catalog_realtek_queries import _soften_stale_realtek_wdm_oem_compare
from catalog_row_rejects import (
    _catalog_hwid_mismatch_note,
    _catalog_row_hwid_matches_ctx,
    _catalog_row_hwid_strict_matches_ctx,
    _realtek_device_component_role,
    _realtek_nic_mscatalog_trusted,
    _realtek_wdm_mscatalog_trusted,
)
from catalog_scoring import (
    _ctx_is_bluetooth_radio_device,
    _ctx_is_wifi_radio_device,
    _load_amd_adrenalin_installed_version,
    _load_amd_chipset_suite_installed_version,
    _load_intel_chipset_suite_installed_version,
    _load_nvidia_branch_installed_version,
    _looks_like_amd_adrenalin_version,
    _looks_like_amd_chipset_package_version,
    compare_driver_to_installed,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_DOWNLOAD_EXTENSIONS = (".exe", ".msi", ".cab", ".zip", ".inf", ".msu", ".7z")


def _primary_display_installed_version(device_ctx: dict | None) -> str:
    if not device_ctx:
        return ""
    for vc in device_ctx.get("video_controllers") or []:
        if not isinstance(vc, dict):
            continue
        name_l = (vc.get("name") or "").lower()
        if any(k in name_l for k in ("geforce", "radeon", "iris", "arc ", "uhd graphics")):
            ver = (vc.get("driver_version") or vc.get("version") or "").strip()
            if ver and ver not in ("?", "—"):
                return ver
    return ""


def _append_oem_bundle_component_note(
    offer: dict,
    vs: str,
    note: str,
    *,
    device_ctx: dict | None,
) -> str:
    """
    When a multi-driver OEM bundle targets one companion row (NPCF, chipset INF, …),
    clarify that only the matched component should be installed — not the full EXE.
    """
    if vs != "newer" or not device_ctx:
        return note
    if (offer.get("source") or "").lower() != "oem":
        return note
    role = (device_ctx.get("catalog_role") or "").lower()
    wrapper = (
        offer.get("offer_wrapper_version")
        or offer.get("version")
        or ""
    ).strip()
    primary_gpu = _primary_display_installed_version(device_ctx)
    title_l = (offer.get("title") or "").lower()
    is_graphics_bundle = any(
        k in title_l for k in ("geforce", "graphics driver", "display driver", "radeon")
    )
    if role == "gpu_companion" and is_graphics_bundle:
        note = _append_compare_note(
            note,
            "Multi-driver OEM graphics bundle — install targets this device's component "
            "only, not the entire package.",
        )
        if primary_gpu and wrapper:
            from catalog_scoring import compare_versions

            if compare_versions(primary_gpu, wrapper) == "older":
                note = _append_compare_note(
                    note,
                    "This bundle's display-driver portion is older than your installed "
                    f"GPU driver ({primary_gpu}). Do not run the full vendor installer.",
                )
    elif offer.get("inner_versions") or offer.get("offer_effective_version"):
        if role == "gpu_companion" or _device_is_amd_chipset_plumbing(device_ctx):
            note = _append_compare_note(
                note,
                "Multi-driver OEM bundle — install targets this device's component only, "
                "not the entire package.",
            )
    return note


def _offer_trusted_for_confident_newer(offer: dict) -> bool:
    """True when an offer may drive a confident device-level 'newer' status."""
    src = (offer.get("source") or "").lower()
    if offer.get("wu_offered"):
        return True
    if src == "microsoft":
        if offer.get("wu_offered") or offer.get("hwid_matched"):
            return True
        kind = _dc("_offer_download_kind")(offer).lower()
        if kind in ("cab", "catalog", "optional_updates", "uri"):
            return True
        if offer.get("update_id") and _offer_has_installable_package(offer):
            return True
        return False
    if src in ("vendor", "oem", "ssd_vendor"):
        return _offer_has_installable_package(offer)
    return _offer_has_installable_package(offer)


def _probe_offer_install_path(offer: dict) -> dict:
    """Resolve vendor/OEM web URLs to direct packages when possible."""
    row = dict(offer)
    if row.get("install_verified") or _offer_has_installable_package(row):
        row["install_verified"] = True
        row["download_resolvable"] = bool(row.get("download_resolvable", True))
        return row
    if is_quick_check_mode():
        return row
    url = (row.get("url") or "").strip()
    if not url:
        return row
    src = (row.get("source") or "").lower()
    if src not in ("vendor", "oem", "ssd_vendor"):
        return row
    cache_key = url.lower()
    cached = _INSTALL_PROBE_CACHE.get(cache_key)
    if cached is not None:
        row.update(cached)
        return row
    ok, _err, direct = _dc("resolve_vendor_package_download_url")(url, row)
    if ok and direct:
        if direct != url:
            row["vendor_page_url"] = row.get("vendor_page_url") or url
            row["url"] = direct
        row["install_verified"] = True
        row["download_resolvable"] = True
    probe_fields = {
        k: row[k]
        for k in ("url", "vendor_page_url", "install_verified", "download_resolvable")
        if k in row
    }
    _INSTALL_PROBE_CACHE[cache_key] = probe_fields
    return row


def _scheme_split_device_for_dual_baseline(ctx: dict | None) -> bool:
    """Devices that often have Windows INF vs suite/package version lines."""
    if not ctx:
        return False
    if _dc("_is_primary_gpu_display_manufacturer_authoritative")(ctx):
        return False
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx).lower()
    if vk in ("realtek", "intel", "killer", "broadcom", "marvell", "qualcomm"):
        return True
    if pnp == "net":
        return True
    if _device_is_intel_chipset_plumbing(ctx) or _device_is_amd_chipset_plumbing(ctx):
        return True
    if any(k in label for k in ("wi-fi", "wifi", "wireless", "ethernet", "2.5g", "bluetooth")):
        return True
    primary = (ctx.get("primary_version") or "").strip()
    return bool(_alternate_installed_baselines(ctx, primary))


def _apply_dual_baseline_gate(
    row: dict,
    primary_installed: str,
    installed_date: str,
    device_ctx: dict | None,
) -> dict:
    """
    Block alt-baseline-only *newer* when Windows INF (primary) disagrees.

    Used after alternate_installed_baseline resolution and for confident newer
    rows on scheme-split non-GPU devices.
    """
    if not device_ctx or not _scheme_split_device_for_dual_baseline(device_ctx):
        return row
    vs = (row.get("vs_installed") or "").lower()
    if vs != "newer":
        return row
    primary = (primary_installed or "").strip()
    if not primary or primary in ("?", "—", "N/A", "unknown"):
        return row

    primary_row = _recompare_offer_row(
        dict(row),
        primary,
        installed_date,
        device_ctx=device_ctx,
        probe_install=False,
        skip_dual_baseline_gate=True,
    )
    primary_vs = (primary_row.get("vs_installed") or "").lower()
    cand = (_offer_compare_version(row, device_ctx) or "").strip()
    equiv_note = ""
    if primary and cand:
        eq, equiv_note = dvi.versions_equivalent(primary, cand, device_ctx=device_ctx)
        if eq:
            primary_vs = "same"

    if primary_vs != "newer":
        out = dict(row)
        out["vs_installed"] = (
            "uncertain"
            if primary_vs in ("uncertain", "unknown")
            else "same"
        )
        out["verification_method"] = "dual_baseline_gate"
        out["compare_note"] = _append_compare_note(
            out.get("compare_note") or "",
            "Package/suite baseline suggested an update, but Windows INF "
            f"({primary}) is already same or ahead of the offer effective version"
            + (f" ({cand})." if cand else "."),
        )
        primary_note = (primary_row.get("compare_note") or "").strip()
        if primary_note and primary_note not in (out.get("compare_note") or ""):
            out["compare_note"] = _append_compare_note(
                out.get("compare_note") or "", primary_note
            )
        if equiv_note and equiv_note not in (out.get("compare_note") or ""):
            out["compare_note"] = _append_compare_note(
                out.get("compare_note") or "", equiv_note
            )
        return out
    return row


def _offer_compare_version(offer: dict, device_ctx: dict | None = None) -> str:
    """Version string used for status compare (inner PCI effective when available)."""
    eff, method, note = oev.resolve_offer_effective_version(offer, device_ctx)
    if eff:
        wrapper = (_dc("_offer_version_from_fields")(offer) or offer.get("version") or "").strip()
        if wrapper and wrapper != eff:
            offer["offer_wrapper_version"] = wrapper
        offer["offer_effective_version"] = eff
        if method:
            offer["effective_version_method"] = method
        if note:
            offer["effective_version_note"] = note
        return eff
    return (_dc("_offer_version_from_fields")(offer) or offer.get("version") or "").strip()


def _apply_update_reporting_policy(
    row: dict,
    vs: str,
    note: str,
    *,
    device_ctx: dict | None = None,
) -> tuple[str, str]:
    """
    Unified update reporting for every source tier.

    - Never report confident *newer* without a verified install path (or WU/HWID catalog proof).
    - Never report confident *same* for vendor/OEM rows without a version to compare.
    - Leave *uncertain* / coverage gaps when verification failed — do not assume up-to-date.
    """
    del device_ctx
    src = (row.get("source") or "").lower()
    has_ver = bool(_dc("_offer_version_from_fields")(row))

    if (
        (row.get("source") or "").lower() == "microsoft"
        and vs == "newer"
        and not row.get("wu_offered")
        and not row.get("hwid_matched")
    ):
        vs = "uncertain"
        note = _append_compare_note(
            note,
            "Microsoft catalog match without hardware ID confirmation — "
            "verify before treating as an update.",
        )

    if vs == "newer" and not _offer_trusted_for_confident_newer(row):
        vs = "uncertain"
        note = _append_compare_note(note, _UNVERIFIED_NEWER_NOTE)

    if vs == "same" and src in ("vendor", "oem", "ssd_vendor") and not has_ver:
        vs = "uncertain"
        note = _append_compare_note(note, _SAME_WITHOUT_VERSION_NOTE)

    return vs, note


def _microsoft_hwid_verified_for_row(row: dict, device_ctx: dict | None) -> bool:
    if bool(row.get("hwid_matched")):
        return True
    if not device_ctx:
        return False
    if _catalog_row_hwid_strict_matches_ctx(row, device_ctx):
        return True
    role = _realtek_device_component_role(device_ctx)
    if role == "wdm":
        return _realtek_wdm_mscatalog_trusted(row, device_ctx)
    if role == "net" or any(
        k in _ctx_device_label(device_ctx).lower()
        for k in ("ethernet", "gbe", "2.5g")
    ):
        return _realtek_nic_mscatalog_trusted(row, device_ctx)
    return _catalog_row_hwid_matches_ctx(row, device_ctx)


def _recompare_offer_row(
    row: dict,
    installed: str,
    installed_date: str = "",
    *,
    device_ctx: dict | None = None,
    probe_install: bool = False,
    skip_dual_baseline_gate: bool = False,
) -> dict:
    """Run compare + reporting policy on one offer row."""
    out = dict(row)
    inst = (installed or "").strip()
    inst_date = (installed_date or "").strip()
    cand = _offer_compare_version(out, device_ctx)
    if cand:
        out["version"] = cand
    hwid_verified = _microsoft_hwid_verified_for_row(out, device_ctx)
    if (out.get("source") or "").lower() == "microsoft":
        out["hwid_matched"] = hwid_verified
    if (
        probe_install
        and cand
        and (out.get("source") or "").lower() in ("vendor", "oem", "ssd_vendor")
        and not _offer_has_installable_package(out)
    ):
        out = _probe_offer_install_path(out)
    vs, note = compare_driver_to_installed(
        inst,
        cand or "",
        installed_date=inst_date,
        candidate_date=(out.get("date") or "").strip(),
        candidate_windows_version=(out.get("windows_display_version") or "").strip(),
        wu_offered=bool(out.get("wu_offered")),
        source=(out.get("source") or "").lower(),
        hwid_verified=hwid_verified,
        device_ctx=device_ctx,
    )
    if (
        device_ctx
        and vs == "older"
        and (out.get("source") or "").lower() == "oem"
        and (
            _ctx_is_wifi_radio_device(device_ctx)
            or _ctx_is_bluetooth_radio_device(device_ctx)
        )
        and _reject_oem_radio_wifi_bt_cross_mismatch(
            (out.get("title") or "").lower(), device_ctx
        )
        is None
    ):
        out["reference_older_oem"] = True
        note = _append_compare_note(
            note,
            "Installed driver is newer than this OEM package — shown for reference.",
        )
    vs, note = _apply_update_reporting_policy(
        out,
        vs,
        note,
        device_ctx=device_ctx,
    )
    eff_note = (out.get("effective_version_note") or "").strip()
    if eff_note:
        note = _append_compare_note(note, eff_note)
    note = _append_oem_bundle_component_note(out, vs, note, device_ctx=device_ctx)
    out["vs_installed"] = vs
    out["compare_note"] = note
    out["installability_rank"] = _offer_installability_rank(out)
    out["installed_version"] = inst or "?"
    out["installed_date"] = inst_date
    if device_ctx:
        _soften_stale_realtek_wdm_oem_compare(out, device_ctx)
        if (
            _device_is_intel_chipset_plumbing(device_ctx)
            and not _ctx_is_intel_chipset_platform_row(device_ctx)
            and _offer_is_intel_chipset_inf(out)
        ):
            out["informational_only"] = True
            out["status_neutral"] = True
        if _ctx_is_amd_chipset_platform_row(device_ctx):
            cand_ver = (_dc("_offer_version_from_fields")(out) or out.get("version") or "").strip()
            if cand_ver and _looks_like_amd_adrenalin_version(cand_ver):
                out["informational_only"] = True
                out["status_neutral"] = True
            if (
                (out.get("source") or "").lower() == "vendor"
                and cand_ver
                and not _looks_like_amd_chipset_package_version(cand_ver)
            ):
                out["informational_only"] = True
                out["status_neutral"] = True
        if (out.get("source") or "").lower() == "microsoft":
            hw_note = _catalog_hwid_mismatch_note(out, device_ctx)
            if hw_note:
                out["compare_note"] = (
                    f"{note} {hw_note}".strip() if note else hw_note
                )
                if vs == "newer":
                    out["vs_installed"] = "uncertain"
    if not skip_dual_baseline_gate and (out.get("vs_installed") or "").lower() == "newer":
        out = _apply_dual_baseline_gate(out, inst, inst_date, device_ctx)
    if not out.get("bundle_components"):
        inner = out.get("inner_versions") or out.get("offer_inner_versions")
        if isinstance(inner, list) and inner:
            from bundle_verification import bundle_components_from_inner_versions

            out["bundle_components"] = bundle_components_from_inner_versions(inner)
    return out


def _alternate_installed_baselines(ctx: dict, primary: str) -> list[str]:
    """Other installed version strings worth trying when compare scheme differs."""
    baselines: list[str] = []
    vk = (ctx.get("vendor_key") or "").lower()
    label = _ctx_device_label(ctx)
    pnp = (ctx.get("pnp_class") or "").lower()
    if vk == "intel":
        if _ctx_is_intel_chipset_platform_row(ctx) or ctx.get("hw_category") == "chipset":
            suite = _load_intel_chipset_suite_installed_version()
            if suite:
                baselines.append(suite)
        if pnp in ("net", "bluetooth") or any(
            k in label for k in ("wi-fi", "wifi", "wireless", "wlan")
        ):
            wireless = _load_intel_wireless_installed_version()
            if wireless:
                baselines.append(wireless)
        if _device_is_intel_me_device(ctx):
            me = _load_intel_me_installed_version()
            if me:
                baselines.append(me)
    if vk == "nvidia" or "nvidia" in label or "geforce" in label:
        branch = _load_nvidia_branch_installed_version()
        if branch:
            baselines.append(branch)
    if vk == "amd" or "radeon" in label:
        adrenalin = _load_amd_adrenalin_installed_version()
        if adrenalin:
            baselines.append(adrenalin)
        chipset = _load_amd_chipset_suite_installed_version()
        if chipset and (_device_is_amd_chipset_plumbing(ctx) or ctx.get("hw_category") == "chipset"):
            baselines.append(chipset)
    if vk == "realtek" and (
        pnp == "net"
        or any(k in label for k in ("ethernet", "gbe", "2.5g"))
    ):
        nic_pkg = _load_realtek_ethernet_installed_version()
        if nic_pkg:
            baselines.append(nic_pkg)
    seen = {(primary or "").strip()}
    out: list[str] = []
    for ver in baselines:
        v = (ver or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _find_corroborating_offer(row: dict, pool: list[dict]) -> dict | None:
    """Another tier reporting the same version with stronger verification."""
    target_ver = (_dc("_offer_version_from_fields")(row) or "").strip()
    if not target_ver:
        return None
    best: dict | None = None
    best_tier = 99
    for other in pool:
        if other is row:
            continue
        over = (_dc("_offer_version_from_fields")(other) or "").strip()
        if over != target_ver:
            continue
        if (other.get("vs_installed") or "").lower() not in ("newer", "same"):
            continue
        if not (
            _offer_trusted_for_confident_newer(other)
            or _offer_has_installable_package(other)
        ):
            continue
        tier = offer_source_sort_tier(other.get("source"))
        if tier < best_tier:
            best_tier = tier
            best = other
    return best


def _inherit_verification_trust(row: dict, corroborator: dict) -> dict:
    """Copy install/HWID proof from a corroborating offer."""
    out = dict(row)
    for key in ("install_verified", "download_resolvable", "hwid_matched", "wu_offered"):
        if corroborator.get(key):
            out[key] = True
    src = (corroborator.get("source") or "").lower()
    if src == "microsoft" and corroborator.get("update_id"):
        if not out.get("update_id"):
            out["update_id"] = corroborator.get("update_id")
            out["download_kind"] = corroborator.get("download_kind") or "catalog"
    corr_url = (corroborator.get("url") or "").strip()
    if corr_url and _offer_has_installable_package(corroborator) and not _offer_has_installable_package(out):
        out["url"] = corr_url
        out["install_verified"] = True
    return out


def _try_resolve_uncertain_offer(
    row: dict,
    pool: list[dict],
    installed: str,
    installed_date: str,
    device_ctx: dict | None,
) -> dict:
    """Attempt to resolve uncertain → newer/same/older using extra verification signals."""
    if (row.get("vs_installed") or "").lower() != "uncertain":
        return row
    if row.get("informational_only") or row.get("status_neutral"):
        return row

    out = dict(row)
    inst = (installed or "").strip()
    cand = (_dc("_offer_version_from_fields")(out) or "").strip()

    if inst and cand:
        eq, eq_note = dvi.versions_equivalent(inst, cand, device_ctx=device_ctx)
        if eq:
            out["vs_installed"] = "same"
            out["compare_note"] = _append_compare_note(out.get("compare_note") or "", eq_note)
            out["verification_method"] = "version_identity"
            return out

    out = _recompare_offer_row(
        out,
        inst,
        installed_date,
        device_ctx=device_ctx,
        probe_install=True,
    )
    if (out.get("vs_installed") or "").lower() != "uncertain":
        out["verification_method"] = out.get("verification_method") or "install_probe"
        return out

    corroborator = _find_corroborating_offer(out, pool)
    if corroborator:
        merged = _inherit_verification_trust(out, corroborator)
        resolved = _recompare_offer_row(
            merged,
            inst,
            installed_date,
            device_ctx=device_ctx,
            probe_install=False,
        )
        if (resolved.get("vs_installed") or "").lower() in ("newer", "same"):
            label = corroborator.get("source_label") or corroborator.get("source") or "catalog"
            resolved["verification_method"] = "cross_source"
            resolved["compare_note"] = _append_compare_note(
                resolved.get("compare_note") or "",
                f"Corroborated by {label} (same version, verified package).",
            )
            return resolved
        out = resolved

    note_l = (out.get("compare_note") or "").lower()
    scheme_hint = any(
        k in note_l
        for k in (
            "suite vs component",
            "adrenalin",
            "branch vs internal",
            "version family",
            "numbering scheme",
            "proset",
            "realtek.com package",
        )
    )
    if scheme_hint and device_ctx:
        for alt_inst in _alternate_installed_baselines(device_ctx, inst):
            alt_row = _recompare_offer_row(
                dict(out),
                alt_inst,
                installed_date,
                device_ctx=device_ctx,
                probe_install=False,
            )
            if (alt_row.get("vs_installed") or "").lower() in ("newer", "same", "older"):
                alt_row["verification_method"] = "alternate_installed_baseline"
                alt_row["compare_note"] = _append_compare_note(
                    alt_row.get("compare_note") or "",
                    f"Resolved using alternate installed baseline ({alt_inst}).",
                )
                return _apply_dual_baseline_gate(
                    alt_row, inst, installed_date, device_ctx
                )

    return out




def _offer_has_installable_package(offer: dict) -> bool:
    """True when Install driver can fetch a real package (not just a web page)."""
    if offer.get("install_verified") or offer.get("download_resolvable"):
        return True
    kind = _dc("_offer_download_kind")(offer).lower()
    if kind in ("cab", "catalog", "package", "direct", "optional_updates", "uri"):
        return True
    if (offer.get("source") or "").lower() == "microsoft" and offer.get("update_id"):
        return True
    url = (offer.get("url") or "").strip()
    if not url:
        return False
    low = url.lower().split("?")[0]
    if any(low.endswith(ext) for ext in _DOWNLOAD_EXTENSIONS):
        return True
    if "downloadmirror.intel.com" in low:
        return True
    if "gfwsl.geforce.com" in low or "international.download.nvidia.com" in low:
        return True
    return False

__all__ = [
    "_alternate_installed_baselines",
    "_apply_dual_baseline_gate",
    "_apply_update_reporting_policy",
    "_find_corroborating_offer",
    "_inherit_verification_trust",
    "_microsoft_hwid_verified_for_row",
    "_offer_compare_version",
    "_offer_has_installable_package",
    "_offer_trusted_for_confident_newer",
    "_probe_offer_install_path",
    "_recompare_offer_row",
    "_scheme_split_device_for_dual_baseline",
    "_try_resolve_uncertain_offer",
]
