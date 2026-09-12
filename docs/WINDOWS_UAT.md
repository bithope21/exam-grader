# Windows User Acceptance Testing (UAT) Guide

> **Version:** 1.0.0  
> **Date:** 2026-09-12  
> **Target Platform:** Windows 10 (64-bit), PyInstaller frozen `.exe`  
> **Repository:** `D:\AI\projects\exam-grader\exam-grader\`  
> **Test Images:** `D:\AI\workspaces\exam-grader-test\`

---

## Table of Contents

1. [Environment & Build Details](#1-environment--build-details)
2. [Clean-Machine Setup Instructions](#2-clean-machine-setup-instructions)
3. [UAT Test Steps](#3-uat-test-steps)
   - [Step 1: Install (PyInstaller .exe)](#step-1-install-pyinstaller-exe)
   - [Step 2: First Launch](#step-2-first-launch)
   - [Step 3: Settings / Template Configuration](#step-3-settings--template-configuration)
   - [Step 4: Create/Open Exam](#step-4-createopen-exam)
   - [Step 5: Import Answer Sheets (Image Scanning)](#step-5-import-answer-sheets-image-scanning)
   - [Step 6: Review Detected Answers](#step-6-review-detected-answers)
   - [Step 7: Grade / Score](#step-7-grade--score)
   - [Step 8: Save Checked Results](#step-8-save-checked-results)
   - [Step 9: Excel Export](#step-9-excel-export)
   - [Step 10: Reopen App (Data Persistence Check)](#step-10-reopen-app-data-persistence-check)
   - [Step 11: Uninstall / Reinstall](#step-11-uninstall--reinstall)
4. [Known Issues Reference](#4-known-issues-reference)
5. [Proposed Automated UAT Test Structure](#5-proposed-automated-uat-test-structure)
6. [Windows-Specific Notes](#6-windows-specific-notes)

---

## 1. Environment & Build Details

| Item | Value |
|------|-------|
| **Python version (build)** | 3.13.15 |
| **Python version (pyproject.toml)** | `>=3.11,<3.14` |
| **PyInstaller version** | 6.x (dev dependency `pyinstaller>=6,<7`) |
| **Installer** | Inno Setup 6 (`PrivilegesRequired=lowest` — per-user install) |
| **Build command** | `python scripts/build/build.py` |
| **Installer command** | `iscc scripts/build/windows-installer.iss` |
| **Installer output** | `dist\Exam-Grader-v1.0.0-Windows-Setup.exe` |
| **Self-check verification** | `dist\ExamGrader\ExamGrader.exe --self-check` |
| **Build OS** | `windows-latest` (GitHub Actions) |
| **Target OS** | Windows 10 64-bit (minimum) |
| **Runtime dependencies** | PySide6 ≥6.8, platformdirs ≥4, openpyxl ≥3.1, opencv-python-headless ≥4.10, numpy ≥2 |
| **App version** | `1.0.0` (from `src/exam_grader/__init__.py`) |

### Install Paths

| Path | Description |
|------|-------------|
| `{localappdata}\Programs\ExamGrader\` | Default install directory (Inno Setup `DefaultDirName`) |
| `{localappdata}\Programs\ExamGrader\ExamGrader.exe` | Main executable |
| `{appdata}\ExamGrader\` | Application data (SQLite DB, content-addressed originals, templates) |
| `{appdata}\ExamGrader\exam-grader.sqlite3` | Primary SQLite database (schema v13) |
| `{appdata}\ExamGrader\input\originals\` | Imported source images (content-addressed) |
| `{appdata}\ExamGrader\templates\references\` | Custom template reference images (content-addressed) |
| `%USERPROFILE%\Documents\ExamGrader\` | Default output root (configurable via Settings) |

> **Note:** `platformdirs.user_data_path("ExamGrader", appauthor=False)` resolves to `%LOCALAPPDATA%\ExamGrader` on Windows. The Inno Setup installer uses `{localappdata}\Programs\ExamGrader` for the app binary itself — these are distinct directories.

---

## 2. Clean-Machine Setup Instructions

### Prerequisites

1. **Windows 10 64-bit** (or later) with .NET Framework 4.6+ (pre-installed on Win10)
2. **No Python installation required** — the `.exe` is self-contained via PyInstaller
3. **Disable Windows Defender real-time scanning** temporarily if export tests fail with `Access Denied` (Defender may lock `.xlsx` files during creation)
4. **Test images directory:** Copy `D:\AI\workspaces\exam-grader-test\` to a local path (e.g., `C:\Users\{user}\Desktop\uat-test-images\`)

### Test Images Available

| File | Purpose | Template | Questions |
|------|---------|----------|-----------|
| `IMG_0910.JPG` | Answer key (เฉลย) | Default #3 | 30 questions, 4 choices |
| `IMG_0911.JPG` | Student sheet | Default #3 | 30 questions, student #52 |
| `IMG_0912.JPG` | Student sheet | Default #3 | 30 questions, student #13 |
| `IMG_0913.JPG` | Student sheet | Default #3 | 30 questions, student #67 |
| `IMG_0914.JPG` | Student sheet | Default #3 | 30 questions, student #19 |

### Installation Steps

```
1. Run Exam-Grader-v1.0.0-Windows-Setup.exe
2. Accept default install location: %LOCALAPPDATA%\Programs\ExamGrader
3. Optionally check "Create desktop shortcut"
4. Click Install → Finish
5. Launch from Start Menu or desktop shortcut
```

---

## 3. UAT Test Steps

### Step 1: Install (PyInstaller .exe)

**Expected behavior:**
- Inno Setup installer runs with per-user privileges (no UAC prompt)
- Installs to `%LOCALAPPDATA%\Programs\ExamGrader\`
- Creates Start Menu entry under "Exam Grader"
- Optionally creates desktop shortcut (unchecked by default)
- Does NOT touch application data directory (exams/preserved across installs)
- Creates uninstall entry in Windows "Add or Remove Programs"

**What to verify:**
- [ ] Installer completes without errors
- [ ] `ExamGrader.exe` exists at install location
- [ ] `icon.ico` bundled correctly (app icon visible in taskbar)
- [ ] Start Menu shortcut created and functional
- [ ] No UAC elevation required (`PrivilegesRequired=lowest`)

**Windows-specific notes:**
- Per-user install avoids admin rights requirement
- Installer uses LZMA2 solid compression
- Uninstall removes app binary but preserves exam data in `%LOCALAPPDATA%\ExamGrader\`

**Known issues:** None at install stage.

---

### Step 2: First Launch

**Expected behavior:**
- Application window opens with the main dashboard (Thai UI)
- SQLite database initialized at `%LOCALAPPDATA%\ExamGrader\exam-grader.sqlite3`
- Schema migration runs (v0 → v13 on first launch)
- Built-in templates registered in database (`default-1`, `default-2`, `default-3`)
- Default output root set to `%USERPROFILE%\Documents\ExamGrader\`
- Application title shows "Exam Grader" with icon

**What to verify:**
- [ ] Window opens within 3 seconds
- [ ] No crash on startup
- [ ] Database file created at correct path
- [ ] Exam list is empty (first launch — no exams yet)
- [ ] Settings button (⚙️ ตั้งค่า) visible in header
- [ ] `--self-check` mode works: `ExamGrader.exe --self-check` outputs JSON with `"storage": "ok"`

**Windows-specific notes:**
- `QSettings("ExamGrader", "ExamGrader")` stores preferences in Windows Registry under `HKEY_CURRENT_USER\Software\ExamGrader\ExamGrader\`
- First launch creates the data directory; ensure `%LOCALAPPDATA%` is writable

**Known issues:** None at first launch.

---

### Step 3: Settings / Template Configuration

**Expected behavior:**
- Click ⚙️ ตั้งค่า → 📋 รูปแบบกระดาษคำตอบ (เพิ่ม/ปรับเทียบ/จัดการแม่แบบ)…
- TemplateSettingsDialog opens with 3 built-in templates listed:
  - Default #1 — กระดาษคำตอบมาตรฐาน (60 ข้อ · 5 ตัวเลือก)
  - Default #2 — กระดาษคำตอบ (60 ข้อ · 4 ตัวเลือก)
  - Default #3 — สุทธิอนุสรณ์ (30 ข้อ · 4 ตัวเลือก)
- Each template shows preview image, specs, and available actions
- Custom annotation colors configurable via 🎨 สีรอยตรวจ

**What to verify:**
- [ ] Settings menu opens from header button
- [ ] Template list shows 3 built-in templates (NOT empty)
- [ ] Preview images load for each template
- [ ] Template specs (question count, choice count) displayed correctly
- [ ] Built-in templates cannot be deleted (delete button disabled)
- [ ] Custom color settings accessible

**Known issues — ⚠️ Issue 1: Template Management Broken in .exe**

> **Status:** OPEN — HIGH CONFIDENCE root cause identified  
> **Severity:** HIGH  
> **Symptom:** Template list appears empty or preview images fail to load

**Root cause:** `importlib.resources.files()` (used in `template_manager.py:302-344`) is incompatible with PyInstaller's frozen layout. In a frozen `.exe`:
- `files("exam_grader")` may raise `ModuleNotFoundError` or return a path without `resources/`
- The `--collect-data exam_grader` flag copies files but `Traversable` path resolution differs from `_MEIPASS` layout
- `settings_ui.py:361-368` silently catches exceptions (`except Exception: pass`), hiding the failure

**Impact:** Users cannot view or manage templates. Core grading still works if exams are created with default templates through the NewExamDialog (which may use fallback paths).

**Proposed fix:**
1. Replace `importlib.resources.files()` with `sys._MEIPASS` fallback in `template_manager.py`
2. Remove silent exception swallowing in `settings_ui.py`
3. Add `--hidden-import importlib_resources` to build script

---

### Step 4: Create/Open Exam

**Expected behavior:**
- Click "➕ สร้างข้อสอบใหม่" on main dashboard
- NewExamDialog opens with fields:
  - ชื่อข้อสอบ (Exam name)
  - ปีการศึกษา (Academic year, e.g., "2569")
  - ชั้น/ระดับชั้น (Grade, e.g., "ป.6")
  - ห้อง (Room)
  - วิชา (Subject)
  - จำนวนข้อ (Question count: 1–60)
  - เลขที่คาดหวัง (Expected student number max, optional)
  - แม่แบบกระดาษ (Template selector)
- Inline ⚙️ จัดการแม่แบบ… button allows template management from dialog
- After creation, exam appears in main list and opens workspace

**What to verify:**
- [ ] All form fields accept Thai Unicode text
- [ ] Question count constrained to 1–60
- [ ] Template dropdown populated (at least default-3 visible)
- [ ] Exam created successfully and appears in list
- [ ] Exam workspace opens with tabs: นักเรียน / เฉลย / ตรวจทาน / ผลลัพธ์

**Windows-specific notes:**
- Thai characters (ก–๙) should render correctly with system Thai font
- Input fields use minimum height 32px for Thai vowel/tone mark visibility
- Exam name field enforces max 200 characters

**Known issues:** Template dropdown may be empty if Issue 1 (template loading) prevents built-in templates from loading.

---

### Step 5: Import Answer Sheets (Image Scanning)

**Expected behavior:**
- Navigate to เฉลย tab → click to import key image (IMG_0910.JPG)
- System performs:
  1. Image decode (JPEG/PNG support)
  2. EXIF orientation correction
  3. Geometric registration (perspective warping to canonical template)
  4. Template matching and validation
  5. OMR-based answer detection per cell
  6. Student number crop and OCR attempt
- Import progress shown with filename and sheet count
- Failed imports logged to `import_failures` table with error messages
- After key import: teacher must review and approve key before student import

**What to verify:**
- [ ] JPEG and PNG files accepted
- [ ] File dialog shows Thai filenames correctly
- [ ] Import progress bar updates
- [ ] Key sheet imported successfully (detected answers visible)
- [ ] Key requires teacher approval before proceeding
- [ ] Invalid/corrupt images handled gracefully (error message, not crash)
- [ ] Duplicate content hash detected (same file imported twice → skipped)

**Windows-specific notes:**
- Content-addressed storage at `%LOCALAPPDATA%\ExamGrader\input\originals\{sha256}.jpg`
- File paths support Thai characters (Unicode-safe via `pathlib.Path`)
- EXIF orientation from camera phone photos handled automatically

**Known issues:** None specific to import stage.

---

### Step 6: Review Detected Answers

**Expected behavior:**
- After key approval, import student sheets (IMG_0911–0914.JPG)
- Navigate to ตรวจทาน tab
- Issue table shows items requiring teacher attention:
  - Uncertain OMR marks (classification: "uncertain")
  - Multiple marks (classification: "multiple")
  - Blank cells (if expected to be filled)
  - Missing/unresolved student numbers
  - Duplicate student numbers
- Each row has: checkbox, student #, question #, current detection, edit controls
- Bulk edit toolbar: [เลือกทั้งหมด], [ล้างการเลือก], selection count, bulk apply button
- Inline editing: answer dropdown (A–E, blank, multiple) + save button per row

**What to verify:**
- [ ] Issue table populated with detection results
- [ ] Checkbox multi-select works (click, Space key, select/deselect all)
- [ ] Bulk edit toolbar counts synchronize with selection
- [ ] Individual row editing works (dropdown + save)
- [ ] Student number issues surfaced with distinct statuses (duplicate, missing, uncertain, out_of_range)
- [ ] Bulk save resolves selected issues and removes them from table
- [ ] Unsolved issues prevent export (stale protection)

**Windows-specific notes:**
- CheckBoxDelegate expanded hit area (52px) for easier clicking on high-DPI displays
- Table horizontal scrollbar absent at 1024×768 viewport (no overflow)
- Row heights 52px minimum for Thai text visibility

**Known issues:** None specific to review stage.

---

### Step 7: Grade / Score

**Expected behavior:**
- Scoring uses approved key + teacher-resolved reviews only
- `score_answer()` in `workflow.py`: 1 point per single correct choice in accepted set
- States: blank (0 pts), multiple (0 pts), boundary_cross (0 pts), correct (1 pt)
- Score rendered in template score ROI on checked image
- `snapshot()` produces versioned, immutable grade data

**What to verify:**
- [ ] Scores calculated correctly against approved key
- [ ] Blank/multiple/boundary_cross answers score 0
- [ ] Review-resolved answers used for scoring
- [ ] Stale key changes trigger re-grade requirement
- [ ] Score visible in Results tab

**Windows-specific notes:** Scoring is pure computation — no OS-specific concerns.

**Known issues:** None at scoring stage.

---

### Step 8: Save Checked Results

**Expected behavior:**
- Checked images generated as derived JPEG (quality 88, long edge ≤2400px)
- Red ✓/✗/! annotations drawn in canonical coordinates, warped with registration inverse
- Student number and score overlaid on checked image
- Checked images saved to export directory under `ผลการตรวจ/`

**What to verify:**
- [ ] Checked images generated for all graded students
- [ ] Annotations aligned with answer cells (visual inspection)
- [ ] Student numbers visible on checked images
- [ ] Scores displayed in score ROI
- [ ] Original source images unchanged (hash verification)

**Known issues — ⚠️ Issue 2: Save/Export Fails with `[WinError 5] Access is denied`**

> **Status:** OPEN — HIGH CONFIDENCE root cause identified  
> **Severity:** HIGH  
> **Symptom:** Export fails with `[WinError 5] Access is denied` during staging → final directory rename

**Root cause:** `os.replace(staging, final)` in `exporting.py:398` fails on Windows because:
1. `os.replace()` cannot atomically replace a directory on Windows (`MoveFileExW` with `MOVEFILE_REPLACE_EXISTING` raises `WinError 5` for directories)
2. The code creates `final.mkdir()` then calls `os.replace(staging, final)` — this exact pattern fails on Windows
3. Additional factors: antivirus file locks, OneDrive sync, file locks from Explorer preview

**Impact:** Users cannot save/export results at all on Windows. Export is a core workflow step.

**Proposed fix:**
1. Replace `os.replace()` with copy-then-cleanup: copy staging contents into `final`, then `shutil.rmtree(staging)`
2. Add retry logic with exponential backoff for `PermissionError` (handles AV locks)
3. Add path length validation before export (Thai folder names + staging UUID can approach MAX_PATH 260)

---

### Step 9: Excel Export

**Expected behavior:**
- `scores.xlsx` generated with openpyxl
- **Scores sheet:** No., Score, Max, Status, Source File per student
- **Info sheet:** Exam metadata, active template name, export timestamp
- **Provenance:** `_system/manifest.json` with artifact hashes and snapshot fingerprint
- Export directory opened automatically after completion

**What to verify:**
- [ ] `scores.xlsx` created and opens in Excel/LibreOffice
- [ ] Scores sheet has correct columns and data
- [ ] Info sheet shows exam metadata
- [ ] Checked image JPEGs present in export directory
- [ ] `manifest.json` contains correct hashes
- [ ] Export path: `%USERPROFILE%\Documents\ExamGrader\{exam_name}_results\ผลการตรวจ\{timestamp}\`

**Windows-specific notes:**
- Export path includes Thai subfolder name "ผลการตรวจ" — must be valid Windows path
- `MAX_PATH` (260 chars) limit: full path can approach limit with long exam names + Thai characters
- `.xlsx` files may trigger Windows Defender real-time scanning → potential file lock
- OneDrive-synced Documents folder may add latency or lock files

**Known issues:** Blocked by Issue 2 (Access Denied on save). If save step fails, Excel export will also fail since they share the same export pipeline.

---

### Step 10: Reopen App (Data Persistence Check)

**Expected behavior:**
- Close app completely, reopen
- Exam list preserved (SQLite database persisted)
- Exam workspace retains all data: imported sheets, key, reviews, scores
- Output root preference preserved (QSettings in Windows Registry)
- Custom annotation colors preserved

**What to verify:**
- [ ] Previously created exam appears in main list
- [ ] Exam opens with all imported sheets intact
- [ ] Key approval status preserved
- [ ] Review decisions preserved
- [ ] Scores unchanged
- [ ] Output root setting remembered
- [ ] Custom color settings remembered

**Windows-specific notes:**
- `QSettings` stored in `HKCU\Software\ExamGrader\ExamGrader\`
- SQLite database at `%LOCALAPPDATA%\ExamGrader\exam-grader.sqlite3` persists across restarts
- App data directory NOT removed by uninstall (data survives uninstall/reinstall)

**Known issues:** None at persistence stage.

---

### Step 11: Uninstall / Reinstall

**Expected behavior:**
- Run Windows "Add or Remove Programs" → Exam Grader → Uninstall
- Inno Setup uninstaller removes:
  - `%LOCALAPPDATA%\Programs\ExamGrader\` (app binary)
  - Start Menu shortcut
  - Desktop shortcut (if created)
- Does NOT remove:
  - `%LOCALAPPDATA%\ExamGrader\` (exam data, database, originals)
  - `%USERPROFILE%\Documents\ExamGrader\` (export results)
  - `QSettings` registry entries
- Reinstall with same or newer version:
  - Database auto-migrates if schema version differs (v13 backup + upgrade)
  - Exams preserved and accessible

**What to verify:**
- [ ] Uninstall completes without errors
- [ ] App binary removed from install directory
- [ ] Exam data directory still exists after uninstall
- [ ] Export results still accessible after uninstall
- [ ] Reinstall succeeds
- [ ] Previous exams visible after reinstall
- [ ] Schema migration handles version differences gracefully

**Windows-specific notes:**
- Uninstaller runs with same privilege level as install (per-user, no UAC)
- QSettings registry entries may persist after uninstall (benign)

**Known issues:** None at uninstall/reinstall stage.

---

## 4. Known Issues Reference

### Issue 1: Template Management Broken in .exe

| Attribute | Detail |
|-----------|--------|
| **Status** | 🔴 OPEN |
| **Severity** | HIGH |
| **Confidence** | HIGH |
| **Symptom** | Template list empty, no preview images in Settings dialog |
| **Root Cause** | `importlib.resources.files()` incompatible with PyInstaller frozen layout |
| **Files** | `template_manager.py:297-344`, `settings_ui.py:361-368`, `scripts/build/build.py:14` |
| **Reproduction** | Build .exe → Launch → ⚙️ ตั้งค่า → 📋 รูปแบบกระดาษคำตอบ |
| **Fix Complexity** | Medium — add `sys._MEIPASS` fallback |
| **macOS Reproducible** | No — only fails in PyInstaller frozen .exe |

### Issue 2: Save/Export Access Denied

| Attribute | Detail |
|-----------|--------|
| **Status** | 🔴 OPEN |
| **Severity** | HIGH |
| **Confidence** | HIGH |
| **Symptom** | `[WinError 5] Access is denied` during export |
| **Root Cause** | `os.replace()` fails on directories on Windows |
| **Files** | `exporting.py:388-398`, `exam_ui.py:1269-1278` |
| **Reproduction** | Create exam → Import sheets → Grade → Click บันทึกผลตรวจ + Excel |
| **Fix Complexity** | Medium — replace with copy-then-cleanup |
| **macOS Reproducible** | No — `os.replace()` works on directories on Unix |

### Issue 3: Template Mismatch (Test Environment)

| Attribute | Detail |
|-----------|--------|
| **Status** | 🟡 OBSERVED (test environment) |
| **Severity** | MEDIUM |
| **Symptom** | Exam using `default-3` (30Q) but DB only has `default-1` (60Q) registered |
| **Context** | Observed during initial Windows test with pre-existing exam data |
| **Resolution** | Ensure schema v13 migration runs (registers all 3 built-ins); Issue 1 may prevent this |

---

## 5. Proposed Automated UAT Test Structure

### Directory Layout

```
tests/uat/
├── __init__.py
├── conftest.py                  # Shared fixtures: app init, temp dirs, image paths
├── test_uat_install.py          # Simulate install verification (paths, binaries)
├── test_uat_first_launch.py     # Database init, schema migration, startup health
├── test_uat_templates.py        # Template loading, preview, built-in registration
├── test_uat_exam_workflow.py    # Full create → import → review → grade → export
├── test_uat_persistence.py      # Reopen, data survive restart
├── test_uat_export.py           # Excel output, checked images, manifest
├── test_uat_unicode_paths.py    # Thai filenames, folder names, MAX_PATH
├── test_uat_error_handling.py   # Corrupt images, missing templates, disk full
└── fixtures/
    ├── images/                  # Symlink or copy of test images
    │   ├── key.JPG
    │   ├── student_01.JPG
    │   └── ...
    ├── expected/                # Expected outputs for golden tests
    │   ├── scores.xlsx
    │   └── manifest.json
    └── configs/
        └── test_settings.json   # Pre-configured settings for UAT
```

### Shared Test Fixtures (`conftest.py`)

```python
"""Shared fixtures for Windows UAT tests."""
import os
import tempfile
from pathlib import Path

import pytest

# Force offscreen rendering for CI/headless environments
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def uat_data_dir(tmp_path):
    """Fresh application data directory for each UAT test."""
    return tmp_path / "app_data"


@pytest.fixture
def uat_app(uat_data_dir):
    """Initialized Application with clean database."""
    from exam_grader.app import initialize
    return initialize(uat_data_dir)


@pytest.fixture
def test_images():
    """Path to real test images."""
    # In CI: tests/uat/fixtures/images/
    # Local: D:\AI\workspaces\exam-grader-test\
    local = Path(r"D:\AI\workspaces\exam-grader-test")
    if local.exists():
        return local
    return Path(__file__).parent / "fixtures" / "images"


@pytest.fixture
def qt_app():
    """ QApplication instance for UI tests."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app
```

### Sample Test: Full Workflow UAT (`test_uat_exam_workflow.py`)

```python
"""End-to-end exam workflow UAT on Windows."""
import json
import os
import tempfile

from pathlib import Path

import pytest

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.exam_ui import BatchWorker
from exam_grader.exporting import export_results
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.workflow import Workflow


def test_full_workflow_import_review_export(uat_app, test_images, tmp_path):
    """Create exam → import key → import students → review → export."""
    app = uat_app
    exam = app.exams.create(ExamDetails(
        name="UAT ทดสอบ",
        academic_year="2569",
        grade="ป.6",
        room="1",
        subject="วิทยาศาสตร์",
        question_count=30,
        expected_number_max=100,
        template_id="default-3",
        template_version=1,
    ))
    flow = Workflow(app.exams.path)
    importer = ImportService(app.exams.path)
    reviewer = ReviewService(app.exams.path)

    # Import key
    key_path = test_images / "IMG_0910.JPG"
    worker = BatchWorker(app.exams.path, exam.id, [key_path], "key")
    worker.start()
    assert worker.wait(60000), "Key import timed out"
    assert not importer.list_failures(exam.id), "Key import failed"

    # Approve key
    key_source = next(
        s for s in importer.list_sources(exam.id) if s["purpose"] == "key"
    )
    reviewer.auto_key(exam.id)

    # Import students
    student_paths = sorted(test_images.glob("IMG_091[1-4].JPG"))
    worker = BatchWorker(app.exams.path, exam.id, student_paths, "student")
    worker.start()
    assert worker.wait(120000), "Student import timed out"

    # Verify snapshot
    snapshot = flow.snapshot(exam.id)
    assert len(snapshot["results"]) == 4

    # Export
    export_dir = tmp_path / "exports"
    result = export_results(flow, exam.id, export_dir)
    assert result.exists()
    assert (result / "scores.xlsx").exists()
    assert (result / "_system" / "manifest.json").exists()


def test_unicode_path_export(uat_app, test_images, tmp_path):
    """Export to a path with Thai characters."""
    app = uat_app
    # ... (similar setup) ...
    export_root = tmp_path / "ผลการตรวจไทย"
    export_root.mkdir(parents=True)
    # Verify export succeeds with Thai path
    # ... export and assert ...
```

### Sample Test: Windows-Specific (`test_uat_export.py`)

```python
"""Windows-specific export behavior tests."""
import os
import sys
import pytest
from pathlib import Path


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_os_replace_fails_on_directory():
    """Verify that os.replace() fails on directories (the known Issue 2)."""
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        src = Path(root) / "staging"
        dst = Path(root) / "final"
        src.mkdir()
        dst.mkdir()
        (src / "test.txt").write_text("hello")
        with pytest.raises(OSError):
            os.replace(str(src), str(dst))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_export_with_copy_fallback(tmp_path):
    """Verify export succeeds using copy-then-cleanup approach."""
    # After fix is applied, this should pass
    pass  # Placeholder for post-fix verification


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_long_thai_path_respects_max_path(tmp_path):
    """Verify export path does not exceed Windows MAX_PATH (260)."""
    long_name = "สอบปลายภาค" * 10  # 30 Thai chars
    export_path = tmp_path / long_name / "ผลการตรวจ" / "2026-09-12_120000"
    # After fix: should either work or give clear error
    # Before fix: may silently fail
```

---

## 6. Windows-Specific Notes

### Path Handling

- All file I/O uses `pathlib.Path` — Unicode-safe on Windows
- Thai folder names (3 UTF-16 code units per character) consume more `MAX_PATH` budget
- `human_readable_name()` truncates at 180 UTF-8 bytes, but `MAX_PATH` counts in UTF-16 code units
- Content-addressed storage uses SHA256 hex strings (ASCII-safe)

### Database

- SQLite at `%LOCALAPPDATA%\ExamGrader\exam-grader.sqlite3`
- Schema v13 with automatic pre-migration backup (`.v12.bak`)
- WAL mode may leave `-wal` and `-shm` sidecar files (normal behavior)
- Concurrent access: single-user app, but antivirus may inspect DB file

### Permissions

- Per-user install: no admin rights needed
- `%LOCALAPPDATA%` is always writable by the user
- `%USERPROFILE%\Documents` may be synced by OneDrive (adds latency/locking)
- Windows Defender may lock newly created files briefly

### QSettings (Preferences)

- Stored in Windows Registry: `HKCU\Software\ExamGrader\ExamGrader\`
- Persists: output_root, annotation_colors, default_template_id
- Survives uninstall (benign — no functional impact)

### Font Rendering

- Thai UI uses system font stack: `"Segoe UI"`, `"Noto Sans Thai"`, `"Thonburi"`
- Minimum row heights enforced (52–58px) to prevent Thai vowel/tone mark clipping
- High-DPI scaling handled by Qt; CheckBoxDelegate hit area expanded to 52px

### PyInstaller Frozen .exe

- Resources bundled via `--collect-data exam_grader`
- `sys._MEIPASS` available at runtime for resource path resolution
- `importlib.resources.files()` may NOT work in frozen environment (Issue 1)
- Self-check mode: `ExamGrader.exe --self-check` verifies storage and dependencies
- Smoke-UI mode: `ExamGrader.exe --smoke-ui` opens and closes UI after 700ms

### Build Reproduction

```bash
# On Windows with Python 3.13
pip install -e .[dev]
python scripts/build/build.py                    # PyInstaller .exe
iscc scripts/build/windows-installer.iss        # Inno Setup installer
dist\ExamGrader\ExamGrader.exe --self-check     # Verify build
```

---

## Appendix: Quick Reference Checklist

| Step | Pass | Fail | Notes |
|------|------|------|-------|
| 1. Install | ⬜ | ⬜ | |
| 2. First Launch | ⬜ | ⬜ | |
| 3. Settings/Templates | ⬜ | ⬜ | Issue 1 expected |
| 4. Create Exam | ⬜ | ⬜ | |
| 5. Import Sheets | ⬜ | ⬜ | |
| 6. Review Answers | ⬜ | ⬜ | |
| 7. Grade/Score | ⬜ | ⬜ | |
| 8. Save Results | ⬜ | ⬜ | Issue 2 expected |
| 9. Excel Export | ⬜ | ⬜ | Issue 2 expected |
| 10. Reopen/Persist | ⬜ | ⬜ | |
| 11. Uninstall/Reinstall | ⬜ | ⬜ | |

**Overall Verdict:** ⬜ PASS ⬜ FAIL ⬜ BLOCKED

**Tester:** _________________ **Date:** _________________ **Build:** v1.0.0

---

*This document covers the full teacher user journey for Windows UAT. Known issues (Issue 1: template management, Issue 2: export Access Denied) are expected blockers that must be resolved before production release on Windows.*
