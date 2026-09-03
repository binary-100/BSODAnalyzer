# Generic Agent Starter Pack rules (portable)

Auto-generated from ``pack/rules/*.mdc``. **Do not edit by hand.**

Regenerate: ``pack\scripts\sync-portable-docs.ps1`` (also runs during ``sync-audit-system.ps1`` on the pack maintainer repo).

| Load path | Tool |
|-----------|------|
| ``%USERPROFILE%\.cursor\rules\*.mdc`` | Cursor (after ``install.ps1``) |
| This file | Claude, Copilot, Windsurf, CLI - paste or attach at session start |

Pack version: 1.8.0
Rule files: 13

---

## agent-defaults-always

Source: `pack/rules/agent-defaults-always.mdc`

# Agent defaults (all sessions)

## Session start

On the **first turn** in a project, read **`docs/AGENT_SESSION_START.md`** when it exists, before substantial work. It carries the stale/fresh verdict for this project's agent context and the absolute paths you are expected to have read. If it reports **stale**, follow **Context refresh** below rather than working from whatever this chat already believes.

Some repositories are meant to be copied or downloaded and therefore keep **no** per-machine files inside themselves. There the context artifacts live in a machine-local directory outside the checkout instead, and `docs/AGENT_SESSION_START.md` will simply be absent — run the context refresh and read the paths it prints rather than concluding the project has no context.

The project's `AGENTS.md` and `AI_INSTRUCTIONS.md` say the same thing — this rule covers projects whose entry files predate that line or were customized.

## Loop-back (all projects)

On **any repeated error**, **same question again**, or **still broken** / **anything else** / **check everything again**:

Follow **`loop-back-protocol.mdc`** and **`pack/docs/AGENT_WORKFLOW.md`** — in the starter pack, or at `%USERPROFILE%\.cursor\AgentStarterPack\pack\docs\AGENT_WORKFLOW.md` from any other project. Read the workstream from the start, validate repo state, diff intent vs reality, then proceed differently. Applies to **all projects**, not only audits.

## Terminal & builds

- Before/after long shell commands: use **agent-hygiene** MCP when available.
- **Preferred one-shot:** `agent_hygiene_full_check` (terminals + orphan py/python scan).
- **After force-killing a terminal** (`exit_code: 4294967295`): run `scan_orphan_agent_processes`, then `cleanup_orphan_agent_processes` with `dry_run=True` first; only set `dry_run=False` after confirming targets.
- Repair stale logs: `fix_stale_terminal_logs`. Kill a specific PID: `kill_terminal_process`.
- Without MCP: `pack/scripts/cleanup-orphan-processes.ps1` (add `-Kill` to terminate).
- Agent-initiated Windows builds: set **`BUILD_NOPAUSE=1`** or run **`build_ci.bat`** — never leave batch files waiting on `pause`. The same applies to any double-click launcher you run yourself.
- GUI/offscreen test suites: expect ~20s; full PyInstaller builds: allow 2–5+ minutes (`block_until_ms` accordingly).
- If the user reports "taking longer than expected": check OS process table; run full hygiene check; tell user to **Kill Terminal** in the editor UI if the tab still spins (agents cannot dismiss UI tabs).

Depth beyond this: skill **`agent-terminal-hygiene`** (diagnosis, stale metadata, orphans) and **`generic-terminal-and-build-hygiene.mdc`** (writing builds that never wait on a prompt). This section is the operational default; those two do not repeat it.

## Audits (Fix / Improve only)

On **audit**, **full scan**, **check everything**, **find problems**, a repeated **still broken** / **anything else**, or audit-system maintenance (same trigger list as **`audit-protocol.mdc`**):

1. **Loop back** first if this is a repeat ask (see above).
2. Product: step 1 **`run_audit.cmd`** (full tests, never `-SkipTests`); step 2 semantic report; step 3 **`finalize_audit.cmd`**. System: **`verify-audit-system.ps1`**.
3. Load skill **`agent-code-audit`**. Report **only** Fix (remove gap) and Improve (mitigate gap).

Docs: `pack/docs/AGENT_WORKFLOW.md`, `AUDIT_SYSTEM_CHANGELOG.md`, `AUDIT_SYSTEM.md`

After audit-system changes: **`sync-audit-system.ps1`** + changelog entry.

## Context refresh (stale chat)

On **refresh pack context**, **sync agent context**, **context refresh**, or **pack update**:

1. Read `docs/AGENT_REFRESH.md` in the **current workspace** if present, then every path in `requiredReads` from `docs/AGENT_CONTEXT.json` (absolute paths — use them if workspace root differs). If neither file is there, the project keeps its context outside the checkout: run the refresh (step 3) and read the paths it prints.
2. Treat anything you learned earlier in this chat as possibly stale where it conflicts.
3. Missing or unclear? Read `docs/AGENT_CONTEXT.json`, call MCP **`check_pack_freshness`** / **`get_agent_refresh_brief`** when agent-hygiene is available, or run the refresh yourself as below.
4. **Handshake:** reply with the pack version and audit engine version you just read when the refresh brief or paste line asks for it.

When an audit reports **Agent context stale / never refreshed / unreadable**, do not hand the user a
command to type: **offer to run `Refresh-AgentContext.cmd` for this project yourself** and let them
approve the run. On approval, run it, then read the regenerated brief in the same turn — the command
prints every path it wrote. It syncs this project's rules and audit files from the installed pack; it
does not change the user profile unless asked with `-Install`.

## Fixes the agent runs (do not offload)

**Agent runs commands; user verifies outcomes.** The user may review output, exit codes, and diffs to see what happened and pivot if something else should happen — that is **verification**, not **execution**. Do not ask the user to type fix commands you can run in this session.

When **you** find a fixable gap during work (verify drift, sync failure, doc-version stale header, test you can run, refresh you can offer):

1. **Run the fix in the same turn** — you execute; report paths, stdout/stderr highlights, and exit codes so the user can verify.
2. **Pause for pivot only when needed** — after reporting, the user may redirect; do not substitute "please run X" for step 1.
3. **Offer + run on approval** only when the fix needs explicit consent (profile **`install.ps1`**, destructive prune, or the user has not asked for profile writes) — still **you** run it after they approve, not "type this yourself."

| You found | Agent runs (same session) |
|---------|---------------------------|
| Audit sync drift (Desktop vs `%USERPROFILE%\.cursor\AgentStarterPack`) | `sync-audit-system.ps1` or `install.ps1 -Scope User -NoPause` |
| Stale doc-version header after engine bump | `sync-doc-versions.ps1` on the maintainer checkout |
| Stale agent context (audit Improve / MCP freshness) | `Refresh-AgentContext.cmd` / `Update-AgentStack.cmd` (offer first when profile `-Install`) |
| Product tests / live validation | Per project `AGENT_READINESS.md` / `PRODUCT_REFERENCE.md` — **never** ask the user to run tests or fix Qt env |

**Forbidden:** ending with "run X to fix" when you can run X yourself (unless blocked — name the blocker and what remains unverified).

## Starter pack location

- `%USERPROFILE%\.cursor\AgentStarterPack\` — prefix the doc paths above and below with this when the
  current project is not the starter pack itself
- **Onboarding:** `pack/docs/START_HERE.md`
- **Any AI tool / new project:** `docs/PORTABLE_SETUP.md`
- Verify: `doctor.ps1`, `verify-audit-system.ps1`, `sync-audit-system.ps1 -VerifyOnly`

## Chat paths

When citing files on the user's machine in chat, use **full absolute paths** — see **`full-paths-in-chat.mdc`** (`alwaysApply: true`).

## Deep / exhaustive requests

When the user asks for **deep**, **full**, **thorough**, **compare**, **everything**, or **check everything** work, follow **`generic-deep-task-execution.mdc`** (`alwaysApply: true`). Run the matching depth contract with tools **before** concluding. Do **not** tell the user to rephrase or add keywords.

## Work queue (what's on the radar)

When the user asks **what's next**, **what's pending**, or priorities **change mid-session**, follow **`handoff-first.mdc`**: **`docs/handoffs/SESSION.md`** first (if present), then **`docs/WORK_QUEUE.md`**, then **`generic-work-queue-discipline.mdc`**. Do not replace the queue in chat without updating that file.

## Agent handoffs (implement / confirm)

When handing work to **another chat**, follow **`generic-agent-handoff-discipline.mdc`** and **`pack/docs/AGENT_HANDOFFS.md`**. One session opener line only; full instructions live in **`docs/handoffs/`**.

## Agent docs (rules, AGENTS.md)

Before adding or duplicating agent guidance, read what already exists — see **`generic-agent-doc-hygiene.mdc`** (`alwaysApply: true`).


---

## audit-protocol

Source: `pack/rules/audit-protocol.mdc`

# Audit protocol

**Trigger list (canonical).** On **audit**, **full scan**, **check everything**, **find problems**, or a repeated **still broken** / **anything else**. `agent-defaults-always.mdc` and any project `audit.mdc` use this same list — one job should not have three vocabularies, and a phrase that only one surface knows is a phrase that gets missed.

1. **Loop back** — per **`loop-back-protocol.mdc`** (all projects) if this is a repeat ask.
2. Read **`pack/docs/AGENT_WORKFLOW.md`** (audit section: Fix/Improve) — in the starter pack itself, or at `%USERPROFILE%\.cursor\AgentStarterPack\pack\docs\AGENT_WORKFLOW.md` from any other project.
3. If **`docs/AUDIT.md`** or **`app/docs/AUDIT.md`** exists → product scope: step 1 **`run_audit.cmd`** (full tests, never `-SkipTests`); step 2 semantic report; step 3 **`finalize_audit.cmd`** (or `-FinalizeOnly`).
4. If audit **system** scope → **`verify-audit-system.ps1`**; do not claim product pass.
5. Load skill **`agent-code-audit`**.

**Gaps (audit only):** **Fix** (remove) or **Improve** (mitigate). No third report section.

**`-SkipTests` is not an audit.** Do not claim pass without finalize (or full `run_audit.cmd` with semantic complete) exit 0.

Do **not** use Phase A/B, add-ons menus, or `*-audit-overlay.mdc`.


---

## full-paths-in-chat

Source: `pack/rules/full-paths-in-chat.mdc`

# Full paths in agent chat

When you tell the user where a file, folder, build output, or log lives **on their machine**, use the **full absolute path** — not a shortened or repo-relative form.

Referenced from **`agent-defaults-always.mdc`** (always-on).

## Required

- **Windows:** `C:\Users\...\project\src\main.py`
- **macOS/Linux:** `/Users/.../project/src/main.py`

## Forbidden in user-facing replies

- Truncated prefixes: `src/...`, `...\docs\file.html`, `Desktop\MyApp\...` (when the full path is known)
- Repo-relative paths in chat when telling the user where a file lives: `docs/handoffs/...`, `app/settings.py` — use the full absolute path instead
- Vague hand-waves: "the config file", "under docs" (unless you immediately give the full path on the same line)

## Allowed

- **Markdown links inside repo docs** (`docs/README.md`) — relative links are fine for navigation in git.
- **Code citations** — use workspace-relative paths in ```startLine:endLine:path``` fences (Cursor navigation).
- **Unknown path** — say you could not resolve it; do not guess a partial path.

## Examples

| Context | Bad | Good |
|---------|-----|------|
| User asked where a doc lives | `docs/README.md` | `C:\Users\alice\Projects\MyApp\docs\README.md` |
| Build output | `dist\app.exe` | `C:\Users\alice\Projects\MyApp\dist\app.exe` |
| Installed global rules | `%USERPROFILE%\.cursor\rules\` | `C:\Users\alice\.cursor\rules\` (expand when profile path is known) |
| Starter pack on a flash drive | `AgentStarterPack\pack\` | `E:\AgentStarterPack\pack\` (use the drive letter you see) |

## Agent Starter Pack

Canonical copy: `pack/rules/full-paths-in-chat.mdc` — copied to `%USERPROFILE%\.cursor\rules\` on **`install.ps1`**. Verified by **`doctor.ps1`**.

Projects that keep a local copy: run **`sync-project-rules.ps1`** after pack edits — see **`pack/docs/PACK_MAINTENANCE.md`**.


---

## generic-agent-doc-hygiene

Source: `pack/rules/generic-agent-doc-hygiene.mdc`

# Agent doc hygiene (all projects)

Before **creating or substantially editing** agent-facing files — `.cursor/rules/*.mdc`, skills, `AGENTS.md`, `AI_INSTRUCTIONS.md`, or similar — and **maintainer entry docs** (install instructions, the session handoff note, handoff `.md` under `docs/handoffs/`):

## 1. Read what already exists

- List and skim **project** `.cursor/rules/` (and nested paths like `app/.cursor/rules/` if the project uses them)
- Read **`AGENTS.md`** and linked agent docs (`AI_INSTRUCTIONS.md`, `CLAUDE.md`, etc.)
- **Agent Starter Pack maintainer repo:** read **`INSTALL.txt`** and **`docs/WORK_QUEUE.md`** before adding any install/handoff/status doc
- If the project **syncs generic rules from Agent Starter Pack**, treat those as read-only in the project — edit **`pack/rules/`** at the pack source, then sync; do not fork copies locally

## 2. Prefer extend over duplicate

- **Extend** an existing rule, `AGENTS.md` section, or **canonical maintainer doc** when the concern fits
- **New file** only when the concern is distinct and would bloat an existing rule or doc
- **One concern per rule** — split only when scopes differ (always-on vs file-specific globs)
- **Install / handoff / status:** keep **one** install doc for humans and **one** handoff doc for agents, and overwrite them; retire or redirect superseded handoffs — **do not** add `STICK_*`, `*_INSTALL.txt`, or parallel cheat sheets for the same job
- When consolidating, **delete** the redundant file — do not leave parallel copies

## 3. Avoid overlap

- Do not restate what global defaults already cover (`agent-defaults-always.mdc`, `loop-back-protocol.mdc`, project `audit.mdc`, etc.)
- Project-only wrappers should **link** to generic pack rules, not copy them verbatim

## 4. After adding

- Update **`AGENTS.md`** links/index if the project uses one
- Merge or remove superseded rules — do not leave parallel guidance

## 5. Version cites in documentation

Doc version sync belongs to **build/test**, not audit. Do not hand-edit version strings across
README/AGENTS when the project has a sync step that can update them.

Which step that is depends on the project — the `docs/VERSION_SYNC.json` and
`scripts/apply_version.py` pipeline only exists in repos bootstrapped with `-Stack Python`. Check
what the repo actually has before running anything; **`generic-version-sync.mdc`** covers the
pipeline in detail.

## 6. After shipping or changing status (Done / Parked / Next)

**Version cites in documentation (above) is not status sync.** Bumping a version string in docs does not update the prose around it — a "not built yet" paragraph survives every version bump until someone edits it.

When a work item moves on **`docs/WORK_QUEUE.md`** (especially to **Done** or **Parked**):

1. Update **derivative docs** that still describe the old state — the handoff's status section, gap/plan rows, spec headers, coordination backlog — not only the queue file.
2. When the slice **changed product behavior** (paths, install modes, capabilities, limits), update the project's **product-truth docs** in the same session — typically files named like `PRODUCT_REFERENCE`, `KNOWN_LIMITATIONS`, install/layout tables in `PROJECT_LAYOUT`, and **`ROADMAP.md` work-queue rows**. Use the project's `DOC_MAP.md` (if present) to find owners; do not wait for the next audit.
3. Prefer **WQ ids** over phase-only labels in handoffs; when a slice carries more than one phase number, keep the id map in the plan doc that owns those phases.
4. **Agent Starter Pack maintainer repo:** run **`verify-complete-picture.ps1`** before claiming done (see **`pack/docs/WORK_COMPLETION.md`** step 5b) — rules-vs-verify inventory in **`pack/docs/RULES_AND_VERIFY_MAP.md`**.

Do **not** add a second always-on rule for this — extend the work queue row and run the verify script.


---

## generic-agent-handoff-discipline

Source: `pack/rules/generic-agent-handoff-discipline.mdc`

# Agent handoff discipline (all projects)

Full convention: **`pack/docs/AGENT_HANDOFFS.md`** (after install: `%USERPROFILE%\.cursor\AgentStarterPack\pack\docs\AGENT_HANDOFFS.md`).

## Problem

Multiple paste blocks for the same implement job (handoff file + PLAN + BUILD_HANDOFF + chat) confuse humans and agents. A second doc claiming **Next** (retired root session mega-doc, 2.22.65) contradicted WORK_QUEUE three times — use **`docs/handoffs/SESSION.md`** for session continuity instead (**pointers only**; see **`handoff-first.mdc`**).

## Build / implement handoffs

When handing **implementation** to another chat:

1. **One handoff file** under `docs/handoffs/active/` — name `HANDOFF_WQnnn_<slug>.md` (or `HANDOFF_<slug>.md` when no WQ id).
2. **Registry table** at top (`## Handoff registry`) — see AGENT_HANDOFFS.md.
3. **One session opener** for the human — single line, full absolute path, ending with `and implement.`
4. **Forbidden in chat:** second paste block, "or say…", "method 1 / method 2", or repeating PLAN fences as the assignment.
5. **PLAN / BUILD_HANDOFF** link the handoff file — they do not duplicate a user paste block or a second session opener.
6. **Paths in chat:** when citing handoff or doc locations to the user, use **full absolute paths** (`full-paths-in-chat.mdc`) — not repo-relative bullets.

## Orientation handoffs (no code)

Same one-line rule; opener ends with **`and confirm.`**  
File: `docs/handoffs/HANDOFF_<topic>.md` (not in `active/` unless still blocking work).

## Multi-agent handoffs

Set **`multi_agent: yes`** and list **`agents_remaining`** until every agent is done.  
Audit **never** suggests archive/delete while `agents_remaining` is non-empty.

## Completing work

Follow **`pack/docs/WORK_COMPLETION.md`** end-to-end (handoff status, WORK_QUEUE Done, `verify-complete-picture.ps1`, audit, archive). Do not duplicate that checklist here.

## Exempt

- Pack context refresh (`AGENT_REFRESH.md`, `refresh pack context`)
- Audits (Fix/Improve only)
- Casual chat without a handoff file

Related: **`generic-work-queue-discipline.mdc`**, **`pack/scripts/verify-agent-handoffs.ps1`**


---

## generic-deep-task-execution

Source: `pack/rules/generic-deep-task-execution.mdc`

# Deep task execution (all sessions)

## Whose job this is

When the user asks for **deep**, **full**, **complete**, **exhaustive**, **thorough**, **everything**, **compare**, **breakdown**, or **check everything** work:

- **The agent** chooses and runs the full depth contract below.
- **Not the user's job** to add magic phrases, checklists, or "say X next time" instructions.
- **Stopping early** because a partial pass "seems enough" is an agent failure — not a user phrasing failure.

Speed, model defaults, and conversation length are **not** reasons to skip mandatory steps.

## Before concluding (every deep task)

1. **State the contract** in the first tool-using turn (e.g. "Depth contract: deep compare — inventory, hashes, version markers, tests both sides").
2. **Run the steps** — tools and commands, not memory or prior-turn summaries alone.
3. **Report evidence first** — counts, paths, exit codes, explicit only-on-A / only-on-B lists.
4. **Then** interpret and answer the user's question.
5. If a step is **blocked** (path missing, permission, timeout), name the step and what remains **unverified**. Do not substitute a shallow verdict.

## Forbidden

- Telling the user to rephrase, add keywords, or paste a checklist so the agent behaves.
- Verdict from spot-checking a few files when the contract requires full inventory.
- "Based on earlier analysis" without fresh evidence **in this turn** for the requested depth.
- Treating "I did something" as "I did enough" when mandatory steps remain.

---

## Contract: deep compare (two trees, folders, branches, copies, versions)

Use when the user compares **two locations** or asks whether one copy covers another.

**Mandatory before any verdict:**

| Step | Requirement |
|------|-------------|
| 1 | Confirm both paths exist; report if either is missing |
| 2 | Recursive file inventory on **both** sides (exclude `.git`, `__pycache__`, `.pytest_cache` unless user includes them) |
| 3 | Content comparison on every **shared relative path** (hash or equivalent) |
| 4 | Explicit **only-on-A** and **only-on-B** file lists |
| 5 | Version / manifest / changelog markers on both sides when present |
| 6 | Line-count or size deltas on **core changed files** (scripts, manifest, entry points) — not just "many files differ" |
| 7 | Run applicable **verify or test scripts on both sides** when runnable; report exit codes and failures |
| 8 | Map results to the user's ** stated checklist or goals** (e.g. "does B cover our update list?") |

**Response order:** Method → Inventory → Differences → Tests → Verdict → Gaps (what was not checked and why).

**Not sufficient alone:** top-level listing, reading one handoff doc, grep for a few keywords, or comparing version strings without file-level evidence.

---

## Contract: full scan / check everything (single repo or system)

Use for **audit**, **full scan**, **check everything**, **review the whole codebase**.

Follow project audit rules when present (`audit.mdc`, skill `agent-code-audit`) — **`audit-protocol.mdc`** holds the canonical audit trigger list, and the words below add depth requirements rather than a second vocabulary. Additionally:

- Run the project's **full test / verify entry point** when one exists — never `-SkipTests` on audits unless docs explicitly allow it.
- Do not report "complete" until required gates exit 0 or you list failing gates explicitly.

---

## Contract: investigation / root cause / "what are we dealing with"

Use when the user needs an **accurate picture** of state, gaps, or regressions — including **handoff doc review**, **where we stand**, **what's pending**, or **status after a merge**.

**Mandatory:**

- Read **primary sources** (files, configs, logs) — not only docs or prior chat.
- **Validate** assumptions with commands (tests, status, diff, inventory).
- Separate **decided vs implemented vs still broken**.

---

## Contract: complete picture (handoff docs, pending work, status)

Use when the user asks for **where we stand**, **what's pending**, **handoff cleanup**, **full review**, or any analysis that must drive **next steps**. This is the class of failure where stopping after one doc or one grep misses whole workstreams.

**Mandatory before any "here's what's next" verdict:**

| Step | Requirement |
|------|-------------|
| 1 | **Inventory all agent/handoff sources** — repo root plus every agent-doc folder the project uses (`docs/`, `docs/handoffs/`, `pack/docs/`) — and list every file read or explicitly skipped with reason. Include **`docs/WORK_QUEUE.md`** when present. |
| 2 | **Grep all of them** for: `deferred`, `not built`, `not implemented`, `open question`, `design goal`, `next step`, `pick up`, `parked`, `remaining`, plus the project's own recurring qualifiers (e.g. `tool-neutral`, `multi-tool`, `editor-specific`, `Windows-only`, `audit depth`) |
| 3 | **Separate tracks** — do not collapse related-sounding work into one bucket. Split by what would have to change to close it, and keep **explicitly deferred** work as its own track with the id or doc that deferred it |
| 4 | **Map each track** to: documented intent → what shipped → what is still open → which doc says so (with path) |
| 5 | **Live state** — version markers, install sync, test exit codes **in this turn** |
| 6 | **Cross-check user callouts** — if the user says a topic should be in the docs, search for it before claiming it is missing |
| 7 | **Response order:** Sources read → Live state → **Work queue summary** (`docs/WORK_QUEUE.md` if present) → Track table (shipped / open / deferred) → Gaps in prior analysis → Recommended next steps |

**Forbidden:**

- Rewriting a handoff status section or chat bullets **without** updating **`docs/WORK_QUEUE.md`** when that file exists.
- Reporting one status section or one handoff file while ignoring the rest of the sources from step 1 — a project's design goals and gap tables usually live in a different section than its "next steps" list.
- Treating one track as closed because a **neighbouring** track shipped. Two tracks that share a word in their names still close separately.
- Dropping a track from "what's next" because it is long-running or was decided against once — a decision to defer keeps the track on the list with its **Re-open when**.

---

## On user pushback ("too fast", "not deep enough", "you missed X")

This is a **loop-back** trigger (see `loop-back-protocol.mdc`):

1. Acknowledge the gap — do not blame user phrasing or ask them to rephrase.
2. Re-read the **original request** and this contract.
3. Run the **missing mandatory steps** in this turn.
4. Show **new evidence** before revising the verdict.

---

## Pack maintenance

Canonical copy: `pack/rules/generic-deep-task-execution.mdc` — installed to `%USERPROFILE%\.cursor\rules\` via `install.ps1`. Referenced from `agent-defaults-always.mdc`.


---

## generic-phased-feature-design

Source: `pack/rules/generic-phased-feature-design.mdc`

# Phased feature design (all projects)

Use for **multi-step features**, refactors, and “fix it properly” workstreams.

**Full guide:** `%USERPROFILE%\.cursor\AgentStarterPack\pack\docs\PHASED_FEATURE_DESIGN.md`

## Non-negotiables

1. **One sequence** — Phases 1 → N; **runtime order = build order**.
2. **No phase skips** — Never implement a later phase before an earlier one is complete.
3. **One checklist** — Single table; project/feature done when every phase is ☑.
4. **Optional work owns a phase** — No orphan “optional” steps in the main flow.

## Optional / deferred work

Choose one style per plan (do not mix inconsistently):

| Style | Where | Rule |
|-------|--------|------|
| **A — Nested (preferred)** | Under owning phase as `4a`, `4b`, … | Mark sub-steps `[required]` or `[optional]`; phase ☑ when required sub-steps done |
| **B — Appendix** | After main checklist | Entries **must** be labeled `Phase Nx` (e.g. `Phase 4d`); build only after Phase N required work |

**Never:** milestones that combine non-contiguous phases (e.g. “2–4 + 7, then 5–6”).

## Before coding

1. Write or read a phased plan (use template in `PHASED_FEATURE_DESIGN.md`).
2. Implement **next unchecked phase only**.
3. Report progress as **“through Phase N”**.

Store plans in `docs/*_PLAN.md` for large features; link from `AGENTS.md` when relevant.


---

## generic-terminal-and-build-hygiene

Source: `pack/rules/generic-terminal-and-build-hygiene.mdc`

# Build hygiene (agents)

Apply when running builds or long shell commands.

**Terminals are covered elsewhere, on purpose.** The before/after sequence for long commands is in
**`agent-defaults-always.mdc`** (always on, so it is the copy that actually loads). Diagnosis —
stale metadata, orphan children, what an agent can and cannot fix — is the skill
**`agent-terminal-hygiene`**. This rule is the third surface of the same subject, so it keeps only
what neither of those covers: making a build finish without a human at the keyboard.

## Running builds (agent-initiated)

1. Set **`BUILD_NOPAUSE=1`** (Windows) or use `build_ci.*` / `--ci` / `CI=true` scripts so batch files **do not** wait on `pause`.
2. Prefer explicit exit: `exit /b %ERRORLEVEL%` (Windows) or `set -e` (Unix).
3. After the build, **read the terminal output** for success or failure — a spinner in the UI is not a result, and an exit code you did not look at is not a pass.

**Windows example:**

```bat
set BUILD_NOPAUSE=1
call build_and_deploy.bat
```

## Writing build scripts

- Never use bare `pause` in a script an agent will run; gate it: `if "%BUILD_NOPAUSE%"=="" pause`.
- Same for `read -p`, `Read-Host`, and any other prompt on the CI path.
- Copy `pack/templates/build-ci.bat.template` → project `build_ci.bat` for a script that is already gated.
- Python projects also copy the version sync templates — see **`generic-version-sync.mdc`**.

## When a build seems stuck

A build waiting on `pause` and a build still working look identical from the outside. Check the
output for a prompt before killing anything, then follow the skill **`agent-terminal-hygiene`** —
force-killing the shell first is what leaves orphaned child processes behind.


---

## generic-version-sync

Source: `pack/rules/generic-version-sync.mdc`

# Version sync (agents)

Prevent **version drift** between runtime code, `VERSION.txt`/release notes, and distrib folders. Drift is often only caught on full audit or `test_version_consistency` — fix the process, not just the symptom.

## Principles

1. **One canonical source** per project (pick one):
   - Python: `VERSION = "x.y.z"` in the main module (e.g. `main.py`, `app.py`)
   - Node: `package.json` → `version`
   - Rust: `Cargo.toml` → `version`
   - Tooling repo with no source module: a root `VERSION` file

2. **Derived artifacts are generated**, not hand-edited:
   - `VERSION.txt`, distrib `README.txt`, about strings copied at build time

3. **Sync before verify**: `run_tests.bat` / `build_ci.bat` runs **`apply_version.py sync`** first (version **and** docs per `docs/VERSION_SYNC.json`).

4. **Idempotent sync**: if already aligned, do not rewrite release dates or churn files.

5. **Build pipeline, not audit**: doc version sync is **`scripts/doc_version_sync.py`** + **`docs/VERSION_SYNC.json`**. Audit Section M can backstop a skipped sync, but it is **off by default** in generated projects (`sectionMachineChecks.M.enabled`) — treat the build step as the only thing that catches stale cites unless you switched M on.

## Python projects

Copy from starter pack (bootstrap `-Stack Python`):

- `docs/VERSION_SYNC.json` — doc sync targets
- `scripts/doc_version_sync.py`, `scripts/apply_version.py`, `scripts/sync_doc_versions.py`
- `scripts/sync_doc_versions.cmd` — manual doc-only pass
- `tests/test_version_consistency.py`, `.cursor/rules/version-sync.mdc`

Wire `run_tests.bat` (template already enables sync):

```bat
py -3 scripts\apply_version.py sync
if errorlevel 1 exit /b 1
```

**Agents:** edit only the canonical `VERSION` in source module; never hand-edit `VERSION.txt` or README version lines. After bumping, run `sync` or `run_tests.bat` / `build_ci.bat`.

## Node / other stacks

| Stack | Canonical | Sync hook |
|-------|-----------|-----------|
| Node | `package.json` | `npm version` / custom script in `pretest` + `VERSION_SYNC.json` |
| Rust | `Cargo.toml` | build script before `cargo build` |

## Audit

If sync is wired into `run_tests.bat`, doc drift should be rare. Audit Section M may still report stale `vX.Y.Z` when sync was skipped — fix by running the build sync, not by editing audit config.


---

## generic-work-queue-discipline

Source: `pack/rules/generic-work-queue-discipline.mdc`

# Work queue discipline (all projects)

## Problem this solves

Agents and humans often **replace** priority lists mid-session. Items discovered during work vanish from chat. Users cannot verify what is still open.

## Canonical file

| Project type | File |
|--------------|------|
| Bootstrapped app | `docs/WORK_QUEUE.md` |
| Agent Starter Pack (maintainer) | `docs/WORK_QUEUE.md` at repo root |
| Product features (apps) | `docs/ROADMAP.md` — **not** the same as the work queue |

If `docs/WORK_QUEUE.md` is missing in a bootstrapped project, treat `docs/ROADMAP.md` Active/Backlog as fallback for product work only — maintainer/process items still belong in a work queue once created.

## Required behavior

### Before changing priorities or saying "what's next?"

Follow **`handoff-first.mdc`** lookup order:

1. Read **`docs/handoffs/SESSION.md`** if present — open items or blockers → **stop here**.
2. Read **`docs/WORK_QUEUE.md`** if it exists (else note its absence).
3. Report: **Next ID**, **Active count**, **Inbox count**, **Parked count** — not only the latest chat bullet list.
4. Unplanned next only when SESSION **and** WQ are clear — label it explicitly.

### When adding work

- **Append** with a new stable ID (`WQ-001`, `WQ-002`, … — never reuse).
- Put surprises in **Inbox**; triage to Active / Parked / Done in the same session when possible.
- Do **not** silently drop rows because a handoff doc or status table was rewritten.

### When completing work

- Move row to **Done log** with date and evidence (test exit code, path, commit — whatever applies).
- Set the next Active row to **Next** (exactly one).
- If a **`docs/handoffs/active/HANDOFF_*.md`** row exists for that WQ: set handoff **`status: completed`**, **`completed:`** date, clear **`agents_remaining`**. Run **`run_audit.cmd`** before archiving; audit **Improve** may suggest `handoff_archive/` — never auto-delete (see **`generic-agent-handoff-discipline.mdc`**).
- **Canonical status propagation (required):** WORK_QUEUE is the source of truth. After editing it, align **every derivative** that mentions that WQ or slice — the handoff's status section, phase/gap plan rows, spec status headers, PARKED/backlog docs, **and product-truth docs when behavior changed** (see **`generic-agent-doc-hygiene.mdc`** after-ship status alignment). Full channel list: **`pack/docs/RULES_AND_VERIFY_MAP.md`** § Canonical status propagation.
- **Maintainer pack repo:** run **`verify-complete-picture.ps1`** (behavior step 37) — exit **0** before claiming the slice done. Same checklist: **`pack/docs/WORK_COMPLETION.md`** step 5b.

### When deferring

- Move to **Parked / deferred** with **Re-open when** — not deleted, not vague "later."
- Remove or update any **Active/Next** or handoff text that still reads as in-progress for that WQ (same propagation list as completing work).

### When reprioritizing (allowed — often required)

Order in **Active queue** is **not frozen**. Move rows when dependencies, blockers, or new findings demand it — as long as **nothing falls off the radar**.

1. **Reconcile IDs first** — before changing order, list every `WQ-xxx` in Active + Inbox + Engineering backlog + Parked + Done. After edits, the same IDs must still appear in one of those sections (or **Superseded by WQ-yyy** in Notes with the replacement ID).
2. **Update the file** — reorder Active rows; change **Next** to exactly one row; add a **Notes** reason (`Moved up: blocks WQ-005`, `Blocked on WQ-201`, `Duplicate of WQ-003 — merged`).
3. **Inbox before Active** — new discoveries go to Inbox first; triage into Active (any position), Parked, or Done — do not jump straight into chat-only priority lists.
4. **Dependencies** — if task B must precede A, move B above A and note why. If work already committed makes A obsolete, move A to **Done** (with evidence) or **Parked**, not delete.
5. **Avoid duplicate WQ IDs** — before appending, scan Active + Inbox + Engineering for the same task; extend an existing row or note **Superseded** instead of parallel IDs.
6. **Chat/handoff** — may summarize the new **Next** ID only after `WORK_QUEUE.md` reflects the reorder.

**Hard invariant:** no row removed without landing in **Done**, **Parked**, or **Superseded by …** in Notes. Rewriting a status table or a chat bullet list is not a substitute.

### Status changes only

- Rewriting the handoff's status section or chat summaries **without** updating `WORK_QUEUE.md` is incomplete handoff.

## Separation of concerns

| Channel | Holds |
|---------|--------|
| `run_audit.cmd` report | Ephemeral **Fix** / **Improve** for that audit run |
| `WORK_QUEUE.md` → Engineering backlog | Recurring gaps worth scheduling (e.g. audit depth findings) |
| `ROADMAP.md` | Product features and phased plans |
| `docs/handoffs/SESSION.md` | Session **now** + pointers (no duplicate Next table) |
| Slice handoffs | Implement packet for one WQ row |

## Forbidden

- Replacing the user's queue in chat without updating `docs/WORK_QUEUE.md`.
- Marking handoff "done" while Inbox rows are untriaged.
- Inventing a new numbered list that conflicts with existing WQ IDs.
- **Deleting** a `WQ-xxx` row or dropping an ID from all sections during a reprioritization.
- Reordering in chat only — file must match before you report the new **Next**.

## Pack maintenance

Canonical copy: `pack/rules/generic-work-queue-discipline.mdc` — installed via `install.ps1`.  
Template: `pack/templates/docs/WORK_QUEUE.md.template` — bootstrap `-Targets` all layouts.  
**Verify:** `pack/scripts/verify-work-queue.ps1 -ProjectRoot PATH` (also in `verify-agent-setup.ps1` and behavior step 31).  
**Status alignment:** `pack/scripts/verify-complete-picture.ps1` (step 37) — see **`pack/docs/RULES_AND_VERIFY_MAP.md`**.  
**Backfill:** `ensure-work-queue.ps1` runs from `refresh-agent-context.ps1` when the file is missing.


---

## handoff-first

Source: `pack/rules/handoff-first.mdc`

# Handoff-first and "what's next?" (all projects)

Normative detail: **`pack/docs/AGENT_HANDOFFS.md`** § Session handoff.

## Canonical files

| File | Owns |
|------|------|
| `docs/handoffs/SESSION.md` | **Now** — where we left off, blockers, open items, pointers only |
| `docs/WORK_QUEUE.md` | **Priority/status** — one **Next**, Active, Inbox, backlog, Parked, Done |
| `docs/handoffs/active/HANDOFF_WQ*.md` | **How** to implement one WQ slice |

**Forbidden:** a second doc claiming **Next**, root session mega-docs (retired 2.22.65), chat-only priority lists.

## Project updated / new session

Read in order:

1. `docs/handoffs/SESSION.md` (if present)
2. `docs/WORK_QUEUE.md` (if present)
3. Active slice handoff if implementing
4. `AGENTS.md` / product docs as needed

## Trigger: "what's next?" (and equivalents)

Includes: **what's next**, **continue**, **pick up**, **updated project**, **where did we leave off**, **what remains**.

| Step | Read | If … then next is … |
|------|------|---------------------|
| 1 | **SESSION.md** | Open items or blockers → **stop here**; report and act on those |
| 2 | **WORK_QUEUE.md** | **Next** / untriaged Inbox → that (after SESSION clear) |
| 3 | Unplanned | Only if SESSION **and** WQ are clear — say so explicitly |

Report format: `Session handoff: … | WQ: … | Unplanned proposal: yes/no`.

## Interrupt rule (while on SESSION or WQ work)

Issues found during the slice (failing tests, verify, regressions, doc contradictions):

- **Fix or triage in the same session** when possible
- Large surprise → **WQ Inbox** row + note in **SESSION** blockers; do not jump to step 3
- Do not abandon a broken tree for greenfield ideas

## End of session

Update **SESSION.md** (evidence, blockers, open items, pointers). If WQ status changed, update **WORK_QUEUE.md** first, then align SESSION pointers in the same session.

Related: **`generic-work-queue-discipline.mdc`**, **`generic-agent-handoff-discipline.mdc`**.


---

## loop-back-protocol

Source: `pack/rules/loop-back-protocol.mdc`

# Loop-back protocol (all projects)

When the user **repeats** the same problem, error, or question — or shows frustration that nothing changed — **stop and loop back**. This applies to **every project**, not only audits.

## Triggers

- “Still broken”, “same error”, “you already tried that”
- “Anything else?”, “what did you miss?”, “check everything again”
- “Too fast”, “not deep enough”, “you didn’t actually do X” — run **`generic-deep-task-execution.mdc`**; do not ask the user to rephrase
- “We keep going in circles” / same goal asked again after you said done

## Required steps

1. **Conversation** — read/search from the **start of this workstream** (transcript, what failed before)
2. **Project docs** — `AGENTS.md`, README, design notes; **do not undo settled decisions** without user request
3. **Validate state** — tests, builds, or project verify scripts; compare repo to your assumptions
4. **Diff intent vs reality** — decided vs implemented vs still broken; flag **regressions**
5. **Proceed differently** — coordinated change; no blind retry of the same fix

Full detail: **`pack/docs/AGENT_WORKFLOW.md`** (starter pack) or `%USERPROFILE%\.cursor\AgentStarterPack\pack\docs\AGENT_WORKFLOW.md`

## Report format

- **Audits** → **Fix** and **Improve** only (skill `agent-code-audit`)
- **Other work** → project format, or: what was wrong, what you re-read, what you’ll do differently


---

## new-project-bootstrap

Source: `pack/rules/new-project-bootstrap.mdc`

# New Project Bootstrap

**Preferred (Cursor + all editor entry files):**

```powershell
& "$env:USERPROFILE\.cursor\AgentStarterPack\pack\scripts\bootstrap-project.ps1" `
    -ProjectRoot "D:\your\repo" -ProjectName "YourApp" -Stack Python -Targets All -NoPause
```

Or **`Bootstrap-Project.cmd D:\your\repo YourApp`** from the starter pack folder.

**Non-Cursor only (no editor-specific entry files):**

```powershell
& "$env:USERPROFILE\.cursor\AgentStarterPack\pack\scripts\bootstrap-project.ps1" `
    -ProjectRoot "D:\your\repo" -ProjectName "YourApp" -Stack Python -Targets Portable -NoPause
```

Or **`Bootstrap-Portable-Project.cmd D:\your\repo YourApp`**. Verify: `pack\scripts\verify-portable-bootstrap.ps1 -ProjectRoot D:\your\repo -RequirePortableOnly`

Guide: **`docs/PORTABLE_SETUP.md`** (any AI tool) and **`pack/docs/START_HERE.md`**.

```
project/
├── AGENTS.md
├── AI_INSTRUCTIONS.md
├── .cursor/rules/audit.mdc
├── docs/AUDIT.md
├── docs/WORK_QUEUE.md
├── docs/ROADMAP.md
├── run_audit.cmd
├── scripts/run_audit.ps1
├── run_tests.bat
├── build_ci.bat        # -Stack Python only
└── tests/
```

`-Stack` defaults to `Generic`, which skips `build_ci.bat`, `scripts/apply_version.py`,
`docs/VERSION_SYNC.json`, and the version-sync rule. Pass `-Stack Python` for the tree above.

## Checklist

1. **`Install-AgentStarterPack.cmd`** once per machine (global rules, skills, MCP)
2. **`bootstrap-project.ps1`** (or manual template copy from `pack/templates/`)
3. Customize **`docs/AUDIT.md`** domain map + **`docs/AUDIT.config.json`**
4. Wire version sync per `generic-version-sync.mdc` (Python `-Stack Python` does this)
5. Multi-step features: `generic-phased-feature-design.mdc` + `pack/docs/PHASED_FEATURE_DESIGN.md`
6. First **audit** → agent follows `docs/AUDIT.md`

See `pack/docs/AUDIT_SYSTEM.md`.


---
