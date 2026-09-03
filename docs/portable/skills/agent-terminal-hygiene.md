# Skill: agent-terminal-hygiene

Auto-generated from `pack/skills/agent-terminal-hygiene/SKILL.md`. **Do not edit by hand.**

Pack version: 1.8.0

---

# Agent Terminal Hygiene

## Diagnosis order

1. **Full check (preferred)** — MCP `agent_hygiene_full_check` (terminals + orphans)
2. **Process alive?** `Get-Process -Id <pid>` (Windows) or `ps -p <pid>` (Unix)
3. **Terminal log complete?** Read `terminals/*.txt` — look for footer `exit_code:`
4. **Orphan children?** After `taskkill` on a parent shell, py/python children often survive
5. **Output ends on `pause` / `Press any key`?** Process may be waiting for input

## Actions

| Situation | Action |
|-----------|--------|
| Full hygiene pass | MCP `agent_hygiene_full_check` |
| Orphan py/python after killed terminal | MCP `scan_orphan_agent_processes` then `cleanup_orphan_agent_processes` (`dry_run=True` first) |
| No MCP available | `pack/scripts/cleanup-orphan-processes.ps1` (add `-Kill` to terminate) |
| Process running, unwanted | `Stop-Process -Id <pid> -Force` or MCP `kill_terminal_process` |
| Process dead, log missing footer | Run `pack/scripts/fix-stale-terminal.ps1` on project |
| Build script for agent | `set BUILD_NOPAUSE=1` then `call build_ci.bat` |
| Cursor UI still spinning | Tell user: Kill Terminal tab (agent cannot dismiss UI) |

## Prevent recurrence

- Use `build_ci.*` templates with `if "%BUILD_NOPAUSE%"=="" pause`
- Agent always sets `BUILD_NOPAUSE=1` for automated builds
- Avoid `read -p`, `pause`, interactive prompts in CI/agent paths

## Stale metadata explained

Cursor agent reads `terminals/<id>.txt`. If a session ends without writing `exit_code`, the header may still show `running_for_ms`. That is **stale metadata** — not necessarily a live hang.

## Orphan processes explained

Force-killing a terminal parent (`exit_code: 4294967295`) often leaves **child** `python.exe` / `py.exe` processes running (blocked on GUI, I/O, etc.). They use near-zero CPU but never exit. Always scan orphans after killing a hung test or build shell.

**Protected from cleanup:** `agent_hygiene_server` (this MCP server).
