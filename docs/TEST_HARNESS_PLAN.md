# Test harness & static gate plan

**Goal:** make a green suite mean what it says, then fix the bugs a green suite was hiding.

**Canonical version:** see [`VERSION.txt`](../VERSION.txt) · **Last updated:** 2026-08-21

---

## Why this plan exists

`run_tests.bat` had no test discovery. It ran each file through
`runpy.run_path(run_name="__main__")` and returned 0 unless the module raised, so a file
executed only the test functions its own hand-written `if __name__ == "__main__":` block
happened to call.

Measured before any change (`_audit_test_reachability.py`):

| Metric | Value |
|--------|------:|
| Test functions defined | 1,038 |
| Never executed | **139 (13.4%)** |
| Files with no `__main__` block (ran 0 tests, still printed `OK`) | **7** |
| Files with a partial call list | 17 |

The 7 silent files included `test_catalog_device_roles.py` and
`test_driver_install_selective.py` — the tests for the 6.5.6/6.5.7 device-roles and
component-install work, including the per-component **downgrade gate**.

Nine confirmed runtime bugs shipped past this suite. Four were plain undefined names that
`pyflakes` reports in about three seconds; no static analysis had ever been run on the
codebase.

---

## Non-negotiables

1. **Per-file process isolation stays.** Tests were authored one-file-per-process and share
   module-level global caches. Discovery is fixed *within* a file; isolation *between* files
   is preserved.
2. **Qt bootstrap stays intact.** `QT_QPA_PLATFORM=offscreen` plus `QT_PLUGIN_PATH` must be
   set before the first PySide6 import, or Windows shows a native platform-plugin dialog.
   See [`AGENT_READINESS.md`](AGENT_READINESS.md) § Qt test bootstrap.
3. **No test rewrites to gain discovery.** Existing `__main__` blocks keep working for
   direct `py -3 tests\test_x.py` runs.
4. **Gate proof stays honest.** `run_tests.bat` may only record the `t2` gate when the run
   actually executed tests.

---

## Master checklist

Implement the next unchecked phase only. Runtime order = build order.

| Phase | Name | Status |
|-------|------|--------|
| **1** | pytest discovery with per-file isolation | ☑ |
| **2** | Triage tests that now run for the first time | ☑ |
| **3** | Static analysis gate (pyflakes, undefined names) | ☑ |
| **4** | Fix the confirmed runtime bugs + regression tests | ☑ |
| **5** | Full validation (T2/T3/T4) + doc sync | ☑ |

---

## Phase 1 — pytest discovery with per-file isolation

- `conftest.py` — Qt plugin bootstrap before PySide6, project root on `sys.path`
  (same contract as `tests/run_test_module.py`).
- `pytest.ini` — `testpaths`, quiet output, no implicit namespace surprises.
- `tests/run_test_module.py` — delegate to pytest for the given file, keep the
  `runpy` path as a documented fallback.
- `run_tests.bat` — unchanged loop shape (one process per file), now reporting an
  executed-test count per file instead of a bare `OK`.

**Done when:** a file with no `__main__` block reports its real test count; a file whose
`__main__` block lists a subset runs *all* its tests; Qt tests still pass offscreen with no
native dialog.

**Result:** **1,041 tests now collected** across 127 files (was ~898 effectively executing).
`conftest.py` + `pytest.ini` added; `tests/run_test_module.py` delegates to `pytest.main()`
per file with `--legacy` kept for the old `runpy` path.

#### A second gate hole, found while verifying Phase 1

`run_tests.bat` used `if errorlevel 1`, which in cmd means **"≥ 1"**. An interpreter crash
returns a *negative* code, so a file that died on an access violation printed `OK`. Three
GUI files were crash-masked this way:

| File | Exit code | Meaning |
|------|-----------|---------|
| `test_gui_checkbox_style.py` | `-1073740791` | `0xC0000409` stack buffer overrun |
| `test_theme_chrome_refresh.py` | `-1073740791` | same |
| `test_workflow_copy_batch4.py` | `-1073740791` | same |

Now a `:run_one` subroutine compares `%ERRORLEVEL%` to `0` explicitly and prints the code.

#### A third gate hole: failures that hid inside a progress line

pytest's final progress line carries no trailing newline, so `echo FAILED: %~1` appended to
it — `....F.FAILED: tests\test_catalog_audit_coverage.py [exit -1073740791]`. A log scan
anchored at the start of a line missed those verdicts entirely, which undercounted the
Phase 2 triage list by two files (`test_catalog_audit_coverage.py`,
`test_gui_vendor_icons.py`). `:run_one` now emits a blank line before the verdict.

### 1a — reachability guard [required] ☑

`tests/test_test_discovery.py` (4 tests) asserts every defined test is actually collected,
that no module redefines a test name, that no signature takes a non-fixture argument, and
that collection reports no import errors. It found one verbatim duplicate
(`test_firmware_peripheral_vendors.py::test_usb_product_hint_pro_type_ultra_pid`).

---

## Phase 2 — Triage newly-running tests

**13 files fail** now that discovery and crash detection work. Triage below; **C** = real
product bug, **T** = stale/incorrect test, **E** = environment/harness.

| Kind | Test | Evidence |
|------|------|----------|
| **C** | `test_catalog_device_roles::…prefers_swc_child` | WU offers dead for all non-integrated-bus devices — see below |
| **C** | `test_facade_reexport_regressions::…technical_minidump_path` | `KeyError: 'size_mb'` raised inside `crash_report_format.py:806` |
| **T** | `test_report_export_parity_batch3::…section2_uses_fix_plan_steps` | Step *is* in the report; assertion did not tolerate line wrapping |
| **C** | `test_driver_only_workflow::…avoids_onedrive_desktop` | Exports resolve into OneDrive despite portable-first rule |
| **C** | `test_portable_build_smoke::test_summary_refresh_generation_guard` | Generation guard not rejecting stale worker results |
| **C** | `test_driver_catalog_quality` (12) | GPU MSCatalog skip, Realtek parent HWID, `summarize_offer_status`, Dell/AMD/NVIDIA scrapes |
| **C/T** | `test_gui_checkbox_style::…menu_checkmark_uses_theme_color` | Real assertion failure **and** a fatal Qt crash after it |
| **E** | `test_theme_chrome_refresh`, `test_workflow_copy_batch4` | Fatal Qt crash — apply `agent-gui-test-hygiene` |
| **T** | `test_batched_online_store::…parallel_seeds_cache` | Patches `_gui_mscatalog_parallel_throttle`, removed from `driver_catalog` |
| **T** | `test_v528_polish::test_find_cdb_memoization` | Patches `_get_cdb_search_paths`, removed from `bsod_analyzer` |
| **T** | `test_vendor_page_render::test_browser_from_registry` | `FakeKey` lacks `__exit__`; production code correctly uses `with` |
| **E** | `test_agent_gate_proof::…fresh_gate` | `_FACADE_AUDIT_REPORT.txt` older than the allowed window |

Several `test_driver_catalog_quality` tests reach the **live network** (`HTTPError 403/404`
`ResourceWarning`s). Offline determinism is a Phase 2 sub-task, not a product fix.

The `—` shown as `?` in captured output is this console's code page, **not** a report
encoding defect — `format_output` emits `\u2014` correctly.

### Fixed so far

Product fixes (each was reachable by a real user):

| Location | Defect | Fix |
|----------|--------|-----|
| `catalog_row_rejects.py` | OEM-only rules judged WU/MSCatalog rows, killing every offer for attached devices | Gate the `_reject_oem_*` group behind `_row_is_oem_sourced` |
| `catalog_mscatalog_session.py:236` | `begin_batch_mscatalog_query_cache` **rebound** the global; `driver_catalog`'s re-export and `catalog_microsoft_fetch._warm_gap_mscatalog_queries` kept the stale dict, so warmed queries were re-issued every scan | Clear in place |
| `crash_report_format.py:806`, `:1064`, `gui_mixin_analysis.py:640` | `d['size_mb']` aborted the whole report on a partial dump entry | Shared `format_minidump_summary_line()`, `.get` for `full_dump` |
| `firmware_catalog.py:1119` | MSI boards report `Micro-Star International Co., Ltd.`, never `msi` — so MSI users got **no** motherboard support link | Use the existing `dc._manufacturer_matches` aliases |
| `vendor_fetch.py:81-89` | When every fetch step failed, `run_steps` returned this **vendor's last successful value**. The key is the vendor name alone, so a second AMD/Intel device inherited the first device's version, and `vendor_endpoint_health` derives `ok` from that version — a dead endpoint reported healthy | Return the failure; keep diagnostics. Regression test in `test_vendor_fetch.py` |
| `catalog_device_context.py:318` | `_realtek_catalog_name_aliases` pre-seeded `seen` with the device's own name, so the loop discarded it on the first iteration. Callers only ever looked up the `(R)` spellings, and a codec Windows names plain `Realtek Audio` never inherited its parent HDAUDIO hardware ID — losing HWID verification for its WU offers | Start `seen` empty so the real name is tried first |
| `catalog_scoring.py:566` | A Realtek NIC bump with an identical build suffix (`1125.28.1224.2025` → `1168.28.1224.2025`) was forced to `uncertain` because the leading segment differed, even though `_realtek_nic_same_oem_family` — and the reject filter that uses it — treat that as one family | Skip the family gate when the suffixes match; helper moved to `catalog_scoring` and re-used by `catalog_row_rejects` |

Test fixes (product was already correct):

| Test | Was wrong |
|------|-----------|
| `test_facade_reexport_regressions::…minidump_path` | Wrote app-crash events into slot 3 (`app_dumps`) instead of slot 12 (`app_crash_events`) |
| `…::…minidump_path`, `test_report_export_parity_batch3::…fix_plan_steps` | Literal `in` checks against wrapped report text — now `report_contains()` in `gui_test_harness` |
| `test_driver_only_workflow::…avoids_onedrive_desktop` | Asserted `"onedrive" not in path`, which fails purely because this checkout lives under OneDrive; the mocked desktop did not exist, so the branch never ran |
| `test_v528_polish::test_find_cdb_memoization` | Patched the `bsod_analyzer` facade; `find_cdb` resolves `_get_cdb_search_paths` inside `bsod_minidump` |
| `test_batched_online_store::…parallel_seeds_cache` | Patched three gates on `driver_catalog`; all three and `warm_batched_mscatalog_queries` live in `catalog_mscatalog_session` |
| `test_vendor_page_render::test_browser_from_registry` | `FakeKey` had no `__enter__`/`__exit__`, and the fake path required a real Edge install |
| `test_portable_build_smoke::…generation_guard` | Asserted `2 != 1 + 1` — unpassable, no product code touched; the guard is genuinely covered in `test_gui_phase2_offscreen.py` |

**Note on facade drift:** three of these tests patched names that the module split moved.
Patching a facade re-export never intercepts a module-internal lookup, so those mocks were
silently inert even before they started erroring.

### Two dominant test-side causes

Most of the 12 `test_driver_catalog_quality` failures were one of these, not product defects:

1. **Offers with no fetchable package.** A versioned offer whose row carries no installer is
   deliberately reported `uncertain` (and an uncertain vendor row is then dropped from
   display). Fixtures that asserted `newer` from a bare `{"source", "title", "version"}` row
   were asserting against a rule the product added later. Giving the row a real `url` both
   fixes the test and makes it exercise what its name claims.
2. **Facade drift.** Patching a `driver_catalog` re-export never intercepts a
   module-internal call. Six manufacturer-tier tests patched
   `dc._manufacturer_catalog_tasks_for_ctx` while `catalog_device_comparison` calls it as a
   module-level name — so those tests hit **live vendor endpoints** and asserted against
   whatever the internet returned that day. Same for `catalog_download.download_file_to_folder`
   (a real `dl.dell.com` download attempt) and `catalog_amd_fetch._amd_fetch_page_html`.
   Fixing the targets cut this file's runtime and removed its `HTTPError` warnings.

Two more were **host-dependent**: they read this machine's real installed AMD versions
(Adrenalin 26.7.1, chipset 8.08.12.551) because the patch landed on the wrong object.

### Qt crashes — all four were object lifetime, not product code

`0xC0000409` is Qt aborting. Three distinct causes, none of which the old runner could
report:

| Cause | Where | Fix |
|-------|-------|-----|
| `QProxyStyle` took ownership of `app.style()` and deleted the application's live style on GC | `test_gui_checkbox_style` | Give the proxy its own `QStyleFactory` base — also makes the pixel geometry host-independent |
| Parentless widget outlived `QApplication` teardown | `test_theme_chrome_refresh`, `test_catalog_audit_coverage` | New `offscreen_widget()` in `gui_test_harness` owns creation and destruction |
| `MainWindow` built by hand with no teardown | `test_workflow_copy_batch4` | Use the existing `offscreen_main_window()` |
| `MainWindow` passes then child aborts on `QApplication` teardown (`0xC0000409`) | `test_workflow_copy_batch4` | Run via `tests/qt_isolated_runner.py` from `run_tests.bat` (parent clears `PYTHONSTARTUP` so it never loads Qt; child output is authoritative) |
| `QPixmap`/`QIcon` built with **no `QApplication` at all** | `test_gui_vendor_icons`, `test_catalog_audit_coverage` | Module fixture / `offscreen_widget`; these files have no `__main__` block, so the tests had never run |

`test_gui_checkbox_style::…menu_checkmark_uses_theme_color` also had a real assertion
failure: it probed one hard-coded pixel at x=22 while the checkmark is painted — in exactly
the right colour — across x 11–20. Replaced with a region colour count.

**Phase 2 result:** all 15 files green (the 13 triaged plus the 2 that had been hiding in a
progress line). Suite: **127 files, 0 failures.**

### Lead finding — Microsoft WU offers suppressed for third-party devices

`_reject_oem_pc_maker_on_third_party_device` is a **PC-maker OEM** filter, but
`_shared_catalog_row_rejects` also applies it to Windows Update rows. Its final rule —
*"row has a version string → reject"* (`catalog_oem_filters.py:273`) — matches essentially
every WU row, so `_wu_device_match_score` returns `-1`.

Measured with `_wu_device_match_score`:

| Device | Bus / manufacturer | Score |
|--------|--------------------|------:|
| Intel Ethernet I225-V | `PCI\` integrated | **19** ✅ |
| LG Monitor Support Application | `SWD\`, LG Electronics | **−1** ❌ |
| iFi USB DAC | `USB\`, iFi | **−1** ❌ |
| Logitech USB input device | `USB\`, Logitech | **−1** ❌ |
| LG SWC, *version field emptied* | `SWD\`, LG Electronics | **29** ✅ |

Integrated PCI/ACPI silicon is unaffected, which is why this survived field use. Everything
attached — external monitors' SoftwareComponent children, USB audio, peripherals, docks —
silently gets no Microsoft offer. The 6.5.5/6.5.6 "LG duplicate offer" fix removed the
duplicate by dropping *both* copies rather than attributing one to the SWC child.

**Done when:** full suite green with no quarantined tests, and every fix has a named cause.

---

## Phase 3 — Static analysis gate

`tests/test_static_analysis.py` (4 tests) with the file-list and pyflakes plumbing in
`tests/static_analysis.py`. pyflakes runs **in-process**: 360 first-party files exceed the
Windows 32k command-line limit, so `py -3 -m pyflakes <files>` cannot be shelled out.

Findings are classified by pyflakes **message class**, not message text — `local variable
'x' is assigned to but never used` (cosmetic) and `local variable 'x' … referenced before
assignment` (fatal) share their opening words.

| Gate | Fails on |
|------|----------|
| `test_no_undefined_names` | `UndefinedName`, `UndefinedLocal`, `UndefinedExport`, syntax/unexpected errors |
| `test_star_import_names_resolve_in_shared_context` | a name pyflakes could not resolve past `from gui_app_context import *` that the hub does not actually export |
| `test_no_dict_literal_silently_drops_a_mapping` | `MultiValueRepeatedKeyLiteral` |
| `test_gate_covers_the_whole_first_party_tree` | the file list shrinking below 300, or losing `tests/` / `scripts/` |

Not gated: **980 unused imports** and **44 assigned-but-unused locals**. Both are cosmetic,
churn heavily, and would drown the signal. Worth a separate cleanup pass if anyone wants it.

`pytest` and `pyflakes` are declared in **`requirements-dev.txt`** — kept out of
`requirements.txt` so nothing test-only reaches the PyInstaller bundle.

### 3a — the star-import blind spot, closed without the 25-file refactor [required] ☑

The plan assumed the only fix for `from gui_app_context import *` was replacing it in ~25
mixins. It is not. pyflakes still *names* every unresolved symbol, it just downgrades the
verdict to "may be undefined, or defined from star imports: gui_app_context". Importing the
hub and checking each name against `dir(gui_app_context)` restores the assertion:

| Star-import name references | Resolve in the hub | Do not |
|----------------------------:|-------------------:|-------:|
| 1,402 | 1,398 | **4** |

The four were real. `mlog` (the `maintenance_log` alias) was never exported, so
`_show_maintenance_history` — the **Activity history** dialog — raised `NameError` before
it could open, as did the maintenance report builder and the manual driver-database refresh
handler. `maintenance_log` had **no importer anywhere in the app**; the module was reachable
only through a name that did not exist. The other three (`kind`, `message`, `extra`) were an
orphaned `slog.progress(...)` fragment spliced onto the end of
`_set_refresh_device_list_ui` — its `def` line lost in the split, its `NameError` swallowed
by `except Exception: pass`.

The 25-file refactor is therefore **not needed for coverage**. Leave the star imports.

---

## Phase 4 — Fix the confirmed runtime bugs

Each fix has a regression test in `tests/test_undefined_name_regressions.py` (11 tests) that
reaches the defective line. Verified by deleting the restored name and confirming the same
exception returns.

| Location | Defect | Who hits it |
|----------|--------|-------------|
| `bsod_events.py:523` | `_summarize_livekernel_message` not imported | **Any PC with a LiveKernel event.** The `NameError` is caught per-future in `analyzer_gather`, so the whole reliability bundle — LiveKernel events, WER errors, stability index — was replaced by `_query_failed` and a data gap. This host has zero LiveKernel events, which is why it never showed here |
| `crash_report_format.py:253` | `list((dv or {}).get("attribution") or {}).get("lines")` — paren one level too early, so `.get` ran on a **list of keys** | Every KernelPower **Event 41** with no repair narrative: `AttributeError` inside Quick Answer, the unexpected-shutdown path |
| `crash_report_fix_plan.py:637,649` | `urllib` never imported | NVMe storage search link and WHEA component search link — the fix plan for storage and hardware-error crashes |
| `catalog_download.py:208` | `sys` never imported | Download on a Windows Update **optional-updates** row, which deep-links to `ms-settings:` |
| `bsod_hardware_wmi.py:1210` | `resolve_device_display_label` not imported | A problem device the enrichment index cannot match — unhandled, so the whole Drivers-tab hardware scan fails |
| `catalog_chipset_comparison.py:213,215` | `_NETWORK_VENDOR_KEYS` / `_EXTENDED_VENDOR_KEYS` undefined | The PC-level HTTP gate for every vendor outside intel/amd/nvidia/realtek: Killer, Broadcom, Qualcomm, MediaTek, TP-Link, Logitech, Samsung, Netgear |
| `gui_mixin_firmware_scan.py:414` | 2-name unpack of `open_firmware_offer`'s 3-tuple | **Every** Firmware-tab Download click: `ValueError` after the confirmation dialog |
| `gui_mixin_maintenance.py:15,107,133`, `gui_mixin_catalog_shell.py:562` | `mlog` never exported by `gui_app_context` | Activity history dialog, maintenance report, manual driver-database refresh |
| `bsod_events.py:154,194` | Naive event-log strings tagged UTC | See below |
| `bsod_hardware_wmi.py` `KNOWN_VENDORS` | Six keys repeated with **different** values | See below |
| `driver_install.py:453-454`, `gui_mixin_catalog_shell.py:85-90` | Orphaned function tails left by module splits | Dead; the `driver_install` pair duplicated `find_inf_dirs_for_hwid_tokens`'s last two lines |

### Event times were local, labelled UTC

Every query in `bsod_events.py` renders `TimeCreated` with `ToString('yyyy-MM-dd HH:mm:ss')`,
which .NET emits in **local** time. `_parse_event_time` tagged those naive strings
`timezone.utc`, so:

- `compute_crash_timeline` compared local-as-UTC instants against a true-UTC `now`, shifting
  every crash by the machine's offset — at UTC−7, seven hours older than reality, enough to
  move events across the 7-day and 30-day boundaries.
- The label read `2026-08-09 03:14 UTC` for a crash the user saw at 03:14 **their** time.
- `fix_progress` compares `last_crash_dt.date()` against driver package dates, so the offset
  could shift that comparison by a day.

Naive strings now become aware local (`dt.astimezone()`); explicit offsets are preserved.
The label drops the false suffix. `parse_last_crash_utc` → **`parse_last_crash_time`**, and
it still accepts the old ` UTC` labels persisted in saved models — those readings were local
all along, so both spellings parse identically.

### KNOWN_VENDORS: 165 entries, 150 distinct keys

Two eras of edits left `tp-link`/`tplink`, `d-link`/`dlink` and `c-media`/`cmedia` mapped
twice with **conflicting** canonicals (hyphenated early, unhyphenated late). Later wins, and
the rest of the codebase gates on the unhyphenated form — `catalog_extended_fetch` compares
`vendor_key` against the literal `"tplink"`. So behaviour was accidentally correct and the
hazard was latent: deleting the "duplicate" would have silently killed TP-Link peripheral
lookups. Collapsed to one entry per key, canonical values unchanged, and
`MultiValueRepeatedKeyLiteral` is now gated so the pattern cannot return.

---

## Phase 5 — Validation & docs

| Tier | Command | Result |
|------|---------|--------|
| **T2** | `run_tests.bat` | exit 0 — **129 files, 0 failures** |
| **T3** | `scripts\verify_facade_gate.cmd` | exit 0 — `_ba` 38 symbols / `core.*` 87 symbols, 0 broken |
| **T4** | `py -3 scripts\live_validate_analysis.py` (admin) | exit 0 — every Phase 2/3/4/5 sub-step PASS |

**Suite scale after this workstream:** 129 files, **1,057 tests collected**, up from ~898
effectively executing before Phase 1.

### What this workstream changed about trust

The suite reported `OK` while 139 tests never ran, three files crashed the interpreter, two
more hid their verdict inside a progress line, and no static analysis had ever run. Fourteen
undefined names, a paren bug, a tuple-arity bug and a timezone bug were sitting in shipped
code — most of them on the exact branches no test walked. The gates added here
(`test_test_discovery.py`, `test_static_analysis.py`, `:run_one` exit-code handling) make
each of those failure modes loud instead of silent.
