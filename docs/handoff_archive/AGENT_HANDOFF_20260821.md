# Agent handoff — BSOD Analyzer (2026-08-21)

**Supersedes:** [`AGENT_HANDOFF_20260820.md`](AGENT_HANDOFF_20260820.md) for *session state*. That
file's **product** content (component-install model §4, communication rules §5, field-test
checklist §6, catalog backlog §7) is still current — read both.

**Purpose:** Onboard the next agent after a **test-harness trust + latent-bug** workstream.
This session did **not** touch catalog fine-tuning. It made a green suite mean what it says,
then fixed the bugs a green suite had been hiding.

| | |
|---|---|
| **Canonical version (source)** | [`bsod_analyzer.py`](../bsod_analyzer.py) → see [`VERSION.txt`](../VERSION.txt) (**6.5.23+** at last doc refresh) |
| **Built portable** | [`BSODAnalyzer_v6/BSODAnalyzer.exe`](../BSODAnalyzer_v6/BSODAnalyzer.exe) — rebuild with `build_ci.bat` after dependency-install changes |
| **Suite** | **144** test files · **1,124** tests · `run_tests.bat` exit 0 · ~4–5 min |
| **Field-test machine** | Alienware **m17 R5 AMD** (portable USB) — 6.5.7 sign-off still **pending** |
| **Host** | User runs **Cursor as Administrator** — agent shell is elevated |
| **Git** | `app/` tree **still entirely untracked**. Nothing from this session is committed. |

**This file:** `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\AGENT_HANDOFF_20260821.md`

---

## 0. Read in this order

| # | Read | Full path | Why |
|---|------|-----------|-----|
| 1 | **This handoff** | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\AGENT_HANDOFF_20260821.md` | Session state, what changed, next steps |
| 2 | **Harness plan** | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\TEST_HARNESS_PLAN.md` | **Full technical detail** of everything summarised here — every bug, cause, and fix |
| 3 | Prior handoff | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\AGENT_HANDOFF_20260820.md` | Component-install model, user communication rules, field checklist §6 |
| 4 | Agent entry | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\AGENTS.md` | Commands, version sync, new **§ Tests** section |
| 5 | Product truth | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\PRODUCT_REFERENCE.md` | What ships; §2 agent obligations (run validation yourself) |
| 6 | Readiness | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\AGENT_READINESS.md` | Priority order, validation tiers, Qt/widget-lifetime rules |
| 7 | Doc index | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\DOC_MAP.md` | Which doc owns what |

Only on demand: `KNOWN_LIMITATIONS.md`, `ROADMAP.md`, `CATALOG_MODULE_SPLIT.md`,
`FACADE_ORCHESTRATION.md`, `AUDIT.md`.

---

## 1. Why this session happened

The user asked for a **fresh, independent audit** — explicitly *not* the built-in
`run_audit.cmd` — including a look at the audit system itself. That found one dominant
problem, and everything else followed from it.

**`run_tests.bat` had no test discovery.** It ran each file through
`runpy.run_path(run_name="__main__")`, so a file executed only the test functions its own
hand-written `if __name__ == "__main__":` block happened to list.

| Metric | Before |
|--------|------:|
| Test functions defined | 1,038 |
| **Never executed** | **139 (13.4%)** |
| Files that ran **zero** tests and still printed `OK` | **7** |
| Files with a partial call list | 17 |

Two further gate holes compounded it:

1. `if errorlevel 1` in cmd means **"≥ 1"**. An interpreter crash returns a *negative* code,
   so three GUI files that died on `0xC0000409` printed `OK`.
2. pytest's progress line has no trailing newline, so `echo FAILED: %~1` appended to it
   (`....F.FAILED: tests\...`). A log scan anchored at line start missed those verdicts,
   hiding two more failing files.

And **no static analysis had ever been run on this codebase.** pyflakes found 14 undefined
names in about three seconds.

The audit system's machine checks are regex + import-smoke only, which is why all of this
passed every prior audit.

---

## 2. What changed — five phases, all complete

Plan of record with full detail: **`docs\TEST_HARNESS_PLAN.md`**.

| Phase | Work | Status |
|-------|------|--------|
| 1 | pytest discovery, per-file isolation preserved; `run_tests.bat` exit-code + newline fixes; `tests/test_test_discovery.py` guard | ☑ |
| 2 | Triage the 15 files that failed once they actually ran | ☑ |
| 3 | pyflakes static gate as a real test (`tests/test_static_analysis.py`) | ☑ |
| 4 | Fix every bug the gates exposed + regression tests | ☑ |
| 5 | T2/T3/T4 validation + doc sync | ☑ |

### 2.1 New permanent gates (do not remove)

| File | Guards |
|------|--------|
| `tests/test_test_discovery.py` | Every defined test is collected; no duplicate test names; no non-fixture args; no collection import errors |
| `tests/test_static_analysis.py` + `tests/static_analysis.py` | pyflakes: undefined names, **star-import resolution**, dict literals with shadowed keys, and that the gate's own file list has not shrunk |
| `run_tests.bat` `:run_one` | Compares `%ERRORLEVEL%` to `0` explicitly, prints the code, emits a newline before the verdict |
| `conftest.py` · `pytest.ini` | Qt plugin bootstrap before PySide6; one process per file (tests share module-level caches) |
| `requirements-dev.txt` | `pytest` + `pyflakes` declared **outside** `requirements.txt` so nothing test-only reaches the PyInstaller bundle |

### 2.2 The star-import discovery — read this before "fixing" the GUI mixins

The old plan said the only way to gate `from gui_app_context import *` (≈25 mixins) was a
25-file refactor to explicit imports. **That is wrong, and the refactor is not needed.**
pyflakes still *names* every unresolved symbol; it only softens the verdict to "may be
undefined, or defined from star imports". Importing the hub and checking each name against
`dir(gui_app_context)` restores a real assertion:

| Star-import name references | Resolve in the hub | Do not |
|----------------------------:|-------------------:|-------:|
| 1,402 | 1,398 | **4** |

All four were live bugs (see §2.3, `mlog`). **Leave the star imports alone** — coverage is
already there.

### 2.3 Product bugs fixed (all were reachable by real users)

Roughly split: the first group is from Phase 2 triage, the second from the Phase 3 gate.

| Location | Defect | Who hit it |
|----------|--------|------------|
| `catalog_row_rejects.py` / `catalog_oem_filters.py` | PC-maker OEM rules also judged **Windows Update** rows. The final rule ("row has a version → reject") matches nearly every WU row, so `_wu_device_match_score` returned `-1` | **Every attached device**: external-monitor SWC children, USB audio, docks, peripherals got **no Microsoft offer**. Integrated PCI/ACPI silicon was unaffected, which is why it survived field use. Fixed per the user's chosen scope: gate the OEM-only rules behind `_row_is_oem_sourced` |
| `catalog_mscatalog_session.py` | `begin_batch_mscatalog_query_cache` **rebound** the global dict; facade re-exports kept the stale one | Warmed MSCatalog queries re-issued every scan — pure wasted scan time |
| `crash_report_format.py`, `gui_mixin_analysis.py` | `d['size_mb']` on a partial dump entry | `KeyError` aborted the whole report |
| `firmware_catalog.py` | Literal `"msi"` check, but WMI reports `Micro-Star International Co., Ltd.` | **All MSI boards** got no motherboard support link. Now uses `dc._manufacturer_matches` |
| `vendor_fetch.py` | When all fetch steps failed, `run_steps` returned that **vendor's last successful value**; the key is the vendor name alone | A second AMD/Intel device inherited the first's version, and `vendor_endpoint_health` derives `ok` from it — a dead endpoint reported healthy |
| `catalog_device_context.py` | `_realtek_catalog_name_aliases` pre-seeded `seen` with the device's own name, discarding it | A codec Windows names plain `Realtek Audio` never inherited its parent HDAUDIO hardware ID — lost HWID verification for its WU offers |
| `catalog_scoring.py` | Realtek NIC bump with identical build suffix forced to `uncertain` | Legitimate OEM revision bumps reported as unknown |
| `bsod_events.py:523` | `_summarize_livekernel_message` not imported | **Any PC with a LiveKernel event.** `analyzer_gather` catches per-future, so the whole reliability bundle — LiveKernel events, WER errors, stability index — became `_query_failed` + a data gap. Dev host has zero LiveKernel events, which is why it never showed here |
| `crash_report_format.py:253` | `list(...)` closed one paren early → `.get` ran on a **list of dict keys** | Every KernelPower **Event 41** without a repair narrative: `AttributeError` inside Quick Answer, the unexpected-shutdown path |
| `crash_report_fix_plan.py:637,649` | `urllib` never imported | NVMe storage search link + WHEA component search link — the fix plan for storage and hardware-error crashes |
| `catalog_download.py:208` | `sys` never imported | Download on a Windows Update **optional-updates** row (deep-links to `ms-settings:`) |
| `bsod_hardware_wmi.py:1210` | `resolve_device_display_label` not imported | A problem device the enrichment index can't match — **unhandled**, so the whole Drivers-tab hardware scan fails |
| `catalog_chipset_comparison.py:213,215` | `_NETWORK_VENDOR_KEYS` / `_EXTENDED_VENDOR_KEYS` undefined | The PC-level HTTP gate for **every vendor outside intel/amd/nvidia/realtek**: Killer, Broadcom, Qualcomm, MediaTek, TP-Link, Logitech, Samsung, Netgear |
| `gui_mixin_firmware_scan.py:414` | 2-name unpack of a 3-tuple | **Every** Firmware-tab Download click: `ValueError` right after the confirmation dialog |
| `gui_mixin_maintenance.py` ×3, `gui_mixin_catalog_shell.py:562` | `mlog` never exported by `gui_app_context`; `maintenance_log` had **no importer anywhere** | **Activity history** dialog, maintenance report, manual driver-database refresh — all raised `NameError`. Fixed by exporting the alias from the hub |
| `bsod_events.py:154,194` | Naive event-log strings tagged UTC | See §2.4 |
| `bsod_hardware_wmi.py` `KNOWN_VENDORS` | Six keys mapped twice with **conflicting** canonicals | See §2.5 |
| `driver_install.py:453-454`, `gui_mixin_catalog_shell.py:85-90` | Orphaned function tails from module splits; one duplicated `find_inf_dirs_for_hwid_tokens`'s last two lines, the other swallowed its `NameError` in a bare `except` | Dead code, deleted |

### 2.4 Event times were local, labelled UTC

Every query in `bsod_events.py` renders `TimeCreated` with `ToString('yyyy-MM-dd HH:mm:ss')`,
which .NET emits in **local** time. `_parse_event_time` tagged those naive strings
`timezone.utc`, so:

- `compute_crash_timeline` compared local-as-UTC instants against a true-UTC `now`, shifting
  every crash by the machine's offset — at UTC−7, seven hours older than reality, enough to
  move events across the 7-day and 30-day boundaries.
- The label read `2026-08-09 03:14 UTC` for a crash the user saw at **03:14 their time**.
- `fix_progress` compares `last_crash_dt.date()` against driver package dates, so the offset
  could shift that by a day.

Naive strings now become aware local (`dt.astimezone()`); explicit offsets preserved; the
label drops the false suffix. **API change:** `fix_progress.parse_last_crash_utc` →
**`parse_last_crash_time`**. It still accepts old ` UTC`-suffixed labels persisted in saved
models — those readings were local all along.

### 2.5 `KNOWN_VENDORS`: 165 entries, 150 distinct keys

Two eras of edits left `tp-link`/`tplink`, `d-link`/`dlink`, `c-media`/`cmedia` mapped twice
with **conflicting** canonicals (hyphenated early, unhyphenated late). Later wins, and the
codebase gates on the unhyphenated form — `catalog_extended_fetch` compares `vendor_key`
against the literal `"tplink"`. So behaviour was *accidentally* correct and the hazard was
latent: deleting the "duplicate" would have silently killed TP-Link peripheral lookups.
Collapsed to one entry per key, canonical values unchanged, and `MultiValueRepeatedKeyLiteral`
is now gated.

### 2.6 Qt crashes were object lifetime, never product code

`0xC0000409` is Qt aborting. Four files, three causes — none of which the old runner could
report:

| Cause | Fix |
|-------|-----|
| `QProxyStyle` took ownership of `app.style()` and deleted the application's live style on GC | Give the proxy its own `QStyleFactory` base |
| Parentless widget outlived `QApplication` teardown | New **`offscreen_widget()`** in `tests/gui_test_harness.py` |
| `MainWindow` built by hand with no teardown | Use existing **`offscreen_main_window()`** |
| `QPixmap`/`QIcon` built with **no `QApplication` at all** | Module fixture / `offscreen_widget` |

**Rule for future tests:** never construct widgets directly — use the harness helpers.

### 2.7 Two recurring test-side causes (not product defects)

Most of the 12 `test_driver_catalog_quality` failures were one of these. Expect them again:

1. **Offers with no fetchable package.** A versioned offer whose row carries no installer is
   deliberately `uncertain`, and an uncertain vendor row is dropped from display. Fixtures
   asserting `newer` from a bare `{source, title, version}` row were testing a rule the
   product replaced. Give the row a real `url`.
2. **Facade drift.** Patching a `driver_catalog` re-export **never** intercepts a
   module-internal call. Six tests patched `dc._manufacturer_catalog_tasks_for_ctx` while
   `catalog_device_comparison` calls it as a module-level name — so those tests hit **live
   vendor endpoints** and asserted against whatever the internet returned that day. Same for
   `catalog_download.download_file_to_folder` (a real `dl.dell.com` download) and
   `catalog_amd_fetch._amd_fetch_page_html`. **Always patch the defining module.**

Two more tests were **host-dependent**, reading this machine's real AMD versions
(Adrenalin 26.7.1, chipset 8.08.12.551) for the same reason.

---

## 3. Validation evidence (this session, on the dev host)

| Tier | Command (cwd `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\app`) | Result |
|------|------------------------|--------|
| **T2** | `run_tests.bat` | **exit 0** — 129 files, 0 failures, 1,057 tests (2026-08-21 rebuild) |
| **T3** | `scripts\verify_facade_gate.cmd` | run after substantive facade edits |
| **T4** | `py -3 scripts\live_validate_analysis.py` (admin) | **exit 0** post-6.5.8 build |
| **Build** | `build_ci.bat` with `BUILD_NOPAUSE=1` | **6.5.8** portable smoke OK (~07:02 local) |

Each of the 11 regression tests in `tests/test_undefined_name_regressions.py` was verified to
**reach the defective line**: the restored name was deleted and the original exception
confirmed to return. Do the same for any new regression test here.

Not run: **T5** perf spot-check (`compare_catalog_scan_timings.py`) — no catalog hot-path
change was intended, but the MSCatalog cache-drift fix in §2.3 should *reduce* scan time, so
a before/after read is worth having once there is a fresh scan to compare.

---

## 4. Where to go from here

Ordered. **P0 rebuild + version bump — done 2026-08-21** (see header table).

| Priority | Work | Status |
|----------|------|--------|
| **P0** | Rebuild portable **6.5.8** | ☑ `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\BSODAnalyzer_v6\BSODAnalyzer.exe` (~07:02) |
| **P0** | Version bump to **6.5.8** | ☑ source + `VERSION.txt` synced |
| **P0** | **Decide the git question with the user.** Entire `app/` tree untracked; only commit when user asks | ☐ open |
| **P1** | **Field-verify on m17 R5** — `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\AGENT_HANDOFF_20260820.md` §6 | ☐ pending user |
| **P1** | Catalog backlog: Dell DUP `-s` extract; install confirm "component-only"; chipset per-component compare | ☐ |
| **P2** | Wire harness gates into `run_audit.cmd`; update `AUDIT.md` | ☐ |
| **P2** | pyflakes unused-import cleanup (980) — separate pass | ☐ defer |
| **Defer** | P2a disk cache, P2b deferral | user rejected |

---

## 5. Things that will bite you if you don't know them

1. **Patch the defining module, not the facade.** See §2.7. This is the single most common
   defect in this test suite's history.
2. **Never construct Qt widgets directly in a test.** `offscreen_widget()` /
   `offscreen_main_window()` from `tests/gui_test_harness.py`. Direct construction aborts
   the process at teardown and, until this session, printed `OK`.
3. **Wrapped report text.** Report assertions must use `report_contains()` from
   `gui_test_harness.py` — literal `in` checks break when the formatter wraps a line.
4. **`run_tests.bat` is the only sanctioned full run.** It sets `PYTHONSTARTUP` and the Qt
   plugin path. Bare `py -3 tests\test_x.py` triggers a native Qt platform-plugin dialog on
   Windows. Targeted runs: `py -3 tests\run_test_module.py tests\test_<area>.py`.
5. **The suite is offline-clean now** — if a test starts emitting `HTTPError` or
   `ResourceWarning`, a mock is targeting the wrong object and it is reaching the real
   internet. Treat that as a failure, not noise.
6. **Agent obligations** (`PRODUCT_REFERENCE.md` §2): run tests, builds, and live validation
   **yourself**. Never hand the user a homework list. Host shell is elevated.
7. **Communication rules** from `AGENT_HANDOFF_20260820.md` §5 still apply — scan-time tables
   must say **Saves time / No meaningful change / Costs time**, never a bare magnitude.
8. **Audit Improve ≠ ROADMAP backlog** — `AGENT_READINESS.md` § Audit findings reconciliation.

---

## 6. Docs updated this session

| File | Change |
|------|--------|
| `docs\TEST_HARNESS_PLAN.md` | **Primary record.** All five phases closed with causes, evidence, and counts |
| `docs\AGENT_READINESS.md` | § Tiered validation: pytest discovery, standing gates, corrected suite size (129 files / 1,057 tests / ~4–5 min). § Qt test bootstrap: `conftest.py`/`pytest.ini` layers, `:run_one` exit codes, widget-lifetime rule |
| `AGENTS.md` | New **§ Tests** — discovery is pytest, the two standing gates, harness helpers |
| `docs\DOC_MAP.md` | Indexed `TEST_HARNESS_PLAN.md`; added the three new test artifacts to § Code & script awareness |
| `requirements.txt` / `requirements-dev.txt` | Split dev tooling out of the runtime deps |
| `docs\PRODUCT_REFERENCE.md` | 6.5.8 capabilities: pytest gates, WU attached-device fix, event times, MSCatalog cache |
| `docs\IMPROVEMENT_BACKLOG.md` | Points to 20260821 handoff; 6.5.8 build status |
| `docs\AGENT_HANDOFF_20260820.md` | §6 merged field checklist; build status → 6.5.8 |
| **This file** | Session handoff; §4 P0 rebuild done |

Not touched: `KNOWN_LIMITATIONS.md`, `ROADMAP.md`.

---

## 7. One-paragraph summary

BSOD Analyzer's test suite reported `OK` while 139 of 1,038 tests never ran, three files
crashed the interpreter, two more hid their verdict inside a progress line, and no static
analysis had ever been run. Fixing discovery and adding a pyflakes gate exposed ~20 real
defects in shipped code — Windows Update offers dead for every attached device, the
reliability bundle lost on any PC with a LiveKernel event, the Firmware download button
broken on every click, the Activity history dialog unable to open, event times labelled UTC
while carrying local values, and MSI boards silently denied a support link. All are fixed
with regression tests that were each verified to reach the defective line; the suite is
129 files / 1,057 tests green; **6.5.8 portable rebuilt** 2026-08-21 at
`C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\BSODAnalyzer_v6\BSODAnalyzer.exe`.
**Next:** field-verify on m17 R5 (`AGENT_HANDOFF_20260820.md` §6); git commit only if user asks;
catalog backlog (Dell DUP extract, component-install UX).
