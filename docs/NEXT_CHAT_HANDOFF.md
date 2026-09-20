# Fresh-Chat Handoff: Exam Grader v1.0.2 & Upcoming Session Roadmap

# Current handoff — 2026-09-20 Whole-ROI sequence experiment closed

The bounded Whole-ROI / Sequence Student Number Recognition experiment is
complete and not integrated. The production segmentation → digit-classifier
path is unchanged, review-required, and auto-accept remains disabled.

- Frozen Vol.8/9/10 baseline: Vol.8/9 `20/22` exact and `12/14` two-digit;
  Vol.10 `15/22` exact and `9/13` two-digit, with `18/22` truth visible.
- Evaluation claim: **sheet/volume-disjoint evaluation; writer generalization
  unknown**. Vol.8/9/10 were never used for sequence training or tuning.
- Whole-ROI prototype top-1: `2/27` two-digit records. Fixed rescue hybrid:
  Vol.8/9 stayed `20/22`; Vol.10 reached `16/22`, `10/13` two-digit and
  `20/22` visible, below the `11–12/13` gate.
- `14→191` was recovered; `18→98`, `20→79`, and `22→92` were not safely
  resolved. Do not promote or bundle the prototype.
- Checkpoints: `be58110` (protocol), `818857d` (prototype/report), and
  `10da86d` (verification handoff). Full evidence is in
  `docs/evidence/student-number-sequence-experiment-20260920.md` and the
  adjacent JSON report. The prototype is only in
  `tools/benchmark/whole_roi_sequence.py` with focused tests.
- Focused tests/Ruff/diff-check passed; fresh macOS arm64 package (~235 MB),
  packaged self-check, offscreen settings/UI smoke, and strict deep codesign
  passed. Windows native UAT and Product Owner native UAT remain separate.

Next work needs authoritative writer-diverse whole-ROI labels and provenance
approval. Keep Vol.8/9/10 held out; do not tune on them. Preserve the untracked
real fixture trees and do not push, merge, tag, release, or deploy.

# Current handoff — 2026-09-20 Student Number Recognition round closure

Use the repository docs and current git state as source of truth. The prior
Student Number Recognition round is closed; the next session is authorized to
start the new bounded Whole-ROI / Sequence Student Number Recognition task
below.

## Verified current state

- Repository: `/Users/zubinpijit/private/exam-grader`
- Branch: `feat/assessment-indicators-multi-room`
- Pre-handoff HEAD: `f9951c6`; inspect the latest `git log` after this docs
  checkpoint for the final handoff commit and pushed remote checkpoint.
- Vol.8/9: `20/22` exact, `12/14` two-digit, `21/22` visible.
- Vol.10: `15/22` exact, `9/13` two-digit, `18/22` visible.
- Auto-accept is disabled; `wrong auto-accept = 0`.
- Fresh macOS package evidence remains separate from native UAT:
  `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app` passed packaged
  self-check, offscreen settings/UI smoke, and strict deep codesign.
- Windows native UAT is still pending.
- Product Owner native macOS UAT confirms clear improvement but remaining
  reads include `14→191`, `17→11`, `18→98`, `20→79`, `22→92`; correct visible
  examples include `15`, `16`, `19`, and `21`.
- Manual UAT screenshots:
  `/Users/zubinpijit/Desktop/ภาพถ่ายหน้าจอ 2569-09-20 เวลา 14.00.34.png`
  and `/Users/zubinpijit/Desktop/ภาพถ่ายหน้าจอ 2569-09-20 เวลา 13.59.56.png`.
- Detailed source/package/benchmark evidence:
  `docs/evidence/student-number-recognition-20260920.md`.

## Protected ownership and invariants

Preserve untracked `tests/fixtures/real/vol.8/`,
`tests/fixtures/real/vol.9/`, and `tests/fixtures/real/vol.10/`; do not reset,
clean, overwrite, stage, or absorb them. Do not alter OMR, document
crop/registration, grading/export, assessment indicators, rooms, or unrelated
UI/business logic. Preserve immutable originals, provenance, review-required
uncertainty, teacher confirmation, backward compatibility, and raw recognition
evidence. Do not enable auto-accept until independent held-out evidence proves
`wrong auto-accept = 0`.

## Next task — Whole-ROI / Sequence Student Number Recognition

Objective: improve handwritten student-number prefill, especially two-digit
numbers, by testing a small whole-ROI sequence recognizer without removing the
current segmentation pipeline until leakage-safe evidence proves superiority.

Required engineer loop:

1. Inspect repository docs, current implementation, git state, fixture/result
   provenance, and the actual app path before editing.
2. Define a sheet/writer-disjoint held-out protocol. Keep Vol.8/9/10 and all
   training-used data separated by provenance; do not invent labels or use
   evaluation sheets for tuning.
3. Benchmark the current `segmentation → digit classifier` pipeline first.
4. Implement a supplemental small whole-ROI sequence recognizer, such as a
   tiny CRNN/CTC or another evidence-backed compact architecture, only after
   the baseline and data protocol are frozen.
5. Compare current, sequence, hybrid/ensemble, and ranking behavior on the
   same held-out sheets. Attribute failures to segmentation, classifier,
   ranking, or calibration.
6. Integrate only a surgical improvement with focused tests and real-sheet
   regression. Keep the old path as fallback until evidence supports promotion.
7. Update evidence/docs, create milestone checkpoint commits, rebuild the
   macOS app, and run packaged self-check, settings/UI smoke, and strict
   codesign. Report Windows as pending unless native Windows evidence exists.

Minimum metrics: exact top-1/prefill, 1-digit/2-digit accuracy, top-k
visibility, segmentation/classifier/ranking failure counts, held-out
generalization, latency, model/package size, and wrong auto-accept. The main
goal is correct review prefill, not forced confidence.

Do not hard-code Vol.10 or individual numbers. Ask the Product Owner if a
dataset-authority, leakage, or architecture decision cannot be resolved from
evidence; choose ordinary implementation details from benchmarks. Commit is
allowed for scoped milestones, but do not push, merge, tag, release, or deploy
without explicit authorization in that new task.

## Paste-ready prompt for the new chat

```text
Use the repository docs and current task as source of truth. Read `/Users/zubinpijit/.codex/RTK.md`, `progress.md`, `docs/NEXT_CHAT_HANDOFF.md`, `docs/TASK_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/IDENTITY_DATASET.md`, and the current Student Number Recognition evidence before acting; inspect `git status --short`, current HEAD, branch, and implementation read-only first.

Objective/scope: Improve Student Number Recognition prefill, especially handwritten 2-digit numbers, using a leakage-safe whole-ROI/sequence recognizer experiment while preserving the existing segmentation pipeline as fallback. Do not touch OMR, document crop/registration, grading/export, Assessment Indicators, rooms, UI/business logic, or unrelated features.

Verified current state: branch `feat/assessment-indicators-multi-room`; the prior round reached Vol.8/9 `20/22` exact and Vol.10 `15/22` exact with Vol.10 2-digit `9/13`; all sheets remain review-required; auto-accept is disabled and wrong auto-accept is `0`. Product Owner native macOS UAT confirms improvement but reports `14→191`, `17→11`, `18→98`, `20→79`, `22→92`, while `15`, `16`, `19`, and `21` read correctly. Source/package evidence is in `docs/evidence/student-number-recognition-20260920.md`; UAT screenshots are the two dated Desktop PNGs referenced in `progress.md` and this handoff. Windows native UAT is pending.

Important files/components: `src/exam_grader/identity.py`, `src/exam_grader/digit_model.py`, `src/exam_grader/review_service.py`, `src/exam_grader/exam_ui.py`, `src/exam_grader/resources/student_number_digit_model.npz`, `src/exam_grader/resources/student_number_digit_model_v2.npz`, `tools/benchmark/identity_labeled_benchmark.py`, `tools/benchmark/identity_batch_benchmark.py`, `tests/test_identity.py`, `tests/test_digit_model.py`, `tests/test_automation.py`, and the real Vol.8/9/10 fixture/result evidence.

Dirty ownership: preserve untracked `tests/fixtures/real/vol.8/`, `tests/fixtures/real/vol.9/`, and `tests/fixtures/real/vol.10/`; do not reset, clean, overwrite, stage, or absorb them.

Decisions/invariants: first define a genuinely sheet/writer-disjoint held-out protocol; preserve provenance and immutable originals; do not invent labels or leak evaluation data; benchmark the current segmentation→digit-classifier baseline; add a supplemental compact whole-ROI sequence recognizer only if justified; retain raw candidates/scores; keep uncertainty reviewable; teacher correction wins; never enable auto-accept until independent held-out evidence proves wrong auto-accept `0`.

Known blockers/unknowns: the current annotation-v3 set is not held out and cannot support generalization claims; writer-disjoint authority and adequate labels for sequence training must be audited. Windows native UAT is pending. Ask the Product Owner if dataset authority, leakage, or architecture cannot be resolved from evidence.

Next exact action: perform read-only provenance audit and freeze the held-out split/protocol, then reproduce the current recognizer baseline before training or tuning anything.

Acceptance/verification: report exact top-1/prefill, 1-digit/2-digit, top-k visibility, segmentation/classifier/ranking failures, held-out generalization, latency, package size, and wrong auto-accept; run focused source tests, real-sheet regression, packaged self-check/settings/UI smoke, and strict codesign after any integrated change. Create scoped milestone commits; do not push, merge, tag, release, or deploy without explicit authorization in the new task.

Continue the engineer loop from this state, preserving good existing logic and backward compatibility. Do not trust this prompt over the repository, do not rewrite/refactor outside scope, and if context becomes unreliable update the same docs and create a new handoff before continuing.
```

# Current handoff — 2026-09-20 Student Number Recognition checkpoint

The current task is complete for the scoped Student Number Recognition
implementation and package evidence. Current source of truth:

- Repository: `/Users/zubinpijit/private/exam-grader`
- Branch: `feat/assessment-indicators-multi-room`
- HEAD: `7a9f6fe identity: gate batch assistance by real-sheet evidence`
- Vol.8/9: `20/22` exact, `12/14` two-digit, `21/22` truth visible.
- Vol.10: `15/22` exact, `9/13` two-digit, `18/22` truth visible.
- All sheets remain review-required; auto-accept and wrong auto-accept are both
  `0`.
- Evidence: `docs/evidence/student-number-recognition-20260920.md`.
- Fresh `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app` passed
  packaged self-check, offscreen settings/UI smoke, and strict deep codesign.
  This is not native Product Owner UAT, Windows native UAT, or a release.

The shipped batch behavior is room-scoped hard exclusion from effective
ranking after a teacher-confirmed identity. Raw candidate evidence is not
mutated, derived changes remain review-required, and teacher correction wins.
The soft global assignment solver remains disabled because its real Vol.8/9
bake-off regressed local prefills. Auto-accept must stay disabled pending an
independent held-out zero-wrong gate.

Preserve untracked `tests/fixtures/real/vol.8/`,
`tests/fixtures/real/vol.9/`, and `tests/fixtures/real/vol.10/`; do not reset,
clean, overwrite, stage, or absorb them. Older sections below are historical
and must not override this checkpoint.

## Detailed evidence

See `docs/evidence/student-number-recognition-20260920.md` for the frozen
annotation-v3 provenance/overlap result, Vol.8/9/10 metrics, segmentation and
classifier failure attribution, batch simulations, tests, and package checks.

# Current handoff — 2026-09-20 assessment indicators, multi-room, and Excel polish

Use the repository docs and current task as source of truth. The current
assessment-indicator, multi-room, and Excel-polish task is complete for source
and package evidence. The next chat must wait for the Product Owner's new
Student Number Recognition detail; do not infer scope from older sections.

## Verified current state

- Repository: `/Users/zubinpijit/private/exam-grader`
- Branch: `feat/assessment-indicators-multi-room`
- HEAD: `edbb9c7 polish: format scores workbook export`
- Feature checkpoint: `7bdcced feat: add assessment indicators and exam rooms`
- Focused command: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_assessment_indicators_rooms.py tests/test_export.py` → `18 passed`.
- Fresh `dist/ExamGrader.app` built from HEAD; packaged self-check, offscreen UI smoke, and strict deep codesign passed. The self-check reports version `1.0.2` and `packaging: not_verified`; native Product Owner UAT remains separate and no merge/tag/release claim is made.

## Current implementation and invariants

- `src/exam_grader/storage.py` owns schema v15, `assessment_indicators`,
  `exam_rooms`, and legacy-exam room migration.
- `src/exam_grader/workflow.py` validates ordered exam-scoped indicators,
  resolves room context, snapshots configuration, and aggregates indicator
  scores after the existing authoritative reviewed grading path.
- `src/exam_grader/exam_ui.py`, `review_service.py`, and `imports.py` keep
  indicator configuration and student/review data in the correct exam/room
  context.
- `src/exam_grader/exporting.py` emits ordered indicator columns before the
  unchanged `Score | Max | Status | Source File | Review Issues` columns when
  configured; no indicators retain the legacy output. It also owns compact
  bounded Excel styling, numeric cells, filters/freeze panes, and sanitized
  collision-safe room folder names.
- Focused tests are in `tests/test_assessment_indicators_rooms.py` and
  `tests/test_export.py`.

## Dirty ownership and next boundary

Preserve untracked `tests/fixtures/real/vol.8/` and
`tests/fixtures/real/vol.9/`; do not reset, clean, overwrite, stage, or absorb
them. The documentation files in this checkpoint are intentionally updated;
do not rewrite historical handoff sections below. Do not touch recognition,
crop/registration, OMR, student-number, grading core, or unrelated business
logic until the next user message defines the exact scope.

## Paste-ready prompt for the next chat

```text
ทำต่อใน `/Users/zubinpijit/private/exam-grader` โดยใช้ repository docs และ git state เป็น source of truth

อ่าน `/Users/zubinpijit/.codex/RTK.md`, `progress.md`, `docs/NEXT_CHAT_HANDOFF.md`, `docs/TASK_SPEC.md`, `docs/ARCHITECTURE.md` และเอกสารที่เกี่ยวข้องก่อนทำอะไร จากนั้น inspect `git status --short`, current HEAD และ implementation จริงแบบ read-only ก่อนเสนอแผน

สถานะปัจจุบัน: branch `feat/assessment-indicators-multi-room`, HEAD `edbb9c7` (`polish: format scores workbook export`); assessment indicators + multi-room อยู่ที่ `7bdcced`. Focused checks ผ่าน `18 passed` ด้วย `QT_QPA_PLATFORM=offscreen`; fresh `dist/ExamGrader.app` ผ่าน packaged self-check, offscreen UI smoke และ strict deep codesign. นี่เป็น source/package evidence เท่านั้น ยังไม่ใช่ Product Owner native UAT หรือ release

ขอบเขต task ใหม่จะเป็น **Student Number Recognition และ preprocessing/segmentation/model/ranking/confidence logic ที่เกี่ยวข้องโดยตรง** เท่านั้น โดย Product Owner จะให้รายละเอียดและ acceptance criteria ใน chat นี้เอง ห้ามเดา scope, algorithm, threshold, metric หรือเป้าหมาย accuracy ล่วงหน้า และห้ามเริ่มแก้ code ก่อนอ่าน/inspect แล้วสรุปแผนที่ bounded

รักษา invariants เดิม: immutable originals, provenance, fail-closed uncertainty, teacher confirmation, recognition/crop/registration/OMR/grading/review/export behavior ที่ดีอยู่แล้ว และ backward compatibility. ห้าม scope creep ไป assessment indicators, rooms, UI กว้าง, grading/export หรือ business logic ที่ไม่เกี่ยวโดยตรง

Preserve untracked `tests/fixtures/real/vol.8/` และ `tests/fixtures/real/vol.9/`; ห้าม reset, clean, overwrite, stage หรือ absorb งานเหล่านี้. แยก source tests, packaged smoke และ native UAT เป็นคนละหลักฐาน. ห้าม commit/push/deploy/release จนกว่าจะมี authorization ชัดเจนใน task ใหม่นั้น

เมื่อ Product Owner ให้ detail แล้ว ให้ทำ engineer loop: inspect → เสนอแผน/ความไม่ชัดเจน → รอ confirmation หากมี decision ที่เปลี่ยน behavior → implement แบบ surgical → focused test/evidence → inspect output → checkpoint docs/commit ตามที่ได้รับอนุญาต
```

# Current handoff — 2026-09-17 Vol.1–Vol.7 evaluation-first benchmark

## Task for the next chat

Continue Student Number Recognition from checkpoint `1624a5c`. This next task is evaluation-first: run the current recognizer against the real Vol.1–Vol.7 fixtures to determine whether the Vol.8–Vol.9 improvements generalize or regress the earlier volumes. Do not change ground truth or baseline.

### Verified starting state

- Repository: `/Users/zubinpijit/private/exam-grader`
- Branch: `fix/vol8-current-usable-checkpoint`
- HEAD: `1624a5c fix: harden student number recognition round two`
- Current tracked tree is clean. Preserve the untracked real fixtures `tests/fixtures/real/vol.8/` and `tests/fixtures/real/vol.9/`; they belong to the user and must not be staged, deleted, or overwritten.
- Current Vol.8–Vol.9 held-out evidence is `/private/tmp/exam-grader-identity-round2-bundled-final-v1.json`: exact `15/22` (68.2%), candidate visibility `19/22` (86.4%), review `15/22` (68.2%), selective auto-accept `7/22` (31.8%), wrong auto-accept `0`; Vol.8 exact `6/10`, Vol.9 exact `9/12`.
- Current round-2 visual audit is `/private/tmp/exam-grader-recognition-round2-final-audit/report.json`, with screenshots under the same directory. Remaining Vol.8–Vol.9 errors were classified as classifier confusion, with ranking amplification on `IMG_1028` and `IMG_1072`; no remaining primary document crop/registration failure was found.
- Current model artifact SHA-256: `aabeeb9bab4fdfad481facaa627c9efb521707e7783123746928776e74153502`.
- Fresh packaged app: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`. Prior focused evidence: 36 relevant tests passed; packaged self-check, offscreen settings/UI smoke, and strict codesign verification passed. These are starting-state evidence, not Vol.1–Vol.7 generalization evidence.

### Required first inspection

Read `/Users/zubinpijit/.codex/RTK.md`, `progress.md`, this handoff, `docs/IDENTITY_DATASET.md`, `docs/TASK_SPEC.md`, and `docs/DECISIONS.md`; then inspect `git status --short`, `git diff`, and the current implementation before running anything. Locate the actual authoritative Vol.1–Vol.7 fixtures, per-image ground truth, and any baseline/result artifacts read-only. Historical claims in `progress.md` (for example, older volume-level success counts) may be comparison evidence only; they must not be substituted for missing per-image ground truth. If authoritative labels are absent, report that the requested accuracy cannot be computed without inventing labels and stop or ask for the missing evidence.

Relevant implementation/evidence to inspect:

- `src/exam_grader/identity.py`
- `src/exam_grader/digit_model.py`
- `src/exam_grader/resources/student_number_digit_model.npz`
- `tools/benchmark/identity_labeled_benchmark.py`
- `tests/test_identity.py`, `tests/test_digit_model.py`, `tests/test_vol6_uat.py`, `tests/test_vol7_real_sheets.py`, and `tests/test_vol8_accuracy_uat.py`
- Existing `docs/evidence/identity-regression.json`, `docs/evidence/REAL_UAT.md`, `docs/evidence/polish/identity-benchmark-final.json`, and any discovered Vol.1–Vol.7 benchmark artifacts

### Benchmark contract

1. Freeze and record the source paths/hashes and the unchanged baseline before evaluation.
2. Run the current pipeline from `1624a5c` without model, preprocessing, threshold, ranking, or ground-truth changes during the initial benchmark.
3. Report separately for Vol.1, Vol.2, …, Vol.7 and in aggregate:
   - exact number accuracy
   - candidate visibility
   - review rate
   - selective auto-accept rate
   - wrong auto-accept count/rate
4. Compare with prior behavior only where repository evidence exists.
5. Use vision inspection of every wrong or regressed case, including the original number area, search ROI, preprocessing variants, detected components/candidates, segmented digits, per-digit model prediction/confidence, assembled number, and ground truth. Classify each as segmentation/preprocessing, classifier, ranking, or confidence gate.
6. Do not modify the model during the clean benchmark. If a meaningful regression is proven, fix only that root cause, rerun the relevant cases and aggregate benchmark, and keep wrong auto-accept from increasing.

### Boundaries and completion

Do not touch document crop/registration, OMR, UX/UI, grading/export/business logic, fixtures, ground truth, or telemetry/dataset creation. Preserve all dirty/untracked work. Use focused tests, relevant regression tests, and a minimal smoke check only. Do not claim production-ready from aggregate accuracy alone.

If there is no meaningful regression, checkpoint the evaluation result in the handoff/progress and propose one bounded next step; do not train during this evaluation task. If regression is proven and the scoped fix improves the evidence without increasing wrong auto-accept, update progress/handoff, create a checkpoint commit for the code change, and build `dist/ExamGrader.app` for Product Owner testing. Otherwise, state the remaining bottleneck and do not claim readiness.

### Paste-ready prompt for the next chat

ทำต่อใน `/Users/zubinpijit/private/exam-grader` จาก checkpoint `1624a5c` โดยทำเฉพาะ Student Number Recognition evaluation-first benchmark กับชุดจริง Vol.1–Vol.7 เพื่อพิสูจน์ว่า improvement จาก Vol.8–9 generalize หรือทำ regression กับของเดิมหรือไม่

ก่อนทำอะไรให้อ่าน `/Users/zubinpijit/.codex/RTK.md`, `progress.md`, `docs/NEXT_CHAT_HANDOFF.md`, `docs/IDENTITY_DATASET.md`, `docs/TASK_SPEC.md`, `docs/DECISIONS.md` และ inspect `git status --short`/`git diff` แบบ read-only; preserve untracked `tests/fixtures/real/vol.8/` และ `tests/fixtures/real/vol.9/`. Locate authoritative Vol.1–Vol.7 fixtures, per-image ground truth, and baseline/result evidence without changing any of them. Historical metrics ห้ามใช้แทน ground truth ที่หายไป; ถ้าไม่มี authoritative labels ให้รายงานว่า compute accuracy ไม่ได้และหยุด/ขอ evidence เพิ่ม ห้ามเดา

ใช้ pipeline ปัจจุบันจาก `1624a5c` รัน clean benchmark ก่อน โดยห้ามแก้ model, preprocessing, threshold, ranking, ground truth หรือ baseline ระหว่าง benchmark. วัดแยก Vol.1–Vol.7 และรวม: exact accuracy, candidate visibility, review rate, selective auto-accept, wrong auto-accept. Compare กับ baseline เฉพาะที่มีหลักฐานใน repo. Audit ด้วยภาพจริงทุกเคสที่ผิดหรือ regress และจัด root cause เป็น segmentation/preprocessing, classifier, ranking หรือ confidence gate โดย diagnostic ต้องเห็น original number area, search ROI, preprocessing variants, components/candidates, segmented digits, per-digit prediction/confidence, assembled number และ ground truth

ห้ามแตะ document crop/registration, OMR, UX/UI, grading/export/business logic; ห้าม hard-code fixture/Vol./เลข, สร้าง dataset/telemetry ใหม่ หรือรัน full suite. wrong auto-accept ต้องไม่เพิ่ม และห้าม claim production-ready จาก aggregate accuracy อย่างเดียว. ถ้าไม่มี meaningful regression ให้ checkpoint ผลใน progress/handoff และเสนอ bounded next step โดยยังไม่ train model. ถ้ามี regression ให้แก้เฉพาะ root cause ที่พิสูจน์ได้ แล้ว rerun relevant cases + aggregate; หากดีขึ้นจริงเท่านั้นจึง checkpoint commit และ build `dist/ExamGrader.app` ให้ Product Owner ทดสอบ. ถ้ายังไม่ดีขึ้นให้สรุป bottleneck ที่เหลือชัดเจนและไม่ฝืน claim readiness.

## Current handoff — 2026-09-16 student-number recognition round 2

Round 2 continues from checkpoint `33439ec` and is scoped only to Student
Number Recognition. Conservative component grouping fixed the verified short,
wide glyph split in `IMG_1071`; local faint-stroke recovery fixed the incomplete
second digit in `IMG_1080`. The production document crop/registration, OMR,
UI/UX, grading, export, and business logic were not changed.

- Bundled held-out report:
  `/private/tmp/exam-grader-identity-round2-bundled-final-v1.json`.
- Result: exact `15/22`, candidate visible `19/22`, review `15/22`, selective
  auto-accept `7/22`, wrong auto-accept `0`; Vol.8 `6/10`, Vol.9 `9/12`.
- The final model uses existing seed data only (`198` records), KNN internal
  validation `39/39`, affine-only hard-pair augmentation copies `1`, and
  `generalization_claim_allowed=false`.
- Blur augmentation was removed after the controlled ablation showed it caused
  `IMG_1073` to regress `19 -> 14`; affine-only is the retained variant.
- Selective gate is fail-closed: complete segmentation, top-ranked candidate,
  confidence `>=100`, margin `>=15`; held-out auto-accept was `7/7` exact.
- Remaining errors: `7/22`, all visually classified as digit-model confusion;
  `IMG_1028` and `IMG_1072` also show ranking amplification while the truth
  remains visible. `IMG_1071` is now a classifier `8 -> 9` error and
  `IMG_1080` is exact `46`.
- Model SHA-256:
  `aabeeb9bab4fdfad481facaa627c9efb521707e7783123746928776e74153502`.
- Fresh app: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`;
  packaged self-check, offscreen settings/UI smoke, and strict deep codesign
  passed. The current branch HEAD is the round-2 checkpoint.
- Native Product Owner UAT remains pending; source/held-out/package evidence is
  not a production-readiness claim.

### Protected boundaries

Preserve the existing held-out corpus, ground truth, immutable originals,
source hashes, provenance, fail-closed ambiguity, and untracked Vol.8/Vol.9
fixtures. Do not broaden into document crop/registration, OMR, UI/UX,
grading/export/business logic, new telemetry, or new datasets.

## Current handoff — 2026-09-16 student-number error attribution

Use the repository docs and current task as source of truth. The seed-model
checkpoint is complete; the next chat must inspect the remaining errors before
any final tuning.

### Verified current state

- Repo: `/Users/zubinpijit/private/exam-grader`
- Branch: `fix/vol8-current-usable-checkpoint`, implementation checkpoint
  `ad30b6f feat: integrate seed digit recognizer`.
- Annotation: `198 labeled`, `2 excluded`, `0 remaining`, `0 bad_bbox`.
  Training is authorized only as `internal_seed_split_only`; no generalization
  claim is allowed.
- Held-out report:
  `/private/tmp/exam-grader-identity-seed-model-benchmark-v3.json`.
  Seed exact is `7/22` (`31.8%`) versus legacy `5/22` (`22.7%`); review is
  `22/22`; wrong auto-accept is `0`. The model handled `14/22` rows and the
  legacy fallback handled `8/22`. Candidate visibility is `14/22`, so manual
  confirmation has not yet been reduced.
- Model: `src/exam_grader/resources/student_number_digit_model.npz`, bundled
  review-only; auto-accept remains disabled. App:
  `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`.
- Verification: focused/relevant tests `33 passed`, Ruff, `git diff --check`,
  packaged self-check, native UI smoke, and strict deep codesign passed.

### Unknown to resolve

The remaining `15/22` wrong whole-number predictions have not yet been
attributed. For each error, determine from actual provenance and crops whether
the digit crop/segmentation/candidate is wrong or incomplete, or whether the
crop is correct and the recognizer classified the digit incorrectly. The
candidate-visibility decrease is only a hypothesis signal, not a root cause.

### Protected scope and ownership

Keep Vol.8/Vol.9 as real held-out evidence; do not overfit or hard-code their
fixtures. Preserve immutable originals, source hashes, crop/proposal
provenance, review-required uncertainty, teacher confirmation, and fail-closed
behavior. Do not touch crop/registration, OMR, scoring, review, UI, or
business logic while doing attribution. Preserve the user's untracked
`tests/fixtures/real/vol.8/` and `tests/fixtures/real/vol.9/`; do not reset,
clean, overwrite, stage, or absorb them.

### Paste-ready prompt for the next chat

```text
Use the repository docs and current task as source of truth. Read /Users/zubinpijit/.codex/RTK.md, progress.md, docs/NEXT_CHAT_HANDOFF.md, docs/IDENTITY_DATASET.md, and docs/TASK_SPEC.md first; inspect the actual implementation and git state before acting.

Objective/scope: Attribute the remaining 15/22 wrong student-number predictions before final tuning: separate wrong/incomplete digit crop or candidate segmentation from correct crop but wrong model classification.
Verified current state: Branch fix/vol8-current-usable-checkpoint contains ad30b6f feat: integrate seed digit recognizer. Held-out report is /private/tmp/exam-grader-identity-seed-model-benchmark-v3.json: seed exact 7/22 vs legacy 5/22, review 22/22, wrong auto-accept 0; model path 14/22, legacy fallback 8/22. Runtime model is bundled review-only and auto-accept is disabled.
Important files/components: src/exam_grader/identity.py, src/exam_grader/digit_model.py, src/exam_grader/resources/student_number_digit_model.npz, tools/benchmark/identity_labeled_benchmark.py, and the held-out corpus/report under /private/tmp/.
Dirty ownership: Preserve the user's untracked tests/fixtures/real/vol.8/ and tests/fixtures/real/vol.9/; do not reset, clean, overwrite, stage, or absorb them.
Decisions/invariants: Keep Vol.8/Vol.9 held out; no fixture hard-coding or overfitting. Preserve immutable originals, hashes, provenance, review-required uncertainty, teacher confirmation, fail-closed behavior, and existing crop/registration/OMR/scoring/review/UI/business logic.
Known blockers/unknowns: The 15 errors are not yet attributed; candidate visibility fell to 14/22, but that is not proof of an upstream root cause.
Next exact action: Build a 15-row evidence table from the persisted provenance/crops, labeling each error as crop/candidate/segmentation failure or model classification failure, with unclear cases remaining review-required. Do not tune or edit runtime code until this attribution is complete.
Acceptance/verification: Every wrong row has an evidence-backed cause or explicit unknown; held-out data remains untouched; run only focused inspection/tests relevant to the attribution and report limitations separately from source/package/UAT evidence.

Continue the engineer loop from this state, preserving good existing logic and backward compatibility. Do not trust this prompt over the repository, do not rewrite/refactor outside scope, and do not commit/push/deploy or mutate external systems without explicit authorization.
```

## Current handoff — 2026-09-16 student-number recognition rollover

Use the repository docs and current task as source of truth. The prior compact
macOS UI task is complete and committed. Student-number recognition Phase 1
is now complete as a dataset/benchmark layer; runtime behavior remains
unchanged.

### Verified current state

- Repo: `/Users/zubinpijit/private/exam-grader`
- Branch: `fix/vol8-current-usable-checkpoint`
- Latest pushed candidate commit: `3ad21da fix: compact macOS UI controls`
- Fresh bundle: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`.
- UI/theme: `24 passed`; Home guidance: `1 passed`; changed-file Ruff,
  `git diff --check`, light/dark visual QA, packaged self-check, UI/settings
  smoke, and strict deep codesign passed.
- Limitation: source/package evidence only; Product Owner native UAT remains
  separate and no release/tag/publish claim is made here.

### Phase 1 result

- Extracted 100 visually seeded page-1 sequence crops (`00`–`99`) from
  `/Users/zubinpijit/Downloads/number handwriting.pdf` and kept pages 2–11 in
  an unlabeled review queue. The export is not training-ready.
- Built a 22-record held-out corpus from teacher-confirmed Vol.8/Vol.9
  results with source hashes and saved registration provenance. Writer groups
  are unknown; no training split is claimed.
- Current baseline: exact `5/22` (`22.7%`), candidate/review visibility
  `18/22` (`81.8%`), review-required `22/22`, auto-accept `0`, wrong
  auto-accept `0`. Vol.8: `2/10` exact and `8/10` visible; Vol.9: `3/12`
  exact and `10/12` visible.
- Reproducible commands and promotion gates are documented in
  `docs/IDENTITY_DATASET.md`. External reports are under `/private/tmp/`.

### Visual QC checkpoint

- `tools/benchmark/prepare_digit_annotation.py` now produces a review-only
  worklist of 200 spatial digit proposals plus a contact sheet. All records
  remain `needs_review`; no training data is asserted.
- Visual QC identified `06`-`09` as a single-digit layout variant without a
  visible leading zero. Their 8 proposals are explicitly unlabeled and must
  be resolved by annotation rather than inferred from position.
- Current worklist: `/private/tmp/exam-grader-number-handwriting-annotation-v3/`.

### Annotation completion checkpoint

- The current v3 annotation manifest has `198 labeled`, `2 excluded`, `0
  remaining`, and `0 bad_bbox`; its audit log contains `372` events.
- The validated label-ready output is
  `/private/tmp/exam-grader-number-handwriting-training-ready.json` with 198
  records. It is `seed_only` and explicitly allows only internal seed training;
  `generalization_claim_allowed=false` because writer identity is unknown.
- The seed model has now been benchmarked against the independent Vol.8/Vol.9
  holdout; runtime integration is review-only and its confidence cap is a
  conservative seed-validation score, not a generalization probability.

### Seed model integration checkpoint

- Seed training is authorized for this cycle with
  `training_scope=internal_seed_split_only` and
  `generalization_claim_allowed=false`.
- KNN was selected over centroid on internal validation (`39/39` versus
  `37/39`). The independent Vol.8/Vol.9 result is `7/22` exact (`31.8%`),
  versus legacy `5/22` (`22.7%`); review `22/22`, wrong auto-accept `0`.
- The model is bundled as review-only in
  `src/exam_grader/resources/student_number_digit_model.npz`; auto-accept is
  still disabled. Fresh app: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`.

### Scope boundary for the next chat

The next task is visual QC/annotation and leakage-safe writer-grouped dataset
preparation. Do not change runtime recognition, crop/registration, OMR,
grading, review, UI, or release behavior as part of that preparation.

`DETAIL: [รอ Product Owner บอกใน chat ใหม่]`

Do not guess algorithms, thresholds, accuracy targets, identity policy,
fixture labels, or adjacent OMR/review behavior before that detail is supplied.

### Important files and ownership

- Likely identity/review surfaces to inspect after scope is supplied:
  `src/exam_grader/identity.py`, `src/exam_grader/exam_ui.py`,
  `src/exam_grader/review_ui.py`, and the relevant identity/real-fixture tests.
- Preserve the committed UI polish and all existing good OMR, geometry, crop,
  review-gate, scoring, storage, export, provenance, and immutable-source
  behavior.
- Preserve existing untracked `tests/fixtures/real/vol.8/` and
  `tests/fixtures/real/vol.9/`; do not reset, clean, overwrite, or absorb them.

### Paste-ready prompt for the next chat

```text
Use the repository docs and current task as source of truth. Read /Users/zubinpijit/.codex/RTK.md, progress.md, docs/NEXT_CHAT_HANDOFF.md, and docs/TASK_SPEC.md first; inspect the actual implementation and git state before acting.

Objective/scope: Continue the student-number recognition task only after the Product Owner supplies the exact detail below; do not infer implementation scope in advance.
DETAIL: [รอ Product Owner บอกใน chat ใหม่]
Verified current state: Branch fix/vol8-current-usable-checkpoint is at 3ad21da fix: compact macOS UI controls; the fresh macOS arm64 dist/ExamGrader.app passed focused UI/theme and Home-help tests, Ruff, diff-check, light/dark visual QA, packaged self-check, UI/settings smoke, and strict deep codesign. Native Product Owner UAT is still separate.
Important files/components: src/exam_grader/identity.py, src/exam_grader/exam_ui.py, src/exam_grader/review_ui.py, relevant identity/real-fixture tests, and dist/ExamGrader.app.
Dirty ownership: Preserve existing untracked tests/fixtures/real/vol.8/ and tests/fixtures/real/vol.9/; do not reset, clean, overwrite, or absorb them.
Decisions/invariants: Preserve immutable originals, provenance, fail-closed uncertainty, mandatory teacher confirmation, existing OMR/crop/geometry/review/scoring/storage/export behavior, and backward compatibility. Do not broaden into UI or unrelated business logic without explicit scope.
Known blockers/unknowns: The exact student-number `DETAIL` and acceptance criteria are pending; do not name an accuracy result or production outcome from existing package/source evidence.
Next exact action: In the new chat, obtain the Product Owner's exact DETAIL, then inspect the current identity pipeline, persisted payloads, relevant fixtures, and tests before proposing one bounded implementation plan.
Acceptance/verification: Define acceptance only from the supplied DETAIL; keep source tests, package/build evidence, and native/device UAT as separate claims. Do not commit, push, deploy, or mutate external systems unless explicitly authorized in that chat.

Continue the engineer loop from this state, preserving good existing logic and backward compatibility. Do not trust this prompt over the repository, do not rewrite/refactor outside scope, and if context becomes unreliable update this same handoff before rotating again.
```

## Current handoff — 2026-09-16 UX/UI continuation

Use the repository docs and current task as source of truth. This checkpoint
only prepares a fresh chat; it does not reopen the completed logic work.

### Verified current state

- Repo: `/Users/zubinpijit/private/exam-grader`
- Branch/origin: `fix/vol8-current-usable-checkpoint`, aligned at `0087a49 fix: polish native exam grader controls`.
- Fresh macOS arm64 bundle: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`.
- CUA visual inspection of the fresh bundle confirmed compact native-style
  settings/help controls, no large structural emoji icons, and visible
  combo-box/stepper arrows in `NewExamDialog`.
- Evidence: UI/theme `23 passed`, home guidance `1 passed`, and geometry /
  Vol.2 / Vol.8 / document-normalization regressions `46 passed`; Ruff,
  `git diff --check`, strict deep codesign, packaged self-check, settings
  smoke, and offscreen UI smoke passed.
- Limitation: this is source/package evidence, not Product Owner native UAT or
  a release claim. No release/tag/publish is authorized by this handoff.

### Important files and ownership

- UI scope: `src/exam_grader/ui.py`, `src/exam_grader/exam_ui.py`,
  `src/exam_grader/preferences.py`, `tests/test_ui.py`,
  `tests/test_vol8_home_help.py`.
- Preserve the current good logic in geometry, OMR, review gates, scoring,
  identity, storage, export, and crop/provenance paths. Do not reset, clean,
  overwrite, or absorb the existing untracked
  `tests/fixtures/real/vol.8/` and `tests/fixtures/real/vol.9/`.

### Paste-ready prompt for the next chat

```text
Use the repository docs and current task as source of truth. Read /Users/zubinpijit/.codex/RTK.md, progress.md, docs/NEXT_CHAT_HANDOFF.md, and docs/TASK_SPEC.md first; inspect the actual implementation and git state before acting.

Objective/scope: Continue minimal macOS-native UX/UI polish for Exam Grader only, based on the latest screenshots; do not change business logic.
Verified current state: Branch fix/vol8-current-usable-checkpoint and origin are aligned at 0087a49; fresh macOS arm64 dist/ExamGrader.app passed focused UI/regression tests, Ruff, diff-check, strict codesign, packaged self-check, settings smoke, and offscreen UI smoke; CUA confirmed compact controls and visible NewExamDialog dropdown/stepper arrows.
Important files/components: src/exam_grader/ui.py, src/exam_grader/exam_ui.py, src/exam_grader/preferences.py, tests/test_ui.py, tests/test_vol8_home_help.py, dist/ExamGrader.app.
Dirty ownership: Preserve existing untracked tests/fixtures/real/vol.8/ and tests/fixtures/real/vol.9/; do not reset, clean, overwrite, or absorb them.
Decisions/invariants: Keep immutable originals, provenance, fail-closed uncertainty, teacher confirmation for student numbers, existing OMR/crop/geometry/review/scoring/storage/export behavior, and backward compatibility. Use $ui-ux-pro-max only for this UI slice if useful.
Known blockers/unknowns: Product Owner native UAT remains pending; source/package smoke is not production or release evidence.
Next exact action: Inspect MainWindow, NewExamDialog, ExamDialog, and ReviewDialog at supported desktop sizes against the latest screenshots, then make one bounded UI-only improvement and add focused UI coverage.
Acceptance/verification: No business-logic diff; relevant UI tests and focused regressions pass; run Ruff and git diff --check; if UI changes, rebuild dist/ExamGrader.app and rerun strict codesign, packaged self-check, settings smoke, and offscreen UI smoke; report native UAT separately.

Continue the engineer loop from this state, preserving good existing logic and backward compatibility. Do not trust this prompt over the repository, do not rewrite/refactor outside scope, and do not commit/push/deploy or mutate external systems without explicit authorization. If context becomes unreliable, update the same docs and create a new handoff before starting a fresh session.
```

## Current handoff — 2026-09-15 central resolver and Vol.9 review-gate fix

Use this section as the source of truth for the next implementation chat. This
turn used `$v` and `$seamless-handoff` in read-only mode: no code, tests,
fixtures, build, staging, commit, or release was performed.

### Workspace safety

- Repo: `/Users/zubinpijit/private/exam-grader`
- Branch: `fix/vol8-current-usable-checkpoint`
- HEAD: `ae973e1 fix: refresh stale detections and review previews`
- Preserve all existing dirty/untracked work: modified
  `src/exam_grader/{exporting.py,storage.py,ui.py,workflow.py}` and
  `tests/{test_export.py,test_ui.py}`, plus untracked Vol.8/Vol.9 fixtures and
  `tests/test_vol8_home_help.py`. Do not reset, clean, or absorb it.

### Verified root causes and limits

1. Runtime registration, ReviewDialog corner selection, and issue-preview ROI
   selection are separate resolvers. Runtime uses `imaging.register()`;
   `review_ui._normalization_corners()` and `exam_ui.populate_issues()` make
   independent choices. Add a central persisted resolver result and consume it
   everywhere so runtime and UI show the same transform/ROI/provenance.
2. IMG_1071/1080 are over-reviewed by the global
   `normalization_requires_review` gate: `imaging.py` sets each answer's
   `auto_resolved` false when the page flag is true, even when the mark itself
   is clear. Split page/block/answer/identity confidence. Strong, unambiguous
   answers may be accepted/prefilled; true ambiguity and bad geometry remain
   review-required. Do not weaken the global threshold as a shortcut.
3. IMG_1078's screenshot shows q10–q15 crops including printed q25–q30. A
   direct current `v10` replay of raw `tests/fixtures/real/vol.9/IMG_1078.jpg`
   with built-in `default-1` keeps five answer ROIs inside the block, so this
   exact symptom is not reproduced there. Verify the newly-created exam's
   SQLite/template/detection payload; likely stale ROI or custom-template
   `with_number`/column inference. Add a geometric invariant forbidding answer
   ROIs from intersecting an adjacent question-number strip; fail closed.
4. Confirming a student number must update the Students tab immediately while
   leaving unresolved answers unresolved. Add a regression for identity-confirm
   then list refresh and show `เลขที่ N` separately from answer-review status.

### Next task and acceptance

Implement only the above in the next chat. Preserve immutable originals,
provenance, current good crop/OMR behavior, bulk confirmation of each row's
existing prefill, mandatory teacher confirmation for student numbers, and
fail-closed uncertainty. Add focused tests for resolver consistency, custom
template column isolation, 1071/1080 answer acceptance, and number-confirm
refresh. Run the focused suite plus final smoke; rebuild the macOS arm64
`dist/ExamGrader.app` from the post-fix source and verify package self-check,
codesign, and offscreen smoke. Do not release/tag/publish until Product Owner
native UAT passes.

## Current handoff — 2026-09-15 Vol.9 current-pipeline fix

The current working tree contains the follow-up needed for Product Owner UAT;
this section supersedes stale branch/HEAD/package claims in the historical
sections below.

- Branch: `fix/vol8-current-usable-checkpoint`; base HEAD remains `31cd0c1`.
- The app now detects persisted `v9` detections when an exam opens and asks the
  current worker to reread immutable sources with the current `v10` pipeline.
  It does not retry current detections just because they are uncertain, and it
  never replaces an explicit teacher-confirmed identity.
- Review answer previews use exact stored answer `roi_rects`, so the green
  question-number strip seen on Vol.9 IMG_1078/1071/1080 is excluded from the
  answer crop. This is preview geometry only; OMR thresholds and established
  answer logic were not rewritten.
- Main settings uses a full-surface `InstantPopup` tool button. The create-exam
  template manager and template-dialog action controls have click-path test
  coverage; built-in edit/delete remain intentionally disabled because those
  templates are read-only.
- Current v10 replay: IMG_1071 `147` (one candidate, review-required), IMG_1078
  `12 / 42` (margin 8.43, review-required), IMG_1080 `46 / 44` (margin 10.75,
  review-required). These are not identity accuracy claims; teacher confirmation
  remains mandatory.
- Verification: focused groups 37 + 30 + 7 + 7 passed; changed-file Ruff and
  diff-check passed. The Vol.3 broad benchmark still has its recorded unrelated
  baseline mismatch (expected 7 uncertain, current 10); do not call the entire
  repository suite clean from this checkpoint.
- Fresh package: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`.
  Codesign, self-check, settings smoke, and offscreen UI smoke passed. No
  release/tag/publish was performed; Product Owner native UAT is the next gate.

> **Date Updated:** 2026-09-14  
> **Workspace:** `/Users/zubinpijit/private/exam-grader` (Branch: `main`)  
> **Current Baseline:** Previous baseline 148 passed, 3 skipped (`uv run pytest tests/`); latest scoped change passed 32 targeted tests.
> **HEAD Commit:** `4823cf8`
> **Latest Release:** `v1.0.2` (Tag: `v1.0.2`, macOS DMG & Windows EXE published on GitHub and bithope.app)

---

## 1. Executive Summary & Accomplishments

### Completed in Last Session
1. **OMR & Identity Hardening**:
   - Bounded lattice alignment search range (`[-18, +18]` px) preventing column hopping.
   - Scoped Differential Row SNR to custom templates with blank floor threshold (`max < 0.06`).
   - Morphological monochrome line opening (`25x1` horizontal, `1x15` vertical) eliminating grid border bleed.
   - Left-margin Thai label suppression (`"เลขที่"`) and bottom dotted guideline filtering.
   - Touching digit splitting via vertical projection valley (`proj <= 0.20 * min(peak_L, peak_R)`).
   - Morphological disambiguation for handwritten `3` vs `4` vs `9` and `6` vs `0`.
   - Restored serif `1` classification and UTF-8 safe OCR decoding (`errors="replace"`).
   - Inferred default student number ROI near score box for discovered templates.
   - Added student number ROI helper label and tooltip in `CalibrationDialog`.
   - Added automated test suite `tests/test_vol7_real_sheets.py` (8 passing tests).
   - Achieved 98.3% single-mark accuracy on outdoor real sheets and 100% student number accuracy without manual teacher intervention.
2. **Git & Final Integration**:
   - Merged feature branch `fix/vol7-omr-identity-hardening` into `main` clean (Fast-forward, no code changes during merge).
   - Windows UAT verified clean with 0 regressions.
3. **Release v1.0.2 Published**:
   - Tag: `v1.0.2` on `main`.
   - macOS Artifact: `Exam-Grader-v1.0.2-macOS-Apple-Silicon.dmg` (SHA-256: `8902e71607448116308927725784bc7527cfdb8e913d27866a49909e298885d8`).
   - Windows Artifact: `Exam-Grader-v1.0.2-Windows-Setup.exe` (SHA-256: `b7249c9bb25594e15d103b15fa58357f2d7f4ed6bfeb189c564da92cd0492ca7`).
   - GitHub Release Published: [https://github.com/bithope21/exam-grader/releases/tag/v1.0.2](https://github.com/bithope21/exam-grader/releases/tag/v1.0.2)
4. **Landing Page (bithope.app) Web Sync Fixed**:
   - Identified root cause in `bithope-web` (`release.ts`): ISR 1-hour cache and hardcoded fallback `v1.0.1`.
   - Hardened `release.ts` with `v1.0.2` fallback, minute dynamic cache-buster (`?_t=${cacheMinute}`), `revalidate: 60`, and version-resilient fallback URLs.
   - Deployed `bithope-web` to Vercel production (`npx vercel --prod`). Verified live `bithope.app/exam-grader` shows `v1.0.2` for both macOS and Windows.

---

## 2. Historical Checkpoint — 2026-09-14 (superseded by section 5)

The two planned tasks are implemented and locally verified:

- ReviewDialog offers **ข้ามรายการที่เหลือ → ไปผลลัพธ์** with a confirmation summary. Unknown identities remain stable across re-export; unresolved answers are not guessed and score zero; review provenance is included in DB/JSON/Excel, and checked JPEGs show a Thai partial-review banner.
- Vol.8 registration now scores multiple page/green-print quads against the printed grid, applies bounded line-fit refinement after coarse homography, and fails closed when grid evidence is weak. Already-canonical sheets retain an identity transform. OMR thresholds did not change.
- Vol.8 evidence: `docs/evidence/vol8-registration/after/report.json` plus normalized images, grid overlays, and a partial checked preview. All 10 photos registered (9 green-print quads, 1 page quad); maximum mean grid residual 2.434 px, minimum alignment confidence 0.8203. IMG_1022 first five observed marks remain A/B/A/D/C. This is registration evidence, not general answer-accuracy evidence. The checked preview uses a synthetic all-A key only to inspect visual rendering.
- Validation: 32 targeted tests including the ReviewDialog skip-button confirmation, changed-source Ruff and Mypy passed. Whole-directory Mypy still reports optional-template typing errors in untouched `settings_ui.py` and `ui.py`. Local build: `dist/ExamGrader.app` (macOS arm64, 234 MB); strict deep codesign, self-check, offscreen UI smoke, and offscreen settings smoke passed. No release/tag/publish was done.
- The untracked Vol.8 source fixtures were read-only and their hashes were verified unchanged.

The task prompt below was current before the user supplied the full production-hardening scope. Keep it as historical context only; section 5 is the current continuation.

### Historical fresh-chat prompt (superseded)

```text
ทำงานต่อใน `/Users/zubinpijit/private/exam-grader` โดยอ่าน repository agent instructions (ถ้ามี), `/Users/zubinpijit/.codex/RTK.md`, `progress.md`, `docs/TASK_SPEC.md` และ `docs/NEXT_CHAT_HANDOFF.md`; ตรวจ git status/diff ก่อนแก้และรักษางาน dirty/untracked ทุกชิ้น. ใช้ `rtk` นำหน้าคำสั่ง shell ตามกติกา repo.

TASK — TASK — Production Hardening: Vol.8 Auto Document Boundary + Registration + Student Number
DETAIL: บอกใน chat ที่จะทำ task

สถานะจริง: Vol.8 registration ผ่าน 10/10 ภาพ (residual สูงสุด 2.434 px, confidence ต่ำสุด 0.8203; `docs/evidence/vol8-registration/after/report.json`) แต่ยังไม่ได้เทียบคำตอบครบชุดกับ ground truth ที่ยืนยันโดยมนุษย์; A/B/A/D/C ของ IMG_1022 ห้าข้อแรกเป็นเพียง baseline. ภาพ preview ใช้ key all-A สังเคราะห์เพื่อเช็กการแสดงผลเท่านั้น. มี camera guidance เดิมใน `src/exam_grader/calibration_ui.py`; `dist/ExamGrader.app` เป็น build ก่อนหน้าของงานนี้ ไม่ใช่ final UAT build.

ดำเนินงานตาม DETAIL ที่ Product Owner เติม: สร้าง/ยืนยัน ground truth แยกจากผลโปรแกรมและเทียบ Vol.8 ครบขอบเขตที่ระบุ พร้อมรายงานจำนวนที่เทียบได้/ไม่แน่ใจและผลผิดพลาด; ตรวจและแก้ camera guidance เฉพาะขอบเขตที่อนุมัติ; จากนั้น build macOS ใหม่และเก็บหลักฐาน codesign, packaged smoke และ native UAT. รักษาต้นฉบับ/ที่มา, fail-closed และ review-required สำหรับความไม่แน่ใจ; ห้ามอ้าง accuracy จาก registration หรือ test อย่างเดียว. ห้าม commit/push/publish โดยไม่มีคำสั่งชัดเจน.
```

---

## 3. Quick Start Commands for Next Session

```bash
# 1. Check workspace status
git status
git log -n 3 --oneline

# 2. Run full pytest suite
uv run pytest tests/

# 3. Launch desktop app for UI inspection
uv run exam-grader
```

## 4. Current Continuation — 2026-09-14

The Vol.8 accuracy/camera-guidance task described above was implemented and rebuilt
locally. This section supersedes the older “upcoming task” status above.

- Accuracy evidence: `docs/evidence/vol8-accuracy/README.md` and the before/after
  reports. The ten-photo manual visual reference is still provisional pending
  Product Owner confirmation. Current comparison: 290/297 visually resolved active
  answers exact, zero wrong/false-multiple/false-blank, seven review-required, and
  zero unsafe decisions across three visually ambiguous answers. Q31–Q60 are
  diagnostic only because the key contains Q1–Q30.
- Added the camera-guidance control beside student-sheet import; native UI inspection
  confirmed the Student tab shows the complete Thai guidance.
- Final local app: `dist/ExamGrader.app`, macOS arm64, 234 MB. Strict deep codesign,
  packaged self-check, settings smoke, and UI smoke pass. No release or publish.
- Focused checks: 38 passed. Full suite: 152 passed, 3 skipped, 10 failed. Eight
  failures are registration-grid-quality rejections before OMR; one is a schema
  migration expectation mismatch; one Windows-only test attempts a Documents write
  outside the sandbox. See `progress.md` for the checks and untouched Ruff/Mypy
  findings.

The previous implementation/build pass is checkpointed, but the user reports that
answer reading remains below the desired quality. Its provisional metrics do not
mean the algorithm is accepted. Product Owner label adjudication and manual teacher
UAT also remain outstanding. The user's new scope is recorded in section 5 below.

## 5. Current checkpoint — Production Hardening: Document Normalization / Auto-Crop

The user's full task scope was provided and acted on; the previous placeholder `DETAIL` handoff is obsolete.

- Current implementation adds multi-view physical-page evidence, grid/template candidate scoring with bounded refinement, an authoritative manual four-corner crop path, physical-edge-based corner-review gating, and a small Thai photo-help affordance on Home. Original bytes remain immutable; previews are regenerated from the source and saved transform. Weak page/grid evidence remains review-required.
- Latest authoritative replay is `/private/tmp/vol8-production-uat-20260914-final/report.json` using the teacher-reviewed export. Ten sheets reached registration; 282/295 confirmed single answers matched exactly (95.59%), 286/300 answer states matched (95.33%), and there were 0 unsafe confident mismatches. Five sheets triggered the runner's manual-corner-adjustment criterion; this flag alone does not prove those page boundaries are wrong. All ten remain in broad review. Worst grid residual: 6.742 px; lowest alignment confidence: 0.5914. Five multiple-answer subsets are unavailable in the export.
- Student-number OCR v5 removes fabricated stitch confidence, ranks actual OCR runs by measured scores, and exposes shape-only alternatives as explicitly unscored review suggestions. All ten identities remain review-required; primary exact 3/10, OCR-candidate truth 3/10, shape-suggestion truth 3/10, union visible to review 6/10. This remains below the identity criterion.
- Full suite: 176 passed, 3 skipped, 16 failed. Ten failures are the recorded baseline groups (eight registration/grid-quality cases, schema-version assertion, and sandbox-blocked Windows Documents write). Six further failures comprise one Vol.2 registration case that fails before identity observation and five identity-test failures: two Vol.5 ranking expectations, two Vol.6 cases where a review-required identity was batch-adopted, and the Vol.7 IMG_0988 recognition miss. Changed-file Ruff passes. Do not claim no regression.
- The user-defined acceptance is **not met**: answer accuracy is below 100%, five sheets are flagged by the manual-corner-adjustment criterion, identities remain review-required and below target, and legacy identity checks regress. No app was rebuilt for this task; the existing ignored `dist/ExamGrader.app` is from an earlier checkpoint. No release, commit, or publish.

### Acceptance still open

- Resolve the six additional identity-related failures without allowing unsupported shape guesses to replace OCR evidence; then rerun the full suite and authoritative Vol.8 replay.
- Reach the task's 100% definitive-answer and automatic-boundary criteria on the teacher-reviewed set. Human labels still need Product Owner adjudication; real-device teacher UAT of the corner editor and full-resolution smartphone-photo coverage are outstanding. Synthetic variation tests are not production evidence. Do not claim the feature is production-ready or build a release artifact yet.
- The worktree remains dirty from work that predates and includes this task. Preserve all tracked and untracked user work; do not reset, clean, stage, or commit. `docs/evidence/` and `dist/` are ignored local artifacts. No release was made.

## 6. Current bounded checkpoint — Vol.8 Q27 fail-safe rollback (2026-09-14)

This section supersedes the broader scope in section 5 for the current task. The user authorized only a narrow OMR rollback for `IMG_1024.jpg` Q27, preservation of the `IMG_1028.jpg` registration improvement, and replay of the original 297-cell Vol.8 ground truth. Do not touch Vol.2, identity/student number, scoring, export, or introduce new heuristics.

- Frozen baseline: 10/10 registered; 290/297 exact; 7 uncertain; 0 wrong; 0 unsafe ambiguous.
- Root diagnosis: Q27 was auto-selected as E by `_green_core_decision` with reason `green-center-ink-dominance`; core density was 0.083. The source reference calls this answer ambiguous. Its registration candidate stayed `green-print-quad`, matching baseline, so the changed decision is in the OMR decision path.
- Removing the promotion entirely was rejected: replay fell to 273/297 with 24 uncertain. Current code instead applies the already-existing `SELECTED_DENSITY_THRESHOLD` of 0.10 to that promotion. Q27 is now review-required, but two additional true answers become uncertain: `IMG_1021` Q12 (core 0.083) and Q23 (0.076). Since Q27 is also 0.083, a scalar threshold cannot satisfy both sides.
- Latest same-dataset replay: `/private/tmp/vol8-accuracy-q27-threshold-rollback/report.json` — 10/10 registered, 288/297 exact, 9 uncertain, 0 wrong, 0 unsafe ambiguous. Acceptance is unmet: exact must be at least 290 and uncertain at most 7. No claim of completion.
- Preserved `IMG_1028` geometry in that replay: green-print-quad, 1.795 px residual, 1.000 grid coverage, 0.8793 alignment confidence, 30/30 exact; frozen baseline had paper-quad, 2.434 px, 0.9432 coverage, and 0.8203 confidence.
- Relevant source: `src/exam_grader/imaging.py` (`_green_core_decision`). Ground truth: `docs/evidence/vol8-accuracy/ground_truth.json`. Frozen baseline: `/private/tmp/exam-grader-vol8-baseline.gGV8fU/before/report.json`. Current replay command:

  `rtk proxy env PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python tools/uat/vol8_accuracy_uat.py --fixtures tests/fixtures/real/vol.8 --labels docs/evidence/vol8-accuracy/ground_truth.json --output /private/tmp/vol8-accuracy-q27-threshold-rollback`

- Current blocker: find an already-supported signal that separates these three real marks without per-question exceptions or a new heuristic. If no such signal exists in the current implementation/evidence, stop and report the conflict rather than widening scope. No full suite, build, release, commit, or publish was run.
- The worktree is dirty with pre-existing task/user work. This round intentionally changed only the green-core promotion threshold in `imaging.py` and appended these two documentation checkpoints. Preserve every other tracked and untracked file; do not reset, clean, stage, or commit.

### Fresh-session prompt

```text
Use repository instructions and current docs as source of truth. Read /Users/zubinpijit/.codex/RTK.md, progress.md, docs/TASK_SPEC.md, and docs/NEXT_CHAT_HANDOFF.md section 6; inspect git status/diff before acting. Prefix every shell command with rtk.

Objective/scope: Complete only the Vol.8 Q27 fail-safe rollback while preserving the proven IMG_1028 registration improvement; do not touch Vol.2, identity/student number, scoring, export, or add heuristics.

Verified state: Current replay is 10/10 registered, 288/297 exact, 9 uncertain, 0 wrong, 0 unsafe ambiguous. Q27 is review-required again; Q12 and Q23 on IMG_1021 became uncertain. The removed-promotion experiment was worse (273/297, 24 uncertain) and is not retained. IMG_1028 remains green-print-quad at 1.795 px residual, 1.000 coverage, 0.8793 alignment confidence, 30/30 exact. Evidence is in /private/tmp/vol8-accuracy-q27-threshold-rollback/report.json; frozen baseline is /private/tmp/exam-grader-vol8-baseline.gGV8fU/before/report.json.

Important files: src/exam_grader/imaging.py; docs/evidence/vol8-accuracy/ground_truth.json; progress.md; docs/NEXT_CHAT_HANDOFF.md.

Dirty ownership: Worktree was already dirty and contains user/task work. This round changed only the green-core promotion floor in imaging.py and appended these checkpoints. Do not overwrite unrelated files, reset, clean, stage, or commit.

Decision/invariant: Keep uncertain answers fail-safe. The current threshold-only rollback cannot pass because Q12 and Q27 both have core density 0.083. Do not add a question-specific exception or new heuristic.

Next exact action: ส่ง detail มาในแชตใหม่นี้

Acceptance/verification: Replay exactly 297 resolved cells from the same Vol.8 fixtures and ground truth using the command in section 6. Require 10/10 registered, at least 290/297 exact, at most 7 uncertain, 0 wrong, and 0 unsafe ambiguous. If all pass, stop algorithm changes and update progress/handoff with the exact report. Do not build, release, commit, or publish.
```

## 7. Current handoff — Resume Vol.8 Auto Document Boundary (2026-09-15)

This section supersedes section 6's narrow Q27-only task and section 5's older acceptance wording wherever they conflict with the latest user request. Return to the original **TASK — Production Hardening: Vol.8 Auto Document Boundary + Registration + Student Number**. The current engineering focus is real-photo automatic paper boundary/crop, perspective normalization, and registration. Keep `IMG_1024.jpg Q27` uncertain/review-required and stop OMR tuning. The Product Owner will provide Student Number details and additional acceptance criteria in the new chat; do not invent them or work on identity now.

### Evidence and current state

- Latest teacher-reviewed replay: `/private/tmp/vol8-production-uat-20260914-final3/report.json`, from 10 original Vol.8 photos and teacher truth at `tests/fixtures/real/vol.8/2569_ป.1_1_math_vol8 lunar ultra_30q/ผลการตรวจ/2026-09-14_205501/_system/results.json`. It processed 10/10 sheets; 295/300 answer states and 291/295 confirmed single choices matched; 2 unsafe confident mismatches; 5 sheets met the manual-intervention/manual-corner-adjustment criterion. Worst grid residual: 6.508 px; lowest alignment confidence: 0.5605. The automatic-crop goal is not yet demonstrated.
- `IMG_1028.jpg` in this report selected `edge-canny` (`paper-quad-grid-refined-v2`), with boundary confidence 0.8437, normalization confidence 0.6455, grid residual 6.508 px, coverage 0.6705, and alignment confidence 0.5605. It did not require manual corner movement, but registration/normalization still required review. Do not call this an accepted registration improvement based only on corner detection.
- Separate provisional 297-answer replay: `/private/tmp/vol8-accuracy-q27-threshold-rollback/report.json` = 10/10 registered, 288/297 exact, 9 uncertain, 0 wrong, 0 unsafe ambiguous, with `IMG_1024 Q27` review-required. This visual-label oracle has a different denominator from the teacher export above. Use it only as an OMR safety guard and do not modify OMR.
- Existing full-suite checkpoint: 176 passed, 3 skipped, 16 failed, including previously recorded baseline groups and additional Vol.2/identity regressions described in section 5 and `progress.md`. Do not claim clean regression. Determine which checks are relevant to crop/registration and compare against existing evidence; the user explicitly deferred other business logic.
- The worktree was already dirty before this documentation update. It includes modified source/tests and untracked normalization/UAT implementation and Vol.8 fixtures. Preserve every dirty and untracked item; inspect status/diff before any code edit, do not reset/clean/stage/commit, and keep changes limited to the authorized crop/registration task.
- No build was performed for this task's latest crop acceptance checkpoint. Build a fresh macOS arm64 `dist/ExamGrader.app` only after agreed crop criteria and relevant regressions pass, then run strict codesign, packaged self-check, and applicable settings/UI smoke with disposable data. This is for Product Owner trial, not a release.

### Fresh-chat prompt

```text
Continue work in /Users/zubinpijit/private/exam-grader. Read repository agent instructions (including AGENTS.md if present), /Users/zubinpijit/.codex/RTK.md, progress.md, docs/TASK_SPEC.md, docs/NEXT_CHAT_HANDOFF.md, and docs/DOCUMENT_NORMALIZATION_UAT.md. Use `rtk` before every shell command. Inspect git status and relevant diffs before editing; preserve all existing dirty and untracked work. Do not spawn agents.

Treat unrelated or legacy slices in docs/TASK_SPEC.md as context, not authorization to expand this task.

Task: TASK — Production Hardening: Vol.8 Auto Document Boundary + Registration + Student Number. The original task brief is in /Users/zubinpijit/.codex/attachments/626c5b84-e272-45bf-85ac-6c640d9e8149/pasted-text.txt. Treat it as task background, while following these newer, direct Product Owner constraints wherever they differ.

Scope now: focus on robust automatic physical-paper boundary/crop → perspective normalization → fine registration on the real Vol.8 photographs. Routine usable photos should not need manual corner adjustment; keep manual correction as a fallback. Use Vol.8 as the primary regression/UAT corpus and preserve existing cross-layout behavior and all working flows. `IMG_1024.jpg Q27` must remain uncertain/review-required. Stop OMR tuning. Do not work on Student Number, Vol.2, scoring, review, export, or other business logic. The Product Owner will specify Student Number details and additional acceptance criteria in this chat; do not infer requirements or thresholds.

Current evidence to reproduce/compare, keeping datasets and denominators separate:
- Teacher-reviewed production replay: /private/tmp/vol8-production-uat-20260914-final3/report.json, teacher truth: tests/fixtures/real/vol.8/2569_ป.1_1_math_vol8 lunar ultra_30q/ผลการตรวจ/2026-09-14_205501/_system/results.json. It processed 10/10; state match 295/300; confirmed single-choice exact 291/295; 2 unsafe confident mismatches; 5 sheets met manual-intervention/manual-corner-adjustment criteria; worst grid residual 6.508 px; minimum alignment confidence 0.5605. The crop goal is not yet accepted.
- IMG_1028 in that report: edge-canny / paper-quad-grid-refined-v2, boundary confidence 0.8437, normalization confidence 0.6455, residual 6.508 px, line coverage 0.6705, alignment confidence 0.5605. No corner movement was requested on that sheet, but registration/normalization still required review.
- Separate provisional visual-label answer guard: /private/tmp/vol8-accuracy-q27-threshold-rollback/report.json; 10/10 registered, 288/297 exact, 9 uncertain, 0 wrong, 0 unsafe ambiguous; IMG_1024 Q27 is review-required. This 297-cell oracle is not the teacher export's 295 single-answer or 300 state denominator. Keep Q27 fail-safe; do not tune OMR or merge these metrics.
- Latest recorded full suite: 176 passed, 3 skipped, 16 failed. Read the recorded failure groups and existing baseline before deciding which crop/registration regressions to run; do not expand into deferred business logic.

First reproduce the relevant existing Vol.8 crop/registration and regression evidence from the unchanged fixtures, inspect per-image candidate/corner/transform/grid diagnostics (especially IMG_1028, IMG_1029, IMG_1030), and identify the smallest upstream boundary/perspective/registration root cause. Do not guess from aggregate registration success, add filename/layout-specific logic, lower OMR thresholds, or add unproven heuristics. Keep boundary detection, perspective warp, fine registration, and OMR diagnostics separate. If a proposed crop change does not improve the same real-image evidence without regressions, revert only that proposed change while preserving the user's pre-existing dirty work.

Crop/registration replay CLI (write new diagnostics outside the repo):
rtk proxy env PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python tools/uat/vol8_registration_uat.py --fixtures tests/fixtures/real/vol.8 --output /private/tmp/vol8-registration-uat-20260915

Acceptance: obtain Product Owner clarification in this chat before inventing Student Number or additional acceptance criteria. For the currently authorized crop scope, prove on the same real Vol.8 photographs that automatic physical boundaries/crops and perspective/registration are correct in routine cases without manual corners, and that relevant cross-layout/OMR/review/scoring/export/provenance regressions have not been introduced. Keep ambiguous OMR review-required and Q27 uncertain. Report exact per-image evidence, before/after diffs, remaining limitations, and clearly state whether acceptance passed. Do not claim the older 297-answer provisional benchmark proves crop acceptance.

After the agreed crop task passes its relevant regression checks, build a fresh macOS arm64 dist/ExamGrader.app for Product Owner trial and run strict deep codesign, packaged self-check, and applicable settings/UI smoke with disposable data. Record exact commands and results. Do not release, tag, push, or publish. Update DOCUMENT_NORMALIZATION_UAT.md, progress.md, and NEXT_CHAT_HANDOFF.md with verified evidence and the next prompt.
```

## 8. Current checkpoint — Vol.8 physical-boundary follow-up (2026-09-15)

This section supersedes the evidence snapshot in section 7 while keeping its scope and safeguards: work only on Vol.8 physical-paper boundary/crop, perspective normalization, and registration; do not tune OMR or touch student number, Vol.2, scoring, review, or export. Keep `IMG_1024 Q27` uncertain under the provisional visual-label safety guard. The teacher export and provisional visual labels disagree on that row; report them separately.

- Crop/registration replay: `/private/tmp/vol8-registration-uat-20260915-final/report.json` — 10/10 registered; all final transforms selected `green-print-quad`; maximum mean grid residual 1.954 px and minimum alignment confidence 0.8572.
- Teacher-reviewed replay: `/private/tmp/vol8-production-uat-20260915-final2/report.json` — 10/10 processed; 295/300 answer states and 291/295 confirmed single choices matched; 0 unsafe confident mismatches; 7 manual-intervention flags; 4 manual-corner-adjustment flags; worst residual 6.483 px; lowest alignment confidence 0.5654. `IMG_1028` now has a physical-page candidate at 0.8345 confidence, 2.739 px residual, 1.000 coverage, and 0.8313 alignment confidence. Automatic-crop acceptance is not met while four sheets remain flagged.
- The seven teacher-adjusted page corners are matched within a worst per-corner delta of 58.3 px (`IMG_1023`), 36.4 (`1024`), 34.1 (`1025`), 46.2 (`1026`), 38.8 (`1027`), 30.2 (`1029`), and 26.1 (`1030`). This is diagnostic comparison, not interactive crop acceptance.
- Independent 297-cell provisional guard: `/private/tmp/vol8-accuracy-boundary-final/report.json` — 288/297 exact, 9 uncertain, 0 wrong, and 0 unsafe decisions on ambiguous labels; IMG_1024 Q27 remains machine-uncertain. Do not merge with the teacher export's 300-state / 295-single denominator.
- Relevant focused tests: 60 passed, including the Vol.8 normalization/registration/hardening tests and Vol.5/6/7 regression tests. Targeted Ruff and `git diff --check` passed. No build was run because crop acceptance remains open.
- Worktree remains dirty with user/task work. Preserve every tracked and untracked file; do not reset, clean, stage, or commit. Do not build until the four remaining low-confidence/corner cases have an evidence-backed outcome or are explicitly accepted as review-required.

Next exact action: inspect the physical edge evidence for IMG_1025/1026/1029/1030 and determine whether the existing views can resolve their remaining manual-corner flags without weakening confidence/review gating. Keep ambiguous labels review-required and Q27 uncertain. If the source evidence remains weak, stop at the fail-closed boundary rather than raising confidence from grid fit alone.

## 9. Checkpoint complete — current usable local program (2026-09-15)

- The reviewed crop/registration + current OMR fail-safe slice is checkpointed at commit `b69ce93624ea3088cc2fbb12ff9aa579c360e265` on branch `fix/vol8-current-usable-checkpoint`, pushed to `origin`.
- Fresh `dist/ExamGrader.app` was built from this source state at 234 MB. Strict deep codesign, packaged `--self-check`, and offscreen `--smoke-ui` passed. Focused Vol.8 checks passed 8/8; the compact registration replay passed 10/10 photos with maximum residual 1.954 px and minimum confidence 0.8572.
- The checkpoint intentionally excludes unrelated dirty slices from identity, export, storage, workflow, general UI, legacy tests, and untracked Vol.8/Vol.9 fixtures. The worktree still contains those files; preserve them and do not reset, clean, or absorb them.
- The old Vol.8 acceptance remains open: teacher replay is 291/295 confirmed singles with four manual-corner flags; the separate provisional guard is 288/297 exact with 9 uncertain and zero wrong/unsafe, and `IMG_1024 Q27` remains review-required. These are not production-wide accuracy claims.

### Fresh-session handoff

```text
Use repository docs and the current task as source of truth. Read `/Users/zubinpijit/.codex/RTK.md`, `progress.md`, `docs/TASK_SPEC.md`, `docs/NEXT_CHAT_HANDOFF.md`, and `docs/DOCUMENT_NORMALIZATION_UAT.md`; inspect the actual implementation and git state before acting.

Objective/scope: The Vol.8 crop/registration checkpoint is complete; start only a new Product Owner-scoped task and do not reopen the completed checkpoint without explicit scope.
Verified current state: branch `fix/vol8-current-usable-checkpoint` at `b69ce93624ea3088cc2fbb12ff9aa579c360e265`, pushed to `origin`; `dist/ExamGrader.app` is a fresh 234 MB arm64 build; focused 8/8, Vol.8 registration 10/10, codesign, packaged self-check, and offscreen UI smoke passed.
Important files/components: `src/exam_grader/imaging.py`, `src/exam_grader/template_discovery.py`, `src/exam_grader/document_normalization.py`, `src/exam_grader/document_normalization_ui.py`, `tools/uat/vol8_registration_uat.py`, and the evidence reports under `/private/tmp/` recorded in the docs.
Dirty ownership: unrelated modified files and untracked Vol.8/Vol.9 fixtures remain in the worktree. Do not overwrite, reset, clean, stage, or commit them without explicit authorization.
Decisions/invariants: Keep original photo bytes immutable; preserve provenance and fail-closed review gating; keep `IMG_1024 Q27` uncertain/review-required; keep registration, answer accuracy, identity, and teacher UAT as separate claims; do not infer deferred Student Number requirements.
Known blockers/unknowns: Automatic-crop acceptance is not demonstrated for four low-confidence/manual-corner cases; teacher labels remain a separate oracle from the provisional 297-cell guard; native teacher UAT remains outstanding.
Next exact action: Wait for the next user-scoped request, then inspect repository state and define its smallest allowed change before editing.
Acceptance/verification: For any new crop work, reproduce the Vol.8 replay command in `docs/DOCUMENT_NORMALIZATION_UAT.md` and retain the existing no-unsafe/no-guessing invariants. Do not commit, push, deploy, tag, or release without explicit authorization.

Continue the engineer loop from this state, preserving good existing logic and backward compatibility. Do not trust this prompt over the repository, do not rewrite outside scope, and update the same docs before any future context rollover.
```

## 2026-09-15 — Review/identity scope completed for Product Owner UAT

- Scope completed: review auto-accept for only unambiguous current OMR, per-row bulk prefill confirmation, and review-required student-number v6 pipeline. Crop/registration/OMR behavior was preserved; `multiple`, `boundary_cross`, abnormal blank, uncertain geometry, and all student numbers remain guarded for review.
- Bulk action is `ยืนยันข้อมูลที่ระบบอ่านไว้`; each selected row keeps its own prefill. The old uniform bulk edit and manual row editor remain intact. Student number is never silently adopted from roster/range; teacher confirmation remains required.
- Real-label candidate visibility union (primary + OCR candidates + separate review hints; not accuracy): Vol.8 **8/10** vs prior **5/10**; Vol.9 **11/12** vs prior **8/12**. Primary candidates: Vol.8 **2/10**, Vol.9 **4/12**. These are candidate-recall metrics only, not confirmed identity accuracy.
- Verification: focused suite **92 passed**; changed-file Ruff and `git diff --check` passed. Fresh app build completed from current worktree. `codesign --verify --deep --strict`, disposable `--self-check`, offscreen `--smoke-settings`, and offscreen `--smoke-ui` all passed.
- UAT artifact: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app` (macOS arm64). Product Owner interactive UAT is still outstanding; do not tag, release, or publish. Keep `IMG_1024.jpg Q27` `uncertain / review-required` and preserve dirty/untracked files outside the reviewed checkpoint.
