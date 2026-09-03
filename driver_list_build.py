"""Off-thread unified driver/device list builder (Batch 5)."""

from __future__ import annotations

import bsod_crash_report as core
import bsod_hardware_wmi as hw_wmi
import bsod_workflow as wf
import driver_catalog as drvcat
import driver_index as drvidx

_DRV_INDEX_HINTS_MAX = 80


def _exclude_from_driver_device_list(dev: dict) -> bool:
    """Firmware-class PnP rows belong on the Firmware tab, not the driver list."""
    try:
        return drvcat.is_driver_scan_excluded_device(dev)
    except Exception:  # noqa: BLE001
        return False


def driver_watchlist_from_profile(prof: dict) -> list[dict]:
    """Merge generic-driver and problem devices into one deduped list."""
    gen = prof.get("devices_with_generic_driver") or []
    probs = prof.get("devices_with_driver_problems") or []
    by_name: dict[str, dict] = {}
    for d in gen:
        name = (d.get("name") or "").strip()
        if not name:
            continue
        row = dict(d)
        row["_reasons"] = ["Generic driver"]
        by_name[name] = row
    for d in probs:
        name = (d.get("name") or "").strip()
        if not name:
            continue
        if name in by_name:
            if "Driver problem" not in by_name[name]["_reasons"]:
                by_name[name]["_reasons"].append("Driver problem")
        else:
            row = dict(d)
            row["_reasons"] = ["Driver problem"]
            by_name[name] = row
    return sorted(by_name.values(), key=lambda x: (x.get("name") or "").lower())


def full_driver_rows(prof: dict) -> list[dict]:
    bio = prof.get("bios_driver_info") or {}
    return list(bio.get("all_drivers") or [])


def has_crash_analysis_context(
    last_model: dict | None, last_fmt_args: tuple | None
) -> bool:
    return wf.has_crash_analysis_context(last_model, last_fmt_args)


def platform_chipset_attention(
    model: dict | None,
    prof: dict | None,
    *,
    last_fmt_args: tuple | None = None,
) -> bool:
    """Crash logs point at BIOS/chipset/platform rather than a named .sys driver."""
    if not has_crash_analysis_context(model, last_fmt_args):
        return False
    m = model or {}
    ctx = (prof or {}).get("system_ctx") or m.get("system_ctx") or {}
    return core.platform_chipset_crash_attention(
        m.get("driver"),
        system_ctx=ctx,
        code_val=m.get("stop_code_val"),
        cause_type=m.get("cause_type"),
        fix_plan=m.get("fix_plan"),
        has_crash_context=True,
    )


def culprit_device_names(
    prof: dict,
    *,
    last_model: dict | None = None,
    last_fmt_args: tuple | None = None,
) -> set[str]:
    if not has_crash_analysis_context(last_model, last_fmt_args):
        return set()
    m = last_model or {}
    bio = (prof or {}).get("bios_driver_info") or m.get("bios_driver_info") or {}
    ctx = (prof or {}).get("system_ctx") or m.get("system_ctx") or {}
    resolved = core.resolve_crash_culprit_context(
        m.get("driver"),
        bio,
        code_val=m.get("stop_code_val"),
        system_ctx=ctx,
        cause_type=m.get("cause_type"),
        fix_plan=m.get("fix_plan"),
        has_crash_context=True,
    )
    return set(resolved["culprit_device_names"])


def driver_other_devices_from_profile(
    prof: dict,
    *,
    full_list: list[dict] | None = None,
) -> list[dict]:
    watch_names = {
        (d.get("name") or "").strip().lower()
        for d in driver_watchlist_from_profile(prof)
    }
    bio = prof.get("bios_driver_info") or {}
    if full_list is not None:
        rows_src = full_list
    else:
        rows_src = full_driver_rows(prof) or core.device_inventory_for_matching(bio)
    inv = core.device_inventory_for_matching(bio)
    devices: list[dict] = list(
        hw_wmi.chipset_driver_catalog_entries(
            prof.get("system_ctx") or {}, inventory=inv
        )
    )
    for d in rows_src:
        name = (d.get("name") or "").strip()
        if not name or name.lower() in watch_names:
            continue
        row = dict(d)
        row["_reasons"] = ["Installed driver"]
        devices.append(row)
    return sorted(
        devices,
        key=lambda x: (x.get("display_name") or x.get("name") or "").lower(),
    )


def driver_rows_for_cache(
    prof: dict,
    *,
    full: bool,
    last_model: dict | None = None,
    last_fmt_args: tuple | None = None,
) -> list[dict]:
    """Source rows for unified cache — lite mode skips full WMI list."""
    bio = prof.get("bios_driver_info") or {}
    all_rows = full_driver_rows(prof)
    if full or not all_rows:
        if all_rows:
            return list(all_rows)
        return driver_other_devices_from_profile(prof)
    keep: set[str] = set()
    for d in driver_watchlist_from_profile(prof):
        n = (d.get("name") or "").strip().lower()
        if n:
            keep.add(n)
    for n in culprit_device_names(
        prof, last_model=last_model, last_fmt_args=last_fmt_args
    ):
        if n:
            keep.add(n.lower())
    inv = core.device_inventory_for_matching(bio)
    lite_inv = list(
        bio.get("device_inventory") or bio.get("drivers") or inv
    )
    if not keep:
        return lite_inv
    out: list[dict] = []
    seen: set[str] = set()
    for rows in (inv, all_rows):
        for d in rows:
            name = (d.get("name") or "").strip()
            key = name.lower()
            if not key or key not in keep or key in seen:
                continue
            seen.add(key)
            out.append(d)
    return out or list(inv)


def _best_newer_package(offers: list | None) -> dict | None:
    for offer in offers or []:
        if (offer.get("vs_installed") or "").lower() == "newer":
            return offer
    return None


def _scan_metadata_from_entry(entry: dict, inventory: list | None = None) -> dict:
    offers = entry.get("offers") or []
    best = _best_newer_package(offers) or drvcat.best_versioned_offer(offers)
    status = entry.get("status") or "none"
    installed = (entry.get("installed_version") or "").strip()
    gap = entry.get("possible_coverage_gap")
    if gap is None:
        gap = drvcat.possible_coverage_gap(
            installed,
            offers,
            status=status,
            device_ctx=entry.get("context"),
        )
    avail_ver = ""
    avail_src = ""
    if best:
        avail_ver = (
            drvcat._offer_version_from_fields(best)
            or (best.get("version") or "")
        ).strip()
        if not avail_ver:
            avail_ver = (best.get("title") or "")[:48].strip()
        avail_src = (
            best.get("source_label") or best.get("source") or ""
        ).strip()
    elif offers and status not in ("newer", "same"):
        o0 = offers[0]
        avail_ver = (
            drvcat._offer_version_from_fields(o0)
            or (o0.get("version") or o0.get("title") or "")
        )[:48].strip()
        avail_src = (o0.get("source_label") or o0.get("source") or "").strip()
    meta = {
        "_check_status": status,
        "_scan_verified": True,
        "_available_version": avail_ver,
        "_available_source": avail_src,
        "_installed_at_scan": installed,
        "_possible_coverage_gap": bool(gap),
        "_none_reason": (entry.get("none_reason") or "").strip(),
    }
    dev_stub = {
        "device_class": entry.get("pnp_class") or entry.get("device_class") or "",
        "pnp_class": entry.get("pnp_class") or "",
        "vendor_key": entry.get("vendor_key") or "",
        "name": entry.get("device_name") or "",
        "version": installed,
        "_installed_at_scan": installed,
        "_available_version": avail_ver,
    }
    drvcat.attach_gpu_version_profile(dev_stub, offers=offers)
    if dev_stub.get("_gpu_version_profile"):
        meta["_gpu_version_profile"] = dev_stub["_gpu_version_profile"]
    drvcat.attach_intel_me_version_profile(dev_stub, offers=offers)
    if dev_stub.get("_intel_me_version_profile"):
        meta["_intel_me_version_profile"] = dev_stub["_intel_me_version_profile"]
    drvcat.attach_chipset_version_profile(dev_stub, offers=offers)
    if dev_stub.get("_chipset_version_profile"):
        meta["_chipset_version_profile"] = dev_stub["_chipset_version_profile"]
    drvcat.attach_chipset_platform_version_profile(dev_stub, offers=offers, inventory=inventory)
    if dev_stub.get("_chipset_platform_version_profile"):
        meta["_chipset_platform_version_profile"] = dev_stub["_chipset_platform_version_profile"]
    drvcat.attach_network_version_profile(dev_stub, offers=offers)
    if dev_stub.get("_network_version_profile"):
        meta["_network_version_profile"] = dev_stub["_network_version_profile"]
    return meta


def _attach_dual_version_profiles_to_devices(
    devices: list[dict],
    prof: dict,
    *,
    session_batch: dict | None = None,
) -> None:
    """Attach dual-version profiles (GPU, ME, chipset, Realtek, network) after merge."""
    bio = prof.get("bios_driver_info") or {}
    inv = core.device_inventory_for_matching(bio)
    batch_by_name = {
        (e.get("device_name") or ""): e
        for e in ((session_batch or {}).get("devices") or [])
    }
    for dev in devices:
        name = (dev.get("name") or "").strip()
        offers = (batch_by_name.get(name) or {}).get("offers")
        drvcat.attach_all_dual_version_profiles(dev, offers=offers, inventory=inv)


def _normalize_device_display_name(dev: dict) -> None:
    """Keep WDM codec friendly names when PnP enrichment picks a companion label."""
    name = (dev.get("name") or "").strip()
    display = (dev.get("display_name") or name).strip()
    ver = (dev.get("version") or "").strip()
    if (
        name
        and "realtek" in name.lower()
        and drvcat._looks_like_realtek_wdm_version(ver)
        and (
            "effects component" in display.lower()
            or "universal service" in display.lower()
        )
        and not any(
            k in name.lower()
            for k in ("effects component", "universal service", "asio")
        )
    ):
        dev["display_name"] = name


def expand_primary_catalog_device_names(
    selected: list[str],
    unified_cache: list[dict],
) -> list[str]:
    """Belt-and-suspenders: always queue primary GPU/NIC/audio/chipset for Search."""
    try:
        from bsod_hardware_wmi import CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
        CHIPSET_DEVICE_INTEL = "__chipset_intel_platform__"
    must: list[str] = []
    for dev in unified_cache:
        name = (dev.get("name") or "").strip()
        if not name:
            continue
        nl = name.lower()
        dc = (dev.get("device_class") or "").lower()
        ver = (dev.get("version") or "").strip()
        if name in (CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL):
            must.append(name)
        elif dc == "display" and any(k in nl for k in ("geforce", "radeon", "rtx", " rx")):
            must.append(name)
        elif dc == "net" and "realtek" in nl and "2.5" in nl:
            must.append(name)
        elif (
            "realtek" in nl
            and drvcat._looks_like_realtek_wdm_version(ver)
            and not any(k in nl for k in ("effects", "asio", "universal service"))
        ):
            must.append(name)
    out: list[str] = []
    seen: set[str] = set()
    for n in list(selected) + must:
        n = (n or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def inject_platform_chipset_devices(merged: dict[str, dict], prof: dict) -> None:
    """Always surface AMD/Intel chipset rows when platform context is known."""
    bio = prof.get("bios_driver_info") or {}
    inv = core.device_inventory_for_matching(bio)
    for d in hw_wmi.chipset_driver_catalog_entries(
        prof.get("system_ctx") or {}, inventory=inv
    ):
        name = (d.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        reason = "Platform (chipset)"
        if key in merged:
            row = merged[key]
            ver = (d.get("version") or "").strip()
            if ver and ver not in ("?", "—") and (row.get("version") or "?") in (
                "?",
                "—",
                "",
            ):
                row["version"] = ver
            if reason not in (row.get("_reasons") or []):
                row.setdefault("_reasons", []).append(reason)
            continue
        merged[key] = {
            **dict(d),
            "name": name,
            "display_name": d.get("display_name") or name,
            "_reasons": list(d.get("_reasons") or [reason]),
            "_check_status": "pending",
        }


def inject_crash_linked_devices(
    merged: dict[str, dict],
    prof: dict,
    *,
    last_model: dict | None = None,
    last_fmt_args: tuple | None = None,
    crash_driver: str | None = None,
) -> None:
    if not has_crash_analysis_context(last_model, last_fmt_args):
        return
    m = last_model or {}
    driver = crash_driver or m.get("driver") or ""

    if platform_chipset_attention(m, prof, last_fmt_args=last_fmt_args):
        bio = prof.get("bios_driver_info") or m.get("bios_driver_info") or {}
        inv = core.device_inventory_for_matching(bio)
        for d in hw_wmi.chipset_driver_catalog_entries(
            prof.get("system_ctx") or {}, inventory=inv
        ):
            name = (d.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            reason = "Crash logs — platform/chipset driver"
            if key in merged:
                merged[key]["_crash_linked"] = True
                merged[key]["_analysis_attention"] = True
                if reason not in (merged[key].get("_reasons") or []):
                    merged[key].setdefault("_reasons", []).insert(0, reason)
                ver = (d.get("version") or "").strip()
                if ver and ver not in ("?", "—"):
                    merged[key]["version"] = ver
            else:
                merged[key] = {
                    **dict(d),
                    "name": name,
                    "display_name": d.get("display_name") or name,
                    "_reasons": [reason],
                    "_crash_linked": True,
                    "_analysis_attention": True,
                    "_check_status": "pending",
                }
    elif core.has_crash_faulting_driver(driver):
        bio = (prof or {}).get("bios_driver_info") or m.get("bios_driver_info") or {}
        ctx = (prof or {}).get("system_ctx") or m.get("system_ctx") or {}
        resolved = core.resolve_crash_culprit_context(
            driver,
            bio,
            code_val=m.get("stop_code_val"),
            system_ctx=ctx,
            cause_type=m.get("cause_type"),
            fix_plan=m.get("fix_plan"),
            has_crash_context=True,
        )
        culprit_names = set(resolved["culprit_device_names"])
        for info in resolved["culprit_driver_info"]:
            name = (info.get("name") or "").strip()
            if core._culprit_info_row_is_placeholder(info):
                continue
            key = name.lower()
            if key in merged:
                merged[key]["_crash_linked"] = True
                merged[key]["_analysis_attention"] = True
                if f"Crash module: {driver}" not in (
                    merged[key].get("_reasons") or []
                ):
                    merged[key].setdefault("_reasons", []).insert(
                        0, f"Crash module: {driver}"
                    )
                continue
            merged[key] = {
                "name": name,
                "display_name": name,
                "version": (info.get("version") or "").strip() or "?",
                "date": info.get("date") or "",
                "device_class": (info.get("device_class") or "").strip(),
                "driver": driver,
                "_reasons": [f"Crash module: {driver}"],
                "_crash_linked": True,
                "_analysis_attention": True,
                "_check_status": "pending",
            }
        real = {
            k for k in culprit_names if not core.is_crash_synthetic_device_key(k)
        }
        if not real and not core.is_kernel_shim_fault_module(driver):
            synth = core.crash_synthetic_device_key(driver)
            key = synth.lower()
            if key not in merged:
                label = core._friendly_driver_label(driver)
                merged[key] = {
                    "name": synth,
                    "display_name": f"{label} (crash module)",
                    "version": "?",
                    "driver": driver,
                    "_reasons": [f"Crash module: {driver}"],
                    "_crash_linked": True,
                    "_analysis_attention": True,
                    "_crash_synthetic": True,
                    "_check_status": "pending",
                }
            else:
                merged[key]["_crash_synthetic"] = True
                merged[key]["_crash_linked"] = True
                merged[key]["_analysis_attention"] = True

        for raw_name in sorted(culprit_names):
            if core.is_crash_synthetic_device_key(raw_name):
                continue
            name = raw_name
            for row in core.device_inventory_for_matching(bio):
                rn = (row.get("name") or "").strip()
                if rn.lower() == raw_name:
                    name = rn
                    break
            key = name.lower()
            reason = f"Crash callout: {driver}" if driver else "Crash callout"
            if key in merged:
                merged[key]["_crash_linked"] = True
                if reason not in (merged[key].get("_reasons") or []):
                    merged[key].setdefault("_reasons", []).insert(0, reason)
            else:
                merged[key] = {
                    "name": name,
                    "display_name": name,
                    "version": "?",
                    "_reasons": [reason],
                    "_crash_linked": True,
                    "_check_status": "pending",
                }


def merge_session_batch_into_devices(
    devices: list[dict], session_batch: dict | None
) -> None:
    batch = session_batch or {}
    by_name = {
        (e.get("device_name") or ""): e for e in (batch.get("devices") or [])
    }
    for dev in devices:
        name = (dev.get("name") or "").strip()
        entry = by_name.get(name)
        if not entry:
            continue
        meta = _scan_metadata_from_entry(entry)
        dev.update(meta)
        if dev.get("_tier") == "culprit":
            continue
        if dev.get("_check_status") == "newer":
            dev["_tier"] = "outdated"
        elif dev.get("_tier") == "outdated":
            dev["_tier"] = "normal"


def build_unified_driver_list(
    prof: dict,
    *,
    full: bool,
    settings: dict,
    session_batch: dict | None,
    crash_driver: str | None,
    last_model: dict | None = None,
    last_fmt_args: tuple | None = None,
) -> list[dict]:
    """Merge devices with sort tier. Use full=False for fast crash-only views."""
    watch = driver_watchlist_from_profile(prof)
    watch_by_name = {(d.get("name") or "").strip().lower(): d for d in watch}
    rows_src = driver_rows_for_cache(
        prof, full=full, last_model=last_model, last_fmt_args=last_fmt_args
    )
    chipset = {
        (d.get("name") or "").strip().lower()
        for d in hw_wmi.chipset_driver_catalog_entries(prof.get("system_ctx") or {})
    }
    merged: dict[str, dict] = {}
    for d in watch:
        name = (d.get("name") or "").strip()
        if not name or _exclude_from_driver_device_list(d):
            continue
        row = dict(d)
        row["_check_status"] = row.get("_check_status", "pending")
        merged[name.lower()] = row
    for d in rows_src:
        name = (d.get("name") or "").strip()
        if not name or _exclude_from_driver_device_list(d):
            continue
        key = name.lower()
        if key in chipset:
            row = dict(d)
            row["_reasons"] = row.get("_reasons") or ["Platform (chipset)"]
        elif key in watch_by_name:
            row = dict(watch_by_name[key])
            for field in ("version", "date", "device_class", "driver", "manufacturer"):
                val = d.get(field)
                if val:
                    row[field] = val
            if not row.get("_reasons"):
                row["_reasons"] = ["Installed driver"]
        else:
            row = dict(d)
            row["_reasons"] = row.get("_reasons") or ["Installed driver"]
        row["_check_status"] = row.get("_check_status", "pending")
        merged[key] = row

    inject_platform_chipset_devices(merged, prof)
    inject_crash_linked_devices(
        merged,
        prof,
        last_model=last_model,
        last_fmt_args=last_fmt_args,
        crash_driver=crash_driver,
    )
    devices = [d for d in merged.values() if not _exclude_from_driver_device_list(d)]
    merge_session_batch_into_devices(devices, session_batch)
    if len(devices) <= _DRV_INDEX_HINTS_MAX:
        hint_targets = devices
    else:
        hint_names: set[str] = set()
        hint_targets = []
        for d in devices:
            if d.get("_crash_linked"):
                hint_targets.append(d)
                hint_names.add((d.get("name") or "").strip().lower())
        for d in devices:
            if len(hint_targets) >= _DRV_INDEX_HINTS_MAX:
                break
            n = (d.get("name") or "").strip().lower()
            if not n or n in hint_names:
                continue
            if d.get("_scan_verified"):
                hint_targets.append(d)
                hint_names.add(n)
    drvidx.apply_index_hints_to_devices(hint_targets, settings)
    drvidx.apply_index_packages_to_verified_devices(devices, settings)

    def tier(dev: dict) -> int:
        name = (dev.get("name") or "").strip().lower()
        if dev.get("_crash_linked"):
            return 0
        if dev.get("_scan_verified") and (dev.get("_check_status") or "") == "newer":
            return 1
        if (
            name in watch_by_name
            or "Generic" in (dev.get("_reasons") or [])
            or "problem" in " ".join(dev.get("_reasons") or []).lower()
        ):
            return 2
        return 3

    for dev in devices:
        t = tier(dev)
        dev["_tier"] = ("culprit", "outdated", "attention", "normal")[t]
        dev["_common_hw"] = hw_wmi.device_row_is_common_hardware(dev)
        try:
            import driver_catalog as dc
            dev["_driver_catalog_excluded"] = dc.is_driver_scan_excluded_device(dev)
        except ImportError:
            dev["_driver_catalog_excluded"] = False
        if "_scan_verified" not in dev:
            dev["_scan_verified"] = False
            dev["_check_status"] = dev.get("_check_status") or "pending"
        _normalize_device_display_name(dev)

    devices.sort(
        key=lambda x: (
            tier(x),
            (x.get("display_name") or x.get("name") or "").lower(),
        )
    )
    _attach_dual_version_profiles_to_devices(
        devices, prof, session_batch=session_batch
    )
    return devices
