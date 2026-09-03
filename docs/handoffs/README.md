# Handoffs — BSOD Analyzer

**Pack baseline:** `C:\Users\binar\.cursor\AgentStarterPack\pack\docs\AGENT_HANDOFFS.md`

## Project policy (overrides pack archive)

Handoffs are **temporary**. They exist only to catch the next agent up on *now* and how to implement the current slice. **Delete them when the slice is Done** — do not move them to an archive folder. Durable record lives in **`WORK_QUEUE.md`** Done log (process) and **`ROADMAP.md`** (product).

| Location | Purpose | When done |
|----------|---------|-----------|
| [`SESSION.md`](SESSION.md) | Session catch-up — blockers, pointers | Rewrite each session; trim shipped bullets |
| [`active/HANDOFF_WQnnn_*.md`](active/) | Build slice — one active WQ row | **Delete file** after WQ → Done + evidence in queue |
| [`../upgrade/BUILD_HANDOFF.md`](../upgrade/BUILD_HANDOFF.md) | Upgrade build gate (permanent process) | Keep — not a status handoff |

**Forbidden:** standing status handoffs, orientation handoffs that duplicate `DESIGN_TIERS.md`, or `handoff_archive/` folders.

**Rules:** `generic-agent-handoff-discipline.mdc` · one session opener line per active handoff.

**Session opener (continue / what's next):**

`Read C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\handoffs\SESSION.md and confirm.`
