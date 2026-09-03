"""Action Plan tab — display filtering and inline action mapping."""

from __future__ import annotations

import re
from typing import TypedDict

import system_health_actions as shealth

ActionKind = shealth.ActionKind

# Steps that belong in Summary / Drivers tabs, not the numbered Action Plan list.
_NARRATIVE_RES = (
    re.compile(r"^the minidump lists .+ — that usually means", re.I),
    re.compile(r"^fix the fault windows logged:", re.I),
    re.compile(r"^fix the whea uncorrectable", re.I),
    re.compile(r"^restart the pc after", re.I),
    re.compile(r"^lower priority:", re.I),
    re.compile(r"^boot/recovery playbook:", re.I),
    re.compile(r"^follow boot/recovery steps on the action plan tab", re.I),
    re.compile(r"^minidump call stack", re.I),
    re.compile(r"^kernel fault on the stack —", re.I),
    re.compile(r"^kernel stack fault —", re.I),
    re.compile(r"^drivers\s*->\s*needs attention:", re.I),
    re.compile(r"^check cbs / windows update history", re.I),
    re.compile(r"^priority \(windbg\):", re.I),
    re.compile(r"^investigate stop code", re.I),
    re.compile(r"^after changes: full shutdown", re.I),
    re.compile(r"^enable memory dumps and re-run", re.I),
    re.compile(r"link below\.?\s*$", re.I),
)

_STEP_OPTION_IDS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"amd chipset|chipset link", re.I), ("amd_chipset", "amd_chipset_guess")),
    (re.compile(r"intel chipset|inf\) drivers", re.I), ("intel_chipset", "intel_chipset_guess")),
    (re.compile(r"update bios|bios/uefi|firmware fixes many", re.I), ("bios_model_search",)),
    (
        re.compile(r"windows update|settings → windows update|quality/cumulative updates", re.I),
        ("wu_optional_platform",),
    ),
    (re.compile(r"download drivers for this pc|pc maker|oem support", re.I), ("oem_model_support",)),
    (re.compile(r"graphics driver|update or roll back the graphics", re.I), ("gpu_nvidia_report", "gpu_amd_report", "gpu_intel_report")),
    (re.compile(r"nvme|storage driver|storage/nvme", re.I), ("storage_nvme_search",)),
    (re.compile(r"search driver/firmware for:", re.I), ("whea_component_search",)),
]

_DRIVER_BTN_LABELS: dict[str, str] = {
    "amd_chipset": "Open AMD chipset",
    "amd_chipset_guess": "Open AMD chipset",
    "intel_chipset": "Open Intel chipset",
    "intel_chipset_guess": "Open Intel chipset",
    "bios_model_search": "Open BIOS page",
    "oem_model_support": "Open PC maker site",
    "wu_optional_platform": "Open Windows Update",
    "storage_nvme_search": "Search storage drivers",
    "whea_component_search": "Search component",
}

_ACTION_BUTTON_KINDS: tuple[ActionKind, ...] = (
    "memory_test",
    "sfc",
    "dism",
    "chkdsk",
)


def iter_action_button_labels() -> list[str]:
    """All Action Plan button captions — used for uniform width sizing."""
    labels = [shealth.action_button_label(k) for k in _ACTION_BUTTON_KINDS]
    labels.extend(_DRIVER_BTN_LABELS.values())
    labels.append("Open graphics drivers")
    return labels


class ActionPlanRow(TypedDict):
    text: str
    health_kinds: list[ActionKind]
    driver_options: list[dict]


def is_narrative_action_plan_step(step_text: str) -> bool:
    text = (step_text or "").strip()
    if not text:
        return True
    return any(p.search(text) for p in _NARRATIVE_RES)


def filter_action_plan_display_steps(steps: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for step in steps:
        text = (step or "").strip()
        if not text or is_narrative_action_plan_step(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _options_by_id(options: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for opt in options:
        oid = opt.get("id")
        if oid:
            out[str(oid)] = opt
    return out


def driver_option_ids_for_step(step_text: str) -> list[str]:
    text = (step_text or "").strip()
    ids: list[str] = []
    for pattern, option_ids in _STEP_OPTION_IDS:
        if pattern.search(text):
            for oid in option_ids:
                if oid not in ids:
                    ids.append(oid)
    return ids


def driver_options_for_step(step_text: str, options: list[dict]) -> list[dict]:
    by_id = _options_by_id(options)
    matched: list[dict] = []
    for oid in driver_option_ids_for_step(step_text):
        opt = by_id.get(oid)
        if opt and opt not in matched:
            matched.append(opt)
    return matched


def driver_action_button_label(option: dict) -> str:
    oid = str(option.get("id") or "")
    if oid.startswith("gpu_"):
        label = (option.get("label") or "Graphics drivers").strip()
        short = label.split("(")[0].strip()
        return f"Open {short}" if short else "Open graphics drivers"
    preset = _DRIVER_BTN_LABELS.get(oid)
    if preset:
        return preset
    label = (option.get("label") or "Open link").strip()
    if len(label) > 42:
        label = label[:42].rstrip()
    return f"Open {label}"


def action_plan_context_line(
    fix_plan: dict | None,
    model: dict | None = None,
    *,
    skip_headline: str = "",
) -> str:
    """One optional evidence line — avoid repeating the banner headline."""
    fp = fix_plan or {}
    skip_blob = " ".join(
        [
            skip_headline,
            (fp.get("headline") or ""),
            ((model or {}).get("cause_subtitle") or ""),
            ((model or {}).get("plain_english") or "")[:200],
        ]
    ).lower()
    for ev in fp.get("evidence") or []:
        text = (ev or "").strip()
        if not text:
            continue
        if text.lower() in skip_blob:
            continue
        return text
    return ""


def build_action_plan_rows(
    steps: list[str],
    driver_update_options: list[dict] | None = None,
) -> list[ActionPlanRow]:
    """Unified Action Plan rows: filtered steps plus any unmatched download actions."""
    options = list(driver_update_options or [])
    filtered = filter_action_plan_display_steps(steps)
    used_option_ids: set[str] = set()
    rows: list[ActionPlanRow] = []

    for step in filtered:
        health = shealth.action_kinds_for_step(step)
        drivers = driver_options_for_step(step, options)
        for opt in drivers:
            oid = opt.get("id")
            if oid:
                used_option_ids.add(str(oid))
        rows.append(
            {
                "text": step,
                "health_kinds": health,
                "driver_options": drivers,
            }
        )

    for opt in options:
        oid = str(opt.get("id") or "")
        if not oid or oid in used_option_ids:
            continue
        label = (opt.get("label") or "Download").strip()
        rows.append(
            {
                "text": label,
                "health_kinds": [],
                "driver_options": [opt],
            }
        )
    return rows
