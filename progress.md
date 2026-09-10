# Exam Grader progress

## Git checkpoint — 2026-09-10

Local Git is initialized on `main`; no remote is configured and nothing has
been pushed. Clean baseline commit: `2f1479e` (`chore: establish stable
exam-grader baseline`). The baseline tracks source, tests, specs, progress,
tools, templates, models, answer-sheet references, and vol.1/vol.2/vol.3
regression fixtures. Generated/manual `docs/evidence`, build artifacts,
caches, virtualenv, `vol.4`, and `.DS_Store` files are intentionally outside
the baseline. An existing Codex snapshot ref keeps approximately 402 MiB in
`.git`; it predates this baseline and was left untouched to avoid deleting
system-managed history.

Next work is a separate feature task: `Custom Answer-Sheet Template /
Calibration System`. It must start from the baseline above and preserve all
current safety and scoring contracts. Do not treat this checkpoint as general
accuracy evidence.

## Current status — 2026-09-09 UI friction extension

The bounded UI follow-up is implemented and visually checked. Home now keeps
only one recoverable delete action per exam row (the bottom selected-delete and
duplicate context-menu actions are removed), and its warning clearly says the
selected set leaves the active list immediately while managed data remains
recoverable from archived exams. Home and student custom rows now render their
metadata once, removing the overlap shown in the supplied screenshots.

Key review pre-fills a clear multi-mark observation such as `B,C`, while the
teacher confirmation checkbox and explicit key approval gate remain required.
Results now visibly expose `บันทึกผลตรวจ + Excel` and show whether outstanding
review work must be completed first. A short detection payload is also handled
without indexing past its available rows, and integer registration matrices are
accepted by the review viewer.

Fresh evidence is in `docs/evidence/polish-ui-20260909/README.md`:
pytest `76 passed`, Ruff/Mypy pass, macOS arm64 build pass, strict codesign,
packaged self-check and smoke-ui pass, vol.1/vol.2 UAT pass, and vol.3 UAT pass
with scores `10,8,5,8,8,12,14,16`, 8 teacher actions, 32 explicit missing
numbers and unchanged fixture source hashes. Visual captures cover home,
student, multi-answer key, review and results.

This remains engineering/UAT evidence for the supplied corpus. It does not
claim general handwriting/OMR accuracy, calibrated digit accuracy, Windows
readiness or interactive teacher UAT.

## Current status — 2026-09-09

This section supersedes the historical status below. The vol.2 low-light and sparse-roster repair is implemented and verified by Luna Max: 67 tests, Ruff, Mypy, native Cocoa UAT, arm64 rebuild, strict codesign, packaged self-check and UI smoke all passed. Evidence: `docs/evidence/vol2/validation.md`.

Vol.1 remains 180/180 automatic. Vol.2 resolves key 39/40 and student answers 199/200 automatically without a wrong resolved answer; three explicit adjudications (key Q28, student 17 Q25, student 10 identity) produce the teacher's scores 10/8/12/14/16. Native UAT also verifies 19 reversible skips for an explicit range 1–24 and unchanged original hashes.

- Explicit teacher confirmation of the latest key is required before student import, review, or export. Replacing the key restores this gate.
- Low-light registration uses guarded SIFT/green-print refinement and a relative contrast fallback. The original successful detector remains preferred unless refinement reduces uncertainty.
- Student-number crops expand when handwriting touches the top. Ambiguous `10/40` stays visible for correction instead of assigning a wrong number.
- Uploads with gaps do not invent missing students. An explicitly configured roster supports individual/bulk skipping and restoration; skipped numbers do not become zero scores or fabricated absences.
- Review rows clear stale widgets and retain inline corrections when opening a sheet dialog. Unresolved key answers are highlighted and scrolled into view.
- Frozen teacher labels and disposable end-to-end evidence: `docs/evidence/vol2/`. No live exam database or historical export was rewritten.
- Correct vol.1 count: key 30 + five students 150 = 180 answers. General handwriting accuracy and Windows readiness remain unverified.

## Next polish scope

Continue from the verified implementation; do not restart the vol.1/vol.2 repair. The next chat should inspect the current UI and source first, then make only bounded polish changes that reduce teacher friction. Preserve the explicit key-confirmation gate, sparse-roster skip/restore behavior, immutable originals, provenance, stale-key protection, and fail-closed review of uncertain answers.

Useful evidence: `docs/evidence/vol2/validation.md`, `docs/evidence/vol2/native-final/report.json`, and `docs/evidence/vol2/README.md`. The supplied real fixtures remain the regression baseline; do not use frozen teacher labels as recognition inputs or claim general handwriting accuracy from this corpus.

## Bounded polish completed — 2026-09-09

The requested student/review/export friction pass is implemented on top of the
verified baseline. Student review prefills only a unique assistant candidate;
ambiguous `10/40` remains a review issue. Keys accept one or more A–E options per
question, while a student multiple mark or `boundary_cross` remains zero credit.
The PO-confirmed two-cell boundary mark is explicit and fail-closed for other
uncertain marks. Individual and bulk review saves retain unsaved row drafts and
stale detection/key guards.

Student rows now have recoverable delete actions plus delete-all confirmation;
the home exam list has a recoverable delete action on each row. Originals and
provenance remain immutable. The broad latest-model reprocess control is gone;
targeted retry remains available for a failed row. Checked exports are compact
JPEG derivatives with color-coded annotations and a recorded legend.

Fresh evidence: `docs/evidence/vol2/polish-offscreen-final/report.json` and
`docs/evidence/vol2/validation.md`. Source checks: pytest `73 passed`, Ruff pass,
Mypy pass. This remains engineering evidence for the supplied corpus, not a
general accuracy or Windows-readiness claim.

Historical notes follow; earlier test counts, schema versions and next-step lists are not the current handoff.

Historical record: 2026-09-08

สถานะปัจจุบัน: bounded polish pass ตาม `docs/TASK_SPEC.md` เสร็จแล้ว

- Source checks: pytest `45 passed`, Ruff ผ่าน, Mypy ผ่าน
- Real fixtures: registration `6/6`, all-choice false positives `0`, auto-accept `0`
- Student-number baseline: review-required; ยังไม่มี independent handwriting ground truth
- Disposable real E2E: นักเรียน 5 คน, คะแนน `10/6/12/26/8`, checked images 5 ใบ, export registry/index ผ่าน
- Checked renderer: วาง annotation สีแดงและคะแนนใน score ROI จาก canonical geometry โดยไม่แก้ originals
- UI: aligned image primary, original secondary, splitter/table ไม่มี horizontal scroll ในขนาดตรวจสอบ
- Exam lifecycle: archive/restore แบบกู้คืนได้, shared originals และ external exports คงอยู่
- macOS arm64 build, strict codesign, packaged self-check และ offscreen smoke ผ่าน
- ยังไม่ claim production accuracy, calibrated digit accuracy, Windows readiness หรือ interactive teacher UAT
- Git checkpoint ทำไม่ได้ใน environment นี้ เพราะ workspace ไม่มี `.git` ที่เขียนได้

หลักฐานหลัก:

- `docs/TASK_SPEC.md`
- `docs/AGENT_HANDOFF.md`
- `docs/DECISIONS.md`
- `docs/evidence/REAL_UAT.md`
- `docs/evidence/real-golden-labels.json`
- `docs/evidence/identity-regression.json`
- `docs/evidence/real-e2e-final.json`

## Handoff สำหรับแชทใหม่ — อัปเดต 2026-09-09

รับช่วงจาก `/Users/zubinpijit/private/exam-grader` โดยอ่าน `progress.md`,
`docs/TASK_SPEC.md`, `docs/AGENT_HANDOFF.md`, `docs/DECISIONS.md` และ
`docs/evidence/vol2/validation.md` ก่อนแก้ไข

Baseline ล่าสุด: vol.1/vol.2 regression ยังผ่าน; vol.3 real-fixture UAT ผ่าน 9/9
ภาพ, key-first gate ผ่าน, ข้ามเลขที่ขาด 32 รายการ, source hashes ไม่เปลี่ยน,
คะแนน `10,8,5,8,8,12,14,16`, teacher actions เหลือ 8 (เติมเลขที่ 3/14/24
อัตโนมัติ; 40/10 ยังต้องยืนยัน), และ Q25 คาบเส้นเป็น `boundary_cross` ได้ 0
คะแนน. Quality gates: pytest `75 passed`, Ruff, Mypy, build, strict codesign,
packaged self-check และ smoke-ui ผ่าน

หลักฐานล่าสุด: `docs/evidence/vol3-real-uat-20260909/report.json`,
`docs/evidence/vol3-benchmark-20260909.json`,
`docs/evidence/vol3-package-check-20260909.json` และ
`docs/evidence/vol2/validation.md`. เหลือให้ตรวจต่อเฉพาะ friction/visual ที่พบจริง;
ความไม่แน่ใจ 7 ช่องยัง fail-closed ตาม policy และไม่ควร auto-accept จาก frozen labels
หรือสร้าง roster จากเลขที่สูงสุดเอง. Fresh Cocoa UAT รอบนี้เปิดหน้าต่างไม่ได้ใน
headless session; ใช้ offscreen UAT และภาพผลลัพธ์ที่ตรวจแล้วเป็นหลักฐานปัจจุบัน

### Prompt สำหรับแชทใหม่ — TASK: Custom Answer-Sheet Template / Calibration System

ทำงานต่อใน `/Users/zubinpijit/private/exam-grader` โดยอ่าน `progress.md`,
`docs/TASK_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` และหลักฐานล่าสุด
ก่อนลงมือ. ให้ agy จัดการ feature ใหญ่เรื่อง Custom Answer-Sheet Template /
Calibration System แบบ production-minded แต่เปลี่ยนเฉพาะ scope ที่จำเป็น.

ต้องรักษา business logic เดิมที่ผ่าน regression แล้ว: key confirmation,
sparse-roster skip/restore, immutable originals, provenance, stale-key
protection, multi-answer scoring และ fail-closed uncertainty. ห้ามอ่าน frozen
teacher labels เข้า algorithm, ห้ามเดาเงียบ, ห้ามทำลายข้อมูลเดิม และห้าม claim
accuracy ทั่วไปจาก vol.1/vol.2/vol.3. ใช้ vol.1/vol.2/vol.3 เป็น regression
baseline และเพิ่มหลักฐานเฉพาะ calibration/template แยกจากผลเดิม.

ก่อนแก้ให้ตรวจ source/data contract จริงและทำ checkpoint เล็ก ๆ ตาม Git history.
ออกแบบให้ครูส่ง template/เฉลย/answer sheets แล้วทำงานอัตโนมัติที่สุด แต่ทุก
calibration ที่ไม่แน่ใจต้องมี provenance, diagnostics, preview และ human
confirmation ที่ fail-closed. ห้ามเริ่มจากการปรับ threshold เพื่อให้ตัวเลขดูดี.
ตรวจ visual output ทุกครั้ง และรัน pytest, Ruff, Mypy, build, codesign,
self-check, smoke-ui และ real-fixture UAT ก่อนรายงานผล. แยก engineering/UAT
evidence ออกจาก accuracy claim และอย่ารายงาน completion จนกว่าผลลัพธ์ภาพและ
quality gates จะผ่านจริง.

`DETAIL: [รอ Product Owner บอกใน chat ใหม่]`

## Vol.3 real-fixture UAT — 2026-09-09

The supplied 40-question vol.3 photographs were replayed from fresh recognition
using `tools/uat/vol3_uat.py`. The historical export at the Product Owner's
path was read only after recognition, for explicit teacher actions and comparison
evidence; it was never an input to the algorithm. All 9 fixture images registered,
the pre-key student-import gate blocked correctly, 32 missing roster numbers were
skipped explicitly, checked JPEG exports and manifest hashes verified, and all
fixture source hashes remained unchanged.

The current pipeline matched the prior run for every active detection except the
known PO change: student 17 question 25 is now `boundary_cross` with explicit
zero credit. The safe identity-domain bulk adoption now resolves numbers 3, 14,
and 24 from already anchored unique numbers; only the 40/10 ambiguity remains a
teacher action. Teacher actions fell from 11 to 8 in this replay, while seven
faint blank-like rows remain fail-closed uncertainty and are resolved explicitly
as blank using the historical review action. Scores remain `10, 8, 5, 8, 8, 12,
14, 16`, matching the existing result export.

Evidence: `docs/evidence/vol3-real-uat-20260909/report.json`,
`docs/evidence/vol3-benchmark-20260909.json`, and
`docs/evidence/vol3-package-check-20260909.json`. The benchmark now accepts a
declared active question count, so vol.3 reports its 40-question uncertainty
surface rather than truncating at 30. This remains engineering/UAT evidence only;
it does not establish general handwriting accuracy or auto-accept accuracy.

## Automation/review UX verification — 2026-09-08

- Updated teacher-corrected run: key 30 answers + 5 student sheets × 30 answers matched `180/180`; scores `10/6/12/27/8`. Q6 and Q15 no longer become uncertain because weak adjacent ink is ignored only when the selected cell has dominant core ink.
- One bulk action applies usable student-number candidates; duplicate, missing, out-of-range, stale-key and attendance conflicts remain in the review queue. Review rows are sorted by number and support inline number, answer, attendance and image retry controls with an image crop.
- New exam form has Buddhist-year selection, editable ป.1–ม.6 grade selection and editable room 1–12 selection.
- Generated number benchmark is `52/52` for 1–50 plus composed 14/41; this is developer-generated evidence, not unseen-handwriting ground truth.
- Final evidence: `docs/evidence/automation/final-native/report.json`, `docs/evidence/automation/final-offscreen/report.json`, `docs/evidence/automation/number-range/report.json`.
- Fresh checks: pytest `62 passed`, Ruff pass, Mypy pass, macOS arm64 build pass, strict deep codesign pass, packaged self-check and offscreen smoke pass. No Git checkpoint exists because this workspace has no writable `.git` repository.

## Final polish verification — 2026-09-08

The requested visual polish is now implemented and verified against the same five
real student sheets. The registered student-number ROI is `[590,73,692,107]` in
the versioned template (`thai-main-draft-v2`); it is cropped at source resolution,
locally normalized, segmented with diagnostics, and passed through a numeric-only
Tesseract backend. The result is always a review candidate with provenance and
never auto-accepted. Candidates/truth are `1/1`, `2/2`, `3/3`, `4/4`, `5/5`; the
first and third retain competing candidates (`1,4` and `3,4`) so the UI still
requires teacher confirmation. The key sheet is excluded from identity scoring.
Evidence: `docs/evidence/polish/identity-benchmark-final.json` and per-sheet
diagnostics under `docs/evidence/polish/final-offscreen-final/numbers/`.

The score ROI is now the actual upper-right green “คะแนนรวม” box `[712,51,808,120]`;
the renderer centers a responsive `n / N` label there using the saved registration
transform. Real header crops for all five sheets and answer-grid crops were visually
inspected. Checked output uses `เลขที่-01.png` style names, puts `manifest.json` and
`results.json` under `_system`, and publishes under a Thai/Unicode-safe human-facing
folder with timestamped runs. Prior runs remain immutable. The latest output tree and
hash checks are recorded in `docs/evidence/polish/final-offscreen-final/report.json`.

Native macOS UI evidence covers 1024×768, 1440×900, and maximized windows at DPR 2;
the review table has no horizontal scroll and the aligned image expands with the
window. Evidence is under `docs/evidence/polish/final-native/`. Fresh final checks:
pytest `52 passed`, Ruff pass, Mypy pass, macOS arm64 build pass, strict deep
codesign pass, packaged self-check pass, packaged offscreen smoke pass. Windows,
production-calibrated digit accuracy, and auto-accept remain intentionally deferred.
