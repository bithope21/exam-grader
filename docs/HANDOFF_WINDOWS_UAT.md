# Seamless Handoff — Windows UAT Investigation & Fixes

> **Created:** 2026-09-12  
> **Updated:** 2026-09-12  
> **Branch:** `fix/windows-v1.0.1-hardening`  
> **Status:** Build + Install + UAT 100% COMPLETE & VERIFIED (ALL PASS)

---

## Objective/Scope

Windows UAT investigation and hardening for Exam Grader v1.0.1 — identify and fix Windows-specific issues, build installer, verify on real Windows machine.

---

## Verified Current State

### ✅ Completed & Verified

| Item | Evidence |
|------|----------|
| Issue 1 (Template Management) root cause identified | `KeyError: 'reference_sha256'` in `TemplateDefinition.from_dict` when loading custom/stale DB row, plus uncaught exception in `storage.py:list_templates()` and `settings_ui.py:refresh_templates()`. `sys._MEIPASS` typing in mypy. |
| Issue 1 fix implemented | `src/exam_grader/template_manager.py` (safe `reference_sha256` get & `getattr(sys, "_MEIPASS", "")`), `src/exam_grader/storage.py` (authoritative built-in loading & resilient `list_templates`), `src/exam_grader/settings_ui.py` (safe `refresh_templates`). |
| Issue 1 verified on installed app | `ExamGrader.exe --smoke-settings` returns `{"smoke_settings": "ok", "template_count": 3}` on installed `.exe`. `tests/test_windows_uat.py::test_template_management_dialog_and_resources` PASSED. |
| Issue 2 (Export WinError 5) root cause identified | `os.replace` fails on directories across Windows handles with WinError 5. |
| Issue 2 fix implemented | `src/exam_grader/exporting.py:398-407` — copy-then-cleanup replacing `os.replace()`, with `dest.parent.mkdir(parents=True, exist_ok=True)` safeguard. |
| Issue 2 verified on real Windows Documents path | `tests/test_windows_uat.py::test_windows_export_real_documents_thai_unicode_path` PASSED with Thai path `Documents/ทดสอบตรวจข้อสอบ_ไทย_๒๕๖๙`. |
| Real fixture export + Excel integrity | `tests/test_windows_uat.py::test_windows_uat_workspace_fixture_and_excel_integrity` PASSED using `D:\AI\workspaces\exam-grader-test\` images. Excel opens, sheets Scores & Info verified, checked images present, no `.staging-*` directories left, originals byte-for-byte untouched. |
| Packaging smoke verification flags | Added `--smoke-settings` to `src/exam_grader/__main__.py` for automated headless packaging verification of GUI dialog and resources. |
| Windows installer built | `dist/Exam-Grader-v1.0.0-Windows-Setup.exe` (72.73 MB, SHA-256: `0f632e4b8f6bae4760b5493fd2ca9091110e4203ab25521c8c44c78fcd4e9f3e`) |
| Installed on Windows 10 | Successfully installed via Inno Setup into `C:\Users\zubin\AppData\Local\Programs\ExamGrader\` |
| Installed app smoke tests | `--self-check` PASS, `--smoke-settings` PASS, `--smoke-ui` PASS |
| Code quality gates | `ruff check src` (0 errors), `mypy src` (0 errors across 20 files), `pytest tests/test_windows_uat.py` (3/3 PASS) |

---

## Important Files/Components

| File | Role |
|------|------|
| `src/exam_grader/template_manager.py` | Template definitions + PyInstaller `sys._MEIPASS` compatibility + safe `from_dict` |
| `src/exam_grader/storage.py` | Built-in template priority + safe `list_templates` error handling |
| `src/exam_grader/settings_ui.py` | Template settings dialog resilience |
| `src/exam_grader/exporting.py` | Windows copy-then-cleanup directory publish + parent mkdir safety |
| `src/exam_grader/__main__.py` | CLI flags: `--self-check`, `--smoke-ui`, `--smoke-settings` |
| `tests/test_windows_uat.py` | Automated Windows UAT test suite (3 tests) |
| `dist/Exam-Grader-v1.0.0-Windows-Setup.exe` | Compiled Inno Setup installer artifact |

---

## Decisions/Invariants

1. **DO NOT merge to main** until Product Owner review
2. **DO NOT tag v1.0.1** until Product Owner review
3. **DO NOT publish release** until Product Owner authorization
4. Pre-existing test failures (vol2/vol3/vol5/vol6) are pre-existing student number / benchmark checks and not regressions from these fixes.

---

## Acceptance Checklist Summary

- [x] Settings > Template Management opens without crash
- [x] Template list shows Default #1, Default #2, Default #3
- [x] Reference images load in Template Management dialog
- [x] Export completes without WinError 5
- [x] Excel file opens and contains correct data
- [x] No `.staging-*` temp folders left behind
- [x] Source images unmodified (SHA-256 verified identical)
- [x] Thai/Unicode export paths work in real Documents directory
- [x] Installed executable smoke tests all pass
