# Work queue — BSOD Analyzer

**Canonical radar** for maintainer and agent-process work in this repo.  
Items are **never deleted** when priorities shift — they move to **Done**, **Parked**, or stay in **Active** / **Inbox**.

| Field | Value |
|-------|--------|
| **Next active ID** | *(none — triage Inbox)* |
| **Last updated** | 2026-09-02 |

---

## How to use

1. **One “next”** — exactly one Active row is **Next** (others **Queued** / **In progress** / **Blocked**).
2. **Order can change** — move Active rows when dependencies or findings require it; reconcile all WQ IDs before and after (see rule).
3. **New findings** (audit reviews, handoff, chat) → **Inbox** first, then triage.
4. **Do not replace lists in chat** — update this file; keep stable **WQ-xxx** IDs.
5. **Product features** → `docs/ROADMAP.md`. **Audit Fix/Improve per run** → `docs/AUDIT.md` report only; recurring debt → **Engineering backlog** here.

Rule: `generic-work-queue-discipline.mdc`.

---

## Active queue (ordered)

| ID | Task | Status | Notes |
|----|------|--------|-------|
| | | | |

---

## Inbox (triage required)

| ID | Task | Source | Triage |
|----|------|--------|--------|
| | | | |

---

## Engineering backlog

Recurring gaps from audits or reviews (not one-off audit Fix lines).

| ID | Task | Priority hint |
|----|------|----------------|
| | | |

---

## Parked / deferred

| ID | Task | Re-open when |
|----|------|----------------|
| | | |

---

## Done log

| ID | Task | Completed | Evidence |
|----|------|-----------|----------|
| WQ-001 | Maintenance USB: PC-local data (no stick persistence) | 2026-08-31 | M1–M4; `run_tests.bat` exit 0; [`MAINTENANCE_USB_DATA_PLAN.md`](upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md) |
| WQ-002 | Remove stick migration (M2 retired) + derivative doc sync | 2026-09-01 | `migrate_maintenance_usb_from_stick` removed; ROADMAP/KNOWN_LIMITATIONS/AGENT_READINESS updated; pack rules strengthened |

---

**Agents:** read **`AGENTS.md`**. Say **audit** for Fix/Improve via **`docs/AUDIT.md`**. For “what’s on the radar?” read **this file** first, then `docs/ROADMAP.md` if the question is product scope.
