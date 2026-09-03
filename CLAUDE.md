# Claude instructions — BSODAnalyzer

**Session start:** read **`docs/AGENT_SESSION_START.md`** when present (stale/fresh + required reads).

**Primary source:** read and follow **`AGENTS.md`** and **`AI_INSTRUCTIONS.md`** in this repository.

**Agent runs commands; user verifies outcomes** — run sync/tests/fixes yourself; report exit codes so the user can pivot. Do not ask them to type commands you can run.

## Audit (when user says "audit")

1. Run **`run_audit.cmd`** (full tests; never skip for a real audit)
2. Deep-scan every module in **`docs/.audit_domain_expanded.json`**
3. Fill **`docs/.audit_semantic_report.json`**; run **`scripts\verify_semantic_audit.cmd`**
4. Run **`scripts\finalize_audit.cmd`**
5. Report **Fix** and **Improve** only

Do not use Phase A/B, add-ons menus, or gate-only audits.

## Hygiene

Before/after long shell commands, prefer **agent-hygiene** MCP if configured (`agent_hygiene_full_check`).  
Without MCP: `%USERPROFILE%\.cursor\AgentStarterPack\pack\scripts\cleanup-orphan-processes.ps1`

## MCP (optional)

If Claude Desktop MCP is configured, see **`docs/portable/mcp-claude-desktop.json`** for the agent-hygiene server entry.  
Setup guide: starter pack **`docs/PORTABLE_SETUP.md`**.

## Multi-step features

One numbered phase list; do not skip phases. See starter pack **`pack/docs/PHASED_FEATURE_DESIGN.md`**.
