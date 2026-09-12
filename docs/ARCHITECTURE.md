# Architecture direction v0.1

สถานะ: proposed implementation boundaries; exact dependencies / production thresholds ยังไม่ frozen

## Shape

Python modular desktop application: PySide6 UI → application use cases → domain contracts; storage, imaging, OMR, recognition, renderer, export เป็น adapters ไม่มี Qt dependency ใน grading/domain และไม่มี database/file-dialog calls ใน detector

Pipeline: immutable source → decode/EXIF → quality + registration → versioned ROIs → answers + number observations → review → approved key snapshot + accepted corrections → deterministic grade → evidence/export

เริ่ม headless pipeline + desktop shell เล็ก ๆ ใช้ worker ที่ยกเลิกได้ ห้ามทำ CV บน UI thread ยังไม่ล็อก thread/process จนวัด workload/native-library behavior

## Contracts to implement incrementally

- Template: id/version, canonical dimensions, anchors, per-question cell polygons, number ROI, allowed variants; coordinates ไม่กระจายใน code
- Exam: authoritative `question_count` selected at creation, constrained to 1–60; an approved key must match it and it cannot change silently
- RegistrationResult: source/template IDs, transforms และ inverse, quality diagnostics, accepted/review/failed; orientation transform ต้อง compose รวม EXIF
- AnswerObservation: question, selected choices, classification, raw features, confidence semantics, detector/config version
- IdentityObservation: raw candidate + uncertainty; human-resolved identity แยกจาก model output
- ReviewDecision: observation reference, previous/new value, reason, timestamp; original detection ไม่ถูกเขียนทับ
- GradeSnapshot: source hash, template/pipeline/model/config versions, approved key version, review revision, scoring policy version
- ExportManifest: run ID, artifact paths/hashes, status; checked image/Excel/JSON ต้องมาจาก snapshot เดียว

Model confidence ไม่ถือเป็น probability ที่ calibrated โดยอัตโนมัติ; registration invalid ต้องหยุด downstream auto-accept
- Draft OMR uses local-darkness features relative to a local background to reduce exposure/illumination sensitivity. It remains review-required and auto-accept is disabled.

## Bounded execution additions — 2026-09-08

Student identity is a separate adapter: registered high-resolution number ROI →
numeric-only baseline candidate (when the local executable is available) →
uncalibrated observation → teacher confirmation. A candidate is never authoritative
and no model is downloaded or trained from corrections.

Checked images are derived from one snapshot. The renderer draws red ticks/X/blank
indicators and the score in canonical template coordinates, then applies the saved
registration inverse to the verified decoded source. Original bytes remain immutable;
renderer, template and detection/review provenance are recorded in the export.

Exam lifecycle uses SQLite archive state rather than recursive deletion. Shared
content-addressed originals remain while any exam can reference them, and export
history stays visible. Human-readable metadata is emitted beside the stable internal
exam/run path for backward-compatible reopen behavior.

## State and integrity

SQLite เป็น authoritative state; filesystem เป็น evidence store ใช้ stable internal IDs ไม่ใช้ชื่อไฟล์หรือเลขที่เป็น primary key รูปซ้ำตรวจด้วย content hash แยกจากเลขที่ซ้ำ

Key lifecycle: draft → approved immutable version → superseded. Detection readiness แยกจาก export readiness ผลของ key/review เก่าต้องแสดง stale

Original import: copy to app-owned location + verify hash; rerun idempotent; ไม่ลบ source ของผู้ใช้ Writes ไป staging แล้ว atomic publish พร้อม transaction/recovery journal เพราะ DB และ filesystem ไม่ได้ commit พร้อมกันเอง

กู้คืน per-sheet checkpoints; cancellation ไม่สร้างผลสำเร็จปลอม; export ซ้ำไม่เขียนทับ evidence คนละ run; generated filenames sanitize ตาม Windows รวม reserved names และ Unicode collisions

## Custom Answer-Sheet Template and Calibration Subsystem — 2026-09-10

- **Template Model (`TemplateDefinition`, `AnswerBlock`)**: Strongly typed data contracts capturing canonical width/height, choice count (2–5), question count (1–60), block-by-block column and row boundary coordinates, cell insets, student number and score ROIs, and bidirectional choice mapping (`choice_map`, `choice_labels`, `display_choice_labels`).
- **Template Storage & Schema v13**: SQLite schema v13 adds `templates` table and binds `template_id` / `template_version` to `exams`. Automatic `.v12.bak` SQLite backup runs prior to migration. Reference images for custom templates are stored content-addressed in `<app_data>/templates/references/<sha256>.png`. Built-in templates (`default-1`, `default-2`) are packaged in application resources.
- **Template Discovery Engine (`template_discovery.py`)**: Automatic paper quad boundary detection, perspective warping, connected component filtering, row/column line cluster analysis, and confidence scoring.
- **Settings & Calibration UI (`settings_ui.py`, `calibration_ui.py`, `ui.py`, `exam_ui.py`)**:
  - Manage templates, set default template, duplicate, inspect alignment overlay, customize annotation colors with live preview strip, and test OMR.
  - In-window header button `⚙️ ตั้งค่า` on `MainWindow` (popup menu for Templates, Colors, Output root, Archives) ensures settings are immediately accessible on macOS without relying on the system top menu bar.
  - Inline `⚙️ จัดการแม่แบบ…` on `NewExamDialog` enables teachers to calibrate or manage templates directly while creating exams, with automatic list reloading.
  - Direct `🎨 สีรอยตรวจ…` button on `ExamDialog` results tab allows custom color adjustments before exporting.

## Candidate stack / early validation

ใช้ทิศทางจาก handoff: Python, PySide6, OpenCV/NumPy, SQLite, Pillow, openpyxl; narrow local model/ONNX เป็น candidate ไม่ใช่ model ที่เลือกแล้ว Pin compatible versions หลัง smoke test; เก็บ model/license/hash แบบ offline ไม่ดาวน์โหลดตอนเปิดแอป

ทดสอบ packaging spike ตั้งแต่ foundation และทำ final installers ท้ายทาง เพื่อพบ native dependency failures เร็ว [Qt deployment](https://doc.qt.io/qtforpython-6.8/deployment/index.html) มีหลายทางเลือก; เปรียบเทียบ PyInstaller กับ pyside6-deploy/Nuitka ด้วย build evidence

[PyInstaller ไม่ใช่ cross-compiler](https://www.pyinstaller.org/en/stable/): Windows artifact ต้องมี Windows build/test evidence อย่าใช้ผล Mac แทน [ONNX Runtime threading](https://onnxruntime.ai/docs/performance/tune-performance/threading.html) มี native thread pools จึงต้องวัด oversubscription เมื่อทำ batch workers

Sources checked: 2026-09-08. เอกสารสนับสนุน direction เท่านั้น ไม่ใช่การรับรอง compatibility ของ dependency version ที่ยังไม่ได้เลือก

