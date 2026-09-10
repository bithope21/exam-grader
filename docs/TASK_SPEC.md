# Exam Grader — bounded improvement task spec

## Latest authorized scope — 2026-09-09

The user authorized autonomous repairs for `tests/fixtures/real/vol.2`, comparison with their corrected 40-question export, preservation of vol.1 behavior, explicit key confirmation before student import, and smooth sparse-roster/inline-review handling. Tests/OCR/package verification are delegated to Luna Max at the user's explicit request. This supersedes older pending-approval/next-step wording below for this scope. No live data rewrite or general accuracy claim is included. Current implementation and acceptance evidence are linked from `../progress.md` and `evidence/vol2/validation.md`.

Date: 2026-09-08
Status: APPROVED FOR EXECUTION — 2026-09-08
Scope owner: Product Owner; engineering follows the latest chat authorization.
PO approved this execution contract in chat on 2026-09-08. Implementation remains bounded by the protected boundaries and approval gates below.

## Decisions and protected boundaries

- Offline/local-first, existing Thai paper, CV/OMR first, narrow local ML only where evidence supports it.
- Preserve immutable originals, authoritative exam question count (1–60), key versioning, stale-result rejection, background processing, failure isolation and retry.
- No Windows work, cloud service, silent training/model downloads, broad redesign, production accuracy/readiness claim, or G3/G4/G7 closure.
- PO says key question 6 was probably selected incorrectly. Treat visual A as a candidate requiring explicit adjudication, not permission to rewrite historical C or rescore the live exam.
- Best-practice defaults proposed here: retain external exports on exam deletion; recoverable managed-data deletion; optional expected number range 1..N; initialize local Git only after implementation approval, with a reviewed baseline allowlist and no remote/push.
- Approval of this spec permits bounded engineering in isolated test data; it does not permit destructive operations on the live exam or rewriting historical runs. Actual user-facing Delete remains a separately confirmed application action.

## Inspected baseline and provenance

Source root: `/Users/zubinpijit/private/exam-grader` (no Git repository at inspection).
Live DB: `/Users/zubinpijit/Library/Application Support/ExamGrader/exam-grader.sqlite3`, schema v7.
Confirmed run: `/Users/zubinpijit/Desktop/exam-grader1/1ddd200c-43eb-47c4-bebd-e61bb435d255/run-8ce2f112-9395-4584-ad5f-955eadd097c1`.
Real fixtures: `tests/fixtures/real` (5 students, 1 key).

Inspection verified all seven manifest artifact hashes, exported key/reviews against DB, student source hashes against fixtures, and Excel scores 10/6/12/26/8 out of 30. Two live exams share six content-addressed source blobs. Preserve both exams throughout engineering.

| Active 30-question sheet | Single | Multiple | Uncertain |
|---|---:|---:|---:|
| IMG_0791.JPG | 28 | 1 | 1 |
| IMG_0792.JPG | 28 | 1 | 1 |
| IMG_0793.jpg | 29 | 1 | 0 |
| IMG_0794.jpg | 29 | 0 | 1 |
| IMG_0795.jpg | 20 | 0 | 10 |
| key.JPG | 28 | 0 | 2 |

Registration 6/6; uncertainty 15/180; all images still require review, so human-review scope is 180/180, not 15/180. Auto-accept 0; accepted-subset error rate is undefined. One six-image source probe took 1.99 seconds excluding review/export; not a throughput guarantee. Existing synthetic corpus has 58 registration rejections and must remain visible in reports.

Baseline algorithm: EXIF decode → bounded ORB extraction → ratio matches → RANSAC homography → coverage checks → 836×818 canonical image → Gaussian local background sigma 9 → darkness >30 density → selected >=0.10, any density in [0.025,0.10) makes the question uncertain. Version: draft-omr-local-ink-v2. No calibrated confidence or digit model.

Key Q6: machine selected A with uncertain state, historical approved answer C; source visually appears A. Other student uncertainties retain the same selected candidate after human confirmation. This supports testing false-uncertainty reduction, not blanket threshold relaxation.

## Common delivery contract

Each slice: inspect current files/state → record assumptions/design → bounded implementation → focused tests → applicable regression → inspect actual UI/artifacts → update existing docs → allowlisted local commit checkpoint. Do not spawn agents or alter ownership without applicable authorization.

Before implementation: inventory files and hashes; establish reviewed Git baseline excluding originals, real/private data, live DB, generated exports, caches, environment and build products. Do not reset/clean or automatically add the whole tree. Do not commit models or fixtures without checking provenance/license/privacy. Maintain local evidence without requiring those bytes in Git.

All migration/recovery/UAT work uses disposable data directories or verified SQLite backup copies. Do not call normal writable Workflow methods on the live DB during inspection. Never copy an active SQLite main file alone as a reliable backup.

Each slice submission states changed paths, exact commands/exit codes, config/template/model versions, metrics with denominators, artifacts and limitations. Update DECISIONS, TEST_STRATEGY, AGENT_HANDOFF and ARCHITECTURE where relevant; preserve historical evidence rather than rewriting old results as new results.

## Slice A — Golden labels and comparable evaluation

Dependencies: approval of this spec. First implementation slice; no recognition threshold changes.
Likely paths: tools/benchmark, tests/test_real_fixture_benchmark.py, docs/evidence/REAL_UAT.md, existing evidence metadata; small versioned label schema as needed.

Deliver:
- Verify fixture/run hashes and preserve the original run snapshot.
- Distinguish machine observation, teacher decision, visual annotation, adjudication status and scoring-key version. Retain source/detection/review IDs, source hash, question bounds, timestamp and label origin.
- For multiple marks, preserve exact marked choices where human-annotated; historical final value `multiple` alone does not supply that truth. Unadjudicated fields are excluded from the corresponding metric and counted explicitly.
- Present Q6 crop plus A/C discrepancy for PO adjudication. Preserve historical key C and historical scores. Any later live correction must create a new approved key and leave old output immutable; never silently rescore.
- Compare BEFORE/AFTER on identical corpus IDs/config manifests: exact choice+state accuracy, confusion matrix, unresolved/excluded counts, review burden, auto-accept coverage/error, registration, per-stage time and batch time.
- Use sheet-grouped validation; never split transformed copies across folds. Record whether author identity is known; six sheets do not establish generalization to new writers. Freeze evaluation definitions before tuning. Use nested or separate calibration where thresholds are selected; revisited held-out data is no longer unseen.

Acceptance: reproducible baseline from immutable sources; independently checkable label provenance; unresolved Q6 never silently becomes training truth; regression catches a deliberately wrong prediction; no fabricated 0% accepted error for zero coverage. Scoring golden and recognition golden remain separate.

## Slice B — Review layout and confirmed-state fidelity

Dependencies: A contracts; can proceed while additional labels await adjudication.
Likely paths: review_ui.py, tests/test_ui.py, tests/test_desktop_workflow.py.

Deliver:
- Primary aligned image with aspect-preserving fit and resize handling; original in secondary zoomable viewer. If registration is invalid, show explicit failure and original/manual review path; never fabricate alignment.
- QSplitter with non-collapsing useful panels; table columns: question, machine result, status, confirmed answer. Font-aware sizing and stretch, vertical scrolling; no hidden clipped controls as a substitute for solving horizontal overflow.
- Verify at logical window sizes 1024×768, 1280×800 and 1440×900, at applicable 1×/2× DPI. Smaller unsupported sizes retain a usable fallback rather than clipping confirmation actions. Fit whole sheet by default; allow intentional detail zoom for faint ink.
- Reopening approved key preloads that key's confirmed answers, while displaying machine observations separately. Bind confirmation to the exact observation/key revision shown. Do not attach a newer unseen detection at save time.

Acceptance: no table horizontal scrolling at listed normal desktop sizes, all choices/confirmation actions reachable, image not stretched; real key Q6 historical C survives reopen without reconfirmation from detector defaults; stale dialog/new detection tests; invalid-registration fallback and authoritative count preserved.

## Slice C — OMR evidence-driven improvement

Dependencies: A adjudicated labels/harness; B facilitates manual verification.
Likely paths: imaging.py, benchmark tools, targeted imaging tests, versioned feature configuration.

Deliver experiments for local background/template-relative ink, top-two margin, contrast, stroke structure and perturbation stability. Explain error examples with cell diagnostics rather than tuning individual sheets. Cache invariant template features only with version-aware correctness checks.

Acceptance: same-corpus uncertainty decreases by at least one adjudicated case without increasing confident wrong candidates or hiding uncertain/multiple/blank cases; report absolute counts, confusion and fold results. Registration remains 6/6 on current real corpus; all-choice false positives remain zero. Existing synthetic rejection remains reported; add appropriate registration-independent cell tests and degraded real derivatives, without presenting them as independent real samples.

Auto-accept remains disabled by default. Experimental offline eligibility may be measured separately from actual application acceptance. Enabling runtime auto-accept requires a later PO-approved evidence gate with corpus coverage, acceptable error/coverage and calibration criteria; zero observed errors on six sheets is insufficient. If no safe gain is demonstrated, retain baseline and report the experiment as inconclusive.

## Slice D — Student-number dataset and local recognizer benchmark

Dependencies: A provenance, registered ROI validation; independent of OMR algorithm changes.
Likely paths: new small identity module, imaging/template integration, tools/benchmark, models/README.md, targeted tests. Dependency additions only if a selected experiment needs them.

Deliver:
- Version/verify existing number ROI (currently 87×25 canonical pixels); extract from high-resolution decoded source using the transform, avoiding unnecessary downsampling.
- Benchmark installed numeric-only Tesseract baseline, then segmentation + small local digit model if justified. ONNX Runtime is an execution option for a chosen model, not an independent recognizer. Sequence recognition only after documented segmentation failures.
- Contract: candidates, proposed value, raw score and calibration semantics, model/config/hash, ROI/segmentation diagnostics, review reasons. Human-confirmed identity is a distinct authoritative revision.
- Cases: one/multiple digits, 1/7, 3/8, 5/6, faint/touching/spaced digits, corrections/overwriting, blank and unreadable. Mark unavailable real cases as corpus gaps; synthetic coverage is not handwriting accuracy evidence.
- No training on corrections automatically. Model promotion requires explicit version, license/source/hash, evaluation and packaged offline smoke; no runtime download.

Acceptance: exact whole-number benchmark, coverage/error and timing; no silent guesses, blank != zero, unusable ROI rejected. With insufficient real data deliver a review-required candidate path and dataset harness, not a production recognizer claim.

## Slice E — Student identity and missing-number UX

Dependencies: D observation contract (manual fallback allowed), B review revisions.
Likely paths: exam_ui.py, workflow.py, storage.py and focused workflow/UI tests.

Deliver numeric ascending/descending sorting, inline edit+explicit save/cancel, teacher-friendly status and duplicate highlighting. Show “ครูยืนยันแล้ว” separately from model confidence. Until calibrated, display “ต้องตรวจทาน”/“ยังไม่ประเมิน” rather than unsupported high confidence. Raw scores remain in details.

Persist optional expected number range 1..N per exam; absent means only “เลขที่ขาดภายในช่วงที่พบ”. Use authoritative confirmed identities for definitive gap/duplicate/export checks; pending predictions appear separately and must not silently close gaps. Unresolved sheets make completeness provisional. Expected range is advisory and does not silently change grading eligibility.

Acceptance: 1,2,10 numeric sorting; Thai-digit normalization and leading-zero duplicate identity preserved; duplicate, invalid, uncertain and out-of-range visible. For observed 1..30 with no range, never claim 31 missing; with expected 1..31, report 31. Inline human edit retains machine prediction, propagates to score/export/filename and invalidates newer-current-output status without deleting old runs. Key-stale answers cannot become fresh via an identity-only edit.

## Slice F — Human-readable export lifecycle

Dependencies: A snapshot contracts, E identity revisions.
Likely paths: exporting.py, storage.py, preferences.py, exam_ui.py, test_export.py.

Persist per-exam output override and export history with exam/run IDs, timestamps, snapshot fingerprint, artifact hashes, selected root and lifecycle state. Display resolved location and reopen/reveal history after app restart; unavailable external disks show an actionable state.

Naming: readable stored metadata (year/grade/room/subject/name/question count), timestamp plus stable unique suffix; Unicode normalization, reserved-character/name handling, bounded path length and collision safety. Do not infer calendar conversion or school level from ambiguous existing metadata. Freeze chosen folder name for each export; old runs remain unchanged.

Retain staging + atomic publication; snapshot fingerprint includes key, source set, review/identity revisions and relevant renderer/template/config versions. Journal publication and reconcile crash windows so a published run does not become invisible if DB recording fails. Only clean owned staging entries with verified boundaries.

Acceptance: Thai/Unicode/reserved names, repeated exports, same metadata, external override restart, permission/file destination failures, disk unavailability, stale changes during export and crash-after-publish recovery. JSON/Excel/checked derive from one snapshot. No migration/move of historical user output required; explicitly register verified legacy runs if needed.

## Slice G — Recoverable exam deletion and storage visibility

Dependencies: F export ownership/history, schema migration/recovery contracts.
Likely paths: storage.py, imports.py, ui.py, lifecycle adapter and focused recovery tests.

Main list provides exam metadata, managed storage explanation and reveal actions. Delete confirmation includes exam name/subject/class/room, source/review/run counts, shared-file retention and external-export retention. Block deletion while the exam has active workers/review/export operations and recheck in the service layer.

Default: archive exam into an app-managed recoverable state, hidden from active list and restorable from a small deleted-exams view. Preserve original blobs while any active or recoverable exam references them. Retain externally exported runs by default and show their location; never recursively delete their parent directory. Explain that recoverable deletion does not immediately reclaim disk space.

Use transactional tombstone/state and an operation journal for any necessary filesystem move. Recovery is idempotent after interruption; restore must recover key/reviews/identities/export links. DB foreign keys and path/symlink boundaries must be checked. No automatic expiry or permanent purge in this slice; OS Trash is not used as a substitute for database recovery.

Acceptance: delete/restore one of two exams sharing all six blobs leaves the other intact; cancel changes nothing; repeated delete/recovery is safe; unrelated external files survive; active work cannot race deletion; failure/restart leaves either a visible exam or an explicit recoverable state, never unexplained orphan state. Test only disposable exams, not the live PO exam.

## Slice H — Teacher-like checked images

Dependencies: A scoring truth, F snapshot/export, validated geometry. Can prepare visual proposal earlier, but rendering semantics require PO approval.
Likely paths: exporting.py or separate renderer.py, resources/template.json, image/renderer tests.

The PO delegated this visual choice to best engineering judgment. The implemented
mock uses a small red check for correct, red X for incorrect, outlined cell/`!` for
blank or multiple, and total score `n/N` in the score ROI. It was inspected on a
real derived image; student ink remains visible and the rationale is recorded in
DECISIONS.md.

After approval: template owns score ROI and cell geometry; render canonical-coordinate overlay transformed onto a full-resolution derived source copy. Use saved registration rather than rerunning a potentially changed detector. Preserve decoded orientation mapping and version all geometry/config/renderer artifacts. No OCR to rediscover score/cell positions. Missing/untrusted registration must prevent a misleading overlay and produce explicit review/error behavior.

Acceptance: visually inspect alignment at full resolution for all six source geometries, no marks beyond active count, score text fits ROI for 1..60 questions, source bytes unchanged, exact snapshot score in image/Excel/JSON. Regeneration from structured snapshot + verified source/template assets is deterministic in the pinned environment. Keep cross-platform pixel differences distinct from semantic correctness.

## Slice I — Full regression and bounded macOS acceptance

Dependencies: accepted B–H; any model/auto-accept blockers remain explicit.

Use the same immutable real inputs with disposable data: create/open 30-question exam → explicitly adjudicated key → import five student sheets → processing → number candidates/manual fallback → review/corrections → grade → annotated checked/score box → Excel → readable result folder → restart/reveal → delete/restore lifecycle. Never invent teacher confirmations to claim manual UAT.

Report BEFORE/AFTER uncertainty, actual human review scope, experimental eligible count, actual accepted count/errors, number exact-match/coverage, registration and timing, output hashes, residual failures and corpus gaps. Historical C-key run and corrected-key test results must be labeled separately; changes in key cannot be attributed to recognition improvement.

Run focused tests per slice and full checks at checkpoints:

```sh
rtk proxy env QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
rtk proxy .venv/bin/ruff check .
rtk proxy .venv/bin/mypy src
```

When changes affect UI/runtime/dependencies/packaging, rebuild and execute existing packaged self-check/offscreen smoke with disposable data; inspect current CLI options before choosing exact smoke invocation:

```sh
rtk proxy .venv/bin/python scripts/build/build.py
rtk proxy codesign --verify --deep --strict dist/ExamGrader.app
```

Record exact actual self-check/smoke commands in evidence; do not assume source tests prove bundle behavior. PO performs interactive macOS review at supported sizes, checks annotations/score and approves teacher UX. Windows and clean-machine production release remain deferred.

## Approval gates and completion

1. COMPLETE: PO reviewed and approved this scope for continuous bounded execution.
2. Slice A: PO adjudicates key Q6 visual/scoring intent. Other safe harness/UI work can proceed if this one label remains excluded.
3. Slice H: COMPLETE for the delegated visual semantics; future visual changes remain
   a separate product decision.
4. Any runtime auto-accept promotion: separate evidence/PO gate; not implicitly included here.
5. Final: distinguish source checks, packaged smoke and actual PO manual UAT. A bounded slice pass never closes production gates automatically.

Next action: finish Slice I verification, record source/build/UAT boundaries and report residual limitations. No giant patch.
