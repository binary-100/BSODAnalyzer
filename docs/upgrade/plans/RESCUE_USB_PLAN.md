# Rescue bootable USB — design plan (Tier 3)

**Status:** Draft · **Tier 2:** ROADMAP **Approved intent** · **Not buildable until work queue + user approval**

| | |
|---|---|
| **Index** | [`NEXT_UPGRADE_INDEX.md`](NEXT_UPGRADE_INDEX.md) |
| **Related** | [`NATIVE_DUMP_ENGINE_PLAN.md`](NATIVE_DUMP_ENGINE_PLAN.md), [`GUIDED_DIAGNOSTIC_PLAN.md`](GUIDED_DIAGNOSTIC_PLAN.md) |

Last updated: **2026-08-24**

---

## Goal

Boot from USB → automatically find the **internal Windows install** (not the USB OS) → read crash evidence → run diagnostics → download drivers over **host NIC** (Ethernet/WiFi) → install into **target Windows** using Windows servicing semantics (Driver Store / DISM offline).

## Non-goals

- Repair non-Windows OSes (v1)
- Auto-flash BIOS/firmware from rescue (download-only policy unchanged)
- User must hunt drive letters manually (auto target resolver required)

---

## Options considered

**Boot environment decision:** **OPEN** — see [`RESCUE_BOOT_ENVIRONMENT.md`](RESCUE_BOOT_ENVIRONMENT.md) (Linux lean, WinPE, hybrid). Phases 9a–9c are **boot-agnostic**; 9d–9h fork after decision gate.

| Option | Pros | Cons | Status |
|--------|------|------|--------|
| **Linux live (primary)** | Generic NIC, OSS-friendly, native dump fits | Offline Windows driver install needs hybrid/staging | **Lean** |
| **WinPE rescue** | DISM/pnputil native | NIC injection, ADK, redistribution | **Candidate** |
| **Hybrid (Linux diagnose + WinPE apply)** | Best of both | Two images, UX complexity | **Candidate** |
| **Windows Safe Mode + portable exe** | Reuses today’s app | Doesn’t help when Windows won’t boot | **Bridge (9a in running Windows)** |

---

## Phased checklist

Runtime order = build order. ☑ only when shipped.

| Phase | Name | Required | Status |
|-------|------|----------|--------|
| **9a** | Target volume detection in **running** Windows (`--target-root`, auto-exclude USB) | yes | ☐ |
| **9b** | Offline log + minidump paths (evtx, `%SystemRoot%` layout on mounted volume) | yes | ☐ |
| **9c** | Target resolver UX — confidence score, multi-install picker | yes | ☐ |
| **9d** | Rescue media builder v1 — USB layout (boot OS **TBD** — see [`RESCUE_BOOT_ENVIRONMENT.md`](RESCUE_BOOT_ENVIRONMENT.md)) | yes | ☐ |
| **9e** | Rescue shell v1 — auto-launch app; network (Linux **or** WinPE per decision) | yes | ☐ |
| **9f** | Offline driver staging — `DISM /Add-Driver` to target image | yes | ☐ |
| **9g** | Rescue catalog mode — download tiers with offline honesty | yes | ☐ |
| **9h** | WiFi + NIC driver injection matrix | optional | ☐ |

---

## Target Windows resolver (9a/9c)

**Signals:** `\Windows\System32\config\SYSTEM`; boot BCD association; `\Windows\Minidump\`, WER paths; `\Users\` profile recency.

**Exclude:** USB rescue volume, WinRE 450MB partitions, stale `Windows.old` unless user selects.

**UX:** “Repair target: Windows 11 on Disk 0 — C: when booted” + override dropdown.

---

## Offline driver install (9f)

| Running target Windows | Offline target (rescue) |
|------------------------|-------------------------|
| `pnputil /add-driver` (today) | `DISM /Image:<TargetRoot>\ /Add-Driver /Recurse` |

UI must distinguish **staged for next boot** vs **applied now**.

---

## Open questions

- Secure Boot support required?
- USB size budget (8 vs 32 GB with driver packs)?
- Dual-boot: v1 best-guess only or always prompt?

---

## Risks (implementation)

| Risk | Mitigation |
|------|------------|
| Wrong disk selected | Confidence + confirm; no destructive default |
| WiFi fails in WinPE | Wired-first; degraded analysis-only mode |
| Offline install bricks boot | Driver backup journal on target; staged-only default |

---

## Handoff

```
Implement Phase 9a only. Read `docs/upgrade/plans/RESCUE_USB_PLAN.md`.
Requires Native Dump offline adapters for 9b — coordinate with NATIVE_DUMP_ENGINE_PLAN Phase D2b.
Do not start WinPE (9e) until 9a–9c validated in running Windows.
```
