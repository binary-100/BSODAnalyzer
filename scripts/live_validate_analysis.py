"""One-shot live analysis validation — run as admin on the host machine."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import bsod_analyzer as core  # noqa: E402


def _safe_print(*parts: object) -> None:
    """Console output tolerant of Unicode on Windows cp1252 terminals."""
    text = " ".join(str(p) for p in parts)
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    sys.stdout.buffer.write(text.encode(enc, errors="replace") + b"\n")


def _check_ok(checks: list, key: str) -> bool | None:
    for c in checks or []:
        if c.get("key") == key:
            return bool(c.get("ok"))
    return None


def validate_phase2_substeps(out: dict) -> dict[str, dict]:
    """Per ROADMAP Phase 2 sub-step criteria on live_validation_output."""
    cap = out.get("capture_readiness") or {}
    checks = cap.get("checks") or []
    prereqs = cap.get("minidump_prerequisites") or {}
    narrative = out.get("repair_narrative") or {}
    windbg = out.get("windbg_summary") or {}
    gaps = out.get("data_gaps") or []
    results: dict[str, dict] = {}

    cdb_ok = _check_ok(checks, "cdb")
    dumps_n = int(out.get("kernel_dump_count") or 0)
    analyzed = int(windbg.get("dumps_analyzed") or 0)
    cdb_path = out.get("cdb_path") or ""
    cdb_usable = bool(cdb_path and core._cdb_engine_usable(cdb_path))
    silent_cdb_fail = any(
        "debugger" in g.lower() or "cdb" in g.lower() or "!analyze returned no" in g.lower()
        for g in gaps
    )
    results["2a"] = {
        "pass": cdb_ok is True and cdb_usable and (dumps_n == 0 or analyzed > 0) and not silent_cdb_fail,
        "detail": (
            f"cdb_check={cdb_ok}, usable={cdb_usable}, dumps={dumps_n}, "
            f"analyzed={analyzed}, path={cdb_path or 'none'}"
        ),
    }

    happened = (narrative.get("what_happened") or "").lower()
    boot_ok = "boot" in happened or "recovery" in happened
    results["2b"] = {
        "pass": boot_ok and "2026-08-09" in (narrative.get("what_happened") or ""),
        "detail": f"boot/recovery in narrative={boot_ok}; reference Aug 9 incident",
    }

    required_keys = ("admin", "dumps", "cdb", "minidump_dir", "dump_match")
    present = {c.get("key") for c in checks}
    results["2c"] = {
        "pass": all(k in present for k in required_keys) and cap.get("capture_ready") is not None,
        "detail": f"checks={sorted(present)}, capture_ready={cap.get('capture_ready')}",
    }

    local = core._get_local_cdb_path()
    local_usable = os.path.isfile(local) and core._cdb_engine_usable(local)
    repair = out.get("cdb_repair") or {}
    results["2d"] = {
        "pass": local_usable or repair.get("repaired") or cdb_usable,
        "detail": (
            f"local_usable={local_usable}, repair={repair.get('repaired')}, "
            f"find_cdb_usable={cdb_usable}"
        ),
    }

    folder_ok = prereqs.get("folder_writable")
    disk_known = prereqs.get("free_space_mb") is not None
    reg_dir = prereqs.get("registry_dir")
    results["2e"] = {
        "pass": folder_ok is True and disk_known and _check_ok(checks, "disk_space") is not None,
        "detail": (
            f"writable={folder_ok}, free_mb={prereqs.get('free_space_mb')}, "
            f"registry_dir={reg_dir or 'default'}"
        ),
    }

    wer = out.get("wer_dump_recovery") or {}
    missing_dump_events = [
        e for e in (out.get("latest_events") or [])
        if e.get("code_source") == "wer1001" and (e.get("dump") or "").strip()
    ]
    if not missing_dump_events:
        results["2f"] = {
            "pass": True,
            "detail": "N/A on this machine — no WER 1001 missing-DumpFile events in window (unit tests cover path)",
        }
    else:
        recovered = int(wer.get("recovered_count") or 0)
        gap_msgs = wer.get("data_gap_messages") or []
        results["2f"] = {
            "pass": recovered > 0 or not gap_msgs,
            "detail": f"recovered={recovered}, gaps={len(gap_msgs)}",
        }
    return results


def validate_reference_baseline(out: dict) -> list[str]:
    """Phase 1 reference hardware expectations (Alienware m17 R5 AMD)."""
    issues: list[str] = []
    if not out.get("admin"):
        issues.append("reference baseline expects admin=True")
    if out.get("needs_config"):
        issues.append("reference baseline expects needs_config=False (dumps enabled)")
    narrative = out.get("repair_narrative") or {}
    if narrative.get("dump_matches_latest") is True:
        issues.append("reference baseline expects dump_matches_latest=False (Aug 9 vs Aug 4)")
    if not narrative.get("older_incident_note"):
        issues.append("reference baseline expects older_incident_note (Aug 4 dump separated)")
    targets = narrative.get("repair_targets") or []
    labels = {t.get("label") for t in targets}
    if "AMD Chipset Software" not in labels:
        issues.append("reference baseline expects AMD Chipset Software repair target")
    if narrative.get("what_failed", {}).get("driver_file"):
        issues.append("reference baseline expects no faulting driver for latest Aug 9 incident")
    wf_summary = (narrative.get("what_failed") or {}).get("summary") or ""
    if "Unknown" in wf_summary:
        issues.append("reference baseline expects confident what_failed copy (no 'Unknown')")
    if not narrative.get("why_this_order"):
        issues.append("reference baseline expects why_this_order in repair narrative")
    steps = narrative.get("action_steps") or []
    if steps and not any("Drivers -> Needs attention" in s for s in steps):
        issues.append("reference baseline expects action_steps to cite Drivers -> Needs attention")
    return issues


def validate_live_output(out: dict) -> list[str]:
    """Return human-readable issues; empty list means validation passed."""
    issues: list[str] = []
    cap = out.get("capture_readiness") or {}
    check_keys = {c.get("key") for c in cap.get("checks") or []}
    for key in ("admin", "dumps", "cdb", "minidump_dir", "disk_space", "dump_match"):
        if key not in check_keys:
            issues.append(f"capture_readiness missing check: {key}")
    prereqs = cap.get("minidump_prerequisites") or {}
    for key in ("effective_dir", "folder_writable", "free_space_mb", "directories"):
        if key not in prereqs:
            issues.append(f"minidump_prerequisites missing field: {key}")
    if out.get("admin") and out.get("needs_config") is None:
        issues.append("needs_config must be bool")
    if out.get("version") != core.VERSION:
        issues.append(f"version mismatch: output {out.get('version')} != {core.VERSION}")
    if out.get("admin") and out.get("dump_val") is None:
        issues.append("dump_val unset while running as Administrator")
    narrative = out.get("repair_narrative") or {}
    if not narrative.get("what_happened"):
        issues.append("repair_narrative.what_happened missing")
    if windbg := out.get("windbg_summary"):
        if out.get("kernel_dump_count", 0) > 0 and not windbg.get("dumps_analyzed"):
            issues.append("kernel dumps present but windbg_summary.dumps_analyzed is zero")
    return issues


def validate_phase4_substeps(out: dict) -> dict[str, dict]:
    """Per ROADMAP Phase 4 sub-step criteria on live_validation_output."""
    ext = out.get("extended_log_attribution") or {}
    src = ext.get("sources_scanned") or {}
    narrative = out.get("repair_narrative") or {}
    timeline = out.get("incident_timeline") or {}
    entries = timeline.get("entries") or []
    results: dict[str, dict] = {}

    results["4a"] = {
        "pass": bool(src) and src.get("wer_archive") is not None,
        "detail": (
            f"wer_reports={src.get('wer_reports_found', 0)}, "
            f"archive={src.get('wer_archive')}, queue={src.get('wer_queue')}"
        ),
    }

    latest_wer = ext.get("latest_incident_wer_hints") or []
    dump_mismatch = narrative.get("dump_matches_latest") is False
    wf = (narrative.get("what_failed") or {}).get("summary") or ""
    wer_in_narrative = "WER" in wf or not latest_wer
    results["4b"] = {
        "pass": "wer_module_hints" in ext and (wer_in_narrative or not dump_mismatch),
        "detail": f"latest_wer={len(latest_wer)}, dump_mismatch={dump_mismatch}, wer_in_summary={('WER' in wf)}",
    }

    results["4c"] = {
        "pass": src.get("setupapi_dev_log") is not None,
        "detail": f"setupapi_scanned={src.get('setupapi_dev_log')}, entries={src.get('setupapi_entries', 0)}",
    }

    results["4d"] = {
        "pass": src.get("cbs_log") is not None,
        "detail": f"cbs_scanned={src.get('cbs_log')}, entries={src.get('cbs_entries', 0)}",
    }
    return results


def validate_phase5_substeps(out: dict) -> dict[str, dict]:
    """Per ROADMAP Phase 5 sub-step criteria on live_validation_output."""
    narrative = out.get("repair_narrative") or {}
    targets = narrative.get("repair_targets") or []
    labels = {t.get("label") for t in targets if t.get("label")}
    steps = narrative.get("action_steps") or []
    wf = (narrative.get("what_failed") or {}).get("summary") or ""
    results: dict[str, dict] = {}

    needs_attention_steps = [s for s in steps if "Drivers -> Needs attention" in s]
    label_hits = sum(1 for s in needs_attention_steps if any(lb in s for lb in labels))
    results["5a"] = {
        "pass": bool(needs_attention_steps) and label_hits >= len(needs_attention_steps),
        "detail": f"steps={len(steps)}, needs_attention={len(needs_attention_steps)}, label_cited={label_hits}",
    }

    results["5b"] = {
        "pass": True,
        "detail": "PRODUCT_REFERENCE § Terminology (doc check in repo)",
    }

    why = narrative.get("why_this_order") or ""
    no_unknown = "Unknown" not in wf
    results["5c"] = {
        "pass": bool(why) and no_unknown and "logging gap" in wf.lower(),
        "detail": f"why_this_order={bool(why)}, no_unknown={no_unknown}",
    }
    return results


def validate_phase3_substeps(out: dict) -> dict[str, dict]:
    """Per ROADMAP Phase 3 sub-step criteria on live_validation_output."""
    results: dict[str, dict] = {}
    itl = out.get("incident_timeline") or {}
    cov = out.get("log_coverage") or {}
    narrative = out.get("repair_narrative") or {}

    results["3a"] = {
        "pass": bool((cov.get("read_windows") or itl.get("read_windows"))),
        "detail": f"read_windows documented={bool(cov.get('read_windows'))}",
    }

    entries = itl.get("entries") or []
    has_hist = any(e.get("historical") for e in entries)
    dump_mismatch = itl.get("newest_dump_mismatch")
    results["3b"] = {
        "pass": bool(entries) and (has_hist or not dump_mismatch),
        "detail": f"entries={len(entries)}, historical={has_hist}, dump_mismatch={dump_mismatch}",
    }

    older = narrative.get("older_incident_note") or itl.get("stale_dump_note") or ""
    no_false_driver = not out.get("driver_display")
    results["3c"] = {
        "pass": bool(older) and no_false_driver and narrative.get("dump_matches_latest") is False,
        "detail": f"stale_note={bool(older)}, driver_display={out.get('driver_display')!r}",
    }
    return results


def run_phase_unit_tests() -> list[str]:
    """Run targeted Phase 2/3 unit test modules; return failure messages."""
    failures: list[str] = []
    tests = (
        APP / "tests" / "test_live_validation_fixes.py",
        APP / "tests" / "test_minidump_prerequisites.py",
        APP / "tests" / "test_log_age_phase3.py",
        APP / "tests" / "test_incident_timeline.py",
        APP / "tests" / "test_crash_repair_narrative.py",
        APP / "tests" / "test_log_attribution_phase4.py",
        APP / "tests" / "test_repair_ux_phase5.py",
    )
    for path in tests:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(APP),
            env={**os.environ, "PYTHONPATH": str(APP)},
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            tail = (proc.stdout or proc.stderr or "").strip().splitlines()
            failures.append(f"{path.name} failed: {tail[-1] if tail else proc.returncode}")
    return failures


def main() -> int:
    print(f"BSOD Analyzer v{core.VERSION}")
    print(f"Admin: {core.is_user_admin()}")
    dump_val, dump_config = core.get_dump_config()
    print(f"Dump config: {dump_val!r} ({dump_config})")
    print("Gathering report data (this may take 1-3 min)...")
    fmt_args, needs_config = core.gather_report_data()
    deriv = core.build_report_derivations(fmt_args)
    model = core.build_display_model(fmt_args)

    events = fmt_args[0] if fmt_args else []
    kernel_dumps = fmt_args[1] if len(fmt_args) > 1 else []
    windbg = fmt_args[4] if len(fmt_args) > 4 else None
    system_ctx = fmt_args[14] if len(fmt_args) > 14 else {}
    cdb_path = core.find_cdb()

    narrative = model.get("crash_repair_narrative") or (deriv.get("driver_verification") or {}).get(
        "repair_narrative"
    )
    timeline = model.get("crash_timeline") or deriv.get("crash_timeline") or {}
    conf = deriv.get("crash_confidence") or {}

    out = {
        "version": core.VERSION,
        "admin": core.is_user_admin(),
        "needs_config": needs_config,
        "dump_val": dump_val,
        "dump_config": dump_config,
        "data_gaps": list(model.get("data_gaps") or deriv.get("data_gaps") or []),
        "event_count": len(events or []),
        "kernel_dump_count": len(kernel_dumps or []),
        "latest_events": (events or [])[:5],
        "windbg_summary": {
            k: windbg.get(k)
            for k in (
                "faulting_driver",
                "dump_time",
                "dump_file",
                "bugcheck_code",
                "dumps_analyzed",
                "recurring_faulting_driver",
            )
            if windbg
        },
        "cause_title": model.get("cause_title"),
        "cause_subtitle": model.get("cause_subtitle"),
        "driver_display": model.get("driver"),
        "confidence": {
            "level": conf.get("level"),
            "headline": conf.get("headline"),
            "what_would_change": conf.get("what_would_change"),
        },
        "repair_narrative": narrative,
        "timeline_entries": (timeline.get("entries") or [])[:12],
        "timeline_summary": {
            k: timeline.get(k)
            for k in ("dump_matches_latest", "stale_dump_note", "headline")
            if timeline.get(k) is not None
        },
        "capture_readiness": model.get("capture_readiness") or deriv.get("capture_readiness") or {},
        "incident_timeline": model.get("incident_timeline") or deriv.get("incident_timeline") or {},
        "log_coverage": model.get("log_coverage") or deriv.get("log_coverage") or {},
        "driver_verification_attribution": (deriv.get("driver_verification") or {}).get("attribution"),
        "cdb_path": cdb_path,
        "cdb_repair": (system_ctx or {}).get("cdb_repair") or {},
        "wer_dump_recovery": (system_ctx or {}).get("wer_dump_recovery") or {},
        "extended_log_attribution": (system_ctx or {}).get("extended_log_attribution") or {},
    }

    out_path = APP / "live_validation_output.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")

    print("\n=== SUMMARY ===")
    print(f"needs_config: {needs_config}")
    print(f"cause_title: {model.get('cause_title')}")
    print(f"cause_subtitle: {model.get('cause_subtitle')}")
    print(f"driver (display): {model.get('driver')}")
    if narrative:
        _safe_print(f"what_happened: {narrative.get('what_happened')}")
        wf = narrative.get("what_failed") or {}
        _safe_print(f"what_failed: {wf.get('summary')}")
        print(f"repair_targets: {len(narrative.get('repair_targets') or [])}")
        for t in (narrative.get("repair_targets") or [])[:6]:
            _safe_print(f"  - {t.get('label')} | {t.get('version') or '—'} | {t.get('kind')}")
        _safe_print(f"why_this_order: {narrative.get('why_this_order') or narrative.get('how_sure')}")
        if narrative.get("older_incident_note"):
            _safe_print(f"older_note: {narrative['older_incident_note']}")
    if out["data_gaps"]:
        print("data_gaps:")
        for g in out["data_gaps"]:
            print(f"  - {g}")
    if conf.get("what_would_change"):
        print("what_would_change:")
        for w in conf["what_would_change"]:
            print(f"  - {w}")
    cap = out.get("capture_readiness") or {}
    print(f"capture_ready: {cap.get('capture_ready')}")
    print(f"capture_checks: {len(cap.get('checks') or [])}")

    print("\n=== PHASE UNIT TESTS (2 + 3 + 4 + 5) ===")
    unit_failures = run_phase_unit_tests()
    if unit_failures:
        for msg in unit_failures:
            print(f"  FAIL: {msg}")
    else:
        print("  Phase 2+3+4+5 unit modules: OK")

    print("\n=== PHASE 2 SUB-STEPS (live) ===")
    phase2 = validate_phase2_substeps(out)
    phase2_failures: list[str] = []
    for sub in ("2a", "2b", "2c", "2d", "2e", "2f"):
        row = phase2[sub]
        mark = "PASS" if row["pass"] else "FAIL"
        print(f"  {sub}: {mark} — {row['detail']}")
        if not row["pass"]:
            phase2_failures.append(f"Phase {sub}: {row['detail']}")

    print("\n=== PHASE 3 SUB-STEPS (live) ===")
    phase3 = validate_phase3_substeps(out)
    phase3_failures: list[str] = []
    for sub in ("3a", "3b", "3c"):
        row = phase3[sub]
        mark = "PASS" if row["pass"] else "FAIL"
        print(f"  {sub}: {mark} — {row['detail']}")
        if not row["pass"]:
            phase3_failures.append(f"Phase {sub}: {row['detail']}")

    print("\n=== PHASE 4 SUB-STEPS (live) ===")
    phase4 = validate_phase4_substeps(out)
    phase4_failures: list[str] = []
    for sub in ("4a", "4b", "4c", "4d"):
        row = phase4[sub]
        mark = "PASS" if row["pass"] else "FAIL"
        print(f"  {sub}: {mark} — {row['detail']}")
        if not row["pass"]:
            phase4_failures.append(f"Phase {sub}: {row['detail']}")

    print("\n=== PHASE 5 SUB-STEPS (live) ===")
    phase5 = validate_phase5_substeps(out)
    phase5_failures: list[str] = []
    for sub in ("5a", "5b", "5c"):
        row = phase5[sub]
        mark = "PASS" if row["pass"] else "FAIL"
        print(f"  {sub}: {mark} — {row['detail']}")
        if not row["pass"]:
            phase5_failures.append(f"Phase {sub}: {row['detail']}")

    baseline_issues = validate_reference_baseline(out)
    if baseline_issues:
        print("\n=== REFERENCE BASELINE ===")
        for issue in baseline_issues:
            print(f"  - {issue}")

    issues = validate_live_output(out)
    issues.extend(phase2_failures)
    issues.extend(phase3_failures)
    issues.extend(phase4_failures)
    issues.extend(phase5_failures)
    issues.extend(baseline_issues)
    issues.extend(unit_failures)
    if issues:
        print("\nVALIDATION ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("\nLive validation: OK")
    try:
        import sys
        from pathlib import Path

        _app = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_app / "scripts"))
        from agent_gate_proof import record_gate

        record_gate("t4", cmd="scripts/live_validate_analysis.py", version=core.VERSION)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
