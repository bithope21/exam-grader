# Decision log

## 2026-09-08 — Role contract (user-directed)

Decision: Codex รับผิดชอบ planning, architecture, test contract และ independent review; Antigravity implement; Product Owner กำหนด business rules และ teacher acceptance

Why: คำสั่งล่าสุดระบุบทบาทชัดเจน
Alternative: Codex เป็น initial implementer ตาม handoff เดิม
Consequence: รอบนี้สร้าง planning artifacts; งาน application ส่งเป็น bounded brief ให้ Antigravity
Revisit: ผู้ใช้เปลี่ยนการแบ่งบทบาท

## 2026-09-08 — Baseline constraints (inherited)

Offline, existing paper, CV answer detection, narrow handwritten-number recognition, teacher-approved key, human review, immutable originals และ installable Mac/Windows เป็น requirements เดิม ไม่เปิดโหวตใหม่

Consequence: technical candidates ต้องพิสูจน์ภายใต้ข้อจำกัดนี้
Revisit: มี blocker พร้อม evidence และ Product Owner เปลี่ยน requirement

## Open

## 2026-09-12 — Exam Grader Landing Page Architecture & Truthful Marketing Gate

Decision: Build the Exam Grader product landing page at route `/exam-grader` within `bithope-web` (`/Users/zubinpijit/bithope/apps/bithope-web`) strictly isolated from shared business logic. Enforce a Truthful Marketing Gate: claim only real, verified capabilities (Offline 100%, Human Review, Bulk Edit, Custom Template, and Excel .xlsx + Checked image export); keep unverified features (PDF, CSV, Windows installer) as Beta/Coming Soon or omitted. Centralize all download/external links in `constants.ts`. Use transparent 2D assets and real app Qt screenshots.

Why: User requested a dedicated landing page for Exam Grader in the bithope ecosystem with 2D assets, authentic app screenshots, and zero regression to existing routes. The user also required truthful marketing claims based on verified codebase inspection.

Consequence:
- Clean modular components in `src/app/exam-grader/components/`.
- Assets in `public/exam-grader/` (`screenshots/`, `illustrations/`, `icons/`).
- Central link wiring in `src/app/exam-grader/constants.ts`.
- Ready for redesign in a fresh session.

## 2026-09-11 — Review Multi-Select Checkbox Architecture and State Synchronization

Decision: Replace table `cellClicked` callback toggle with a dedicated `CheckBoxDelegate(QStyledItemDelegate)` for Column 0 of `issue_table`. Provide single-source-of-truth selection tracking via stable issue keys (`self.selected_issue_keys: set[tuple]`).

Why: The prior implementation suffered from a double-trigger race condition: clicking the checkbox indicator triggered Qt delegate toggle followed by `cellClicked` which inverted it back, making direct checkbox clicks fail or unchecking impossible. Moreover, selections were cleared unconditionally on table refresh.

Implementation & Constraints:
- `CheckBoxDelegate.editorEvent` captures Left-click release across the entire cell rectangle (52px wide) and Space keypress, updating `Qt.ItemDataRole.CheckStateRole` once and consuming the event (`return True`).
- Mouse press on LeftButton is consumed to prevent rubber-band drag glitches.
- Indicator is painted centered horizontally and vertically within the cell.
- `selected_issue_keys` uses stable issue tuples independent of row indexing or sorting.
- Preserves selection across `populate_issues()`, refreshes, and prunes keys upon bulk resolution.
- 100% backward compatible with existing single-row review and bulk edit services.

## 2026-09-09 — Bounded teacher-friction polish

Accepted key answers may be a single choice or a validated set such as `A,B`;
student answers remain single-choice for credit, while blank, multiple, and a
new connected mark that truly crosses two cells are zero-credit outcomes. The
boundary-cross state is versioned in new detections only; it supersedes the
prior student 17 Q25 adjudication only for newly processed/reviewed material;
stored reviews and exports are immutable. Ambiguous handwritten student numbers remain unfilled
until teacher confirmation, and only unique candidates are eligible for the
explicit bulk identity action.

Student sources use recoverable `archived_at` tombstones. Active queries and
snapshots exclude archived sheets, reimporting the same content hash restores
the source, and original blobs/reviews/exports remain recoverable. Checked
images are derived JPEGs (quality 88, long edge capped at 2400 px) with encoding
settings recorded in provenance; originals and prior output runs are untouched.

## 2026-09-08 — Task spec approved for bounded execution

PO approved `docs/TASK_SPEC.md` and authorized continuous execution across slices.
Historical key question 6 remains disputed for recognition truth: preserve the
historical scoring key/run and exclude that field until independent visual
adjudication. Runtime auto-accept still requires a separate evidence gate.

## 2026-09-08 — User-authorized foundation implementation

ผู้ใช้ขอให้ Codex implement โครงก่อน จึงอนุญาต Codex สร้าง generic foundation ขณะที่ WF-001 ยังเปิดอยู่ Scope: desktop shell, exam metadata persistence, migration, tests, dependency lockfile ไม่มี recognition/scoring/template decision เพิ่ม

เลือกใช้ modules ขนาดเล็กแทน empty package tree; แยก domain/storage/app/UI เพื่อ Antigravity ต่อเป็น package ได้เมื่อจำเป็น Packaging และ OS support matrix ยังต้องพิสูจน์ตาม G1/G7

WF-001 partial product input: ผู้ใช้เลือกแบบหลักหนึ่งแบบก่อน แล้วเพิ่มแบบอื่นภายหลัง (2026-09-08) ขอบเขตชัดแล้ว แต่รอ inventory/geometry evidence ก่อนปิด ticket

WF-001 ยังไม่ resolved. Preferred stack ใน ARCHITECTURE เป็น direction; ยังไม่มี benchmark, approved canonical template, scoring policy, model selection หรือ packaging verdict

## 2026-09-08 — Post-inspection task-spec approval and execution

PO indicates historical key question 6 was probably selected incorrectly and delegates technical defaults to best practice. This is not a definitive visual label or authorization to rewrite the live key/run. The scope and approval boundaries in [TASK_SPEC.md](TASK_SPEC.md) are approved for bounded implementation.

Defaults applied: retain external exports on exam deletion; recoverable managed exam state with shared originals preserved; optional expected range 1..N. No runtime auto-accept without a separate evidence gate. The workspace `.git` directory is read-only, so implementation checkpoints are documented rather than committed.

## 2026-09-08 — Checked renderer semantics

Use red check marks for answers matching the approved key, red X marks for incorrect
answers, a red outlined cell plus `!` for multiple, and an outlined cell for blank.
Render score `n/N` inside the template score ROI. Draw in canonical coordinates and
warp with the saved registration inverse so student ink remains visible. This is a
derived evidence copy; original source bytes are never modified. The renderer is
versioned `checked-overlay-canonical-v1` and remains review evidence, not a new
recognition decision.

## 2026-09-09 — Low light, explicit key approval and sparse rosters

Use a guarded feature-registration/green-print alignment fallback and relative local contrast when baseline registration fails or refinement reduces uncertain answers. Keep the original successful path for vol.1. A mark crossing a cell border is not automatically ambiguous: one connected mark with at least 60% ink ownership can resolve to that cell, while separate marks and near-even B/C ownership remain reviewable. These are engineering heuristics validated on the supplied corpus, not calibrated probabilities.

Expand the number crop upward only when a significant component touches its top. Preserve competing 10/40 candidates rather than inferring identity from missing roster numbers; gaps are legitimate and must not force a digit interpretation.

Require explicit teacher approval of the latest imported key before student work. Machine-origin keys cannot satisfy this gate. Do not infer a continuous roster from the highest uploaded number. An explicit expected range enables missing-number review with reversible skip actions, recorded separately from absence and excluded from scores.

Teacher adjudications are frozen test labels, never recognition inputs. Keep original images and existing exports immutable; run acceptance against disposable databases. See `evidence/vol2/validation.md` for completed verification.

## 2026-09-08 — Real-sheet polish geometry and export layout

Decision: promote the inspected real-sheet geometry to versioned draft template
`thai-main-draft-v2`, with student-number ROI `[590,73,692,107]` and score ROI
`[712,51,808,120]`; center score text responsively in that score box. Keep every
identity candidate review-required and preserve competing candidates/provenance.

Why: the original score ROI was visibly under the number line, while the real
printed score box is the green box at the upper right. The previous numeric crop
included the wrong printed boundaries and returned no useful candidate. Five real
registered crops now produce candidates matching the existing teacher-confirmed
numbers, but the corpus is too small for calibrated accuracy or auto-accept.

Decision: user-facing exports use a sanitized metadata folder, `ผลการตรวจ/<timestamp>/`,
`checked/เลขที่-NN.png`, `scores.xlsx`, and `_system/manifest.json` plus
`_system/results.json`; internal UUIDs remain in metadata and export registry.

Consequence: old exports are not renamed or migrated; new runs are human-readable,
collision-safe and revealable from the UI while immutable source/provenance records
remain intact. Native macOS visual evidence and fresh packaged checks are recorded
under `docs/evidence/polish/`.

## 2026-09-10 — Custom Answer-Sheet Template and Calibration System

Decision: Introduce a versioned, template-driven OMR architecture supporting multiple built-in layouts (Default #1: 60Q/5C/4×15, Default #2: 60Q/4C/3×20) and teacher-defined custom templates.

Key Architectural Decisions:
1. **Single Unified Pipeline**: Retain a single unified grading and OMR registration pipeline across all answer-sheet variants. Do not branch or fork grading logic per template.
2. **Template-Driven Choice Count & Geometry**: Choice count (2–5) is an explicit property of the template. For 4-choice sheets (Default #2), only choices A–D are analyzed; the non-existent 5th choice is never read or synthesized. Cell insets (e.g. 6px for Default #2) are explicitly configured per template to prevent thick-border bleeding.
3. **Canonical Internal Choices**: Paper-facing choice labels (e.g. ก, ข, ค, ง, จ or A, B, C, D, E) are strictly mapped to internal canonical choices `(A, B, C, D, E)`. Grading, scoring, and key logic only ever operate on canonical choices, keeping scoring logic independent of paper headers.
4. **Schema Migration v12 → v13**: SQLite schema upgraded to v13 with automatic `.v12.bak` pre-migration backup. Adds `templates` table and binds `template_id` / `template_version` to `exams`. Existing exams are backfilled safely to `default-1` v1. Deletion of templates referenced by existing exams is blocked.
5. **Content-Addressed Reference Storage**: Custom reference images are stored in app-data content-addressed file storage (`<app_data>/templates/references/<sha256>.png`) rather than SQLite BLOBs, preventing database bloat and simplifying migrations. Built-in templates are bundled within package resources.
6. **Built-in Default #2 Calibration**: Calibrated using real fixtures (`default#2.JPG`), verified via visual inspection overlays (`docs/evidence/default2_full_overlay.png` and `docs/evidence/default2_checked_example.jpg`), and frozen into built-in assets (`template_default2.json`, `reference_default2.png`).
7. **Customizable Annotation Colors**: Teacher preferences for checked export marks (correct, incorrect, uncertain, score) are persisted via `preferences.py` (QSettings) with instant live preview and reset-to-defaults capabilities.
8. **Visible In-Window Settings & Calibration Entry Points**: On macOS, `QMenuBar` defaults to the screen-top system menu bar, making settings invisible to teachers looking at the app window. To eliminate friction, explicit in-window controls are provided:
   - Header `⚙️ ตั้งค่า` button with dropdown popup in `MainWindow` (access to Template Manager, Annotation Colors, Output Directory, and Archives).
   - Inline `⚙️ จัดการแม่แบบ…` button beside the template selector in `NewExamDialog` with automatic template reload upon dialog close.
   - Cross-dialog navigation in `TemplateSettingsDialog` to open `AnnotationColorSettingsDialog`.
   - Dedicated `🎨 สีรอยตรวจ…` action in `ExamDialog` results tab before exporting.

## 2026-09-10 — Polish UI/UX, vol.5 Default #2 Registration Robustness & Fail-Closed Purge Safety

Decision: Enhance registration robustness for dense-keypoint answer sheets (e.g. Default #2 pink paper vol.5), ensure fail-closed safety, make deletion semantics clear and complete, and eliminate UI friction across calibration, review, and export.

Key Architectural Decisions:
1. **Dense Inlier Registration & Fail-Closed Safety**:
   - SIFT registration accepts dense inlier sets (`inliers >= 80 and ratio >= 0.35`, `inliers >= 150 and ratio >= 0.30`) with standard RANSAC 2.5 and fallback 3.5.
   - Preserves 100% fail-closed safety: Cross-template attempts (Default #2 on Default #1, Default #1 on Default #2), truncated images, and random noise fail registration completely.
2. **True Disk-Level Purge with Accurate UI Claims**:
   - `ExamStorage.purge(exam_id)` transactionally purges all database entities and unlinks unshared source images from `<app_data>/input/originals/`.
   - UI confirmation dialog avoids overclaiming: explicitly informs teachers that system records and internal images are permanently removed, while previously exported Excel directories remain untouched.
3. **Dynamic Template Geometry in UI Previews**:
   - Both `ReviewDialog` and `ExamDialog.populate_issues()` dynamically warp using `template_def.canonical_width` and `template_def.canonical_height`, correctly slicing thumbnails for all templates without clipping or empty artifacts.
4. **Failed Sheet Friction Elimination**:
   - Added direct dismiss/delete actions in the Student failure table, Issue table, and Review dialog, preventing teachers from getting trapped on corrupt/unreadable uploads.
5. **Interactive Calibration Nudge Controls**:
   - Added directional nudge controls (1px, 5px, 10px) to `CalibrationCanvas` and `CalibrationDialog` for fast manual adjustments, paired with actionable photography guidance.
6. **Export Metadata Tracking**:
   - Added dedicated `Info` sheet in `scores.xlsx` documenting exam metadata and active template name without altering the `Scores` tabular format.

## 2026-09-11 — Built-in Default #3 Integration, Theme Design System & Iterative Visual QA

Decision: Integrate Default #3 (สุทธิอนุสรณ์ 30 ข้อ 4 ตัวเลือก 3 ชุด) as an immutable built-in template, centralize appearance themes (Light/Dark/System), resolve Thai typography clipping, ensure honest fixture evaluation, and enforce an iterative generate-inspect-fix Visual QA loop.

Key Architectural Decisions:
1. **Immutable Built-in Default #3 (`default-3`)**:
   - Packaged canonical warped reference image `resources/reference_default3.png` (1200 × 1720 px, SHA256: `3e60d1a3d85b5bd106bc305298253088234634ac1ff867be985f736d25a4ea6e`).
   - Packaged `resources/template_default3.json` with kind `builtin`, 30 questions, 4 choices (`A`–`D` / `ก`–`ง`), 3 blocks × 10 rows.
   - Built-in geometry frozen and verified against real fixture `tests/fixtures/default3/default#3.PNG` (`docs/evidence/default3_full_overlay.png`):
     - Student Number ROI `(468, 440, 776, 515)` cleanly captures "เลขที่ ............." without text interference.
     - Score ROI `(813, 224, 1076, 527)` snugly frames the "คะแนนรวม" score box.
     - Cell grids across all 3 blocks align centered within printed cell boundaries.
2. **Fixture Honesty (Zero Synthetic Claims)**:
   - For Default #3, only the real reference sheet `tests/fixtures/default3/default#3.PNG` exists.
   - Strictly deleted simulated photo fixtures (`photo.jpg`) and removed hypothetical `table_coverage >= 0.85` claims. Unit and UAT tests only claim what is backed by real physical fixtures.
3. **Centralized Semantic Theme System (`preferences.py`)**:
   - Unified `create_theme_palette` with full semantic `QPalette` color roles and comprehensive QSS design tokens for Light and Dark modes.
   - Eliminated dark mode white rectangular view flashes, popup white-on-white text, and unstyled list widgets.
4. **Thai Typography & Adaptive Layout Containment**:
   - Enforced minimum item heights (58px on home list, 52px on student rows) preventing upper/lower Thai vowel and tone mark clipping.
   - Simplified Template Manager table to 2 columns (`ชื่อแม่แบบ`, `ชนิด`) without horizontal scrollbars.
   - Bounded Calibration Dialog within `screen.availableGeometry()`, placed parameter controls in vertical `QScrollArea`, and pinned the action bar permanently at the bottom.
5. **Iterative Visual QA Loop**:
   - Automated generation of 10 screenshots across all 5 core UI flows in Light and Dark modes (`docs/evidence/visual_qa/`).
   - Inspected each screenshot visually using `view_file`. Diagnosed and fixed horizontal squeezing of toolbar buttons and parameter cards, re-captured, and verified zero visual clipping or contrast defects.

## 2026-09-11 — Review Bulk Edit, Student Number Recognition & Custom Template Overlay

1. **Transaction-Safe Review Bulk Edit (`review_service.py`, `exam_ui.py`)**:
   - Added `bulk_resolve(exam_id, operations)` executing in an explicit single SQLite transaction with rollbacks on failure.
   - Preserves unselected rows untouched, allowing teachers to quickly resolve repeated blank or common answers without tedious one-by-one row edits.
   - Automatically re-evaluates student completeness and finalizes ready sheets upon bulk apply.
2. **Evidence-First Student Number Identification & Fail-Closed Boundaries (`identity.py`, `review_service.py`)**:
   - Recognizer confidence and score margins are the primary basis for student number adoption.
   - Missing numbers in a roster/range serve strictly as tie-breakers for ambiguous multi-candidate sheets, never as an inference generator for unrecognized sheets.
   - Ambiguous sheets or collisions fail closed into Review with distinct status classifications (`duplicate`, `missing`, `uncertain`, `out_of_range`).
3. **Strict Template Geometry Invariant in Export Overlays (`exporting.py`)**:
   - Fixed custom template resolution in `export_results` by resolving the actual exam template via `load_exam_template_def(database, exam_id)`.
   - Maintained invariant: `detected cell == rendered overlay cell`. Exported checked images strictly match the template canonical dimensions and cell coordinates without falling back to default forms.

## 2026-09-12 — Landing Page Redesign & Editorial Art Direction (bithope-web)

1. **Minimal Editorial Illustration ("วาดน้อย แต่จำได้")**:
   - Converted all illustration assets in `public/exam-grader/illustrations/` to minimal colored-pencil / crayon editorial style (naive proportions, loose pencil outlines, visible grain, 3–5 colors: forest green, orange, cream, charcoal, muted blue).
   - Hero: Single friendly teacher grading answer sheet with orange pencil (removed all floating props, clutter, and classroom scenery).
   - Workflow: Exactly one visual metaphor per step (Blank paper + pencil, Answer sheet + checkmark, 3 Papers, Offline laptop + cloud-cross, Review magnifier, Spreadsheet + score sheet).
2. **Truthful Marketing & Zero-Noise Simplification**:
   - Removed all references to "Beta", "Trial", and pricing across `/exam-grader`. Standardized on "ฟรี 100%" and "ดาวน์โหลดฟรี".
   - macOS download truthfully wired to `v1.0.0 (Apple Silicon)` with clear "Open Anyway" Gatekeeper instructions. Windows labeled "เร็ว ๆ นี้ (Coming Soon)".
   - Eliminated green header pill tags across all sections and stripped `กระบวนการมาตรฐาน` tags and category chips from workflow cards.
3. **Interactive PySide6 App Evidence & Responsive Containment**:
   - Interactive modal on all 6 workflow cards showing authentic native desktop PySide6 app screenshots.
   - Added `export const viewport: Viewport` in Next.js page and responsive Thai typography wrapping (`[word-break:break-word]`), ensuring 100% clean rendering on 320px, 375px, 768px, and 1280px viewports.
