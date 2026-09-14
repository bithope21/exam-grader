# Antigravity handoff

## Current handoff — 2026-09-14 (Production-Ready OMR & Identity Detection Hardening)

OMR Answer Detection and Student Number Identity recognition on real exam sheets (Vol.7 Shopee 60Q/5C) have been hardened and verified:
- **OMR Accuracy:** 98.3% single mark resolution (177/180) across real outdoor sheets.
- **Student Number Recognition:** 100% (6/6) accurate recognition without teacher correction (1, 3, 12, 13, 27, 49).
- **Test Suite:** 148 passed, 3 skipped in 82.12s (`uv run pytest tests/`).
- **macOS App:** `dist/ExamGrader.app` rebuilt, codesigned, `--self-check` passed, `--smoke-ui` passed.
- **Windows UAT Plan:** Windows test runner should checkout branch `fix/vol7-omr-identity-hardening` and run the exact UAT commands below.

## Previous handoff — 2026-09-12

Windows packaging and UAT have **never been executed**. See [WINDOWS_UAT.md](WINDOWS_UAT.md) for the full investigation, known risks, and next steps.

**Current Windows readiness:**
- PyInstaller build on Windows: **NOT RUN**
- Inno Setup installer: **NOT RUN**
- Tesseract OCR (Windows binary): **NOT TESTED**
- OpenCV SIFT / PySide6 on Windows: **NOT TESTED**
- Thai font rendering on Windows: **NOT TESTED**
- Self-check / smoke-ui from packaged build: **NOT TESTED**
- Clean-machine non-developer UAT: **NOT TESTED**

This blocks G1 (packaging spike requires separate Mac/Windows evidence per `docs/ROADMAP.md`) and G7 (release requires clean installation on declared OS/CPU matrix).

Source now uses OMR `omr-illumination-v4`, student-number `student-number-adaptive-roi-v4`, and schema 11 (`skipped_numbers`). Latest-key teacher confirmation gates student import and export. Sparse uploads do not imply a continuous roster; explicitly configured missing numbers can be skipped/restored without inventing scores. Review controls operate inline and clear stale row widgets.

The supplied vol.2 teacher labels contain three genuine adjudications: key Q28 has B/E marks, student 17 Q25 straddles B/C, and student 10 has competing OCR 40/10. Preserve these uncertainties rather than hardcoding teacher labels into recognition. Detector code never reads the frozen teacher-results fixture.

Final tests, native Cocoa screenshots, rebuilt app and package checks are owned by the user-requested Luna Max verifier. See its evidence report for actual completed checks. Live databases and historical exports remain untouched. Workspace has no Git repository.

Updated: 2026-09-08 | Current gate: G0 open + G1 foundation partial, G5/G6 prototype | Current decision: WF-001 open

## Verified current state

- มี handoff เดิม + reference PNG 4 ภาพ; Codex อ่าน handoff ทั้งฉบับและดูครบ 4 ภาพ
- ยังไม่มี Git repository, model, production template หรือ installer
- ผู้ใช้อนุญาต Codex ต่อจนสุดที่พิสูจน์ได้: `src/exam_grader/` มี desktop shell, SQLite, import integrity, draft OMR, manual review, deterministic grading/export และ tests; production-calibrated digit recognition ยังไม่ complete
- macOS bundle build/self-check/offscreen UI: PASS; Windows packaging: NOT RUN; teacher UAT: NOT RUN
- Codex verification: 30 tests PASS; ruff + mypy PASS; original hashes unchanged 4/4. See `docs/evidence/FOUNDATION.md` and `docs/evidence/CODE_REVIEW.md`.
- Synthetic fixture verification: 58 manifest entries present; same-environment seed-42 regeneration byte-identical; current OMR benchmark rejects 58/58 at registration and auto-accepts 0. See `docs/evidence/SYNTHETIC_OMR.md`.
- Setup/run commands: README; execution evidence: `docs/evidence/FOUNDATION.md`

## Working agreement

Codex วางแผนและตรวจรับ Antigravity implement Product Owner ตัดสิน business rules ใช้ handoff เดิมร่วมกับ PRODUCT_SPEC; คำสั่ง user ล่าสุดมี precedence

อ่าน repo instructions ก่อนทำงาน; shell commands ต้อง prefix `rtk` ตาม `/Users/zubinpijit/.codex/RTK.md` ใน environment นี้ ห้ามแก้ originals หรือ handoff เดิม ไม่เพิ่ม cloud service ไม่แก้ scope/model/scoring/template support เงียบ ๆ งานที่เกิน brief ส่ง evidence กลับ Codex

## Completed brief: AG-001 — Reference inventory

Codex ทำเสร็จตามคำสั่งผู้ใช้ให้ต่อ: [report](evidence/AG-001/REPORT.md), manifest และ contact sheet อยู่ใน evidence folder Tests รวม 8 PASS; ไม่ต้องทำ inventory ซ้ำเว้นแต่ inputs เปลี่ยนหรือกำลังตรวจทวน

Objective: ทำให้ WF-001 มี evidence ตรวจซ้ำได้ โดยยังไม่เลือก production template

Owner: Codex (claimed/completed 2026-09-08); historical brief below preserved for traceability

Allowed changes:

- `tools/inspect/` สำหรับ reproducible inventory tool
- `docs/evidence/AG-001/` สำหรับ report, manifest, derived contact sheet
- `docs/AGENT_HANDOFF.md` เฉพาะ status/evidence ของงานนี้
- dependency declaration แบบ minimal ถ้าจำเป็นต่อ tool พร้อม exact setup instructions

Tasks:

1. อ่าน docs และตรวจ current files ก่อนเขียน; อย่าทับงานที่มีอยู่
2. Inventory ทุกไฟล์ใน answer-sheet: relative path, SHA-256, bytes, width/height, format; รายงาน decode error ชัดเจน
3. ทำ contact sheet ระบุชื่อไฟล์และภาพครบทุกใบลง evidence folder; ต้นฉบับ unchanged
4. เปรียบเทียบ visible layout: groups/rows/choices, printed inner boxes, header/number location, crop/glare และความต่างที่ต้องทดสอบ ห้ามสรุปเป็นหลาย template จาก visual difference อย่างเดียว
5. ผู้ใช้เลือกแบบหลักหนึ่งแบบแล้ว ให้ประเมิน candidate ภาพเวลา 07.58.58.png พร้อมเหตุผล/ข้อจำกัด; canonical geometry ยัง pending evidence ไม่รวมแบบอื่นใน support claim
6. ระบุ missing evidence: clean reference, real marked sheets/number crops และ ground-truth procedure ที่จำเป็นต่อขั้นต่อไป
7. ส่ง report พร้อม commands/exit codes, hashes before/after และรายการไฟล์ที่เพิ่ม

Acceptance:

- รายการครบ 4 ภาพที่มีอยู่ ณ baseline; หาก inputs เปลี่ยนให้บันทึกเพิ่ม ไม่ hardcode ผ่านด้วยเลข 4
- อ่านภาพได้หรือรายงาน failure อย่างตรงไปตรงมา
- Source hashes ก่อน/หลังเหมือนกัน; tool rerun ให้ inventory เดิมเมื่อ source ไม่เปลี่ยน
- Report links ใช้งานได้ และภาพ derived ไม่อ้างว่าเป็น clean canonical template
- ไม่มี accuracy claim, model download, runtime app, Git remote หรือ external publication

Verification by Codex: rerun inventory, independently compare source hashes/dimensions, inspect contact sheet/report, review allowed diff; ตัดสิน AG-001 แยกจากการปิด WF-001

Stop after AG-001 submission. อย่าเริ่ม full UI หรือเลือก scoring policy แทนผู้ใช้

## Next three steps

1. Product Owner จัดหา clean full-resolution blank reference และ real marked sheets/number crops พร้อม ground truth; จากนั้น Codex ตรวจ overlay และ resolve WF-001
2. เพิ่ม durable batch journal/restart recovery และ path-based exam package lifecycle ให้ครบ G1/G6
3. เมื่อมี corpus แล้ว benchmark/calibrate OMR และสร้าง narrow digit recognizer; หลังจากนั้นทดสอบ Windows build/installer และ clean-machine UAT

## Synthetic Dataset Status

### PO-confirmed macOS usability bounded implementation — 2026-09-08

- PO confirmed exam question count is selected at creation, constrained to 1–60,
  and authoritative after key approval. Default convenience is 60 but remains editable.
- Schema/domain now persist `question_count`; answer-key approval requires exact count
  and rejects student-purpose sources.
- Draft OMR now uses local-darkness/local-background features and emits photometric,
  per-cell, and stage diagnostics. On immutable real UAT fixtures, registration is
  6/6 accepted and all-five-choice false positives are 0; this is not accuracy evidence.
- Review UI now separates automatic state from teacher-confirmed answer and permits
  manual resolution of blank/multiple/uncertain key observations.
- Exam workflow is separated into `เฉลย / นักเรียน / ตรวจทาน / ผลลัพธ์`; processing is
  backgrounded with filename/progress, failed-import journal/retry, and output-root
  preference plus per-exam override.
- Evidence: [REAL_UAT.md](evidence/REAL_UAT.md) and
  [real-uat-regression.json](evidence/real-uat-regression.json).
- Verification: full pytest `37 passed`, ruff pass, mypy pass; macOS arm64 bundle
  rebuild passed, packaged self-check/offscreen UI smoke exited 0, and strict deep
  codesign verification passed. Offscreen real full-flow probe exported 5 checked
  images from a 30-question exam and preserved all source hashes; interactive PO
  teacher UAT is still separate. Windows, production accuracy, G3/G4/G7 remain
  deferred/blockers.

### Bounded geometry compatibility slice — 2026-09-08

- Synthetic page/grid/ROI geometry is now derived from the canonical versioned
  `src/exam_grader/resources/template.json`; duplicated renderer coordinates were
  removed. The last-row cell-bound bug was corrected and all 58 fixtures regenerated
  with seed 42.
- Added safe registration diagnostics (stage, match count, inlier ratio, coverage,
  timing) while preserving `ValueError` compatibility and fail-closed rejection.
- Benchmark now reports registration accepted/rejected, exact selected-question
  counts, review rate, aggregate timings, and keeps `auto_accept_count=0` by contract.
- Added geometry diff tool/test and a negative identity regression test. Current
  synthetic-vs-canonical diff is 0 px anchor/cell-center error and 1.0 ROI overlap.
- Header/barcode/text dependency is **not proven**: registration still uses the
  whole screenshot reference and no ablation claim is made. A clean full-resolution
  production reference is still required.
- Verification: full pytest `32 passed`; ruff `All checks passed`; mypy `Success:
  no issues found in 13 source files`; geometry diff is exact. Benchmark remains
  `registration_accepted=0`, `registration_rejected=58`, `auto_accept_count=0`.
  In-memory header-text ablation on the canonical reference was accepted, but this
  does not establish barcode or real-photo dependency behavior.
  Windows remains deferred.

- **Fixtures Directory**: `tests/fixtures/synthetic/` (`clean/`, `degraded/`, `edge_cases/`, `expected/`)
- **Generator**: `tools/synthetic/generate_dataset.py` (Deterministic PRNG seed: `42`)
- **Disclaimer**: Fixture ชุดนี้เป็น **synthetic/provisional เท่านั้น** สร้างขึ้นเพื่อให้ Codex ใช้ทดสอบ OMR pipeline และ benchmark progression
- **Caution**: **ห้ามใช้ชุด synthetic นี้แทน real-world accuracy benchmark**, **ห้าม train digit model** จากชุด synthetic นี้ และ **ห้าม claim production OMR accuracy** จาก dataset ชุดนี้

## Copy/paste prompt

> อ่าน README.md, docs/AGENT_HANDOFF.md, docs/WAYFINDER_MAP.md และ docs/evidence/AG-001/REPORT.md ก่อนเริ่ม AG-001 เสร็จแล้ว อย่าทำซ้ำ ให้รับ scoped brief งาน geometry overlay ถัดไปจาก Codex โดยเก็บ originals unchanged และไม่อ้างว่า draft coordinates เป็น production template

## Current frontier — 2026-09-08 continuous execution

Phase A inspected source, live SQLite read-only, confirmed run, fixtures and UI evidence. PO approved [TASK_SPEC.md](TASK_SPEC.md) for bounded continuous execution. Slice A provenance harness, Slice B review layout, Slice C conservative diagnostics, Slice D review-required number baseline, Slice E identity/missing UX, Slice F export registry/index, Slice G archive/restore, Slice H canonical checked renderer, and Slice I bounded regression are complete. Historical key Q6 C versus visual/machine A remains excluded from recognition truth; preserve the historical run. Runtime auto-accept remains disabled. The workspace `.git` directory is read-only in this environment, so commit checkpoints cannot be created; changed paths and exact test evidence are recorded here instead.

Intermediate verification: full pytest `43 passed`, ruff pass, mypy pass; real fixture benchmark
6/6 registered, all-choice false positives 0, auto-accept 0; identity benchmark 6/6
review-required with no accuracy claim. Checked overlay was visually inspected from a
real fixture and score ROI was readable. Exact commands are the TASK_SPEC commands plus
`tools/benchmark/identity_benchmark.py`; macOS bundle rebuild/smoke remains to run after
the final source checkpoint.

Final verification after the bounded pass: pytest `45 passed`, Ruff pass, Mypy pass
(15 source files). Real benchmark remains 6/6 registration, 0 all-choice false
positives, 0 auto-accept. Identity benchmark is 6/6 review-required with accuracy
null. `scripts/build/build.py`, strict deep codesign, packaged self-check and
offscreen smoke all passed on macOS arm64. No Git commit could be created because
the supplied `.git` directory is read-only; this is an environment limitation, not
a source or test failure. Next safe action is Product Owner interactive UAT at the
listed window/DPI sizes and review of the generated checked images/results index.

Disposable real-fixture E2E also passed after the final renderer/lifecycle changes:
5 students, scores `10/6/12/26/8`, 5 checked images, export registry and readable
index present, all five source hashes verified. The numeric baseline yielded no
usable candidates on the five student sheets; all remained review-required and
none was auto-accepted.

## Final polish checkpoint — 2026-09-08

The next-action polish is complete in source and evidence. `template.json` is now
`thai-main-draft-v2`: the registered student-number ROI is `[590,73,692,107]` and
the printed score ROI is `[712,51,808,120]`. `identity.py` performs source-resolution
ROI extraction, local-lighting/ink segmentation, diagnostic crops and a pinned
numeric-only Tesseract observation. It emits candidates, competing candidates,
backend/version/hash provenance and review reasons; it does not establish an
authoritative identity or auto-accept. On the five real sheets the primary
candidates match the existing teacher-confirmed numbers 1–5; ambiguous alternatives
remain visible for 1 and 3. Evidence: `docs/evidence/polish/identity-benchmark-final.json`.

`exporting.py` now centers responsive score text inside the real upper-right score
box, keeps overlays on derived images, names images `เลขที่-NN.png` with collision
fallback, and publishes `ผลการตรวจ/<timestamp>/` under a sanitized human-readable
exam folder. Technical JSON is under `_system`; registry/reveal uses the published
run path. `review_ui.py` and `exam_ui.py` were rechecked at 1024×768, 1440×900 and
maximized macOS windows. Screenshots, number diagnostics, score/header/grid crops,
directory tree and hash checks are under `docs/evidence/polish/final-native/` and
`docs/evidence/polish/final-offscreen-final/`.

Final commands and results: pytest `52 passed`; Ruff and Mypy passed; PyInstaller
macOS arm64 build passed; `codesign --verify --deep --strict` passed; packaged
self-check and packaged offscreen smoke exited 0. Originals remained hash-identical.
The workspace `.git` remains read-only, so no commit checkpoint is available.

## Latest bounded automation pass — 2026-09-08

The current implementation has 62 passing tests and has been exercised with
disposable data against the corrected teacher run: 180/180 answer decisions
match, scores are 10/6/12/27/8, and one bulk identity action completes the five
sheets. Review is exception-only with inline controls and image crops; attendance
states are exported without fabricated scores. See `docs/evidence/automation/`
and the latest addendum in `progress.md`.

## 2026-09-13 — Calibration hardening continuation

Calibration changes are in the working tree and intentionally uncommitted. The proven
Vol.7 root cause was interval grouping: 24 vertical dividers were treated as
four-choice groups, so question-number dividers became answer columns. Candidate
contour ordering also let a narrow overlapping contour hide the full answer table.
The detector now infers the repeated number-divider lattice, retains the broad table,
and emits conservative geometry provenance and review warnings.

`src/exam_grader/calibration_model.py` is the canonical editor model. `AnswerBlock`
boundaries remain the sole OMR geometry source. Explicit line editing supports row or
column movement and add/delete; `user_edited` survives serialization and late detector
results are revision-gated. Vol.7 overlay and metrics are under
`docs/evidence/calibration-hardening/after/`.

Validation: 7 new geometry tests, 24 calibration/template tests, and the relevant full
regression (129 passed, 3 skipped). The one real-Documents UAT is sandbox-deselected;
Vol.7 has no answer adjudication, so its OMR smoke is reachability evidence only.

## 2026-09-13 — Vol.7 keyyy and distribution refresh

`ถ่ายในที่แจ้ง/keyyy.jpg` is now recorded as a teacher-key evidence sheet. The
red-ink overlay confirms Q1–Q30 selections, including the Q4 A+D multiple mark;
Q31–Q60 remain blank. See
`docs/evidence/calibration-hardening/after/vol7-keyyy-answer-key.json` and its
overlay. This source-backed observation still requires teacher adjudication for
the multiple mark and does not change grading semantics.

The current macOS arm64 PyInstaller bundle was rebuilt after the calibration
changes. Strict deep codesign, packaged self-check, template-settings smoke, and
offscreen UI smoke all passed against disposable data. The prior UI screenshot was
an old `dist` artifact; quit it and reopen `dist/ExamGrader.app` to load the
generalized detector and template resources. Windows and interactive native teacher
UAT remain unverified.
