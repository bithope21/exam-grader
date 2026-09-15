# Fresh-Chat Handoff: Exam Grader v1.0.2 & Upcoming Session Roadmap

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
