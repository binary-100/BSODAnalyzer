"""Extract remaining catalog slices from driver_catalog.py (6.4.97–6.4.105)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
CATALOG = APP / "driver_catalog.py"

# Functions to extract per new module (order = removal order bottom-up safe).
SLICES: list[tuple[str, list[str], str, tuple[str, ...]]] = [
    (
        "catalog_device_comparison.py",
        [
            "catalog_device_source_path",
            "_is_primary_gpu_display_manufacturer_authoritative",
            "_manufacturer_catalog_tasks_for_ctx",
            "_run_catalog_source_tasks",
            "_microsoft_catalog_task",
            "_skipped_firmware_driver_comparison",
            "build_device_driver_comparison",
            "_build_device_comparison_from_ctx",
        ],
        '''"""Per-device catalog tier orchestration (extracted from driver_catalog)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable

from catalog_chipset_comparison import build_chipset_platform_comparison
from catalog_device_context import (
    _ctx_is_chipset_component_plumbing,
    _device_is_amd_chipset_plumbing,
    _nvidia_gpu_driver_lookup_applicable,
    get_device_context_for_name,
    is_driver_scan_excluded_ctx,
)
from catalog_mscatalog_session import _gui_catalog_mode, is_quick_check_mode
from catalog_offer_pipeline import _finalize_catalog_offers, _installed_driver_date_from_ctx
from catalog_tier_policy import (
    _ctx_gpu_or_network_catalog,
    _ctx_is_chipset_catalog,
    _manufacturer_gpu_lookup_uncertain,
    _should_skip_oem_after_manufacturer_tier,
    should_defer_microsoft_catalog,
)
from catalog_tier_policy import _NETWORK_VENDOR_KEYS


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


''',
        (
            "_log_catalog_skip",
            "fetch_nvidia_driver_offer",
            "fetch_amd_driver_offers",
            "fetch_intel_driver_offers",
            "fetch_realtek_driver_offers",
            "fetch_network_vendor_offers",
            "fetch_extended_vendor_offers",
            "fetch_generic_vendor_offer",
            "fetch_oem_driver_offers",
            "fetch_microsoft_driver_offers",
            "fetch_microsoft_catalog_search_offers",
            "_amd_vendor_version_lookup_applicable",
            "_resolve_primary_installed_version",
            "_v6_catalog_enabled",
            "_EXTENDED_VENDOR_KEYS",
            "_VENDOR_DRIVER_URLS",
            "_catalog_system_ctx_from",
            "_manufacturer_vendor_lookup_applicable",
        ),
    ),
    (
        "catalog_online_store.py",
        [
            "ensure_online_driver_store_loaded",
            "fetch_storage_driver_store_offers",
        ],
        '''"""Online driver store load gate and storage matching (extracted from driver_catalog)."""

from __future__ import annotations

import re

from catalog_mscatalog_session import (
    _get_cached_online_driver_store_rows,
    _peek_online_driver_store_cache,
    _should_skip_online_driver_store,
)
from catalog_scoring import compare_firmware_versions


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


''',
        (),
    ),
    (
        "catalog_scan_summary.py",
        [
            "build_summary_comparison_from_device_entries",
            "catalog_scan_mode_summary",
            "build_uncertain_inspector_summary",
        ],
        '''"""Scan mode summaries and uncertain-offer inspector text (extracted from driver_catalog)."""

from __future__ import annotations

from datetime import datetime

from catalog_mscatalog_session import is_quick_check_mode
from catalog_offer_pipeline import filter_offers_for_display, sort_catalog_offers
from catalog_offer_status import summarize_offer_status


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


''',
        ("_v6_catalog_enabled", "_offer_version_from_fields"),
    ),
    (
        "catalog_ps_context.py",
        [
            "_get_pnpsigned_driver_rows",
            "_build_pnpsigned_version_index",
            "extend_system_ctx_for_catalog",
        ],
        '''"""PowerShell context probe and PnPSignedDriver index (extracted from driver_catalog)."""

from __future__ import annotations

import json
import threading
import time

import catalog_mscatalog_session as _mscat_sess
from catalog_mscatalog_session import _cap_session_rows


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


_CATALOG_CACHE_LOCK = threading.Lock()


def _run_catalog_ps(script: str, timeout: int = 30) -> tuple[bool, str]:
    """Catalog/WMI PowerShell — globally serialized to keep the GUI stable."""
    run_catalog_powershell = _dc("run_catalog_powershell")
    run_powershell = _dc("run_powershell")
    if run_catalog_powershell is not None:
        return run_catalog_powershell(script, timeout=timeout)
    if run_powershell is not None:
        return run_powershell(script, timeout=timeout)
    return False, "PowerShell unavailable"


def mark_catalog_powershell_degraded() -> None:
    _dc("mark_catalog_powershell_degraded")()


''',
        ("mark_catalog_powershell_degraded",),
    ),
    (
        "catalog_oem_offers.py",
        [
            "_tag_offer_freshness",
            "oem_data_freshness_note",
            "_oem_support_link_offers",
            "fetch_oem_driver_offers_deep",
            "fetch_oem_driver_offers",
        ],
        '''"""OEM offer orchestration and disk-cache freshness (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_mscatalog_session import is_quick_check_mode
from catalog_offer_status import _is_oem_support_link_offer
from catalog_tier_policy import _oem_disk_offers_stale_vs_installed
from catalog_wu_scoring import _filter_offers_for_device_ctx


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


''',
        (
            "fetch_oem_catalog_for_system",
            "system_has_oem_driver_catalog",
            "_system_manufacturer_oem_url",
            "_fetch_live_oem_offers",
        ),
    ),
    (
        "catalog_vendor_offers.py",
        [
            "_catalog_system_ctx_from",
            "_manufacturer_vendor_lookup_applicable",
            "_offer_version_from_fields",
            "_record_vendor_empty_extraction",
            "_vendor_fetch_get",
            "_vendor_coverage_gap_offer",
            "_vendor_offer_row",
            "fetch_generic_vendor_offer",
        ],
        '''"""Shared vendor offer rows and manufacturer lookup gating (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_extended_fetch import _EXTENDED_VENDOR_KEYS
from catalog_http import _http_get
from catalog_scoring import extract_version_from_text
from catalog_tier_policy import _NETWORK_VENDOR_KEYS


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


''',
        ("_VENDOR_DRIVER_URLS", "_manufacturer_vendor_lookup_applicable", "_catalog_system_ctx_from"),
    ),
    (
        "catalog_system_actions.py",
        [
            "get_system_restore_status",
            "open_system_protection_settings",
            "enable_system_restore",
            "create_system_restore_point",
            "backup_device_driver",
            "open_device_manager",
        ],
        '''"""System Restore, protection settings, Device Manager (extracted from driver_catalog)."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


''',
        ("run_powershell",),
    ),
    (
        "catalog_download.py",
        [
            "microsoft_catalog_view_url",
            "resolve_vendor_package_download_url",
            "_microsoft_catalog_url",
            "_offer_download_kind",
            "_filename_from_url",
            "download_file_to_folder",
            "download_driver_package_for_install",
            "download_driver_offer",
        ],
        '''"""Driver package download and URL resolution (extracted from driver_catalog)."""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request

from catalog_http import _looks_like_html_payload, catalog_user_agent
from catalog_oem_live import (
    _DELL_DRIVER_ID_RE,
    _is_dell_driver_details_url,
    _resolve_dell_driver_download_url,
)


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


_CATALOG_BASE = "https://www.catalog.update.microsoft.com/Search.aspx?q="
_CATALOG_VIEW_BASE = (
    "https://www.catalog.update.microsoft.com/ScopedViewInline.aspx?updateid="
)
_DOWNLOAD_EXTENSIONS = (".exe", ".msi", ".cab", ".zip", ".inf", ".msu", ".7z")


''',
        ("resolve_vendor_package_download_url", "_offer_download_kind"),
    ),
]

# Also move PS degraded flag helpers into catalog_ps_context (prepended there).
PS_CONTEXT_EXTRA = [
    "catalog_powershell_available",
    "mark_catalog_powershell_degraded",
    "consume_catalog_powershell_degraded",
]

KEEP_FUNCS = {"_log_catalog_skip"}

REMOVE_DEAD = {
    "_primary_catalog_tasks_for_ctx",
}

REMOVE_ASSIGN_NAMES = {
    "_OEM_MIN_MATCH_SCORE",
    "_DELL_SERVICE_TAG_PS_CACHE",
    "_CATALOG_BASE",
    "_CATALOG_VIEW_BASE",
    "_DOWNLOAD_EXTENSIONS",
    "_POWERSHELL_CATALOG_DEGRADED",
    "_CATALOG_CACHE_LOCK",
}


def _parse_functions(source: str) -> dict[str, tuple[int, int, str]]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    out: dict[str, tuple[int, int, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            text = "".join(lines[node.lineno - 1 : node.end_lineno])
            out[node.name] = (node.lineno, node.end_lineno, text)
    return out


def _patch_lazy(body: str, names: tuple[str, ...]) -> str:
    for name in sorted(names, key=len, reverse=True):
        body = re.sub(rf"(?<![\w.]){re.escape(name)}\(", f'_dc("{name}")(', body)
    return body


def _collapse_blank_runs(text: str, max_run: int = 2) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    blanks = 0
    for line in lines:
        if line.strip() == "":
            blanks += 1
            if blanks <= max_run:
                out.append(line)
        else:
            blanks = 0
            out.append(line)
    return "".join(out)


def main() -> None:
    source = CATALOG.read_text(encoding="utf-8-sig")
    funcs = _parse_functions(source)

    extract_names: set[str] = set()
    for _, names, _, _ in SLICES:
        extract_names.update(names)
    extract_names.update(PS_CONTEXT_EXTRA)
    extract_names.update(REMOVE_DEAD)

    missing = [n for n in extract_names if n not in funcs and n not in REMOVE_DEAD]
    if missing:
        raise SystemExit(f"Missing functions: {missing}")

    # Build catalog_ps_context with PS helpers first.
    ps_header_end = SLICES[3][2]
    ps_names = PS_CONTEXT_EXTRA + SLICES[3][1]
    ps_parts = [SLICES[3][2]]
    lazy = set(SLICES[3][3])
    for name in ps_names:
        if name in ("mark_catalog_powershell_degraded",):
            continue  # defined inline in header
        _, _, body = funcs[name]
        ps_parts.append(_patch_lazy(body, lazy))
        lazy.discard(name)
    ps_parts.append(
        "\n_POWERSHELL_CATALOG_DEGRADED: bool = False\n\n"
    )
    # Re-add mark/consume from original after inline stub removed
    for name in PS_CONTEXT_EXTRA:
        if name == "mark_catalog_powershell_degraded":
            continue
        _, _, body = funcs[name]
        ps_parts.append(body.replace("global _POWERSHELL_CATALOG_DEGRADED", "global _POWERSHELL_CATALOG_DEGRADED"))
    (APP / "catalog_ps_context.py").write_text("".join(ps_parts), encoding="utf-8")

    slice_files: dict[str, str] = {"catalog_ps_context.py": (APP / "catalog_ps_context.py").read_text(encoding="utf-8")}

    for idx, (fname, names, header, lazy_names) in enumerate(SLICES):
        if fname == "catalog_ps_context.py":
            continue
        parts = [header]
        lazy = set(lazy_names)
        for name in names:
            _, _, body = funcs[name]
            parts.append(_patch_lazy(body, lazy))
            lazy.discard(name)
        (APP / fname).write_text("".join(parts), encoding="utf-8")
        slice_files[fname] = (APP / fname).read_text(encoding="utf-8")

    # Fix catalog_ps_context: mark_catalog_powershell_degraded was duplicated wrong.
    ps_src = (APP / "catalog_ps_context.py").read_text(encoding="utf-8")
    ps_src = ps_src.replace(
        'def mark_catalog_powershell_degraded() -> None:\n    _dc("mark_catalog_powershell_degraded")()\n\n\n',
        "",
    )
    if "def mark_catalog_powershell_degraded" not in ps_src:
        insert = funcs["mark_catalog_powershell_degraded"][2] + "\n\n" + funcs["consume_catalog_powershell_degraded"][2] + "\n\n"
        ps_src = ps_src.replace("_POWERSHELL_CATALOG_DEGRADED: bool = False\n\n", f"_POWERSHELL_CATALOG_DEGRADED: bool = False\n\n{insert}")
        ps_src = ps_src.replace(
            "def mark_catalog_powershell_degraded() -> None:\n    global _POWERSHELL_CATALOG_DEGRADED\n    _POWERSHELL_CATALOG_DEGRADED = True\n",
            "def mark_catalog_powershell_degraded() -> None:\n    global _POWERSHELL_CATALOG_DEGRADED\n    _POWERSHELL_CATALOG_DEGRADED = True\n",
        )
        ps_src = ps_src.replace("return run_powershell is not None\n", 'return _dc("run_powershell") is not None\n')
    (APP / "catalog_ps_context.py").write_text(ps_src, encoding="utf-8")

    # Rebuild driver_catalog body: drop extracted function line ranges + dead assigns.
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    drop: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.name in extract_names or node.name in REMOVE_DEAD:
                drop.update(range(node.lineno, node.end_lineno + 1))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in REMOVE_ASSIGN_NAMES:
                    drop.update(range(node.lineno, node.end_lineno + 1))

    kept_lines = [line for i, line in enumerate(lines, start=1) if i not in drop]
    new_source = _collapse_blank_runs("".join(kept_lines))

    import_block = '''
from catalog_download import (
    _DOWNLOAD_EXTENSIONS,
    _microsoft_catalog_url,
    _offer_download_kind,
    download_driver_offer,
    download_driver_package_for_install,
    download_file_to_folder,
    microsoft_catalog_view_url,
    resolve_vendor_package_download_url,
)

from catalog_system_actions import (
    backup_device_driver,
    create_system_restore_point,
    enable_system_restore,
    get_system_restore_status,
    open_device_manager,
    open_system_protection_settings,
)

from catalog_vendor_offers import (
    _catalog_system_ctx_from,
    _manufacturer_vendor_lookup_applicable,
    _offer_version_from_fields,
    _record_vendor_empty_extraction,
    _vendor_coverage_gap_offer,
    _vendor_fetch_get,
    _vendor_offer_row,
    fetch_generic_vendor_offer,
)

from catalog_oem_offers import (
    _tag_offer_freshness,
    fetch_oem_driver_offers,
    fetch_oem_driver_offers_deep,
    oem_data_freshness_note,
)

from catalog_ps_context import (
    _build_pnpsigned_version_index,
    _get_pnpsigned_driver_rows,
    catalog_powershell_available,
    consume_catalog_powershell_degraded,
    extend_system_ctx_for_catalog,
    mark_catalog_powershell_degraded,
)

from catalog_scan_summary import (
    build_summary_comparison_from_device_entries,
    build_uncertain_inspector_summary,
    catalog_scan_mode_summary,
)

from catalog_online_store import (
    ensure_online_driver_store_loaded,
    fetch_storage_driver_store_offers,
)

from catalog_device_comparison import (
    _build_device_comparison_from_ctx,
    _is_primary_gpu_display_manufacturer_authoritative,
    _manufacturer_catalog_tasks_for_ctx,
    _microsoft_catalog_task,
    _run_catalog_source_tasks,
    _skipped_firmware_driver_comparison,
    build_device_driver_comparison,
    catalog_device_source_path,
)

'''

    anchor = "from catalog_multi_device import ("
    pos = new_source.find(anchor)
    if pos == -1:
        raise SystemExit("catalog_multi_device import anchor not found")
    end = new_source.find("\n)\n", pos)
    if end == -1:
        raise SystemExit("catalog_multi_device import end not found")
    end += len("\n)\n")
    new_source = new_source[:end] + import_block + new_source[end:]

    CATALOG.write_text(new_source, encoding="utf-8")
    print(f"Wrote {CATALOG.name} ({len(new_source.splitlines())} lines)")
    for fname in [
        "catalog_download.py",
        "catalog_system_actions.py",
        "catalog_vendor_offers.py",
        "catalog_oem_offers.py",
        "catalog_ps_context.py",
        "catalog_scan_summary.py",
        "catalog_online_store.py",
        "catalog_device_comparison.py",
    ]:
        p = APP / fname
        print(f"  {fname}: {len(p.read_text(encoding='utf-8').splitlines())} lines")


if __name__ == "__main__":
    main()
