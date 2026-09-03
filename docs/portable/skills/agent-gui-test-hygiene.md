# Skill: agent-gui-test-hygiene

Auto-generated from `pack/skills/agent-gui-test-hygiene/SKILL.md`. **Do not edit by hand.**

Pack version: 1.8.0

---

# Agent GUI Test Hygiene

## Environment

- Set `QT_QPA_PLATFORM=offscreen` (Qt) **before** importing Qt widgets.
- Use an isolated settings/temp dir per test (no install-mode dialogs).
- Pump events with a **timeout** (`processEvents` loop + deadline), never infinite wait.

## Rules for test code

| Rule | Why |
|------|-----|
| No blocking modal dialogs during teardown | `QMessageBox.exec()` blocks forever offscreen |
| `closeEvent`: skip user prompts when `_shutting_down` | Programmatic `win.close()` must not open modals |
| Teardown waits on **all** worker threads | `_summary_refresh_thread`, `_ps_thread`, `_drv_thread`, etc. |
| Mock long I/O workers in unit tests | PowerShell, network, CDB scan — keep tests <30s |
| One logical assertion per window lifecycle | Avoid chaining multiple async workers without waiting |

## Teardown checklist

```python
def teardown_main_window(win):
    win._shutting_down = True
    for attr in ("_summary_refresh_thread", "_ps_thread", "_drv_thread", ...):
        th = getattr(win, attr, None)
        if th and th.isRunning():
            th.quit()
            th.wait(2000)
        setattr(win, attr, None)
    win.close()
    app.processEvents()
```

## If tests hang

1. Run `agent_hygiene_full_check` — orphan python often survives after killing the test shell.
2. Identify blocking modal: search `QMessageBox`, `dialog.exec()`, `input(` in close/teardown paths.
3. Split hung test: run single test function in isolation with a wall-clock timeout.
4. Use `run_tests.bat` for the full suite; use `run_audit.cmd` when auditing.

## Agent timing

- Offscreen GUI smoke (6–10 tests): **~20–45s** total
- If a single test exceeds **60s**, treat as hung — kill and fix teardown/worker mock

## Do not

- Assume `close()` is instant when background workers or modals exist
- Force-kill parent shell without running orphan cleanup afterward
