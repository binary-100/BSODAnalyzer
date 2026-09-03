# Action Plan checklist UX — Tier 1 exploration (Concept B)

**Status:** Tier 1 Exploration — flow/behavior TBD. **Not** on ROADMAP until promoted to Approved intent.  
**Log:** [`upgrade/inbox/EXPLORATION_LOG.md`](upgrade/inbox/EXPLORATION_LOG.md)
**Mockups:** `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\action_plan_tab_mockups.html` (Concept B = checklist + progress header)  
**User preference (2026-08-23):** Concept B over A/C; defer implementation until behavior is defined.

---

## Problem

- Text-only steps (e.g. “disable overclocking / clean vents”) leave an empty 196px button column — looks misaligned.
- No session memory of what the user already tried; Action Plan cannot adapt suggestions.

Concept B adds per-step checkboxes and a “N of M done” header **after** we know what checking a box means for analysis and persistence.

---

## Open design questions (must answer before build)

| # | Question | Options to decide |
|---|----------|-------------------|
| 1 | **Persistence scope** | Session-only · per machine fingerprint · per crash signature · export with report |
| 2 | **Reset trigger** | New Run Analysis · new minidump · manual “Reset checklist” · never auto-reset |
| 3 | **Effect on Action Plan** | Hide completed · collapse “Done” section · reorder next step · feed Summary only |
| 4 | **Effect on analysis** | None (UX only) · downgrade repeated steps · skip auto catalog for done driver rows · session log annotation |
| 5 | **Text-only rows** | Full-width row + “Manual step” badge · no checkbox required · checkbox optional |
| 6 | **Admin health steps** | Checkbox after launch vs after user confirms completion dialog |

---

## Proposed behavior (draft — not approved)

1. **Checkboxes are user-owned state**, not auto-checked when a link opens.
2. **Progress header:** `completed / total` for actionable + manual steps; “Next: …” from first unchecked row.
3. **Persistence (when built):** PC-local under `%LOCALAPPDATA%\BSODAnalyzer\` (Maintenance USB model) — **not** on the USB stick. Key by `machine_fingerprint` + optional `stop_code` / `faulting_driver` hash. See [`upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md`](upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md).
4. **Analysis integration (minimal v1):** Session log entries when user checks/unchecks; Action Plan text unchanged until v2.
5. **Layout fix (can ship earlier):** Concept A-style full-width text rows without checkboxes — independent of checklist logic.

---

## Implementation phases (when promoted to Approved intent + work queue)

| Phase | Work | Depends on |
|-------|------|------------|
| **AP-1** | Layout only — full-width rows, no empty button column (Concept A subset) | None |
| **AP-2** | Checkbox UI + session-only state (lost on exit) | AP-1 |
| **AP-3** | Persist per machine + reset rules | AP-2 + settings schema |
| **AP-4** | Analysis hooks (log, optional step suppression) | AP-3 + product sign-off |

---

## Related files (today)

| File | Role |
|------|------|
| `gui_mixin_action_plan.py` | Row layout, button column |
| `action_plan_ui.py` | Step → button mapping |
| `driver_verification.py` / `bsod_crash_report.py` | Step source text |

---

## References

- Mockups: `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\action_plan_tab_mockups.html`
- Tier 1 log: [`upgrade/inbox/EXPLORATION_LOG.md`](upgrade/inbox/EXPLORATION_LOG.md) — promote to ROADMAP Approved intent when ready
