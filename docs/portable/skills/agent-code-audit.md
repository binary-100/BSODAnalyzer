# Skill: agent-code-audit

Auto-generated from `pack/skills/agent-code-audit/SKILL.md`. **Do not edit by hand.**

Pack version: 1.8.0

---

# Agent Code Audit

Read **`docs/AUDIT.md`** first. Its **`## Checklist sections`** are the required sections for this
project — the letters differ per project, so scan the ones that file defines rather than assuming a
range.

## Complete audit = machine + deep scan (same session)

| Step | Required work |
|------|----------------|
| 1 | **`run_audit.cmd`** — runs the project's full test command (`tests.script` in `docs/AUDIT.config.json`); never `-SkipTests` |
| 2 | Read **`docs/.audit_inventory.json`** + **`docs/.audit_domain_expanded.json`** (auto-generated) |
| 3 | **Deep scan** — inventory, §2/§2b static analysis, **open every module in expanded domain map** |
| 4 | **`docs/.audit_semantic_report.json`** — `testsGitHead` from manifest; `modulesReviewed[]` for domain-map modules **and** checklist path sections (pack: **E**, **H**, **I**); `inventoryAck` on B |
| 5 | **`scripts\verify_semantic_audit.cmd`** — exit 0 |
| 6 | **`scripts\finalize_audit.cmd`** — exit 0 |
| 7 | Report **only** Fix and Improve to user |

## Product-truth on a closing slice (Step 3d)

When the audit finds **product-truth** docs contradict **shipped** behavior (capability/limitation prose vs code, Done **WQ** still reads not built/deferred, ROADMAP **Next** for a Done id), and the user is **closing a slice** (`WORK_COMPLETION` Step 3):

- Report **Fix** — not Improve — until prose matches shipped behavior or the WQ row is corrected.
- Recurring drift with **no active slice** may stay **Improve** (backlog / awareness).

Mechanical backstop: `verify-complete-picture.ps1` and `verify-product-truth-paths.ps1` (Step 5b / Update-AgentStack `-VerifyOnly`).

**Forbidden:** bulk `"Nothing found."`; missing `modulesReviewed[]`; stale semantic before test pass; gate-only.

## Section B layout pass (mandatory)

Machine checks in B answer "delete this." They never answer "can a newcomer tell what these folders
are?" Do this pass before writing B's summary, even when `machineFixesBySection.B` is empty:

1. Read the project's layout doc (`PROJECT_LAYOUT.md`, or `layoutPolicy.glossaryDoc` in `docs/AUDIT.config.json`) and compare it to the actual tree.
2. Locate the folders that hold **build output**, **runtime user data**, and any **release/archive copy**. Names that read as separate products, or one dirname used in two roles, are findings.
3. Read `machineImprovesBySection.B` in `docs/.audit_agent_manifest.json` and address every line.
4. Report **Improve** for naming confusion, a missing or outdated glossary, redundant copies, and workflows that recreate what the checklist forbids.
5. Report **Fix** only when layout breaks a build or test, commits build output, or contradicts the committed checklist.

**Forbidden:** closing B with "removed `dist/`" when the glossary, duplicate copies, or a script that
recreates a forbidden path were never examined. Ephemeral dirs reappear on the next build — deleting
them is not a permanent fix, so say so rather than reporting it as closed.

The audit **reports**; it never deletes folders or asks for cleanup permission. Acting on layout is
project work the user schedules.

## Output (only this)

```markdown
## Fix
...

## Improve
...
```

## After fixes

Re-run **`run_audit.cmd`** if production code changed; else semantic + finalize (only if tree fingerprint unchanged).
