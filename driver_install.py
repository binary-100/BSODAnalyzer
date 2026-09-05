"""
User-initiated driver installation helpers.

Nothing here runs automatically — the GUI must confirm before calling these functions.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

try:
    from bsod_runtime import run_powershell
except ImportError:
    run_powershell = None  # type: ignore[assignment,misc]

_INSTALLABLE_EXTENSIONS = (".inf", ".cab", ".zip", ".msu", ".7z")
_VENDOR_INSTALLER_EXTENSIONS = (".exe", ".msi")
_VENDOR_SETUP_NAMES = ("setup.exe", "install.exe", "inst.exe", "installer.exe")
SEVEN_ZIP_REQUIRED = "SEVEN_ZIP_REQUIRED"
_PROGRESS = Callable[[str], None] | None


def _emit(progress_cb: _PROGRESS, message: str) -> None:
    if progress_cb:
        progress_cb(message)


def is_vendor_installer_path(path: str) -> bool:
    low = (path or "").lower()
    return any(low.endswith(ext) for ext in _VENDOR_INSTALLER_EXTENSIONS)


def package_needs_seven_zip(path_or_url: str) -> bool:
    try:
        import bsod_runtime as rt
    except ImportError:
        return (path_or_url or "").lower().split("?")[0].endswith(".7z")
    return rt.package_may_need_seven_zip(path_or_url)


def offer_needs_seven_zip(offer: dict) -> bool:
    for key in ("downloaded_path", "local_package_path", "url"):
        val = (offer.get(key) or "").strip()
        if val and package_needs_seven_zip(val):
            return True
    return False


def seven_zip_required_message() -> str:
    return (
        "This driver package uses the .7z archive format.\n\n"
        "BSOD Analyzer opens .7z files with 7-Zip — a free, widely used compression "
        "tool from 7-zip.org (similar to built-in .zip support, but for a format "
        "some AMD, Intel, and OEM driver packages use).\n\n"
        "We do not bundle or modify 7-Zip. Install it once from the official site, "
        "then restart BSOD Analyzer and try Install driver again."
    )


def bundle_component_extract_failed_message(
    *,
    device_name: str = "",
    vendor_label: str = "",
) -> str:
    vendor = (vendor_label or "The vendor").strip()
    device = (device_name or "this device").strip()
    return (
        f"{vendor} packaged multiple drivers together and the component for "
        f"{device} could not be extracted with the tools available to BSOD Analyzer.\n\n"
        "Do not run the full bundle installer from this row — it may update (or "
        "downgrade) other drivers in the same package and leave the system less "
        "consistent overall.\n\n"
        "Open the vendor download page or use the manufacturer’s own installer if "
        "you need the complete package."
    )


def bundle_no_matching_inf_message(*, device_name: str = "", instance_id: str = "") -> str:
    device = (device_name or "the selected device").strip()
    extra = ""
    if instance_id:
        extra = f"\nHardware ID: {instance_id}"
    return (
        f"The package was extracted but no driver INF matched {device}.{extra}\n\n"
        "Do not install the full bundle from this row — other components in the "
        "same package may be older than what you already have."
    )


def _should_use_component_install(
    offer: dict | None,
    device_ctx: dict | None,
    *,
    package_path: str = "",
) -> bool:
    """True when install should target one bundle component, not the full package."""
    if not device_ctx:
        return False
    path = (package_path or "").strip()
    if path and is_vendor_installer_path(path):
        return True
    if (device_ctx.get("catalog_role") or "") == "gpu_companion":
        return True
    offer = offer or {}
    if offer.get("inner_versions") or offer.get("offer_effective_version"):
        return True
    if offer.get("bundle_components"):
        try:
            from catalog_device_context import _device_is_chipset_plumbing

            if _device_is_chipset_plumbing(device_ctx):
                return True
        except ImportError:
            pass
    return False


def component_install_confirm_note(
    offer: dict,
    device_ctx: dict | None,
    *,
    package_path: str = "",
) -> str:
    """Extra install-dialog copy when the pipeline targets one bundle component."""
    if not device_ctx:
        return ""
    path = (
        package_path
        or (offer.get("downloaded_path") or offer.get("local_package_path") or "")
    ).strip()
    use_component = _should_use_component_install(offer, device_ctx, package_path=path)
    if not use_component:
        return ""
    role = (device_ctx.get("catalog_role") or "").lower()
    if role == "gpu_companion" or offer.get("inner_versions") or offer.get("bundle_components"):
        return (
            "\n\nComponent-only install: BSOD Analyzer extracts and installs the driver "
            "for this device only — not the full multi-driver vendor bundle."
        )
    return (
        "\n\nComponent-only install: only the matching component from this package "
        "will be installed."
    )


def component_install_version_gate(
    offer: dict,
    device_ctx: dict | None,
    *,
    installed_version: str = "",
) -> tuple[bool, str]:
    """
    Per-component downgrade gate for multi-driver bundles.

    Compares the effective inner version for *this* device against *this* device's
    installed version — not the bundle wrapper or unrelated components (NPCF vs display,
    chipset INF vs suite headline, etc.).
    """
    if not device_ctx:
        return True, ""
    inst = (
        (installed_version or "").strip()
        or (offer.get("installed_version") or "").strip()
        or (device_ctx.get("primary_version") or "").strip()
    )
    if not inst or inst in ("?", "—", "N/A", "n/a"):
        return True, ""
    try:
        import oem_effective_version as oev
        from catalog_scoring import compare_versions
    except ImportError:
        return True, ""

    eff, _method, _note = oev.resolve_offer_effective_version(offer, device_ctx)
    cand = (
        eff
        or (offer.get("offer_effective_version") or offer.get("version") or "").strip()
    )
    if not cand:
        return True, ""
    if compare_versions(inst, cand) == "older":
        device = (
            device_ctx.get("target_device_name")
            or device_ctx.get("device_label")
            or "this device"
        )
        return False, (
            f"Installed driver on {device} ({inst}) is already newer than the "
            f"component in this package ({cand}).\n\n"
            "Component-only install was blocked to avoid a downgrade. Other parts of "
            "the same bundle may still be older — do not run the full vendor installer."
        )
    return True, ""


def needs_seven_zip_but_missing(offer: dict | None = None, path: str = "") -> bool:
    if not offer_needs_seven_zip(offer or {}) and not (
        path and package_needs_seven_zip(path)
    ):
        return False
    try:
        import bsod_runtime as rt
    except ImportError:
        return True
    return not rt.seven_zip_available()


def classify_driver_install_outcome(install_msg: str) -> str:
    """Classify pnputil/vendor install text for post-install verification."""
    low = (install_msg or "").lower()
    if "not a better match" in low or "already the best driver" in low:
        return "windows_kept_driver"
    if "reboot" in low and ("installed" in low or "success" in low):
        return "reboot_required"
    if "installed successfully" in low or "driver package staged" in low:
        return "staged"
    if "opened the vendor installer" in low or "vendor installer" in low:
        return "vendor_wizard"
    if "fail" in low or "error" in low:
        return "failed"
    return "unknown"


def offer_install_capability(offer: dict) -> tuple[bool, str]:
    """Return (can_install, short_reason). Firmware rows should never pass install."""
    if (offer.get("kind") or "") in ("bios", "ssd", "firmware"):
        return False, "BIOS and SSD firmware cannot be installed from this app."

    kind = (offer.get("download_kind") or offer.get("install_kind") or "url").strip()
    update_id = (offer.get("update_id") or "").strip()
    path = (offer.get("downloaded_path") or offer.get("local_package_path") or "").strip()
    url = (offer.get("url") or "").strip()
    title = (offer.get("title") or "").strip()
    vs = (offer.get("vs_installed") or "").lower()
    src = (offer.get("source") or "").lower()

    if src == "utility":
        return (
            False,
            "This row is a detection or support tool, not an installable driver package. "
            "Use Download to open the vendor page.",
        )

    if src == "microsoft":
        if vs in ("same", "older"):
            return False, "Installed driver is already at or above this catalog package."
        if vs == "uncertain" and not offer.get("hwid_matched"):
            return (
                False,
                "Hardware ID not confirmed for this device — use Open in Update Catalog "
                "to check Package Details first.",
            )

    if path:
        if is_vendor_installer_path(path):
            return True, "Launch the vendor installer (you complete the setup wizard)."
        if path.lower().endswith(_INSTALLABLE_EXTENSIONS) or os.path.isdir(path):
            return True, "Install from downloaded package (requires Administrator)."

    if update_id and offer.get("source") == "microsoft":
        if vs == "uncertain" and not offer.get("hwid_matched"):
            return (
                False,
                "Hardware ID not confirmed for this device — use Open in Update Catalog "
                "to check Package Details first.",
            )
        return True, "Download (if needed) and install via Windows Update (Administrator)."

    if kind == "catalog" or (kind == "url" and "catalog.update.microsoft.com" in url.lower()):
        if title or update_id:
            return True, "Download from Microsoft Update Catalog, then install."
        return False, "No catalog package title to download."

    if kind in ("optional_updates", "uri"):
        if update_id:
            return True, "Install via Windows Update (requires Administrator)."
        return False, "Open Windows Update in Settings — no local package ID for automatic install."

    if kind == "url" and url:
        low = url.lower().split("?")[0]
        if any(low.endswith(ext) for ext in _INSTALLABLE_EXTENSIONS + _VENDOR_INSTALLER_EXTENSIONS):
            return True, "Download the package, then install or launch the vendor setup."
        if low.endswith(".7z"):
            return True, "Download the .7z package (requires 7-Zip to extract), then install."
        if low.startswith("ms-"):
            return False, "Open Windows Update in Settings for this package."
        return True, "Download from the vendor, then install or launch the setup program."

    return False, "No installable package for this row — run Search for updates first."


def launch_vendor_installer(path: str) -> tuple[bool, str]:
    """Open a vendor .exe/.msi for the user to complete (never silent)."""
    package = os.path.abspath(path)
    if not os.path.isfile(package):
        return False, f"Installer not found: {package}"
    if not is_vendor_installer_path(package):
        return False, "Not a vendor installer (.exe/.msi)."
    try:
        if sys.platform == "win32":
            os.startfile(package)  # type: ignore[attr-defined]
        else:
            subprocess.Popen([package], close_fds=True)
    except OSError as exc:
        return False, f"Could not open installer: {exc}"
    return (
        True,
        "Opened the vendor installer.",
    )


def _extract_if_zip(archive: str, dest_dir: str) -> str:
    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(dest_dir)
    return dest_dir


_GENERIC_BUS_TOKENS = frozenset({
    "ACPI", "USB", "PCI", "HID", "ROOT", "SWD", "BTH", "SCSI", "HDAUDIO", "SW",
})


def _filter_hwid_tokens(tokens: list[str]) -> list[str]:
    """Drop bus-only and overly short tokens that cause false INF matches."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in tokens:
        tok = (raw or "").strip().upper()
        if not tok or tok in seen:
            continue
        parts = [p for p in tok.split("\\") if p]
        if len(parts) == 1 and parts[0] in _GENERIC_BUS_TOKENS:
            continue
        if len(tok) < 8 and "VEN_" not in tok and "DEV_" not in tok:
            continue
        seen.add(tok)
        out.append(tok)
    out.sort(key=len, reverse=True)
    return out


def _inf_hwid_match_score(inf_text: str, tokens: list[str]) -> int:
    """Higher = better HWID match (prefer full HWID lines over substring noise)."""
    if not tokens:
        return 0
    upper = inf_text.upper()
    best = 0
    for tok in tokens:
        if tok not in upper:
            continue
        score = len(tok) * 10
        # HWID assignment lines: ", ACPI\\NVDA0820" or "= ACPI\\NVDA0820"
        if f", {tok}" in upper or f"= {tok}" in upper or f",{tok}" in upper:
            score += 500
        # Penalize substring hits inside unrelated identifiers (e.g. RmDisableACPI)
        if len(tok) <= 8 and f", {tok}" not in upper and f"= {tok}" not in upper:
            score -= 200
        best = max(best, score)
    return best


def find_inf_dirs_for_hwid_tokens(root: str, hwid_tokens: list[str]) -> list[str]:
    """
    Return .inf directories whose contents mention HWID tokens (e.g. ACPI\\NVDA0820).

    Locates one component inside a multi-driver OEM/chipset extract for targeted pnputil.
    Directories are ordered by match strength (most specific HWID first), then depth.
    """
    tokens = _filter_hwid_tokens(hwid_tokens)
    if not root or not tokens:
        return []
    root_path = Path(root)
    if not root_path.exists():
        return []
    hits: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for dirpath, _dirs, files in os.walk(root_path):
        infs = [f for f in files if f.lower().endswith(".inf")]
        if not infs:
            continue
        best_score = 0
        for inf_name in infs:
            inf_path = Path(dirpath) / inf_name
            try:
                text = inf_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            best_score = max(best_score, _inf_hwid_match_score(text, tokens))
        if best_score <= 0:
            continue
        norm = str(Path(dirpath).resolve())
        if norm in seen:
            continue
        seen.add(norm)
        depth = dirpath.replace(str(root_path), "").count(os.sep)
        hits.append((best_score, depth, norm))
    hits.sort(key=lambda x: (-x[0], x[1]))
    return [path for _score, _depth, path in hits]


def _find_vendor_setup_exe(root: str) -> str | None:
    """Find a vendor Setup/Install.exe in an extracted package (prefer shallowest)."""
    root_path = Path(root)
    if not root_path.exists():
        return None
    candidates: list[tuple[int, str]] = []
    for dirpath, _dirs, files in os.walk(root_path):
        depth = dirpath.replace(str(root_path), "").count(os.sep)
        for name in files:
            if name.lower() in _VENDOR_SETUP_NAMES:
                candidates.append((depth, os.path.join(dirpath, name)))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _subprocess_no_window() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _expand_cab_star(cab_path: str, dest_dir: str) -> tuple[bool, str]:
    """Extract all files from a .cab (expand.exe -F:*)."""
    os.makedirs(dest_dir, exist_ok=True)
    proc = subprocess.run(
        ["expand.exe", "-F:*", os.path.abspath(cab_path), dest_dir],
        capture_output=True,
        text=True,
        timeout=180,
        creationflags=_subprocess_no_window(),
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "expand.exe -F:* failed").strip()
        return False, msg[:500]
    return True, ""


def _expand_cab_legacy(cab_path: str, dest_dir: str) -> tuple[bool, str]:
    """Older expand.exe syntax (single-file / legacy cabinets)."""
    os.makedirs(dest_dir, exist_ok=True)
    proc = subprocess.run(
        ["expand.exe", os.path.abspath(cab_path), dest_dir],
        capture_output=True,
        text=True,
        timeout=180,
        creationflags=_subprocess_no_window(),
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "expand.exe failed").strip()
        return False, msg[:500]
    return True, ""


def _expand_cab_tar(cab_path: str, dest_dir: str) -> tuple[bool, str]:
    """Windows tar can extract some cabinet layouts (Win10+)."""
    os.makedirs(dest_dir, exist_ok=True)
    proc = subprocess.run(
        ["tar", "-xf", os.path.abspath(cab_path), "-C", dest_dir],
        capture_output=True,
        text=True,
        timeout=180,
        creationflags=_subprocess_no_window(),
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "tar -xf failed").strip()
        return False, msg[:500]
    return True, ""


def _expand_cab_all(cab_path: str, dest_dir: str) -> tuple[bool, str]:
    """Try every supported .cab extraction path (broad driver-package compatibility)."""
    last_err = ""
    for expand_fn in (_expand_cab_star, _expand_cab_legacy, _expand_cab_tar):
        ok, err = expand_fn(cab_path, dest_dir)
        if ok and _find_inf_dir(dest_dir):
            return True, ""
        if ok:
            return True, ""
        last_err = err or last_err
    return False, last_err or "Could not expand .cab with any supported method."


def _extract_zip_powershell(archive: str, dest_dir: str) -> tuple[bool, str]:
    if run_powershell is None:
        return False, "PowerShell not available."
    os.makedirs(dest_dir, exist_ok=True)
    arc_esc = archive.replace("'", "''")
    out_esc = dest_dir.replace("'", "''")
    ps = rf"""
$ErrorActionPreference = 'Stop'
Expand-Archive -Path '{arc_esc}' -DestinationPath '{out_esc}' -Force
"ok"
"""
    ok, out = run_powershell(ps, timeout=180)
    if not ok:
        return False, (out or "Expand-Archive failed")[:500]
    return True, ""


def _extract_zip_all(archive: str, dest_dir: str) -> tuple[bool, str]:
    """Python zipfile first, then PowerShell Expand-Archive."""
    try:
        _extract_if_zip(archive, dest_dir)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        last_err = str(exc)
    ok, err = _extract_zip_powershell(archive, dest_dir)
    if ok:
        return True, ""
    return False, err or last_err


def _extract_7z(archive: str, dest_dir: str) -> tuple[bool, str]:
    try:
        import bsod_runtime as rt
    except ImportError:
        return False, SEVEN_ZIP_REQUIRED
    exe = rt.seven_zip_exe()
    if not exe:
        return False, SEVEN_ZIP_REQUIRED
    os.makedirs(dest_dir, exist_ok=True)
    proc = subprocess.run(
        [exe, "x", os.path.abspath(archive), f"-o{dest_dir}", "-y"],
        capture_output=True,
        text=True,
        timeout=240,
        creationflags=_subprocess_no_window(),
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "7-Zip extract failed").strip()
        return False, msg[:500]
    return True, ""


def _targets_from_extracted_tree(work: str) -> tuple[bool, str, list[tuple[str, bool]]]:
    inf_dir = _find_inf_dir(work)
    if inf_dir:
        return True, "", [(inf_dir, True)]
    setup = _find_vendor_setup_exe(work)
    if setup:
        return True, "", [(setup, False)]
    return False, "Archive has no .inf driver package or Setup/Install.exe.", []


def _find_inf_dir(root: str) -> str | None:
    """Return a directory containing at least one .inf (prefer shallowest)."""
    root_path = Path(root)
    if root_path.is_file() and root_path.suffix.lower() == ".inf":
        return str(root_path.parent)
    candidates: list[tuple[int, str]] = []
    for dirpath, _dirs, files in os.walk(root_path):
        infs = [f for f in files if f.lower().endswith(".inf")]
        if infs:
            depth = dirpath.replace(str(root_path), "").count(os.sep)
            candidates.append((depth, dirpath))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _hwid_tokens_from_device_ctx(device_ctx: dict | None) -> list[str]:
    if not device_ctx:
        return []
    tokens: list[str] = []
    inst = (device_ctx.get("instance_id") or "").strip().upper()
    if inst:
        tokens.append(inst)
        parts = inst.split("\\")
        for end in range(len(parts), 0, -1):
            tokens.append("\\".join(parts[:end]))
    for raw in device_ctx.get("pci_tokens") or []:
        tok = str(raw or "").strip().upper()
        if tok:
            tokens.append(tok)
    out: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return _filter_hwid_tokens(out)


def _extract_dell_dup_exe(exe_path: str, dest_dir: str) -> tuple[bool, str]:
    """
    Dell Update Package silent extract when 7-Zip cannot open the self-extractor.

    Tries common DUP flags (/passthrough, /S /E=) — non-interactive, no full wizard.
    """
    package = os.path.abspath(exe_path)
    if not os.path.isfile(package):
        return False, f"Installer not found: {package}"
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.abspath(dest_dir)
    attempts: list[list[str]] = [
        ["/passthrough", "/v/qn", f"EXTRACTDIR={dest}"],
        ["/S", f"/E={dest}"],
        ["/s", f"/e={dest}"],
    ]
    last_err = ""
    for args in attempts:
        proc = subprocess.run(
            [package, *args],
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=_subprocess_no_window(),
        )
        if proc.returncode == 0 and (_find_inf_dir(dest) or _find_vendor_setup_exe(dest)):
            return True, ""
        last_err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:500]
    return False, last_err or "Dell DUP silent extract did not produce driver files."


def _extract_archive_to_work(path: str, work: str) -> tuple[bool, str]:
    low = path.lower()
    if low.endswith(".zip"):
        return _extract_zip_all(path, work)
    if low.endswith(".7z"):
        return _extract_7z(path, work)
    if low.endswith(".exe"):
        ok, err = _extract_7z(path, work)
        if ok:
            return True, ""
        ok_dup, err_dup = _extract_dell_dup_exe(path, work)
        if ok_dup:
            return True, ""
        if err == SEVEN_ZIP_REQUIRED:
            ok_dup2, err_dup2 = _extract_dell_dup_exe(path, work)
            if ok_dup2:
                return True, ""
            return False, err_dup2 or seven_zip_required_message()
        return False, err_dup or err or "Could not extract vendor installer."
    return False, "Unsupported archive for extraction."


def _collect_component_pnputil_targets(
    package_path: str,
    device_ctx: dict,
    offer: dict | None = None,
) -> tuple[bool, str, list[tuple[str, bool]]]:
    """Extract a bundle and locate INF folder(s) for one target device."""
    path = os.path.abspath(package_path)
    if not os.path.isfile(path):
        return False, f"Path not found: {path}", []
    low = path.lower()
    if not low.endswith((".exe", ".zip", ".7z", ".cab")):
        vendor = (device_ctx.get("vendor_key") or "oem").strip()
        return (
            False,
            bundle_component_extract_failed_message(
                device_name=(
                    device_ctx.get("target_device_name")
                    or device_ctx.get("device_label")
                    or ""
                ),
                vendor_label=vendor,
            ),
            [],
        )

    work = tempfile.mkdtemp(prefix="bsod_component_")
    try:
        if low.endswith(".cab"):
            ok, err = _expand_cab_all(path, work)
        else:
            ok, err = _extract_archive_to_work(path, work)
        if not ok:
            if err == SEVEN_ZIP_REQUIRED:
                return False, seven_zip_required_message(), []
            vendor = (device_ctx.get("vendor_key") or "oem").strip()
            return (
                False,
                bundle_component_extract_failed_message(
                    device_name=(
                        device_ctx.get("target_device_name")
                        or device_ctx.get("device_label")
                        or ""
                    ),
                    vendor_label=vendor,
                ),
                [],
            )
        try:
            import bundle_selective_install as bsi

            manifest_dirs = bsi.find_manifest_guided_inf_dirs(work, device_ctx, offer)
        except ImportError:
            manifest_dirs = []
        if manifest_dirs:
            return True, "", [(d, False) for d in manifest_dirs[:3]]
        tokens = _hwid_tokens_from_device_ctx(device_ctx)
        inf_dirs = find_inf_dirs_for_hwid_tokens(work, tokens)
        if not inf_dirs:
            return (
                False,
                bundle_no_matching_inf_message(
                    device_name=(
                        device_ctx.get("target_device_name")
                        or device_ctx.get("device_label")
                        or ""
                    ),
                    instance_id=(device_ctx.get("instance_id") or ""),
                ),
                [],
            )
        return True, "", [(d, False) for d in inf_dirs[:3]]
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def _collect_pnputil_targets(
    package_path: str,
    device_ctx: dict | None = None,
    offer: dict | None = None,
) -> tuple[bool, str, list[tuple[str, bool]]]:
    """Return install targets as (path, use_subdirs) — tried in order until one succeeds."""
    if device_ctx and _should_use_component_install(offer, device_ctx, package_path=package_path):
        ok_c, err_c, targets_c = _collect_component_pnputil_targets(
            package_path, device_ctx, offer=offer
        )
        if targets_c:
            return ok_c, err_c, targets_c
        device_name = (
            device_ctx.get("target_device_name")
            or device_ctx.get("device_label")
            or ""
        )
        return (
            False,
            err_c
            or bundle_no_matching_inf_message(
                device_name=device_name,
                instance_id=(device_ctx.get("instance_id") or ""),
            ),
            [],
        )

    path = os.path.abspath(package_path)
    if not os.path.exists(path):
        return False, f"Path not found: {path}", []

    if os.path.isdir(path):
        inf_dir = _find_inf_dir(path)
        if not inf_dir:
            return False, "No .inf files found in that folder.", []
        return True, "", [(inf_dir, True)]

    low = path.lower()
    if low.endswith(".inf"):
        return True, "", [(str(Path(path).parent), True)]

    if low.endswith(".cab"):
        targets: list[tuple[str, bool]] = []
        work = tempfile.mkdtemp(prefix="bsod_cab_")
        ok_exp, err = _expand_cab_all(path, work)
        if ok_exp:
            inf_dir = _find_inf_dir(work)
            if inf_dir:
                targets.append((inf_dir, True))
        targets.append((path, False))
        if len(targets) == 1 and not ok_exp:
            shutil.rmtree(work, ignore_errors=True)
            return False, err or "Could not expand .cab", []
        return True, "", targets

    if low.endswith(".zip"):
        work = tempfile.mkdtemp(prefix="bsod_zip_")
        ok, err = _extract_zip_all(path, work)
        if not ok:
            shutil.rmtree(work, ignore_errors=True)
            return False, err or "Could not extract .zip", []
        ok_t, err_t, targets = _targets_from_extracted_tree(work)
        if not ok_t:
            shutil.rmtree(work, ignore_errors=True)
        return ok_t, err_t, targets

    if low.endswith(".7z"):
        work = tempfile.mkdtemp(prefix="bsod_7z_")
        ok, err = _extract_7z(path, work)
        if not ok:
            shutil.rmtree(work, ignore_errors=True)
            if err == SEVEN_ZIP_REQUIRED:
                return False, seven_zip_required_message(), []
            return False, err or "Could not extract .7z", []
        ok_t, err_t, targets = _targets_from_extracted_tree(work)
        if not ok_t:
            shutil.rmtree(work, ignore_errors=True)
        return ok_t, err_t, targets

    if low.endswith(".msu"):
        work = tempfile.mkdtemp(prefix="bsod_msu_")
        try:
            if run_powershell is None:
                return False, "PowerShell not available.", []
            msu_esc = path.replace("'", "''")
            work_esc = work.replace("'", "''")
            ps = rf"""
$ErrorActionPreference = 'Stop'
& expand.exe -F:* '{msu_esc}' '{work_esc}' | Out-Null
$cab = Get-ChildItem -Path '{work_esc}' -Filter *.cab -Recurse -File |
  Sort-Object Length -Descending |
  Select-Object -First 1
if (-not $cab) {{ throw 'No .cab found inside .msu package.' }}
$cabDir = Join-Path '{work_esc}' 'cab'
New-Item -ItemType Directory -Path $cabDir -Force | Out-Null
& expand.exe -F:* $cab.FullName $cabDir | Out-Null
"ok"
"""
            ok, out = run_powershell(ps, timeout=240)
            if not ok:
                shutil.rmtree(work, ignore_errors=True)
                return False, out or "Could not expand .msu package.", []
            inf_dir = _find_inf_dir(work)
            if not inf_dir:
                shutil.rmtree(work, ignore_errors=True)
                return False, "Expanded .msu but no .inf driver package was found.", []
            return True, "", [(inf_dir, True)]
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(work, ignore_errors=True)
            return False, str(e), []

    return False, "Unsupported file type. Use a folder, .inf, .cab, .zip, .7z, or .msu.", []


def _run_pnputil_once(target: str, *, subdirs: bool) -> tuple[bool, str]:
    if run_powershell is None:
        return False, "PowerShell not available."
    target_esc = target.replace("'", "''")
    if subdirs:
        args = f"/add-driver '{target_esc}' /subdirs /install"
    else:
        args = f"/add-driver '{target_esc}' /install"
    ps = rf"""
$ErrorActionPreference = 'Stop'
$out = & pnputil {args} 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {{ throw $out }}
$out
"""
    ok, out = run_powershell(ps, timeout=300)
    text = (out or "").strip()
    if ok:
        outcome = classify_driver_install_outcome(text)
        if outcome == "windows_kept_driver":
            return True, (
                f"{text}\n\nWindows kept the current driver (not a better match)."
            )
        return True, text or "Driver package staged with pnputil."
    return False, out or "pnputil failed (try Run as administrator)."


def install_driver_via_pnputil(
    package_path: str,
    device_ctx: dict | None = None,
    offer: dict | None = None,
) -> tuple[bool, str]:
    """Stage driver with pnputil /add-driver /install (Administrator)."""
    ok, err, targets = _collect_pnputil_targets(
        package_path, device_ctx=device_ctx, offer=offer
    )
    if not ok or not targets:
        return False, err or "No install target."
    errors: list[str] = []
    for idx, (target, subdirs) in enumerate(targets):
        if is_vendor_installer_path(target):
            ok_v, msg_v = launch_vendor_installer(target)
            if ok_v:
                if "setup.exe" in target.lower() or "install.exe" in target.lower():
                    msg_v = (
                        "Opened the vendor installer (Setup/Install.exe from the "
                        f"downloaded package).\n\n{msg_v}"
                    )
                if idx > 0 and errors:
                    msg_v = (
                        f"{msg_v}\n\n(Opened Setup.exe from extracted package — "
                        f"fallback method {idx + 1} of {len(targets)}.)"
                    )
                return True, msg_v
            errors.append(msg_v.strip())
            continue
        ok2, msg = _run_pnputil_once(target, subdirs=subdirs)
        if ok2:
            if idx > 0 and errors:
                msg = (
                    f"{msg}\n\n(Installed using fallback method {idx + 1} "
                    f"of {len(targets)}.)"
                )
            return True, msg
        errors.append(msg.strip())
    combined = errors[-1] if errors else "pnputil failed (try Run as administrator)."
    if len(errors) > 1:
        combined += f"\n\nAlso tried {len(errors) - 1} other install method(s)."
    return False, combined


def install_driver_via_windows_update(update_id: str) -> tuple[bool, str]:
    """Install one optional update by UpdateID via Windows Update COM (Administrator)."""
    if run_powershell is None:
        return False, "PowerShell not available."
    uid = (update_id or "").strip()
    if not uid:
        return False, "No Windows Update ID for this package."
    uid_esc = uid.replace("'", "''")
    ps = rf"""
$ErrorActionPreference = 'Stop'
$Session = New-Object -ComObject Microsoft.Update.Session
$Searcher = $Session.CreateUpdateSearcher()
$Result = $Searcher.Search("IsInstalled=0 and Type='Driver'")
$ToInstall = New-Object -ComObject Microsoft.Update.UpdateColl
foreach ($U in $Result.Updates) {{
  if ($U.Identity.UpdateID -eq '{uid_esc}') {{
    [void]$ToInstall.Add($U)
  }}
}}
if ($ToInstall.Count -eq 0) {{
  throw 'Update is not available locally. Download the catalog package first or open Optional updates in Settings.'
}}
$Installer = $Session.CreateUpdateInstaller()
$Installer.Updates = $ToInstall
$InstallResult = $Installer.Install()
if ($InstallResult.ResultCode -eq 2) {{
  'Installed successfully. A reboot may be required.'
}} elseif ($InstallResult.ResultCode -eq 3) {{
  'Installed with reboot required.'
}} else {{
  throw ('Install result code: ' + $InstallResult.ResultCode)
}}
"""
    ok, out = run_powershell(ps, timeout=600)
    if ok:
        return True, (out or "Windows Update install finished.").strip()
    return False, out or "Windows Update install failed (Administrator required)."


def _ensure_package_downloaded(
    offer: dict,
    *,
    progress_cb: _PROGRESS = None,
) -> tuple[bool, str, dict]:
    """Download package when needed. Returns (ok, message, updated_offer)."""
    import driver_catalog as drvcat

    offer = dict(offer or {})
    path = (offer.get("downloaded_path") or offer.get("local_package_path") or "").strip()
    if path and os.path.exists(path):
        return True, "", offer

    kind = (offer.get("download_kind") or offer.get("install_kind") or "url").strip()
    update_id = (offer.get("update_id") or "").strip()
    if update_id and offer.get("source") == "microsoft" and kind != "catalog":
        return True, "", offer

    _emit(progress_cb, "Downloading driver package…")
    ok, msg, downloaded = drvcat.download_driver_package_for_install(
        offer, progress_cb=progress_cb
    )
    if not ok:
        return False, msg, offer
    if downloaded:
        offer["downloaded_path"] = downloaded
    return True, msg, offer


def install_driver_offer(
    offer: dict,
    *,
    device_name: str = "",
    device_ctx: dict | None = None,
    progress_cb: _PROGRESS = None,
) -> tuple[bool, str, dict]:
    """
    Download (when needed) and install a driver package after explicit user confirmation.
    Never call without a prior confirmation dialog in the GUI.

    Returns (success, message, offer) — offer includes downloaded_path when a file was saved.
    """
    offer = dict(offer or {})
    can, reason = offer_install_capability(offer)
    if not can:
        return False, reason, offer

    ok_dl, dl_msg, offer = _ensure_package_downloaded(offer, progress_cb=progress_cb)
    if not ok_dl:
        return False, dl_msg, offer

    if needs_seven_zip_but_missing(offer):
        return False, seven_zip_required_message(), offer

    path = (offer.get("downloaded_path") or offer.get("local_package_path") or "").strip()
    update_id = (offer.get("update_id") or "").strip()
    suffix = f"\n\nDevice: {device_name}" if device_name else ""

    if path:
        use_component = _should_use_component_install(offer, device_ctx, package_path=path)
        if is_vendor_installer_path(path) and not use_component:
            _emit(progress_cb, "Opening vendor installer…")
            ok, msg = launch_vendor_installer(path)
            return ((True, msg + suffix, offer) if ok else (False, msg, offer))

        if use_component:
            ok_gate, gate_msg = component_install_version_gate(
                offer, device_ctx, installed_version=(offer.get("installed_version") or "")
            )
            if not ok_gate:
                return False, gate_msg, offer

        _emit(progress_cb, "Installing driver (this may take a minute)…")
        ok, msg = install_driver_via_pnputil(
            path,
            device_ctx=device_ctx if use_component else None,
            offer=offer if use_component else None,
        )
        return ((True, msg + suffix, offer) if ok else (False, msg, offer))

    if update_id and offer.get("source") == "microsoft":
        _emit(progress_cb, "Installing via Windows Update…")
        ok, msg = install_driver_via_windows_update(update_id)
        return ((True, msg + suffix, offer) if ok else (False, msg, offer))

    return False, dl_msg or "Could not download a driver package for this row.", offer
