# AI agent instructions (all tools)

This repository is bootstrapped with the **Agent Starter Pack** so agents start with audit wiring, hygiene defaults, and clear workflows — not ad-hoc fixes later.

## Read first

0. **Session start:** read **`docs/AGENT_SESSION_START.md`** when present (stale/fresh verdict + required reads)
1. **`AGENTS.md`** — project-specific commands, audits, builds, version sync
2. **`docs/WORK_QUEUE.md`** — canonical task radar (stable WQ IDs; reorder allowed; nothing drops off)
3. **`docs/AUDIT.md`** — audit checklist (Fix + Improve only when user says **audit**)
4. **`docs/ROADMAP.md`** — parked **product** work (not the work queue; not audit Improve items)

Starter pack onboarding (install paths, pitfalls):  
`%USERPROFILE%\.cursor\AgentStarterPack\pack\docs\START_HERE.md`

Portable / multi-tool setup:  
`%USERPROFILE%\.cursor\AgentStarterPack\docs\PORTABLE_SETUP.md`

**Non-Cursor global rules (no `.mdc` auto-load):** read **`docs/portable/GENERIC_RULES.md`** in this repo first (synced on stack refresh); fallback: installed or checkout `pack/docs/portable/GENERIC_RULES.md`.  
Skills: **`docs/portable/skills/*.md`** (project copy) or `pack/docs/portable/skills/*.md`. Regenerate pack export via `pack\scripts\sync-portable-docs.ps1`.

## On refresh

Trigger phrases (also in `docs/AGENT_CONTEXT.json`): **refresh pack context**, **sync agent context**, **context refresh**, **pack update**.

When any of those apply — or this chat stayed open across a pack update — read **`docs/AGENT_REFRESH.md`**, then every path in **`requiredReads`** inside `docs/AGENT_CONTEXT.json` (absolute paths; use them even if the editor workspace is a parent folder). Reply with the **pack version** and **audit engine version** you read (handshake).

**MCP (agent-hygiene):** `check_pack_freshness` and `get_agent_refresh_brief` return the same contract without pasting.

When an audit reports **Agent context stale / never refreshed / unreadable**, do not hand the user a command to type: **offer to run `Refresh-AgentContext.cmd` for this project yourself** (or `Update-AgentStack.cmd` when install + refresh together). Run it once they approve, then read the regenerated brief in the same turn. Any agent host that can run a shell command with user consent can do this — approving a proposed command is the whole interaction. It writes `docs/` artifacts and syncs this project's rules and audit files from the installed pack; it does not touch the user profile unless run with `-Install`.

## Agent runs commands (user verifies)

**You run commands; the user verifies outcomes.** Report paths, exit codes, and key output so they can see what happened and pivot. Do not ask the user to type fix/sync/test commands you can run in this session. Portable copy of the full rule table: **`docs/portable/GENERIC_RULES.md`** (this repo) section **agent-defaults-always** (*Fixes the agent runs*).

Upgrade overview: `%USERPROFILE%\.cursor\AgentStarterPack\docs\AGENT_UPGRADE_PATH.md` (or the project's copy after audit sync).

## Non-negotiables

- **Audits:** run `run_audit.cmd` (full tests); report **Fix** and **Improve** only — no Phase A/B or add-ons menus. **Non-Cursor:** read `docs/portable/skills/agent-code-audit.md` (or the installed pack mirror) before claiming audit complete.
- **Multi-step work:** one phased plan; runtime order = build order (`PHASED_FEATURE_DESIGN.md` in starter pack)
- **Work queue:** read `docs/WORK_QUEUE.md` before changing priorities; update it when order or scope shifts (`generic-work-queue-discipline.mdc`)
- **Loop-back:** if the user repeats the same error, re-read the thread and repo before retrying
- **Long shell commands:** use agent-hygiene MCP when available (`agent_hygiene_full_check`)
- **Windows agent builds:** `BUILD_NOPAUSE=1` or `build_ci.bat` — never leave batch files on `pause`

## Tool-specific entry points

| Tool | File in this repo |
|------|-------------------|
| Cursor | `.cursor/rules/*.mdc` + global skills |
| Claude Desktop | `CLAUDE.md` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Windsurf | `.windsurfrules` |
| Any other agent | This file + `AGENTS.md` |

## Reference

**Bootstrapped app pattern:** audit + version sync + phased plans — see `docs/PORTABLE_SETUP.md` and `pack/audit/behavior-fixture/`.
