# Document Normalization / Auto-Crop — UAT Checkpoint

## 2026-09-15 follow-up — Vol.9 stale detection and review-crop correction

This follow-up addresses the Product Owner report that Vol.9 IMG_1071, IMG_1078,
and IMG_1080 still showed old review behavior and that the answer preview could
include the printed green question-number strip. It does not reopen the proven
OMR/crop threshold work.

- Fixture metadata was confirmed as pipeline
  `omr-illumination-v9-document-normalization-v1`, while current source is
  `omr-illumination-v10-document-normalization-v2`. Opening an exam now detects
  that mismatch and reprocesses from the immutable source image. Existing
  teacher-confirmed keys/identities are preserved; stale answer reviews are
  invalidated by detection id rather than silently reused.
- The answer preview now crops from the current detection's exact `roi_rects`.
  This removes the adjacent green printed question-number strip from the UI
  evidence. It does not alter the answer classifier or make uncertain answers
  automatic.
- Direct v10 replay using the canonical reference from each raw fixture image:
  IMG_1071 produced `147` with one candidate; IMG_1078 produced `12 / 42`
  (margin 8.43); IMG_1080 produced `46 / 44` (margin 10.75). All remain
  review-required as required by the human-confirmation identity contract.
- OMR/geometry observations were preserved for comparison: 1071 had 30 single
  and 30 blank; 1078 had 18 single, 30 blank, 1 uncertain, and 11 multiple;
  1080 had 29 single and 31 blank. These are diagnostic current-pipeline
  observations, not a ground-truth accuracy score.
- Focused checks passed: UI/automation/workflow 37, normalization/Home 30,
  Vol.8 hardening 7, and Vol.8 registration 7. The packaged current app passed
  deep codesign, self-check, settings smoke, and offscreen UI smoke.

Product Owner must still perform native macOS UAT on the fresh package,
including opening a Vol.9 exam, confirming that the old v9 result is refreshed,
opening IMG_1078/1071/1080 review rows, and confirming that ambiguous identity
and answer geometry remain review-required. No release/tag/publish claim is made.

Date: 2026-09-14  
Status: current production-hardening task is **not accepted**. The package checks described in the historical checkpoint below belong to the earlier normalization pass; no app was rebuilt after this task because its acceptance criteria did not pass.

## 2026-09-15 handoff addendum — crop and registration remain open

This addendum supersedes the older “Latest production-hardening evidence” figures below where reports differ. The user has returned scope to the original Vol.8 auto-boundary task: prioritize physical paper crop, perspective normalization, and registration on real photos; keep `IMG_1024.jpg Q27` uncertain/review-required and stop OMR tuning. Student-number specifics and additional acceptance criteria are deferred to the Product Owner in the next chat.

- Newest teacher-reviewed report: `/private/tmp/vol8-production-uat-20260914-final3/report.json` (`tools/uat/vol8_production_uat.py`), with the same 10 Vol.8 source photographs and teacher export identified above. All 10 registered; 295/300 answer states matched and 291/295 confirmed single choices matched. There were 2 unsafe confident mismatches. Five sheets met the runner's manual-intervention/manual-corner-adjustment criterion; worst grid residual was 6.508 px and lowest alignment confidence 0.5605. These results do not establish that automatic crop/registration is accepted.
- `IMG_1028.jpg`: `paper-quad-grid-refined-v2`, selected `edge-canny`; boundary confidence 0.8437; normalization confidence 0.6455; grid residual 6.508 px; grid-line coverage 0.6705; alignment confidence 0.5605. No manual corner adjustment was required for this image in that report, but normalization and registration still required review/manual intervention.
- Keep the separate provisional 297-cell visual-label replay distinct: `/private/tmp/vol8-accuracy-q27-threshold-rollback/report.json` reports 10/10 registered, 288/297 exact, 9 uncertain, 0 wrong, 0 unsafe ambiguous, with `IMG_1024 Q27` review-required. Its 297 resolved-answer denominator is not the teacher export's 295 confirmed single-choice denominator or 300 answer-state denominator. It is a fail-safe/no-regression guard only; do not tune OMR.
- No new replay or code change was made for this documentation handoff, and no app was built. The crop task remains open; after the next session's agreed crop criteria and relevant regression checks pass, build a fresh macOS arm64 app for Product Owner trial.

## Latest production-hardening evidence

This section supersedes the v8→v9 checkpoint below for the task **Vol.8 Auto Document Boundary + Registration + Student Number**. It uses the teacher-reviewed Vol.8 export at `tests/fixtures/real/vol.8/2569_ป.1_1_math_vol8 lunar ultra_30q/ผลการตรวจ/2026-09-14_205501/_system/results.json`; the runner checks the original-image hashes before and after replay. The five teacher-confirmed `multiple` answers preserve only the multiple state, so their marked-choice subsets are not scored.

- Latest machine-readable report: `/private/tmp/vol8-production-uat-20260914-final/report.json` (`tools/uat/vol8_production_uat.py`). Ten of ten source sheets reached registration with zero failed question cells. State match was 286/300 (95.33%); exact single-choice match was 282/295 (95.59%). Outcomes were 5 uncertain, 2 wrong single choices, 1 missed multiple, 1 false blank, and 5 false multiples. Four of five multiple states matched, but their exact marks cannot be evaluated. There were zero unsafe confident mismatches.
- Boundary registration now evaluates multiple physical-page candidates against template-grid fit and performs bounded grid refinement after a coarse page warp. The valid four-corner path accepts the teacher-selected crop even when the grid fit is weak, marks the result for review, and does not replace the manual crop with an auto-fit. Five of ten pages still meet the runner's corner-adjustment criterion; all ten remain in broad manual review. Worst grid residual is 6.742 px and lowest alignment confidence is 0.5914.
- Student-number OCR v5 keeps whole-word OCR candidates ordered by measured scores and only scores a digit stitch when every digit has direct finite OCR support. Shape-derived corrections are separate unscored review suggestions; they do not override an OCR candidate or count as a confirmed identity. All ten identities remain review-required. The primary candidate matched 3/10 teacher labels; the OCR candidate list contained truth for 3/10; a separate review suggestion contained truth for 3/10. Six of ten had the teacher label visible in either list, still short of acceptance.
- Source hashes were unchanged. The result is not comparable to the earlier provisional 290/297 visual-label metric because this run uses a different, teacher-reviewed oracle and its explicit single-choice denominator is 295.
- Focused normalization, identity, home-help, and Vol.8 hardening checks include new regression coverage. Full suite on this source state: **176 passed, 3 skipped, 16 failed**. Ten failures correspond to the previously recorded registration/grid-quality, schema-version, and sandbox-only Windows-write groups. Six further failures comprise one Vol.2 registration failure before identity observation and five identity-test failures: two Vol.5 ranking expectations, two Vol.6 cases where a review-required identity was batch-adopted, and the Vol.7 IMG_0988 recognition miss. These require resolution or explicit contract-aligned tests before acceptance. Changed-file Ruff checks pass.
- No app build, package smoke, native corner-editor UAT, release, commit, or publish was performed for this task. The existing ignored `dist/ExamGrader.app` is from an earlier checkpoint and is not evidence for these changes.

### Acceptance remains open

The user requires 100% definitive-answer accuracy, zero unsafe decisions, correct identities where evidence is adequate, and automatic physical-boundary detection without manual corners. The current run meets only the zero-unsafe criterion. The answer, identity, manual-corner, regression, and interactive-device criteria remain unmet. Five sheets trigger the runner's manual-corner-adjustment criterion; this flag does not by itself prove that their detected boundaries are wrong. Product Owner adjudication of the export and native teacher UAT are also outstanding. Do not call this production-ready or build/release it until the acceptance gaps are resolved.

## What changed

- Added a document-normalization boundary around the existing decode → page/grid registration → OMR path. `QImageReader.setAutoTransform(True)` remains the EXIF-orientation authority. Candidate diagnostics retain multiple color-mask/edge proposals; template-aware line/grid fit scores page candidates before the canonical registration is chosen.
- The canonical raster is produced through a source-to-template homography and the existing fine grid registration. Registration diagnostics now report boundary proposals, selected corners, confidence components, grid residual/coverage/contrast, OMR uncertainty by question, source SHA-256, and canonical dimensions.
- The stored original remains immutable. The aligned preview is not persisted; it is regenerated from the verified source and saved transform when review is opened.
- Review UI shows a detected-edge/corner preview, an automatic-detection status, a short Thai photo tip, and an optional keyboard-operable four-corner adjustment. A successful manual adjustment appends a new detection from the original and reopens review; it does not accept an answer key or student answers. Low normalization confidence clears machine auto-resolution so answers require a person.
- The OMR illumination feature remains the established local-background subtraction (`sigma=9`) on the canonical raster. It is feature-space contrast, not a destructive replacement of the source/canonical pixels.

## Vol.8 before/after

All counts below use the local visual-reference file `docs/evidence/vol8-accuracy/ground_truth.json`, whose answer labels are provisional and still need Product Owner adjudication. The exact-accuracy denominator is 297 visually resolved active answers; 3 visually ambiguous labels are evaluated separately.

| Pipeline | Exact | Uncertain on resolved | Wrong | False multi | False blank | Unsafe on 3 ambiguous | Exact accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| v6 baseline | 252/297 | 44 | 0 | 1 | 0 | 0 | 84.8485% |
| v8 prior OMR baseline | 290/297 | 7 | 0 | 0 | 0 | 0 | 97.6431% |
| v9 document-normalization | 290/297 | 7 | 0 | 0 | 0 | 0 | 97.6431% |

The valid normalization comparison is v8 → v9: **no OMR-accuracy or uncertainty improvement**. The prior v6 → v8 gain predates this task and must not be attributed to normalization. Current residual uncertainty is concentrated in faint/competing marks (IMG_1021 Q14 and IMG_1025 Q6/Q24–Q27/Q30), not failed page or grid registration. That evidence does not justify lowering mark thresholds.

Vol.8 registration remains 10/10. The selected candidate mix moved from 9 green-print + 1 page-quad to 8 green-print + 2 paper-edge-contour; worst residual remains 2.434 px and minimum alignment confidence remains 0.8203. The boundary strategy changed for IMG_1023; the measured OMR result did not. Source hashes are recorded in the generated report.

Two independent sampling/photometric probes were rejected before integration: one-pass source-to-final warping reduced exact answers to 282/297, raised uncertainty to 15, and introduced 3 unsafe ambiguous decisions; 2× raster sampling with scaled blur did not beat the baseline. The relative-cell sigma candidate (12 px) kept 290/297 but changed one ambiguous IMG_1024 answer into an unsafe E decision. Retain the current conservative path.

Machine-readable per-sheet reports and registration previews are local, ignored UAT artifacts under:

- `docs/evidence/vol8-document-normalization/accuracy-final/report.json`
- `docs/evidence/vol8-document-normalization/registration-final/report.json`
- `docs/evidence/vol8-document-normalization/registration-final/normalized/`
- `docs/evidence/vol8-document-normalization/registration-final/grid-overlays/`

## Generic/layout and safety validation

- `tests/test_document_normalization.py` has **19 passing tests**. The broader focused suite passed **52 tests**, including review UI, Vol.8 registration, and the existing Vol.5/6/7 tests.
- Manual perspective normalization is exercised against all three built-in layouts (default-1/2/3). Synthetic phone-photo detector checks cover rotation, perspective, distance, shadow/uneven lighting, background clutter, partial border, warm/cool lighting, and blur. These are robustness/geometry tests, **not** accuracy evidence.
- EXIF orientation, immutable source bytes, corner validation, candidate diagnostics, low-confidence review gating, and a registration-failure stage/candidate report are directly tested.
- Experiments did not establish improved answer recognition from more aggressive photometric or resampling changes. The attached CamScanner screenshots are qualitative reference only; no claim is made that synthetic cases replace real phone-photo/manual teacher UAT.

## Full checks and package

- Full source suite: **172 passed, 3 skipped, 10 failed**. The 10 failures are the same existing baseline failures: 8 registration/grid-quality rejections, the v12→v13 migration assertion (current schema is v14), and the Windows Documents-path write denied by this macOS sandbox. No new failing tests appeared versus the recorded 152/3/10 baseline; this task added 20 passing tests.
- Ruff passed for changed source/tests/UAT files. Mypy passed for the five changed source modules checked.
- Rebuilt local `dist/ExamGrader.app` on macOS arm64 (234 MB, ad-hoc signed). `codesign --verify --deep --strict`, packaged `--self-check`, offscreen `--smoke-settings` (three built-in templates), and offscreen `--smoke-ui` passed using disposable data.
- No DMG was rebuilt, and no release, commit, or publish was performed. Packaged smoke is not manual crop-dialog acceptance or native teacher UAT.

## Remaining acceptance gaps

- The task's accuracy DoD requires a real, adjudicated Vol.8 improvement; the measured answer result is unchanged, so this is the principal blocker to calling the feature ready.
- Visual labels remain provisional. Product Owner truth adjudication and interactive macOS teacher UAT of the new corner editor are not complete.
- The synthetic photo variants do not establish robustness on the user's full-resolution phone photos, all paper colors, severe occlusion, or low-contrast borders. Weak/unverifiable cases must stay review-required; do not claim universal smartphone-photo support.
- Storage remains source + structured transform/diagnostics; normalized pixels are regenerated on demand. If future users need exported normalized documents, that is separate storage/product scope.

## 2026-09-15 — Real-photo boundary follow-up

This checkpoint resumes only physical-page boundary/crop, perspective normalization, and fine registration. It does not change OMR thresholds, student-number handling, or scoring/review/export behavior.

- The boundary detector now retains multi-scale closed-edge proposals and their supporting proposal methods. Physical-corner selection is reported separately from the final registration transform; corroborated physical proposals are compared using the known page/grid evidence. The low physical-boundary confidence gate now also keeps normalization in review. Original photo bytes remain unchanged.
- Crop/registration replay: `/private/tmp/vol8-registration-uat-20260915-final/report.json`. It processed 10/10 photos; all selected registration transforms were `green-print-quad`, maximum mean grid residual was 1.954 px, and minimum alignment confidence was 0.8572. This replay uses the built-in reference and is supporting registration evidence, not the teacher-corner acceptance result.
- Teacher-reviewed replay: `/private/tmp/vol8-production-uat-20260915-final2/report.json`, checked against the unchanged 10-photo fixture set and the teacher export. It processed 10/10; 295/300 answer states and 291/295 confirmed single choices matched; unsafe confident mismatches fell from 2 to 0 after low-boundary cases were held for review. Seven sheets require manual intervention, and four still meet the runner's manual-corner-adjustment criterion. Worst grid residual is 6.483 px and minimum alignment confidence is 0.5654. The feature acceptance remains open.
- On the seven teacher-adjusted crops, the selected automatic physical corners differ from the teacher-selected corners by at most 58.3 px for IMG_1023, 36.4 px for IMG_1024, 34.1 px for IMG_1025, 46.2 px for IMG_1026, 38.8 px for IMG_1027, 30.2 px for IMG_1029, and 26.1 px for IMG_1030. These comparisons show improved boundary proposals, but do not erase the four low-confidence/manual-corner flags or substitute for interactive teacher acceptance.
- IMG_1028 now uses a physical page edge with 0.8345 boundary confidence; its teacher replay residual is 2.739 px, line coverage 1.000, and alignment confidence 0.8313. This is improved evidence for this fixture, not a claim of general camera-photo acceptance.
- The independent provisional visual-label guard is `/private/tmp/vol8-accuracy-boundary-final/report.json`: 288/297 exact, 9 uncertain, 0 wrong, 0 unsafe decisions on the three ambiguous labels. The ambiguous IMG_1024 Q27 remains machine-uncertain in this guard. The separate teacher export labels that same row E, so keep these datasets and denominators distinct; no OMR change was made.
- Focused cross-layout and crop suite: 60 passed, including Vol.5/6/7 and Vol.8 normalization/registration/hardening tests. Targeted Ruff and `git diff --check` passed. No app build was made because crop acceptance remains open.

Next work should address the four manual-corner flags with stronger physical-edge evidence while retaining the existing confidence/review gate. Do not raise confidence solely because the answer grid fits, do not tune OMR, and keep IMG_1024 Q27 uncertain under the provisional visual-label guard.

## 2026-09-15 — Checkpoint and Product Owner trial build

- The current usable crop/registration + OMR fail-safe slice is checkpointed at `b69ce93624ea3088cc2fbb12ff9aa579c360e265` on `fix/vol8-current-usable-checkpoint`, pushed to `origin`.
- Fresh app: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app` (macOS arm64, 234 MB). `codesign --verify --deep --strict`, packaged `--self-check`, and offscreen `--smoke-ui` passed. Focused Vol.8 checks passed 8/8; registration replay passed 10/10 with residual max 1.954 px and confidence min 0.8572.
- This build is a local Product Owner trial artifact, not a release. The acceptance gaps remain unchanged: four manual-corner flags in teacher replay, provisional guard 288/297 exact with 9 uncertain, and `IMG_1024 Q27` review-required.
- Unrelated dirty source/tests and untracked Vol.8/Vol.9 fixtures were preserved outside the checkpoint. Do not treat the checkpoint as absorbing those files.

## 2026-09-15 — Follow-on review and student-number UAT slice

This follow-on slice is intentionally separate from the physical-boundary acceptance evidence above. It does not reopen crop/registration or tune OMR.

- Review now auto-accepts only unambiguous current single marks/normal blanks. Multiple marks, boundary-crossing geometry, abnormal blanks, uncertain geometry, and student identity remain review-required. The new bulk action confirms each selected row's measured prefill independently; the existing manual and uniform-bulk edits remain available.
- Student-number v6 uses an expanded ROI, form/reference/line suppression, connected-component candidate grouping, touching-stroke splitting, digit-only 0–9 recognition across multiple preprocess variants, measured voting, and review-only shape suggestions. Roster/range is validation only. The local backend is Tesseract; no MNIST accuracy claim and no local ONNX model was introduced.
- On the real Vol.8/Vol.9 fixture labels, candidate visibility union improved Vol.8 **5/10 → 8/10** and Vol.9 **8/12 → 11/12**; primary candidates remained **2/10** and **4/12**. These are candidate-recall observations, not accepted identity accuracy; all identities remain teacher-confirmation-required.
- Focused verification: **92 passed**; changed-file Ruff and `git diff --check` passed. Fresh `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app` passed strict deep codesign, disposable-data `--self-check`, offscreen settings smoke, and offscreen UI smoke. No release/tag/publish was performed.
- Remaining UAT uncertainty: Product Owner must test the new review/bulk flow on real sheets; identity labels still need teacher confirmation; immutable originals/provenance and fail-closed uncertainty remain required. Keep `IMG_1024.jpg Q27` uncertain/review-required.
