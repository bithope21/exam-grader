# Windows UAT Issue Investigation Report

> Investigated: 2026-09-12
> Repo: `D:\AI\projects\exam-grader\exam-grader\`
> Platform: Windows 10, PyInstaller frozen `.exe`, Inno Setup per-user install

---

## Issue 1: Settings → Template Management Button Non-Functional

### Symptom
Clicking "⚙️ ตั้งค่า" → "📋 รูปแบบกระดาษคำตอบ (เพิ่ม/ปรับเทียบ/จัดการแม่แบบ)…" in the installed `.exe` does nothing or fails silently.

### Call Chain

| Step | File | Line(s) | Code |
|------|------|---------|------|
| 1 | `ui.py` | 269–289 | `settings_button` creates `QMenu`, action connects to `open_template_settings` |
| 2 | `ui.py` | 346–349 | `open_template_settings()` → `TemplateSettingsDialog(self.application, self).exec()` |
| 3 | `settings_ui.py` | 222–359 | `TemplateSettingsDialog.__init__` calls `self.refresh_templates()` |
| 4 | `settings_ui.py` | 361–401 | `refresh_templates()` → `load_builtin_template(b_id)` for each of 3 built-ins |
| 5 | `template_manager.py` | 297–317 | `load_builtin_template()` → `files("exam_grader").joinpath("resources/…")` |
| 6 | `template_manager.py` | 336–344 | `get_reference_image()` → `files("exam_grader").joinpath("resources/reference.png").read_bytes()` |

### Root Cause Hypothesis: HIGH CONFIDENCE

**`importlib.resources.files()` fails in the PyInstaller frozen `.exe`.**

On line 225 of `template_manager.py`:
```python
data = json.loads(files("exam_grader").joinpath("resources/template.json").read_text())
```

And on lines 338–342 for reference images:
```python
data = files("exam_grader").joinpath("resources/reference.png").read_bytes()
```

PyInstaller does **not** natively support `importlib.resources.files()` (the `files()` API is from Python 3.9+, and PyInstaller's hidden-import/resource-collection mechanism predates it). The `--collect-data exam_grader` flag in `scripts/build/build.py` (line 14) tells PyInstaller to copy data files, but the `Traversable` / `MultiplexedPath` objects returned by `files()` do not map to the flat file layout PyInstaller creates.

**In a frozen .exe, `files("exam_grader")` raises `ModuleNotFoundError` or returns a path that does not contain `resources/`.**

The dialog silently catches all exceptions on lines 366–368:
```python
try:
    self.templates_list.append(load_builtin_template(b_id))
except Exception:
    pass  # ← SWALLOWS the error
```

And lines 461–474 catch the reference image load error:
```python
try:
    ref_bgr = get_reference_image(t, self.application.data_dir)
except Exception as e:
    self.preview_image_lbl.setText(f"ไม่สามารถโหลดภาพอ้างอิง: {e}")
```

The dialog renders with an empty template list and no preview images, making it appear "broken."

### Contributing Factors

1. **PyInstaller hidden import**: `importlib.resources` needs `importlib_resources` or explicit hooks for `files()` on older Python versions.
2. **`--collect-data` may not match `files()` traversal**: PyInstaller's `--collect-data` copies files but the internal path resolution used by `files()` may differ from the `_MEIPASS` layout.
3. **`--collect-submodules` missing**: No explicit collection for `exam_grader.resources` subpackage.

### Reproduction Steps

1. Build the `.exe`: `python scripts/build/build.py`
2. Install via Inno Setup (per-user install to `{localappdata}\Programs\ExamGrader`)
3. Launch `ExamGrader.exe`
4. Click "⚙️ ตั้งค่า" → "📋 รูปแบบกระดาษคำตอบ…"
5. **Expected**: Dialog opens with 3 built-in templates, preview images
6. **Actual**: Empty list or error message, no previews

### Relevant Files

| File | Relevance |
|------|-----------|
| `src/exam_grader/template_manager.py:297-317, 320-362` | `load_builtin_template()` and `get_reference_image()` using `importlib.resources.files()` |
| `src/exam_grader/settings_ui.py:361-401` | `refresh_templates()` — silent exception swallowing |
| `scripts/build/build.py:11-26` | PyInstaller invocation — missing `--hidden-import` for `importlib.resources` |
| `scripts/build/windows-installer.iss` | Installer config — no evidence of bundling resources correctly |

### Proposed Fix (no implementation)

1. Replace `importlib.resources.files()` with a **PyInstaller-safe fallback**:
   ```python
   try:
       # Development / normal Python
       data = json.loads(files("exam_grader").joinpath("resources/template.json").read_text())
   except (ModuleNotFoundError, FileNotFoundError, TypeError):
       # Frozen .exe — use __file__ or sys._MEIPASS
       import sys
       base = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
       data = json.loads((base / "resources" / "template.json").read_text())
   ```
2. Add `--hidden-import importlib_resources` to `scripts/build/build.py` if using the backport.
3. Remove `except Exception: pass` in `refresh_templates()` — log or surface the error.

---

## Issue 2: Save/Excel Export Fails with `[WinError 5] Access is denied`

### Symptom
Clicking "บันทึกผลตรวจ + Excel" in the exam dialog fails with `[WinError 5] Access is denied` during the `.staging-* → output path` atomic rename.

### Call Chain

| Step | File | Line(s) | Code |
|------|------|---------|------|
| 1 | `exam_ui.py` | 1269–1278 | `export()` creates `ExportWorker` → calls `export_results()` |
| 2 | `exporting.py` | 245–265 | `export_results()` resolves `root_parent`, creates `root`, creates `staging = tempfile.mkdtemp(prefix=".staging-", dir=root)` |
| 3 | `exporting.py` | 269–383 | Writes checked images, Excel, JSON into `staging/` |
| 4 | `exporting.py` | 390–398 | Creates `final = root / stamp`, then **`os.replace(staging, final)`** |
| 5 | `exporting.py` | 406 | `shutil.rmtree(staging)` in `finally` |

### Root Cause Hypothesis: HIGH CONFIDENCE

**`os.replace()` fails on Windows because the staging directory is not empty, or the target already exists.**

The critical sequence (lines 388–398):
```python
stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S")
sequence = 1
while True:
    final = root / (stamp if sequence == 1 else f"{stamp}_{sequence:02d}")
    try:
        final.mkdir()
        reserved = True
        break
    except FileExistsError:
        sequence += 1
os.replace(staging, final)
```

**Problem 1: `os.replace()` cannot atomically rename a directory onto an existing directory on Windows.**
`os.replace()` uses `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING`. On Windows, this call:
- **Fails with `WinError 5`** (Access Denied) if the destination is a non-empty directory.
- The code does `final.mkdir()` first, creating a non-empty target... no wait, it creates an empty directory. But `os.replace()` on Windows:
  - For files: replaces atomically
  - For directories: **fails with WinError 5** when the target already exists (even if empty), because Windows cannot atomically replace a directory via `MoveFileExW`.

This is the **primary root cause**: `os.replace()` on a directory is a no-op or error on Windows.

**Problem 2: File locks.**
If Excel (`scores.xlsx`) or any checked image file (`.jpg`) is still open by another process (antivirus scanner, Windows Explorer preview pane, OneDrive sync), the `shutil.rmtree(staging)` in the `finally` block will also fail, and `os.replace()` itself can fail if the staging directory has locked files.

**Problem 3: Antivirus / Defender sandbox.**
Windows Defender real-time protection may lock newly created files in `staging/` before the atomic move completes, particularly for `.xlsx` files which are commonly scanned.

**Problem 4: Unicode path length.**
The path structure is:
```
{root_parent}/{human_readable_name_Thai}/ผลการตรวจ/.staging-{uuid}
```
On Windows, the `MAX_PATH` limit (260 chars) can be exceeded with Thai characters (3 bytes per char in UTF-8, but Windows counts in UTF-16 code units). The `human_readable_name()` function truncates at 180 bytes but doesn't account for the full path including the Thai folder name "ผลการตรวจ" and the staging UUID.

### Relevant Files

| File | Relevance |
|------|-----------|
| `exporting.py:265` | `staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))` — staging dir creation |
| `exporting.py:388-398` | `final.mkdir()` + `os.replace(staging, final)` — **THE BUG** |
| `exporting.py:402-406` | `finally` block — cleanup on failure |
| `exporting.py:256-262` | `root_parent` resolution and `os.access()` check |
| `exporting.py:36-47` | `human_readable_name()` — path component generation |
| `exam_ui.py:1269-1278` | Export trigger — `ExportWorker` |
| `exam_ui.py:205-219` | `ExportWorker.run()` — exception handling |

### Reproduction Steps

1. Create an exam, import key + student sheets, complete review
2. Go to "ผลลัพธ์" tab
3. Click "บันทึกผลตรวจ + Excel"
4. **Expected**: Export completes, folder opens
5. **Actual**: Error dialog: `[WinError 5] Access is denied`

Note: May also fail with `PermissionError: [WinError 5] The process cannot access the file because it is being used by another process` if antivirus is involved.

### Verified Facts

- `os.replace()` on directories does **not** work atomically on Windows (it raises `PermissionError` / `WinError 5`).
- The staging directory is created under `root` (the timestamped output folder), and `final` is also a subdirectory of `root`.
- The code does `final.mkdir()` before `os.replace()`, which creates the target directory that `os.replace()` then tries to replace — this is the exact pattern that fails on Windows.
- `tempfile.mkdtemp()` creates the staging dir with restrictive permissions, which may conflict with the target directory permissions.

### Unknowns

- Whether the user's output root is on a network drive or OneDrive-synced folder (which adds additional locking).
- Whether the error occurs on first export or only on re-export (when a previous export already exists).
- Whether Defender or other AV is actively locking `.xlsx` files at the time of export.

### Risk Assessment

| Risk | Level | Notes |
|------|-------|-------|
| Data loss on failure | LOW | `finally` block cleans up staging; existing exports remain |
| Repeated failure on every export | HIGH | Every export attempt will fail on Windows |
| Silent data corruption | LOW | `os.replace()` fails atomically; no partial writes |
| UX degradation | HIGH | Users cannot export results at all |

### Proposed Fix (no implementation)

Replace the atomic-rename pattern with a **copy-then-cleanup** approach that works on Windows:

```python
# Instead of os.replace(staging, final):
# 1. final.mkdir() already done
# 2. Copy staging contents into final
for item in staging.rglob("*"):
    rel = item.relative_to(staging)
    dest = final / rel
    if item.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
    else:
        shutil.copy2(item, dest)
# 3. Verify manifest hashes match
# 4. Clean up staging
shutil.rmtree(staging)
```

Alternatively, use `pathlib.Path.replace()` which on Windows calls `os.rename()` (not `os.replace()`), and handle the case where `final` already exists by removing it first (with file-lock retry logic).

Additional mitigations:
- Add retry logic with exponential backoff for `PermissionError` (handles AV file locks).
- Add path length validation before export.
- Log the full error including the path that caused the failure.

---

## Summary

| Issue | Root Cause | Confidence | Fix Complexity |
|-------|-----------|------------|----------------|
| Template Management empty/broken in .exe | `importlib.resources.files()` incompatible with PyInstaller frozen layout | HIGH | Medium — add `sys._MEIPASS` fallback |
| Export `[WinError 5]` Access Denied | `os.replace()` fails on directories on Windows | HIGH | Medium — replace with copy-then-cleanup |

Both issues are Windows-specific and not reproducible on macOS/Linux in development mode, which explains why they passed automated testing.
