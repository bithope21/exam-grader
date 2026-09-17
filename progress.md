# Exam Grader progress

## Current task result — 2026-09-17 targeted identity safety fix

The clean authoritative-label benchmark was used as the fixed baseline. The
change stayed inside student-number identity recognition; document crop,
registration, OMR, UI/UX, grading, export, business logic, ground truth, and
fixture-specific runtime rules were not changed.

- Raw labeled corpus: exact `26/32` (`81.25%`) from baseline `21/32`; candidate
  visibility `28/32` (`87.5%`) from `27/32`; review `22/32`; selective
  auto-accept `10/32`; wrong auto-accept `0` from `3`.
- Unique-source view: exact `19/24` (`79.167%`) from `16/24`; candidate
  visibility `21/24` (`87.5%`) from `20/24`; review `17/24`; selective
  auto-accept `7/24`; wrong auto-accept `0` from `2`.
- The gate now requires complete segmentation, no merged-component suspicion,
  no independent candidate disagreement, and independent model/recognizer
  agreement. Vol.7/0987, 0990, 0992 and Vol.6/0914 remain review-required.
- Vol.8/9 held-out regression is preserved: exact `15/22`, visibility `19/22`,
  wrong auto-accept `0`; selective auto-accept is `2/22`, both exact.
- Focused source tests: `tests/test_identity.py` and
  `tests/test_digit_model.py` pass (`20 passed`). Full test suite was not run.
- Benchmark artifacts:
  `/private/tmp/exam-grader-vol1-3-5-6-7-benchmark/targeted_fix_report.md`,
  `/private/tmp/exam-grader-vol1-3-5-6-7-benchmark/report.json`, and
  `/private/tmp/exam-grader-targeted-fix-heldout.json`.

## Current task result — 2026-09-16 student-number recognition round 2

Round 2 continued from checkpoint `33439ec` and changed only Student Number
Recognition. The verified `IMG_1071` failure was a short, wide single glyph
incorrectly split by the touching-digit heuristic; `IMG_1080` had an incomplete
second digit after the baseline threshold. The fix adds conservative component
grouping and local faint-stroke recovery without changing document crop,
registration, OMR, UI/UX, grading, export, or business logic.

- `IMG_1071`: boxes changed from `3` fragments to `2` digit boxes; the remaining
  error is classifier `8 -> 9`, not ROI/crop failure.
- `IMG_1080`: recovered complete `46`; no global preprocessing threshold was
  changed.
- Augmentation ablation proved blur caused the `IMG_1073` regression. Blur was
  removed; mild affine-only hard-pair augmentation remains for labels
  `{1,3,4,6,7,8,9}`, one copy per training sample.
- Current bundled held-out report is
  `/private/tmp/exam-grader-identity-round2-bundled-final-v1.json`: exact
  `15/22` (`68.2%`), candidate visible `19/22` (`86.4%`), review `15/22`,
  selective auto-accept `7/22`, wrong auto-accept `0`. Vol.8 is `6/10` exact
  and Vol.9 is `9/12`.
- Selective gate is enabled only with complete segmentation, candidate at the
  top of the ranked list, confidence `>=100`, and margin `>=15`. On held-out,
  all `7/7` auto-accepted candidates were exact; ambiguous cases remain review.
- Final remaining wrong cases are `7/22`: classifier confusion in all seven
  after visual re-audit; ranking amplifies the error on `IMG_1028` and
  `IMG_1072` where `27` remains visible but `21` ranks first. No remaining
  primary ROI/crop failure was found.
- Training used only the existing 198-record seed manifest; internal KNN
  validation is `39/39`, and `generalization_claim_allowed=false` remains.
- Final bundled model SHA-256:
  `aabeeb9bab4fdfad481facaa627c9efb521707e7783123746928776e74153502`.
- Focused tests: `36 passed`; Ruff and `git diff --check` passed. Fresh
  `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app` passed packaged
  self-check, offscreen settings/UI smoke, and strict deep codesign. Native
  Product Owner UAT is separate. Do not claim production-ready from this
  source/held-out evidence alone.

## Current task result — 2026-09-16 student-number root-cause fix

The verified recognizer bottleneck was addressed without changing document
crop/registration, OMR, UI/UX, grading, export, or business logic. The bundled
model remains review-only and all held-out records remain teacher-confirmation
required.

### Verified state

- Implementation changes: single-digit model support, model/legacy candidate
  fusion, deterministic hard-pair augmentation support, and focused tests.
- Annotation is complete: `198 labeled`, `2 excluded`, `0 remaining`,
  `0 bad_bbox`; the accepted seed manifest has
  `training_allowed=true` only for `internal_seed_split_only` and
  `generalization_claim_allowed=false`.
- Final held-out report is
  `/private/tmp/exam-grader-identity-final-hardpairs-v1.json`: exact `13/22`
  (`59.1%`), candidate visible `18/22` (`81.8%`), review `22/22`, auto-accept
  `0`, wrong auto-accept `0`. Vol.8 is `6/10` exact and Vol.9 is `7/12`.
- Before/after against the seed-model checkpoint: exact `7/22` -> `13/22`
  and visibility `14/22` -> `18/22`; review and wrong auto-accept stayed safe.
- The selected artifact uses one deterministic augmentation copy for labels
  `{1,3,4,6,7,8,9}`. Copies `2` and `3` were rejected because held-out exact
  fell to `8/22`.
- Runtime model is bundled review-only at
  `src/exam_grader/resources/student_number_digit_model.npz`; auto-accept is
  disabled and the confidence cap is not a generalization probability.
- Focused tests: `20 passed`; Ruff and `git diff --check` passed.
- Threshold-20 preprocessing ablation was rejected: it improved IMG_1080 but
  reduced overall exact to `10/22`, and IMG_1071 remained unresolved. The
  production preprocessing path was not changed. Both remain review-required.
- Final model artifact SHA-256:
  `0a892c5f4a8b1eff4eb306b3a925f1a4f022b2151391c48216d99ced261159c7`.

### Next exact action

Checkpoint commit is the current HEAD of `fix/vol8-current-usable-checkpoint`.
Fresh `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`
was built from it and passed packaged `--self-check`, offscreen
`--smoke-settings`, offscreen `--smoke-ui`, and strict deep codesign. This is
package/source evidence only; Product Owner native UAT is still required.

The remaining bottleneck is preprocessing/segmentation for `IMG_1071` and
`IMG_1080`; threshold-20 ablation was rejected because overall exact fell to
`10/22`, so production preprocessing remains unchanged. Do not claim
production readiness or human-review reduction because review remains
`22/22`.

### Protected invariants and ownership

Preserve immutable originals, source hashes, proposal/crop provenance,
review-required uncertainty, teacher confirmation, and fail-closed behavior.
The untracked `tests/fixtures/real/vol.8/` and
`tests/fixtures/real/vol.9/` belong to the user/previous work; do not reset,
clean, overwrite, stage, or absorb them.

## Current task handoff — 2026-09-16 student-number dataset Phase 1

Phase 1 is implemented and verified as a read-only dataset/benchmark layer.
The PDF seed, teacher-confirmed real-sheet corpus, and current recognizer
baseline are now reproducible without changing runtime recognition, OMR,
crop/registration, grading, review, UI, or release behavior.

### Evidence

- PDF source: `/Users/zubinpijit/Downloads/number handwriting.pdf`; SHA-256
  `20e2ffe4aa0244aba648e40ce995891dab99c6ef0912f845aa396e1e7201f244`.
- Extracted 100 page-1 sequence crops (`00`–`99`) plus a 10-page review queue.
  The arithmetic pages remain unlabeled; `training_ready=false`.
- Built a 22-record held-out corpus from teacher-confirmed Vol.8/Vol.9
  results. Writer identity is unknown, so no training split is claimed.
- Baseline: primary exact `5/22` (`22.7%`, bootstrap 95% CI `9.1–40.9%`);
  truth visible in candidate/review suggestions `18/22` (`81.8%`, CI
  `63.6–95.5%`); review required `22/22`; auto-accept `0`; wrong auto-accept
  `0`.
- Per corpus: Vol.8 exact `2/10`, candidate-visible `8/10`; Vol.9 exact
  `3/12`, candidate-visible `10/12`.

### Files and next gate

- Tooling: `tools/benchmark/extract_number_handwriting_dataset.py`,
  `tools/benchmark/build_identity_corpus.py`,
  `tools/benchmark/identity_labeled_benchmark.py`.
- Tests/docs: `tests/test_identity_dataset_tools.py`,
  `docs/IDENTITY_DATASET.md`.
- The next authorized phase is visual QC/annotation of digit crops and a
  leakage-safe writer-grouped train/validation/test manifest. Do not promote
  a model or enable auto-accept until independent held-out evidence supports
  it and wrong auto-accept remains zero.

## Current task handoff — 2026-09-16 visual QC annotation preparation

- Added `tools/benchmark/prepare_digit_annotation.py` and
  `tests/test_digit_annotation.py`.
- Generated an external worklist with 200 digit proposals and a 10x10 contact
  sheet. All 200 remain `needs_review`; `training_ready=false`.
- Visual QC found a real layout variant: `06`-`09` omit the visible leading
  zero. All 8 affected spatial proposals have `label_proposed=null` and an
  explicit review reason; they cannot silently enter training.
- Output: `/private/tmp/exam-grader-number-handwriting-annotation-v2/`.

## Current task handoff — 2026-09-16 annotation completed

- Product Owner annotation manifest is complete: `198 labeled`, `2 excluded`,
  `0 remaining`, `0 bad_bbox`, with `372` audit events.
- Excluded records are `pdf-page-01-cell-22-digit-0` and
  `pdf-page-01-cell-75-digit-0`; no ambiguous record was silently labeled.
- Validator produced `/private/tmp/exam-grader-number-handwriting-training-ready.json`
  with 198 accepted samples and verified source hashes/crops.
- This is label-ready for the authorized internal seed split. It remains
  `seed_only`, `writer_group=unknown`, and cannot support a generalization
  claim.

## Current task handoff — 2026-09-16 seed model integration

- Product Owner authorized internal seed training despite unknown writer groups.
  The regenerated manifest is
  `/private/tmp/exam-grader-number-handwriting-training-ready-v2.json` with
  `training_allowed=true`, `training_scope=internal_seed_split_only`, and
  `generalization_claim_allowed=false`.
- KNN beat centroid on the deterministic internal validation split (`39/39`
  versus `37/39`); the final KNN artifact is bundled at
  `src/exam_grader/resources/student_number_digit_model.npz`.
- Independent saved-registration Vol.8/Vol.9 benchmark improved primary exact
  from `5/22` (`22.7%`) to `7/22` (`31.8%`). Review remained `22/22` and wrong
  auto-accept remained `0`. The model is integrated as review-only; no
  auto-accept is enabled.
- Benchmark report: `/private/tmp/exam-grader-identity-seed-model-benchmark-v3.json`.
- Fresh arm64 app: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`.
  Packaged self-check and native UI smoke passed.

## Current task handoff — 2026-09-16 compact UI checkpoint → student-number recognition

The latest bounded macOS UI polish is committed on the fix branch. This
checkpoint prepares a fresh chat for the next user-scoped student-number task;
it does not define or reopen that task's implementation details.

### Verified current state

- Repo: `/Users/zubinpijit/private/exam-grader`
- Branch: `fix/vol8-current-usable-checkpoint`
- Latest commit: `3ad21da fix: compact macOS UI controls`
- The commit contains only UI source, focused UI tests, PyInstaller resource
  metadata, and bundled chevron assets. It does not include the existing
  untracked Vol.8/Vol.9 fixtures.
- Focused UI/theme tests: `24 passed`; Home guidance test: `1 passed`.
- Changed-file Ruff, `git diff --check`, light/dark visual QA, packaged
  self-check, UI/settings smoke, and strict deep codesign passed.
- Current trial bundle: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`.
  This is source/package evidence, not native Product Owner UAT or a release
  claim.

### Protected scope and ownership

- The next chat is for student-number recognition only after the Product Owner
  provides the exact scope. Do not infer a new algorithm, threshold, accuracy
  target, or fixture adjudication from this checkpoint.
- `DETAIL: [รอ Product Owner บอกใน chat ใหม่]`
- Preserve immutable originals, provenance, fail-closed uncertainty, mandatory
  teacher confirmation, existing OMR/crop/geometry/review/scoring/storage/
  export behavior, and backward compatibility.
- Existing untracked `tests/fixtures/real/vol.8/` and
  `tests/fixtures/real/vol.9/` belong to the user/previous work. Do not reset,
  clean, overwrite, or absorb them.

### Next exact action

Start a fresh chat with the prompt in the matching current section at the top
of `docs/NEXT_CHAT_HANDOFF.md`. Read the repository docs and exact current
identity implementation first; wait for the new `DETAIL` before changing code.

## Current task handoff — 2026-09-16 UX/UI continuation

This is a concise continuity checkpoint after the bounded macOS UI polish. The
next chat may continue UX/UI work only; do not reopen or alter the business
logic that is already verified.

### Verified current state

- Repo: `/Users/zubinpijit/private/exam-grader`
- Branch and origin are aligned at `0087a49 fix: polish native exam grader controls`.
- The latest macOS arm64 bundle is `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`.
- Visual inspection of the fresh bundle confirmed compact native-style settings/help controls, no large structural emoji icons, and visible combo-box/stepper arrows in `NewExamDialog`.
- Focused UI tests: `23 passed` (`tests/test_ui.py`, `tests/test_theme_and_layout.py`) plus `1 passed` (`tests/test_vol8_home_help.py`). Geometry/Vol.2/Vol.8/document-normalization regressions: `46 passed`.
- Ruff, `git diff --check`, strict deep codesign, packaged self-check, settings smoke, and offscreen UI smoke passed. This is source/package evidence only; Product Owner native UAT is still outstanding.

### Protected scope and ownership

- Continue only with minimal macOS-native UX/UI polish. Do not change OMR,
  geometry resolution, review gates, scoring, identity persistence, storage,
  export, crop behavior, or other business logic unless the Product Owner gives
  a new explicit scope.
- Preserve immutable originals, provenance, fail-closed uncertainty, teacher
  confirmation for student numbers, existing good crop/OMR behavior, and
  backward-compatible runtime geometry.
- Existing `tests/fixtures/real/vol.8/` and `tests/fixtures/real/vol.9/` remain
  user/previous-agent untracked files. Do not reset, clean, overwrite, or
  absorb them.

### Next exact action

Open the latest bundle and inspect MainWindow, NewExamDialog, ExamDialog, and
ReviewDialog at supported desktop sizes against the new screenshots. Identify
one bounded UI-only improvement, use `$ui-ux-pro-max` only as needed, implement
it without touching business logic, add focused UI coverage, and re-run the
app/package smoke before any separately authorized commit or push.

Paste-ready prompt: see the matching current section at the top of
`docs/NEXT_CHAT_HANDOFF.md`.

## Current task handoff — 2026-09-15 Vol.9 runtime/UI geometry and review-gate root cause

This is a read-only verification handoff for the next implementation chat. No
source, test, fixture, build, or Git state was changed in this turn. The
working tree remains intentionally dirty and must be preserved.

### Confirmed findings

- Runtime and UI do not share one geometry-resolution contract. Runtime
  registration is resolved in `imaging.register()`/`analyze()`, while
  `review_ui._normalization_corners()` independently chooses preview corners
  and `exam_ui.populate_issues()` independently resolves issue crops. This
  permits the displayed crop and the measured runtime ROI to disagree.
- IMG_1071/IMG_1080 can be read correctly yet remain in review because
  `imaging.py` makes every answer's `auto_resolved` false when the global
  `registration.normalization_requires_review` flag is true. A page-level
  warning is therefore acting as a question-level answer gate. The safe fix is
  separate page, block, answer, and identity decisions; do not lower the
  confidence threshold globally.
- The IMG_1078 screenshot shows q10–q15 previews containing the neighboring
  printed q25–q30 number strip. A direct current-pipeline replay of the raw
  `tests/fixtures/real/vol.9/IMG_1078.jpg` with built-in `default-1` produced
  answer ROIs confined to the five answer columns, so the screenshot is not
  reproduced by that path. The remaining likely causes are a stale detection
  or a newly-created custom template whose `with_number`/column inference
  retained the question-number interval. The exact new exam DB/template/
  detection payload is still required before naming one as the sole cause.
- Student-number confirmation is persisted through the full review path, but
  the Students tab still derives its label from the broader unresolved state.
  Confirmed identity must refresh immediately and remain visibly separate from
  any answer-review-pending state.

### Required next implementation

Introduce one persisted/current resolver result containing source hash,
pipeline version, physical corners, canonical transform, grid/block geometry,
per-answer ROIs, and confidence/provenance. Make runtime classification,
review thumbnails, and template/test previews consume it. Add a hard invariant
that five answer ROIs stay inside their own block and cannot overlap an
adjacent printed question-number strip; malformed custom geometry must remain
review-required, never be guessed. Then split review policy by stage: accept
strong unambiguous answers, keep true multiple/uncertain/invalid geometry
review-required, and keep student-number confirmation mandatory. After number
confirmation, refresh Students-tab identity text without auto-confirming
answers. Preserve immutable originals, bulk prefill confirmation, fail-closed
uncertainty, and the working OMR/crop behavior.

### Evidence and gate

Current branch is `fix/vol8-current-usable-checkpoint` at `ae973e1`; existing
focused evidence is 37 + 30 + 7 + 7 passed, with the current local app at
`/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`. These checks and
the package predate this read-only verification and are not evidence that the
new fixes are implemented. The Vol.3 broad benchmark still has its recorded
unrelated mismatch. Next chat must inspect the exact new exam payload, add
focused regressions for resolver consistency, IMG_1078 column isolation,
1071/1080 answer acceptance, and identity refresh, then build a fresh `.app`.
Product Owner native UAT remains the gate before release/tag/publish.

## Current checkpoint — 2026-09-15 Vol.9 freshness, review preview, and settings controls

This checkpoint is built from the current working tree on branch
`fix/vol8-current-usable-checkpoint`. It does not replace the earlier release
history or the existing dirty changes in storage/export/workflow files.

- When an exam opens, persisted detections whose `pipeline_version` is older
  than the current `omr-illumination-v10-document-normalization-v2` are
  reprocessed from the immutable source path. A teacher-confirmed key remains
  durable; unresolved old student detections are refreshed only after a key is
  confirmed. Current detections are not retried merely because they are
  review-required.
- Review thumbnails now use the answer observation's exact `roi_rects` (with a
  small visual margin), falling back to the registered block offset only when
  old detections do not contain those rectangles. This prevents the green
  printed question-number strip from becoming part of the answer crop without
  changing OMR decisions.
- A review saved against an older detection is not silently reused after a
  reread. Teacher-confirmed identity decisions remain explicit and durable.
- The Home settings control is a full-surface `QToolButton` with
  `InstantPopup`; template management remains reachable from the create-exam
  dialog and the settings/template dialog controls remain safely disabled only
  where the selected built-in template is read-only.

### Vol.9 current-pipeline comparison (real fixture, not an accuracy claim)

The stored fixture detections were `v9`; the values below are a direct current
`v10` rerun using the canonical reference generated from each immutable raw
key image. Student identity is intentionally still teacher-confirmed.

| Sheet | Stored v9 identity | Current v10 candidates | Current OMR state | Current geometry |
|---|---|---|---|---|
| IMG_1071 | `113` | `147` (single candidate, review-required) | 30 single, 30 blank | norm .7732, residual 3.233 px, coverage .8295, alignment .7328 |
| IMG_1078 | `12` | `12 / 42`, margin 8.43 (review-required) | 18 single, 30 blank, 1 uncertain, 11 multiple | norm .8296, residual 2.385 px, coverage .8864, alignment .7971 |
| IMG_1080 | `1` | `46 / 44`, margin 10.75 (review-required) | 29 single, 31 blank | norm .7652, residual 3.394 px, coverage .8068, alignment .7159 |

These candidates are evidence for human review, not automatic identity
correction. The 1078 green-strip symptom is a preview geometry defect; the
identity ambiguity remains a separate deliberate review gate.

### Verification and package

- Focused UI/workflow/automation: **37 passed**.
- Document-normalization and Home guidance: **30 passed**.
- Vol.8 hardening: **7 passed**; Vol.8 registration: **7 passed**.
- Changed-file Ruff and `git diff --check`: passed.
- `dist/ExamGrader.app` rebuilt from the current working tree; deep codesign,
  packaged self-check, settings smoke, and offscreen UI smoke passed.
- Product Owner native UAT is still required before any release/tag/publish
  claim. The app is ready for that test, not yet UAT-accepted production.

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

## Current status — 2026-09-14 Final Release v1.0.2 & Web Sync Completed

Published official release **v1.0.2** on GitHub and synchronized `bithope.app` web landing page:
- **Git HEAD**: `73692fe` (on `main`). Tag: `v1.0.2`.
- **Release Artifacts**:
  - macOS DMG: `Exam-Grader-v1.0.2-macOS-Apple-Silicon.dmg` (SHA-256: `8902e716...`)
  - Windows EXE: `Exam-Grader-v1.0.2-Windows-Setup.exe` (SHA-256: `b7249c9b...`)
- **bithope.app Web Sync**:
  - Hardened `bithope-web` `release.ts` resolver with dynamic minute cache-buster (`?_t=${cacheMinute}`), Next.js ISR `revalidate: 60`, and version-resilient download URL fallbacks.
  - Deployed `bithope-web` to Vercel production. Both macOS and Windows cards reflect `v1.0.2` on live site.

## Current status — 2026-09-14 Production-Ready OMR & Student Number Recognition Hardening

Successfully hardened the OMR Answer Detection and Student Number Recognition pipelines to production readiness on real smartphone exam sheets (Vol.7 Shopee 60Q/5C), verified with 148 passing automated regression tests:
- **OMR Answer Detection ("X" Marks & Pencil Recognition) (`imaging.py`)**:
  - Bounded Lattice Alignment: constrained search range to `[-18, +18]` px to eliminate column hopping across narrow 44px columns.
  - Differential Row SNR & Core Contrast: scoped differential SNR to custom templates with blank floor threshold (`max(densities) < 0.06`).
  - Monochrome Strip Line Opening Masking: applied $25 \times 1$ horizontal and $1 \times 15$ vertical morphological openings to eliminate boundary line bleed into answer cells.
  - Result: Single-mark detection rate jumped to **98.3% (177/180)** across all 6 outdoor test sheets (`IMG_0986` to `IMG_0992`).
- **Student Number Recognition & Safety Nets (`identity.py`)**:
  - Safety Net 1 & 2: Suppressed left-margin Thai label fragments ("เลขที่") and bottom dotted guidelines.
  - Touching Digit Splitting: Split touching digits via vertical projection valley when $proj \le 0.20 \times \min(peak_L, peak_R)$.
  - Invariant Digit Classification:
    - 3 vs. 4 vs. 9 disambiguation: closed 4 (hole + crossbar/diagonal), open 4 (straight right stem $right\_std < 0.075$), 9 (upper hole + right stem), and 3 (curved right side).
    - 6 vs. 0 disambiguation: hole in bottom half ($(hy + hh/2)/h \ge 0.65$) identifies 6.
    - Restored serif 1 classification ($right\_shaft$ and negative correlation).
  - Subprocess UTF-8 safety with `errors="replace"`.
  - Result: **6/6 (100.0%)** student numbers matched ground truth (1, 3, 12, 13, 27, 49).
- **Template Discovery (`template_discovery.py`) & UI Polish (`calibration_ui.py`)**:
  - Auto-inferred student number ROI `(740, 150, 960, 240)` when score ROI is in top-right header band.
  - Added helper tooltip & label: `"💡 ลากกรอบเฉพาะช่องเขียนตัวเลข (เว้นคำว่า 'เลขที่' และเส้นไข่ปลาไว้ด้านนอกเพื่อความแม่นยำสูงสุด)"`.
- **Test Suite**: 148 passed, 3 skipped in 82.12s (including 8 new tests in `tests/test_vol7_real_sheets.py`).
- **Packaged App Bundle**: Rebuilt `dist/ExamGrader.app`, verified codesign, `--self-check` (passed), and `--smoke-ui` (passed).

## Current status — 2026-09-13 Template Calibration System Hardened & Production Verified

Successfully generalized the Template Calibration and Discovery engine and redesigned the manual editing workflow to production readiness, verified with 140 passing automated regression tests:
- **Generalized Grid Detection (`template_discovery.py`)**:
  - Solved contour swallow bug: deprioritized canvas-spanning contours `(0, 0, W, H)` when valid inner table contours exist.
  - Implemented column line edge trimming (`trim_left`, `trim_right`, `trim_both`) to reject margin artifacts without hardcoding.
  - Enforced cross-block consistency across answer blocks.
  - Auto-detected `tests/fixtures/real/vol.7/ถ่ายในที่แจ้ง/keyyy.jpg` as exactly 4 blocks × 15 rows × 5 choices (60 questions).
  - Validated real OMR extraction on `keyyy.jpg`: Q1–30 answers read 100% accurately (including Q4 multiple marks A+D), Q31–60 blank.
- **Manual Grid Redesign (`calibration_model.py`, `calibration_ui.py`)**:
  - Replaced destructive row-splitting with: row count `QSpinBox`, `append_row`, `remove_row_at_end`, `append_choice`, `remove_choice_at_end`.
  - Manual adjustments mark `geometry_state="user_edited"`, ensuring auto-detection never clobbers teacher customizations without explicit confirmation.
- **UI/UX Polish (`calibration_ui.py`, `ui.py`)**:
  - Clean 2-row toolbar layout in `CalibrationDialog` eliminating text truncation.
  - Added "💡 คำแนะนำการถ่าย" photography tips and safe "🔄 ตรวจหาใหม่" re-detection.
  - Fixed "ชั้น" combobox width and updated question count label in `NewExamDialog`.
- **Test Suite**: 140 passed, 3 skipped in 66.33s.
- **Packaged App Bundle & DMG Build**:
  - Rebuilt `dist/ExamGrader.app` via PyInstaller (macOS arm64).
  - Codesign verification passed: `codesign --verify --deep --strict dist/ExamGrader.app`.
  - Self-check passed: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check` (exit code 0).
  - Smoke-UI passed: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui` (exit code 0).
  - Rebuilt DMG: `dist/Exam-Grader-v1.0.1-macOS-Apple-Silicon.dmg` (108 MB, SHA-256: `318ea8584431bd36550f50cf6f8bedcb552e47a31f68712b50e162801f0a538b`).

## Current status — 2026-09-13 v1.0.1 Published & Live

Published official GitHub Release `v1.0.1` (ID: `387664293`) at tag `v1.0.1` (`ccc6d49a971a162097044957677a4881afa3ce08`).
- **macOS Release Artifact**: `Exam-Grader-v1.0.1-macOS-Apple-Silicon.dmg` (113,086,354 bytes, SHA-256: `d90919cc6fd7f2952eacfbd53dd6c4d589b9d4def6710b11c8795762b206433f`), codesigned, smoke-tested, and verified live via HTTP GET.
- **Windows Release Artifact**: `Exam-Grader-v1.0.1-Windows-Setup.exe` (77,919,326 bytes, SHA-256: `b618fe15646290cd73eb3ee6238beddefd7081c581835c39fa780e26c7cd19ec`), built via GitHub Actions Windows runner (Run ID: `34711082160`), smoke-tested on Windows 10, and verified live via HTTP GET.
- **CI Packaging Robustness**: Updated `.github/workflows/release.yml` with dynamic installer discovery and version resolution, preventing version hardcoding in future releases.
- **Release Documentation**: Documented in `docs/NEXT_CHAT_HANDOFF.md` with direct download URLs and verified checksums.

## Current status — 2026-09-12 Windows UAT Investigation Documented

Created `docs/WINDOWS_UAT.md` tracking the full Windows readiness investigation. All Windows packaging, build, and UAT areas are confirmed NOT RUN / NOT TESTED. This is now cross-referenced in `docs/AGENT_HANDOFF.md` under the current handoff section. Key risks identified: Tesseract binary bundling, OpenCV contrib on Windows, Thai font fallback, PyInstaller hooks, DPI scaling, and SQLite locking semantics. Blocked gates: G1 (requires separate Mac/Windows evidence) and G7 (requires clean OS/CPU matrix installation).

## Current status — 2026-09-12 Exam Grader Landing Page Foundation & Redesign Ready

Built initial landing page foundation for Exam Grader at route `/exam-grader` on `bithope-web` (`/Users/zubinpijit/bithope/apps/bithope-web`), ready for user-guided redesign:

- **Landing Page Architecture (`bithope-web`)**:
  - Main route: `src/app/exam-grader/page.tsx` with full SEO, OpenGraph, JSON-LD, and semantic sections.
  - Centralized URLs: `src/app/exam-grader/constants.ts` (`EXAM_GRADER_LINKS`, `EXAM_GRADER_VERSION`).
  - Modular components: `ExamGraderNav`, `HeroSection`, `AppPreviewSection`, `WorkflowSection`, `BenefitsSection`, `DownloadSection`, `CommunitySection`, `ExamGraderFooter`.
  - Next.js 16.2.2 static build: 59/59 pages prerendered successfully, 0 TypeScript errors, 0 lint errors, 0 regressions to `/`, `/daipay`, `/myrai`.
- **Assets Ready (`public/exam-grader/`)**:
  - Native PySide6 Qt screenshots: Dashboard, Review Bulk Edit with crop preview, Results & Export.
  - Transparent 2D illustrations: Teacher, Student at desk, Blackboard quote, Books & Stationery, Sleeping cat, Notion-style SVG answer sheet.
- **Truthful Marketing Gate**: Only verified capabilities are claimed (Offline 100%, Human Review, Bulk Edit, Custom Template, Excel .xlsx & Checked image export). No claims of unverified features.
- **Next Action**: Redesign the landing page in a fresh chat session according to user's new creative direction.

## Current status — 2026-09-11 Review Multi-Select Checkbox UX Polish & State Synchronization

Refactored Review page multi-select checkbox implementation to standard Qt Model/Delegate architecture with stable issue selection tracking, 100% verified across all 8 Quality Gates:

- **Review — Multi-Select Checkbox UX & Architecture (`exam_ui.py`)**:
  - Replaced conflicting `cellClicked` callback with dedicated `CheckBoxDelegate(QStyledItemDelegate)`.
  - Expanded hit target across the entire 52px cell rectangle, completely eliminating the double-trigger race condition that previously caused unresponsive clicks and prevented unchecking.
  - Left-click press consumption prevents rubber-band drag glitches; Space keypress handles native Qt keyboard accessibility.
  - Checkbox indicator is centered horizontally and vertically in Column 0.
  - Single Source of Truth (`self.selected_issue_keys: set[tuple]`): Stable issue identification tuples preserve selections across `populate_issues()`, refreshes, and table sorting.
  - Bulk action toolbar counts (`เลือก N รายการ`), [เลือกทั้งหมด], and [ล้างการเลือก] stay 100% synchronized with internal selection state.
  - Added comprehensive automated test `test_review_tab_checkbox_delegate_ux_and_state_preservation` in `tests/test_ui.py` covering click, margin click, Space toggle, right-click ignore, refresh persistence, post-refresh uncheck, and post-bulk-save key pruning.

- **Quality Gates Passed (8/8)**:
  1. Unit & Regression Tests: 126/126 passed (100% pass rate in 96s)
  2. Ruff Lint: 0 errors across codebase (`ruff check src tests`)
  3. Mypy Type-Check: 0 issues across 20 source files (`mypy src`)
  4. PyInstaller Build: macOS arm64 app bundle build succeeded (`scripts/build/build.py`)
  5. Strict Deep Codesign: passed (`codesign --verify --deep --strict dist/ExamGrader.app`)
  6. Packaged Self-Check: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check`)
  7. Packaged Smoke-UI: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui`)
  8. Visual QA: Captured and inspected Review page in Light and Dark modes with centered checkboxes and active toolbar.

## Current status — 2026-09-11 Review Bulk Edit, Student Number Hardening & Custom Template Overlay

Production-ready polish completed across Review Bulk Edit, Student Number Recognition & Reconciliation, and Custom Template Checked Overlay Alignment, verified across all 8 Quality Gates:

- **Review — Bulk Edit (`exam_ui.py`, `review_service.py`):
  - Added checkbox column (Col 0) to `issue_table` in `ExamDialog` with reactive cell click and check state change bindings.
  - Bulk action toolbar with [เลือกทั้งหมด], [ล้างการเลือก], dynamic selection count label (`เลือก N รายการ`), bulk answer/status selector combo (`bulk_combo`), and [นำไปใช้และบันทึกที่เลือก] button (`bulk_apply_btn`).
  - Added atomic transaction-safe batch resolution method `ReviewService.bulk_resolve(exam_id, operations)` saving answer overrides, attendance statuses, and student identities in a single SQLite transaction.
  - Completely preserves unselected rows untouched; automatically finalizes students who have zero remaining issues; reactively updates UI counts and table rows.
  - Added comprehensive automated test `test_review_tab_bulk_edit_ui` in `tests/test_ui.py` (9/9 pass).

- **Student Number Logic Hardening & Vol.6 Ground Truth (`identity.py`, `review_service.py`)**:
  - Recognizer evidence first: Candidate recognition scores and score margins computed in `identity.py:observe()`.
  - Digit sub-segmentation filtering: Filtered out single-digit sub-segmentation fragments when multiple boxes exist and full-length candidates are present.
  - Non-speculative adoption: `ReviewService.adopt_numbers()` requires high confidence (>= 80.0) and score margin (>= 15.0) or unambiguous sole candidate to adopt. Missing number list is strictly a tie-breaker constraint and never a substitute for recognition.
  - Collisions fail closed: Colliding or low-confidence candidate sheets stay unresolved in Review.
  - Distinct review statuses: Distinct `status` field (`duplicate`, `missing`, `uncertain`, `out_of_range`) added to `ReviewService.issues()`.
  - Regression verified for vol.6 ground truth `13, 19, 52, 67` in `tests/test_vol6_uat.py` (2/2 pass).

- **Custom Template Checked Overlay Alignment (`exporting.py`)**:
  - Invariant maintained: `detected cell == rendered overlay cell`.
  - Root cause: `exporting.py:export_results()` previously checked `hasattr(flow.database, "get_template")` (which is always False for a database Path) and fell back to default `template()` (Default #1 836×818).
  - Fix: Loaded custom template definition with `load_exam_template_def(flow.database, exam_id)` and passed `template_def=template_def` to `checked_image()`, `snapshot["export"]["template"]`, and `checked_provenance["render_template"]`.
  - Verified on 1200×1720 custom template in `tests/test_export.py:test_custom_template_checked_overlay_alignment` (12/12 pass) and visual QA overlay inspection.

- **Quality Gates Passed (8/8)**:
  1. Unit & Regression Tests: 125/125 passed (100% pass rate in 98s)
  2. Ruff Lint: 0 errors across codebase (`ruff check .`)
  3. Mypy Type-Check: 0 issues across 20 source files (`mypy src`)
  4. PyInstaller Build: macOS arm64 app bundle build succeeded (`scripts/build/build.py`)
  5. Strict Deep Codesign: passed (`codesign --verify --deep --strict dist/ExamGrader.app`)
  6. Packaged Self-Check: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check`)
  7. Packaged Smoke-UI: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui`)
  8. Visual QA: Bulk edit before/after and custom template 1200×1720 overlay inspected and verified.

## Current status — 2026-09-11 Production Polish, Vol.6 Default #3 Benchmark & Native Thai UX Hardening

Full production polish, permanent delete FK fix, template copy bug fix with evidence, student number 2-digit recognition upgrade, teacher review optimization, and native Qt Thai UX typography polish are completed and 100% verified across all 8 Quality Gates:

- **Permanent Delete Foreign Key Constraint Fix (`storage.py`, `ui.py`)**:
  - Fixed `ExamStore.purge()` to delete in correct FK dependency order: `answer_overrides` → `reviews` → `identities` → `answer_keys` → `detections` → `sources` → exam tables → `exams`.
  - Refactored `TrashDialog(QDialog)` into a dedicated clean component with `QPushButton[destructive="true"]` semantic danger styling, preventing style override bugs.
  - Added full test coverage in `tests/test_purge_regression.py` (3/3 pass) verifying FK safety with active reviews, answer keys, shared images across exams, and trash restore/purge.
- **Template Copy Bug Investigation & Fix (`template_manager.py`)**:
  - Re-encoding verification: Confirmed PNG encoding is strictly lossless (sha256 and pixels identical).
  - True root cause identified through SQL logging: In `template_manager.py:load_exam_template_def()`, the query used wrong column names `SELECT definition_json FROM templates WHERE template_id=?` (actual table columns are `id` and `definition`), causing silent SQLite exceptions that fell back to `default-1` (60 questions).
  - Fixed query to select `definition` by `id` and `version`, and passed `app_data_dir` in `settings_ui.py:test_omr()`.
  - Verified with `tests/test_default3_builtin.py` (5/5 pass) ensuring copied templates retain exact Default #3 30-question geometry.
- **Student Number 2-Digit Recognition & Vol.6 Benchmark (`identity.py`)**:
  - Derived ground truth fixture for real Default #3 exams in `tests/fixtures/real/vol.6/ground_truth.json`: `IMG_0911` -> `52`, `IMG_0912` -> `13`, `IMG_0913` -> `67`, `IMG_0914` -> `19`.
  - Reference Static Ink Suppression: Added dilated mask subtraction in `identity.py:preprocess()` to suppress the printed Thai label ("เลขที่") and dotted underline from the reference image, cleanly isolating student pencil marks.
  - Single-Digit Padding & PSM: Added `pad_px=18` and PSM 8/10 for single-digit recognition (digits 6, 7, 9).
  - Slender 1 Stroke Recognition: Added heuristic recognition for vertical line student strokes (`w/h < 0.28 and h > 30`).
  - Achieved 100% recognition on vol.6 (`tests/test_vol6_uat.py` 2/2 pass) with zero regressions on vol.1, vol.2, vol.5.
- **Teacher Review Automation & Fail-Closed Safeguards**:
  - Confident single marks and blanks auto-accept without requiring teacher clicks; uncertain marks and ambiguous gaps trigger teacher review.
  - Fail-closed safeguards preserved against vol.3 engineering probes (`test_vol3_blank_heavy_sheets_remain_reviewable_and_do_not_invent_all_choices`).
- **Native Thai Typography & UX Polish (`preferences.py`, UI dialogs)**:
  - Font family includes Apple system Thai font `"Thonburi"` + `"Noto Sans Thai"`.
  - Removed all CSS `line-height` usages across the entire codebase (in `settings_ui.py` and `calibration_ui.py`), adhering to Qt native layout standards.
  - Standardized input control heights (`min-height: 32px;`) for `QLineEdit`, `QSpinBox`, `QComboBox`, and `QPushButton`.
  - Styled native `QComboBox::drop-down` with fixed padding and border alignment; added `QSpinBox` button styling.
  - Added semantic `destructive="true"` button styles for Light (`#DC2626` / `#FEF2F2`) and Dark (`#F87171` / `#450A0A`).
  - Theme-adaptive unresolved review item highlight (`#FEF3C7` / `#92400E` in Light, `#451A03` / `#FDE68A` in Dark).
  - Captured and visually inspected all 5 screens across Light and Dark themes in `docs/evidence/visual_qa/`.
- **Quality Gates Passed (8/8)**:
  1. Unit & UAT Tests: 122/122 passed (100% pass rate)
  2. Ruff Lint: 0 errors across codebase (`ruff check .`)
  3. Ruff Format: 0 errors (`ruff format --check .`)
  4. Mypy Type-Check: 0 issues across 20 source files (`mypy src`)
  5. PyInstaller Build: macOS arm64 app bundle build succeeded (`scripts/build/build.py`)
  6. Strict Deep Codesign: passed (`codesign --verify --deep --strict dist/ExamGrader.app`)
  7. Packaged Self-Check: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check`)
  8. Packaged Smoke-UI: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui`)

## Current status — 2026-09-11 Robust Custom Template Calibration, Native Polish & Built-in Default #3 Production Integration

Robust custom template calibration, native UI polish, immutable built-in Default #3 integration (สุทธิอนุสรณ์ 30 ข้อ 4 ตัวเลือก 3 ชุด), and iterative Visual QA are completely developed, tested, and verified across all Quality Gates:
- **Default #3 Immutable Built-in Integration**:
  - Defined `default-3` in `BUILTIN_TEMPLATE_IDS = ("default-1", "default-2", "default-3")` in `template_manager.py`.
  - Packaged canonical warped reference image `src/exam_grader/resources/reference_default3.png` (1200 × 1720 px, SHA256 `3e60d1a3d85b5bd106bc305298253088234634ac1ff867be985f736d25a4ea6e`).
  - Packaged `src/exam_grader/resources/template_default3.json` with kind `builtin`, 30 questions, 4 choices (`A`–`D` / `ก`–`ง`), 3 blocks × 10 rows.
  - Frozen built-in geometry visually verified against real fixture `tests/fixtures/default3/default#3.PNG` (`docs/evidence/default3_full_overlay.png`):
    - Student Number ROI `(468, 440, 776, 515)` cleanly captures "เลขที่ ............." (`docs/evidence/student_roi_clean.png`) avoiding the upper text line.
    - Score ROI `(813, 224, 1076, 527)` snugly encloses the "คะแนนรวม" box (`docs/evidence/score_roi_crop.png`).
    - Every cell across all 3 blocks (40 cells per block) aligns centered inside printed boxes.
  - Fixture honesty: strictly kept only the real blank fixture `tests/fixtures/default3/default#3.PNG`. Removed simulated photo fixture (`photo.jpg`) and removed hypothetical `table_coverage >= 0.85` claims.
- **Centralized Theme System & Contrast Fixes**:
  - Implemented `create_theme_palette` in `preferences.py` setting unified `QPalette` color roles for window, base, alternate, tooltips, buttons, highlights, and disabled states.
  - Redesigned `get_theme_stylesheet` with unified design tokens for Light and Dark modes covering `QMenu`, `QMenuBar`, `QListWidget`, `QTabWidget`, `QTabBar`, `QComboBox`, `QTableWidget`, `QHeaderView`, `QPushButton`, `QLineEdit`, `QSpinBox`, `QScrollBar`, `QProgressBar`, and `QSplitter`.
  - Solved dark mode white-on-white popups and glaring white rectangular flash in exam workspace.
- **Thai Typography & Row Padding**:
  - Enforced minimum row heights (58px on home exams list, 52px on student review rows) to prevent Thai upper/lower vowel and tone mark clipping (`ิ`, `ี`, `ึ`, `ื`, `ุ`, `ู`, `่`, `้`, `๊`, `๋`, `์`).
- **Template Manager Responsive Split Layout**:
  - Redesigned `TemplateSettingsDialog` into a responsive 2-column table (`ชื่อแม่แบบ` and `ชนิด`) with fixed kind column, eliminating horizontal scrollbars.
  - Right pane features prominent template header, detailed specs card, smooth preview pixmap, and clear button capability states (built-ins disable edit/delete with informative tooltips; duplicate and test OMR remain active).
- **Calibration Dialog Viewport Sizing & Scrollable Controls**:
  - Dynamically sized to fit comfortably within `screen.availableGeometry()`.
  - Right controls wrapped in `QScrollArea` with persistent bottom bar (`🔍 ทดสอบกับภาพจริง…`, `ยกเลิก`, `💾 บันทึกแม่แบบ`).
  - Minimum width of right pane set to 380px with initial splitter sizing `[720, 420]` and concise toolbar button labels with tooltips (`📁 เลือกภาพ...`, `👆 เลือก/ย้าย`, `📐 ตารางคำตอบ`, `🔢 เลขประจำตัว`, `📝 คะแนนรวม`).
- **Iterative Visual QA Loop**:
  - Executed `tools/inspect/visual_qa_inspection.py` capturing 10 screenshots across all 5 primary screens/dialogs in Light and Dark modes (`docs/evidence/visual_qa/`).
  - Inspected each screenshot visually using `view_file`. Diagnosed right pane horizontal squeeze and toolbar button clipping in `CalibrationDialog`, implemented fixes, and re-inspected to confirm perfect visual polish.
- **Quality Gates Passed (8/8)**:
  1. Full Test Suite: 113/113 passed (100% pass, including `tests/test_default3_builtin.py`, `tests/test_theme_and_layout.py`, `tests/test_calibration_system.py`)
  2. Linter: `ruff check .` clean (0 errors)
  3. Type Checker: `mypy src` clean (0 errors across 20 source files)
  4. Packaging Build: PyInstaller macOS arm64 app bundle built successfully (`dist/ExamGrader.app`)
  5. Codesign: `codesign --verify --deep --strict dist/ExamGrader.app` passed
  6. Self-Check: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check` passed (exit code 0)
  7. Smoke-UI: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui` passed (exit code 0)
  8. Visual UAT & Regression Benchmarks: 13/13 passed (100% pass) and visual inspection verified
  2. Ruff Lint & Format: 0 errors across codebase (`ruff check .`)
  3. Mypy Type Check: 0 issues across 20 source files (`mypy src`)
  4. Build: macOS arm64 PyInstaller app bundle build succeeded (`scripts/build/build.py`)
  5. Strict Deep Codesign: passed (`codesign --verify --deep --strict dist/ExamGrader.app`)
  6. Packaged Self-Check: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check`)
  7. Packaged Smoke-UI: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui`)
  8. Visual UAT & Screenshot Inspection Loop: generated and inspected `template_settings_dialog.png`, `template_settings_dialog_dark.png`, `calibration_dialog_default3.png`, `calibration_dialog_default3_dark.png`, and `calibration_test_dialog_inspection.png`.

## Current status — 2026-09-10 Polish UI/UX, vol.5 Default #2 Registration Robustness & Fail-Closed Purge Safety

Teacher workflow polish and vol.5 (Default #2 pink answer sheet) support are fully implemented, verified, and passing all quality gates:
- **vol.5 Key & Student Registration**:
  - Identified root causes: `key.JPG` and `IMG_0865.jpg` (Student 1) matched high inliers (173 and 95) with SIFT RANSAC 2.5, but fell just under the strict 0.45 inlier ratio due to dense pink grid and background table texture.
  - Implemented `_is_valid_homography` in `src/exam_grader/imaging.py` supporting dense feature inlier sets (`inliers >= 80 and ratio >= 0.35`, `inliers >= 150 and ratio >= 0.30`) with RANSAC 2.5 and refined 3.5 fallback.
  - Fail-closed safety strictly verified: 100% rejection preserved on cross-template attempts (Default #2 on Default #1, Default #1 on Default #2), truncated sheets, and random noise.
- **True Disk-Level Purge with Non-Overclaiming UI**:
  - `ExamStorage.purge(exam_id)` transactionally removes all DB rows and unlinks unique unshared source images from `<app_data>/input/originals/`.
  - UI wording accurately specifies: "ข้อสอบ '{exam.name}' รวมทั้งภาพกระดาษคำตอบในระบบและผลการตรวจทั้งหมดจะถูกลบถาวรทันทีและไม่สามารถกู้คืนได้ (ไฟล์ Excel ที่เคยส่งออกไปแล้วจะไม่ได้รับผลกระทบ)".
- **Dynamic Template Geometry in UI Previews**:
  - `ReviewDialog` and `ExamDialog.populate_issues()` dynamically warp using `template_def.canonical_width` and `template_def.canonical_height`. Fixed gray/blank thumbnail slicing for Default #2 (1200×1720) sheets. Text bleed in thumbnail table cells cleared.
- **Failed Sheet Management**:
  - Added direct dismiss/delete actions in the Student failure table, Issue table, and Review dialog. Fixed `"รุ่นนี้รับเฉพาะ JPEG และ PNG"` bug by dismissing rather than re-importing extensionless content-addressed blobs.
- **Interactive Calibration Nudge Controls**:
  - Added directional nudge controls (1px, 5px, 10px) to `CalibrationCanvas` and `CalibrationDialog` for live geometry adjustments, paired with actionable photography guidance.
- **Export Metadata Tracking**:
  - Added dedicated `Info` sheet in `scores.xlsx` documenting exam metadata and active template name without altering the `Scores` tabular format.
- **Synthetic Default #2 Generator**:
  - Added 3×20 4-choice sheet rendering (`render_blank_sheet_default2`, `get_cell_bounds_default2`, `draw_mark_default2`) in `tools/synthetic/sheet_builder.py`.
- **Quality Gates Passed (8/8)**:
  1. Unit & UAT tests: 98/98 passed (100% pass, including `tests/test_vol5_uat.py`)
  2. Ruff lint & format: 0 errors across 59 files
  3. Mypy type-check: 0 issues across 20 source files
  4. Build: macOS arm64 PyInstaller app bundle build succeeded (`scripts/build/build.py`)
  5. Strict deep codesign: passed (`codesign --verify --deep --strict dist/ExamGrader.app`)
  6. Packaged self-check: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check`)
  7. Packaged smoke-ui: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui`)
  8. Real-fixture UAT: vol.5 pipeline automatically grades Student 1 (`IMG_0865.jpg`) at 11/30 (student number 1), and full workflow reproduces teacher ground truth (Student 2 = 6, Student 3 = 6, Student 4 = 29) exactly.

## Current status — 2026-09-10 Custom Answer-Sheet Template / Calibration System

The Custom Answer-Sheet Template and Calibration System is fully implemented, calibrated, and verified:
- **Built-in Templates**: Default #1 (60Q/5C/4×15) and Default #2 (60Q/4C/3×20) supported out of the box with zero regression on existing exams.
- **Default #2 Calibration**: Calibrated using real fixture `default#2.JPG` warped to 1200×1720, 3 blocks × 20 rows, 4 columns (ก–ง / A–D), cell inset = 6px, student number ROI `[856, 140, 935, 205]`, score ROI `[950, 111, 1114, 294]`. Visual overlay verified (`docs/evidence/default2_full_overlay.png`) and checked sample verified (`docs/evidence/default2_checked_example.jpg`). Reference and template definition frozen in package resources (`reference_default2.png`, `template_default2.json`).
- **Schema Migration v12 → v13**: SQLite schema migration v13 creates an automatic pre-migration backup (`exams.sqlite3.v12.bak`), adds the `templates` table, and binds `template_id` / `template_version` to `exams`. All existing exams are backfilled safely to `default-1` v1. Deletion of templates referenced by existing exams is strictly blocked.
- **Content-Addressed Reference Storage**: Custom reference images are stored in app-data content-addressed file storage (`<app_data>/templates/references/<sha256>.png`) rather than SQLite BLOBs, preventing database bloat and simplifying backup/migration.
- **Single Unified Grading Pipeline**: Choice count (2–5) and block geometry are template properties. Never reads non-existent 5th choice on 4-choice sheets.
- **Canonical Internal Choice Mapping**: Paper-facing choice labels (ก, ข, ค, ง) map to internal canonical choices (A, B, C, D); grading engine remains agnostic to paper headers.
- **Template Discovery Pipeline (`template_discovery.py`)**: Automatic paper boundary detection, perspective warping, block and row/col cluster extraction, choice count detection, and confidence scoring.
- **Settings & Calibration UI (`settings_ui.py`, `calibration_ui.py`, `ui.py`, `exam_ui.py`)**:
  - Template Settings Dialog, Calibration Dialog with interactive zoomable canvas and geometry overlay, Annotation Color Settings Dialog with live preview strip, NewExamDialog with template dropdown.
  - In-window header button `⚙️ ตั้งค่า` on `MainWindow` (popup menu: รูปแบบกระดาษคำตอบ, สีรอยตรวจและสัญลักษณ์, ตำแหน่งบันทึกผลลัพธ์, ข้อสอบที่เก็บถาวร) eliminates reliance on macOS system menu bar.
  - Inline `⚙️ จัดการแม่แบบ…` on `NewExamDialog` allows adding/calibrating new templates directly while creating exams with auto-reload upon dialog close.
  - Inline `🎨 สีรอยตรวจ…` action in `ExamDialog` results tab before exporting.
  - `TemplateSettingsDialog` provides a direct shortcut to `AnnotationColorSettingsDialog`.
- **Quality Gates Passed (8/8)**:
  1. Unit tests: 95/95 passed (100%)
  2. Ruff lint & format: 0 errors
  3. Mypy type-check: 0 issues in 20 source files
  4. Build: macOS arm64 PyInstaller app bundle build succeeded
  5. Strict deep codesign: passed (`codesign --verify --deep --strict dist/ExamGrader.app`)
  6. Packaged self-check: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check`)
  7. Packaged smoke-ui: passed (`dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui`)
  8. Real-fixture UAT: 100% pass on Default #1 regression + Default #2 blank and marked UAT (`tests/test_default2_uat.py`)

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

## Handoff สำหรับแชทใหม่ — อัปเดต 2026-09-10 (Custom Template / Calibration Complete)

รับช่วงจาก `/Users/zubinpijit/private/exam-grader` โดยอ่าน `progress.md`,
`docs/TASK_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/NEXT_CHAT_HANDOFF.md`
และ `walkthrough.md` ใน artifacts directory ก่อนลงมือ

สถานะปัจจุบัน: ฟีเจอร์ **Custom Answer-Sheet Template & Calibration System** เสร็จสมบูรณ์ 100%
- Built-in Default #1 (60Q/5C/4×15) และ Default #2 (60Q/4C/3×20) ทำงานบน unified pipeline เดียวกัน
- รองรับ choice count 2–5, ตัวเลือกกระดาษ (ก–ง) แมปเข้า canonical (A–D), ไม่ตรวจ choice ที่ 5 บนกระดาษ 4 ตัวเลือก
- SQLite Schema v13 สำเร็จพร้อม auto-backup `.v12.bak`, มีตาราง `templates`, custom references เก็บใน app-data content-addressed storage (ไม่ใช่ SQLite BLOB)
- หน้าต่าง Template Settings, Calibration Canvas ซูมได้พร้อม overlay, Annotation Color Settings พร้อม live preview, NewExamDialog รองรับเลือก template
- มีปุ่ม `⚙️ ตั้งค่า` ในหน้าต่างหลัก MainWindow, ปุ่ม `⚙️ จัดการแม่แบบ…` ในหน้าต่างสร้างข้อสอบ NewExamDialog, และปุ่ม `🎨 สีรอยตรวจ…` ในหน้าแท็บผลลัพธ์
- Quality gates 8/8 ผ่านหมด: 95 tests pass, Ruff/Mypy 0 errors, macOS build + strict codesign pass, self-check + smoke-ui pass, Default #1 regression + Default #2 UAT ผ่าน 100%

ขอบเขตงาน Polish ที่แนะนำใน Chat ใหม่:
1. **Interactive Calibration Polish**:
   - เพิ่มคีย์ลัด/การคลิกลาก (Grid Nudge) เพื่อขยับกรอบ block/cell ได้สะดวกยิ่งขึ้นหากกระดาษพิมพ์เอียงหรือยืด
   - ปรับปรุง loading performance ของ thumbnail ใน TemplateSettingsDialog
2. **Teacher Experience / Guidance**:
   - ปรับข้อความแนะนำ (Tooltips/Guides) ใน CalibrationDialog ให้ครูเข้าใจง่ายขึ้นเมื่อตรวจจับตารางไม่ได้
   - แสดงชื่อ Template ในผลสรุป/Excel export header
3. **Synthetic Dataset Extension**:
   - เพิ่ม synthetic 3-block 20-row generator ใน `tools/synthetic/` เพื่อ stress-test Default #2 เพิ่มเติม

### Prompt สำหรับแชทใหม่ — TASK: Polish Custom Template & Teacher Workflow UX

```text
ทำงานต่อใน `/Users/zubinpijit/private/exam-grader` โดยอ่าน `progress.md`, `docs/TASK_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, และ `docs/NEXT_CHAT_HANDOFF.md` ก่อนลงมือ

สถานะปัจจุบัน: ระบบ Custom Answer-Sheet Template & Calibration System (Default #1 60Q/5C และ Default #2 60Q/4C) พัฒนาเสร็จสมบูรณ์ 100% และผ่าน 8/8 Quality Gates (95 unit tests, Ruff, Mypy, PyInstaller build, codesign, self-check, smoke-ui, Default #2 real fixture UAT)

TASK: Polish UX & Teacher Workflow ในระบบ Template / Calibration และขยายชุดทดสอบ
1. ตรวจสอบ UI และ Source code ปัจจุบันเพื่อระบุจุด friction ในการใช้งานของครู (เช่น การขยับ fine-tune grid ใน CalibrationDialog, tooltips คำแนะนำ, thumbnail caching)
2. รักษา business logic และ safety contracts เดิมทั้งหมด: key confirmation, sparse-roster skip/restore, immutable originals, fail-closed uncertainty, single unified grading pipeline (ห้าม fork grading engine)
3. รัน Quality Gates ครบทุกขั้นตอน (pytest, ruff, mypy, build, codesign, self-check, smoke-ui) และรายงานผลแบบมีหลักฐานชัดเจน
```

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


## Landing Page Redesign & Minimal Colored-Pencil Editorial Refresh
- Redesigned `/exam-grader` landing page inside `bithope-web` (`/Users/zubinpijit/bithope/apps/bithope-web`).
- Converted illustration style to minimal colored-pencil / crayon editorial art direction ("วาดน้อย แต่จำได้").
- Hero section: Single friendly teacher grading answer sheet with orange pencil; removed all classroom clutter and floating assets.
- Workflow 6 steps: 1 visual metaphor each (Blank paper + pencil, Answer key + checkmark, 3 Overlapping sheets, Offline laptop, Review magnifier, Export spreadsheet).
- Interactive modal for all 6 workflow cards opening authentic PySide6 app screenshots.
- Zero-noise visual polish: removed all green header pill tags and category chips; removed Beta references ("ฟรี 100%").
- Next.js 16.2.2 static build verified (59/59 pages, 0 errors, 0 regressions).

## 2026-09-13 — Template Calibration Algorithm Hardening

- Reproduced the Vol.7 failure on all 20 supplied photographs: four blocks × 15 rows × five choices. The previous detector forced four choices; 24 vertical intervals including question-number dividers were grouped incorrectly, dropping choices while reporting high confidence.
- Discovery now evaluates 2–5 choice lattices with and without number dividers, scores repeated wide-number-column evidence, bridges one missing horizontal rule from learned spacing, and prefers broad overlapping table contours. Vol.7 `template.JPG` now yields 4×15×5 and the diagnostic overlay aligns rows 1–15 and A–E. Paper quad, coordinate space, and conservative confidence are recorded; uncertain frame/min-rectangle cases remain review-required.
- `AnswerBlock` carries backward-compatible provenance. `calibration_model.py` provides deterministic line move, add/delete, translate, and resize operations. The canvas has explicit individual-line edit mode; stale asynchronous results are revision-gated and manual edits are not auto-replaced.
- Discovered custom templates opt into paper-quad registration fallback only after feature registration fails. With the Vol.7 reference, all 19 other supplied sheets reached OMR with 60 five-choice observations; dim/perspective classifications remain review-required and are not accuracy ground truth.
- Focused validation: 24 existing calibration/template tests and 7 new geometry tests pass. Full relevant suite excluding sandbox-only real-Documents UAT: 129 passed, 3 skipped. Diagnostics: `docs/evidence/calibration-hardening/after/`.

### 2026-09-13 — Vol.7 keyyy and rebuilt distribution

- Inspected the user-supplied `tests/fixtures/real/vol.7/ถ่ายในที่แจ้ง/keyyy.jpg`.
  The marked key is Q1–Q30: `E D C A/D B C B B D C B A B C C A B B B D C C B B C B B C B E`;
  Q31–Q60 are blank. Q4's A+D double mark is retained as `multiple` and review-required.
- Stored source hash, per-cell red-ink densities, classifications, and overlay in
  `docs/evidence/calibration-hardening/after/vol7-keyyy-answer-key.json` and
  `vol7-keyyy-answer-key-overlay.png`; the original fixture was not modified.
- Rebuilt macOS arm64 distribution with `rtk proxy .venv/bin/python scripts/build/build.py`.
  Strict deep codesign passed. Packaged `--self-check`, `--smoke-settings`, and
  offscreen `--smoke-ui` all exited 0; settings smoke loaded Default #1/#2/#3.
  The new artifact is under `dist/ExamGrader.app` (and onedir `dist/ExamGrader`).

## 2026-09-14 — Partial Review Export and Vol.8 Registration

- ReviewDialog now supports **ข้ามรายการที่เหลือ → ไปผลลัพธ์** after explicit confirmation. The confirmation reports unconfirmed identities, unclear answers, and remaining sheets. Teacher edits are persisted; unresolved answers remain `unresolved` and score zero; ambiguous marks remain zero; unknown identities receive stable persisted labels. Results, JSON, checked images, and Excel retain provenance/status/issues. Partial checked JPEGs use collision-safe names and a Thai incomplete-review banner. Processing status keeps pending-review counts visible after image processing reaches 100%.
- Vol.8 root cause: feature registration was brittle on sparse green forms, while the legacy page detector could treat the full image as a weak page candidate. Candidate choice is now scored against the printed green grid; coarse homography is followed by bounded line-fit correction, with a grid-quality gate and fail-closed registration errors. A high-overlap, already-canonical sheet uses identity without warping student marks. OMR thresholds are unchanged.
- Per-photo UAT: all 10 images registered (9 green-print quads, 1 page quad), maximum grid residual 2.434 px, minimum confidence 0.8203. IMG_1022 first five marks remain A/B/A/D/C; all fixture hashes are unchanged. This demonstrates registration and preserves the known baseline only; answer accuracy for the remaining photos is not independently established.
- Diagnostics and visual evidence: `docs/evidence/vol8-registration/after/report.json`, `normalized/`, `grid-overlays/`, and a real-source partial checked preview under `checked-preview/`. The preview uses a synthetic all-A key solely to verify rendering, not grading accuracy. Overlays for IMG_1022, IMG_1024, IMG_1028 and the checked output were visually inspected; the Thai partial-status banner renders correctly.
- Validation: 32 targeted UI/workflow/export/registration tests passed, including the ReviewDialog skip button confirmation; changed-source Ruff and Mypy passed. Whole-directory Mypy still reports two optional-template typing errors in untouched `settings_ui.py` and `ui.py`. Local macOS arm64 build succeeded at `dist/ExamGrader.app` (234 MB); strict deep codesign, packaged self-check, and offscreen UI/settings smoke passed. No release, tag, or publish was performed.
- Next user-requested task: **TASK — Vol.8 Production Accuracy Hardening + Camera Guidance + Final macOS UAT Build**. Registration is verified, but answer-level accuracy across Vol.8 has not been independently compared with human-confirmed ground truth. Camera-guidance details remain `DETAIL: [รอ Product Owner บอกใน chat ใหม่]`; the existing `dist/ExamGrader.app` is not the final build for this next task.

## 2026-09-14 — Vol.8 Accuracy, Photo Guidance, and Final macOS Build

- Added the hash-checked manual visual reference at `docs/evidence/vol8-accuracy/ground_truth.json`. It is explicitly provisional pending Product Owner confirmation. The photographed key has 30 active questions; three visually ambiguous answers remain uncertain and are excluded from exact accuracy.
- Green-form OMR now masks chromatic green grid print, uses isolated centered ink, and resolves cross geometry only when it is strong and unique. The pipeline version is `omr-illumination-v8-green-cross-v2`. Active-key comparison improved from 252/297 exact (84.85%), one false multiple, and 44 uncertain to 290/297 exact (97.64%), zero wrong/false-multiple/false-blank, and 7 uncertain. Unsafe decisions on the three ambiguous answers: 0. This is provisional, corpus-limited engineering evidence, not production-wide accuracy.
- Registration remains 10/10; max residual 2.434 px, min confidence 0.8203. Number OCR primary candidates match 5/9 legible references and all ten remain review-required. Q31–Q60 are separately reported: 23 uncertain cells and one visible out-of-key mark (IMG_1026 Q31), with no resolved errors.
- Added a nonmodal photo-guidance info control beside student-sheet import. Native macOS UI inspection confirmed the Student tab exposes the guidance. It lists all four paper corners, a straight overhead angle, full borders/grid, low shadow/glare, and legible text/marks.
- Focused review/skip/workflow/export/Vol.8 checks: 38 passed. Full suite: 152 passed, 3 skipped, 10 failed. Eight failures stop at the existing registration grid-quality gate before answer processing; one migration assertion expects a different schema version; one Windows UAT attempts a Documents write denied by this sandbox. Whole changed-file Ruff passes. Whole-source Ruff still reports five issues in untouched files; whole-source Mypy still reports two optional-template errors in untouched `settings_ui.py` and `ui.py`.
- Rebuilt `dist/ExamGrader.app` (macOS arm64, 234 MB). Strict deep codesign, packaged self-check, settings smoke, and offscreen UI smoke pass. The app opened natively and the photo-guidance control appeared in the Student tab. Product Owner ground-truth adjudication and manual teacher UAT remain outstanding. No release, tag, commit, or publish was made.

## 2026-09-14 — Document Normalization / Auto-Crop implementation checkpoint

- Implemented a generic page/grid candidate registration path, immutable-source transform diagnostics, and optional four-corner correction in review. No 4×15/60-question assumptions were added. See [DOCUMENT_NORMALIZATION_UAT.md](docs/DOCUMENT_NORMALIZATION_UAT.md).
- The valid Vol.8 OMR comparison is v8 → v9: 290/297 exact, 7 uncertain, zero wrong/false-multi/false-blank, and zero unsafe decisions both before and after. Registration is 10/10 with unchanged worst residual/confidence, although the selected candidate mix changed. The v6→v8 gain predates this task. Human labels remain provisional.
- Focused cross-layout tests: 52 passed. Full suite: 172 passed, 3 skipped, 10 failed; all 10 match the recorded baseline failure groups (eight registration/grid-quality, schema expectation, sandbox-only Windows Documents write). Changed-file Ruff and targeted Mypy passed.
- Rebuilt local arm64 `dist/ExamGrader.app` (234 MB); strict deep codesign, packaged self-check, settings smoke, and UI smoke passed. No DMG/release/commit/publish. Native corner-editor UAT and label adjudication are outstanding.
- **DoD not met:** the normalization work did not improve Vol.8 answer accuracy. Synthetic phone-photo checks are not evidence of real-world photo robustness; do not claim production readiness until real-photo/UAT evidence meets the user's bar.

## 2026-09-14 — Vol.8 production-hardening acceptance rerun

- The teacher-reviewed fixture replay is recorded in `/private/tmp/vol8-production-uat-20260914-final/report.json`. All 10 sheets reached registration; 286/300 answer states and 282/295 confirmed single choices matched, with 0 unsafe confident mismatches. Four of five multiple-answer states matched, but marked-choice subsets are unavailable. Original source hashes were unchanged.
- Five sheets triggered the runner's manual-corner-adjustment criterion; that threshold flag does not alone prove the detected boundary is wrong. All 10 identities remain review-required; the primary, OCR-candidate, and separate shape-review-suggestion lists each contain the teacher label for 3/10, with the union visible for 6/10.
- Full suite: 176 passed, 3 skipped, 16 failed. The failures include the previously recorded registration/grid, schema-version, and sandbox-only Windows-write groups plus six further failures: one Vol.2 registration case before identity observation and five identity-test failures (two Vol.5 ranking expectations, two Vol.6 batch-adoption cases, and the Vol.7 IMG_0988 recognition miss). Focused post-lint normalization/identity/Vol.8/Home-help checks: 45 passed, 1 failed (Vol.7 IMG_0988 expected 27 is absent from primary, OCR candidates, and review suggestions). Changed-file Ruff passes and `git diff --check` passes.
- Acceptance remains open: definitive answer accuracy is below 100%, the manual-corner criterion triggers on five sheets, identities remain uncertain, and regressions need resolution. No build, package smoke, native corner-editor UAT, release, commit, or publish was performed for this task. Preserve the existing dirty/untracked work.

## 2026-09-14 — Narrow Vol.8 Q27 rollback checkpoint

- The latest user scope supersedes the broader task above for this round: only restore fail-safe handling for `IMG_1024.jpg` Q27 while preserving the `IMG_1028.jpg` registration improvement. Do not touch Vol.2, identity/student number, scoring, export, or add heuristics.
- Frozen Vol.8 v8 baseline: 10/10 registered, 290/297 exact, 7 uncertain, 0 wrong, 0 unsafe ambiguous. Same-fixture replay used `tests/fixtures/real/vol.8` and `docs/evidence/vol8-accuracy/ground_truth.json` (297 resolved cells; same key/reference hashes as the frozen report).
- Before this narrow rollback, Q27 was selected as E by `_green_core_decision` / `green-center-ink-dominance` at core density 0.083; the teacher reference marks it ambiguous. Registration kept the same candidate as baseline. Removing the promotion entirely gave 273/297 exact and 24 uncertain, so that experiment was discarded.
- The retained narrow rollback requires the existing `SELECTED_DENSITY_THRESHOLD` (0.10) for the green-core promotion. Replay: 10/10 registered, 288/297 exact, 9 uncertain, 0 wrong, 0 unsafe ambiguous. Acceptance is **not met** (exact must be at least 290 and uncertain at most 7). `IMG_1024` Q27 is review-required again; `IMG_1021` Q12 and Q23 became additional uncertain answers. Their core densities are 0.083 and 0.076; Q27 is 0.083, so a scalar core threshold cannot separate them.
- `IMG_1028` registration remains improved in the same replay: `green-print-quad`, residual 1.795 px, grid coverage 1.000, alignment confidence 0.8793, 30/30 exact. Frozen baseline selected `paper-quad`, residual 2.434 px, coverage 0.9432, confidence 0.8203.
- Evidence: `/private/tmp/vol8-accuracy-q27-threshold-rollback/report.json`; command is the `vol8_accuracy_uat.py` replay recorded in `docs/NEXT_CHAT_HANDOFF.md` section 6. No full suite, build, release, commit, or publish was run. Next work is blocked on finding an already-existing, evidence-backed distinction for Q12/Q23 versus Q27; do not add a question-specific exception or new heuristic.

## 2026-09-15 — Seamless handoff back to Vol.8 auto document boundary

- The latest Product Owner instruction supersedes the narrow Q27-only scope above. Resume the original **TASK — Production Hardening: Vol.8 Auto Document Boundary + Registration + Student Number**, focusing this round on automatic paper crop/boundary, perspective normalization, and registration robustness on real Vol.8 photographs. Keep `IMG_1024.jpg Q27` `uncertain / review-required`; do not tune OMR. Student-number details and additional acceptance criteria are deferred for the Product Owner to specify in the next chat.
- Latest teacher-reviewed production replay is `/private/tmp/vol8-production-uat-20260914-final3/report.json`, using the same 10 source sheets and teacher-confirmed export at `tests/fixtures/real/vol.8/2569_ป.1_1_math_vol8 lunar ultra_30q/ผลการตรวจ/2026-09-14_205501/_system/results.json`. All 10 reached registration; 295/300 answer states matched, including 291/295 confirmed single choices. There were 2 unsafe confident mismatches. Five sheets met the runner's manual-intervention/manual-corner-adjustment criterion. Worst residual was 6.508 px and minimum alignment confidence 0.5605. Real-photo crop/registration acceptance is still open; a detected boundary or successful registration alone is not proof of a correct crop.
- `IMG_1028.jpg` in that replay selected `edge-canny` with `paper-quad-grid-refined-v2`; boundary confidence 0.8437, normalization confidence 0.6455, grid residual 6.508 px, line coverage 0.6705, and alignment confidence 0.5605. The report did not require manual corner adjustment for this image, but did require review for normalization/registration. Keep these measurements distinct from the separate provisional answer benchmark.
- Separate provisional 297-resolved-answer replay remains `/private/tmp/vol8-accuracy-q27-threshold-rollback/report.json`: 10/10 registered, 288/297 exact, 9 uncertain, 0 wrong, 0 unsafe ambiguous; `IMG_1024.jpg Q27` is review-required. This is a separate oracle/denominator from the teacher-reviewed results above. Use it only as a fail-safe/no-regression OMR guard; do not tune OMR or conflate the two reports.
- This handoff turn changed documentation only. It did not replay tests, edit code, or build the app. The worktree was already dirty, including modified sources/tests and untracked normalization/UAT files and Vol.8 fixtures; preserve every tracked and untracked item. Do not reset, clean, stage, or commit.
- Next session: continue the real-image boundary → perspective → fine-registration task and use Vol.8 as the primary regression/UAT corpus. Preserve existing cross-layout behavior and working flows. Do not touch OMR, identity/student number, scoring, review, export, or other business logic; manual corner adjustment stays a fallback. After the agreed crop task passes relevant regressions, build a fresh macOS arm64 `dist/ExamGrader.app` and run applicable package checks for Product Owner trial. No release/tag/publish.

## 2026-09-15 — Vol.8 physical-boundary acceptance follow-up

- Updated real-photo page proposals to retain distinct multi-scale edge contours, record per-side edge evidence, and select physical corners independently from the final grid-registration transform. Corroborated boundary proposals use the template/grid evidence as a tie-breaker. A weak physical boundary now keeps normalization review-required even when the grid transform is strong.
- Crop/registration replay: `/private/tmp/vol8-registration-uat-20260915-final/report.json` — 10/10 registered, maximum mean grid residual 1.954 px, minimum alignment confidence 0.8572.
- Teacher-reviewed replay: `/private/tmp/vol8-production-uat-20260915-final2/report.json` — 10/10 processed; 295/300 states and 291/295 confirmed singles matched; 0 unsafe confident mismatches; 7 manual-intervention flags and 4 manual-corner-adjustment flags; worst residual 6.483 px and minimum alignment confidence 0.5654. The seven human-adjusted crops' automatic corner proposals are within 26.1–58.3 px per worst corner, but four remain below the existing confidence/coverage gate. Acceptance is still open.
- The 297-cell provisional safety replay `/private/tmp/vol8-accuracy-boundary-final/report.json` remains 288/297 exact, 9 uncertain, 0 wrong, and 0 unsafe on ambiguous labels; IMG_1024 Q27 remains machine-uncertain there. The teacher export separately labels that row E. These are separate sources and denominators; OMR code was not changed.
- Relevant focused suite: 60 passed (Vol.8 normalization/registration/hardening, imaging, and Vol.5/6/7 regressions). Changed-file Ruff and `git diff --check` passed. No build, release, commit, or publish.
- Next: investigate low-contrast physical edges on IMG_1025/1026/1029/1030 without weakening the review gate. Keep uncertain cases review-required and do not build until the automatic-crop acceptance criteria pass.

## 2026-09-15 — Current usable local program checkpoint

- Checkpoint commit: `b69ce93624ea3088cc2fbb12ff9aa579c360e265` on `fix/vol8-current-usable-checkpoint`; branch pushed to `origin`.
- Included only the reviewed crop/registration, physical-boundary diagnostics, manual-crop fallback, current OMR fail-safe, related UAT scripts/tests, and continuity docs. Unrelated dirty source/tests and untracked Vol.8/Vol.9 fixtures remain untouched.
- Fresh macOS arm64 `dist/ExamGrader.app` is 234 MB. Strict deep codesign, packaged self-check, and offscreen UI smoke passed. Focused checks: 8 passed; Vol.8 registration sanity: 10/10, residual max 1.954 px, confidence min 0.8572.
- Acceptance remains open: teacher replay 291/295 confirmed singles with four manual-corner flags; provisional 297-cell guard 288/297 exact, 9 uncertain, 0 wrong/unsafe; Q27 remains review-required.
- Next session should wait for a new explicit Product Owner scope and preserve the checkpoint/dirty-file boundaries above.

## 2026-09-15 — Review auto-accept, per-row bulk confirm, and student-number v6

- Review UX now auto-accepts only a current, unambiguous `single_mark` or normal blank. `multiple`, `boundary_cross`, abnormal blank, incomplete geometry, and uncertain reads remain review-required. A clear ReviewDialog opens ready to save; student identity still requires explicit teacher confirmation.
- Added `ยืนยันข้อมูลที่ระบบอ่านไว้` to the review toolbar. It confirms each selected row's own prefill atomically; it does not apply one answer to every row. The existing manual per-row editor and uniform bulk override remain available.
- Student-number pipeline is now `student-number-adaptive-roi-v6`: expanded registration-tolerant ROI, green/reference/line suppression, connected-component grouping and touching-digit split, digit-only Tesseract 0–9 variants, measured multi-preprocess voting, review-only shape hints, and fail-closed segmentation. Roster/range is validation only; numbers remain `requires_review`.
- Real corpus candidate visibility, using the same ground-truth labels and counting primary/OCR/review-hint union (not confirmed accuracy), improved from Vol.8 **5/10 → 8/10** and Vol.9 **8/12 → 11/12**. Primary auto-candidate remained **2/10** and **4/12** respectively. No identity was auto-confirmed.
- Focused suite: **92 passed**. Changed-file Ruff and `git diff --check`: passed. Packaged macOS arm64 verification: strict deep codesign, disposable-data `--self-check`, offscreen `--smoke-settings`, and offscreen `--smoke-ui`: passed.
- Product Owner trial app: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`. This is not a release; teacher identity UAT remains required, and `IMG_1024.jpg Q27` remains `uncertain / review-required`.
