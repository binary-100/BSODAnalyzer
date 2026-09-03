# Build handoff — implementation agents

**Use when promoting a slice from Tier 3 → Build (work queue).**

Parent: [`README.md`](README.md) · Tiers: [`DESIGN_TIERS.md`](DESIGN_TIERS.md) · **Handoff convention:** [`../handoffs/README.md`](../handoffs/README.md) · pack `AGENT_HANDOFFS.md`

Last updated: **2026-08-30**

---

## Before you touch product code

All must be true:

- [ ] User promoted item to **ROADMAP work queue** (Approved intent alone is not enough)
- [ ] **`docs/handoffs/active/HANDOFF_WQnnn_<slug>.md`** exists with registry table + **one session opener** line
- [ ] User named **PLAN file** under `docs/upgrade/plans/`
- [ ] User named **phase ID** (e.g. `D1`, `G1`, `M1–M4`) — one phase per session unless user says otherwise
- [ ] `upgrade-planning-only` rule is **off** (or fresh implementation chat)

---

## Authoring a build handoff (planning agent)

1. Copy fields from [`../handoffs/README.md`](../handoffs/README.md) and pack `HANDOFF_BUILD.md.template`.
2. Set registry: `kind: build`, `status: active`, `wq_id`, `plan`, `phases`.
3. Put **one session opener** in the handoff file — full absolute path, `and implement.`
4. Point **WORK_QUEUE** and **ROADMAP** at the handoff path — not a paste block in chat.

**Human gives the other agent only the session opener line** from the handoff file.

---

## Examples (PLAN + phases)

| Task | PLAN | Phase | Handoff file |
|------|------|-------|--------------|
| WinDbg replacement parity harness | `NATIVE_DUMP_ENGINE_PLAN.md` | D1 | `HANDOFF_WQnnn_native_dump_d1.md` |
| Plain-language Summary | `GUIDED_DIAGNOSTIC_PLAN.md` | G1 | `HANDOFF_WQnnn_guided_g1.md` |
| Offline target volume | `RESCUE_USB_PLAN.md` | 9a | `HANDOFF_WQnnn_rescue_9a.md` |
| PC-local data (Maintenance USB) | `MAINTENANCE_USB_DATA_PLAN.md` | M1–M4 | ☑ Done — see WQ-001 in [`WORK_QUEUE.md`](../WORK_QUEUE.md) |

---

## After phase ships

See **`docs/WORK_COMPLETION.md`** (project) and pack **`pack/docs/WORK_COMPLETION.md`**.

1. Mark phase ☑ in the PLAN doc.
2. Update [`ROADMAP.md`](../ROADMAP.md) if work queue row completes.
3. Move WQ row to **Done** with evidence (tests, paths, commit).
4. **Delete** `docs/handoffs/active/HANDOFF_*.md` for that slice — handoffs are temporary; Done log is the record.
5. Update [`PRODUCT_REFERENCE.md`](../PRODUCT_REFERENCE.md) when **user-visible** behavior changes.
6. Run applicable validation per `AGENTS.md` / `AGENT_READINESS.md`.

---

## Isolation rules

| OK in Build | Forbidden without user ask |
|-------------|----------------------------|
| Edit source, `tests/`, `scripts/` for **assigned phase only** | Whole upgrade in one PR |
| Add tests for assigned phase | Wire all PLAN phases at once |
| Spike learnings **reimplemented** cleanly | Copy `plans/spikes/` into production |
