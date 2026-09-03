# Work completion — BSOD Analyzer

**Canonical rules:** `C:\Users\binar\.cursor\AgentStarterPack\pack\docs\WORK_COMPLETION.md` (read that first).

This file adds **project paths only** — no duplicate lifecycle rules.

---

## Project paths

| Item | Path |
|------|------|
| Project root | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer` |
| Work queue | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\WORK_QUEUE.md` |
| Active handoffs | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\handoffs\active\` |
| Session handoff | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\handoffs\SESSION.md` |
| Tests | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\run_tests.bat` |
| Audit | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\run_audit.cmd` |
| Product truth (capabilities) | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\PRODUCT_REFERENCE.md` |
| Doc owners index | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\DOC_MAP.md` |
| Tradeoffs / install modes | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\KNOWN_LIMITATIONS.md` |
| Roadmap / work-queue row | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\ROADMAP.md` |
| Layout / runtime paths | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\PROJECT_LAYOUT.md` |

Canonical Step 3 procedure: `C:\Users\binar\.cursor\AgentStarterPack\pack\docs\WORK_COMPLETION.md` § Step 3.

**BSOD handoff policy:** when a slice is Done, **delete** `docs/handoffs/active/HANDOFF_*.md` after updating the WQ Done log — no handoff archive in this repo.

---

## BSOD audit Fix vs delete (common mistake)

Section B Fix lines may name **gitignored build scratch** (`build\`, `dist\`, committed `__pycache__`) or **obsolete migration scripts** listed in `docs/AUDIT.config.json`. They do **not** authorize removing:

- `BSODAnalyzer_v6\` (build output — policy in `PROJECT_LAYOUT.md`)
- `BSODAnalyzer_portable\` (runtime user data)
- `docs\handoffs\`, `docs\WORK_QUEUE.md`, or any `.audit_*` JSON

When in doubt, **Improve** or ask — do not bulk-delete.
