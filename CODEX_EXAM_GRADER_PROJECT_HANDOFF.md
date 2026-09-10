# Codex Project Handoff — Offline Cross‑Platform Exam Grader

> **Role:** Codex is the initial Project Lead / Systems Architect.  
> **Goal:** Build a production-ready desktop program for teachers that grades the existing Thai answer-sheet format from photographs, works fully offline, and can be installed on both macOS and Windows by normal end users.
>
> **Target workspace:**  
> `/Users/zubinpijit/private/[project-name]`
>
> Replace `[project-name]` with a short, stable repository/folder name after inspecting the project intent.  
> Suggested working name if no better name is chosen: `exam-grader`.

---

## 0. Operating instruction for Codex

Start by reading this entire handoff.

### First action

1. Inspect the environment and available skills.
2. If any material architectural/product decision is still genuinely unsettled, invoke `/wayfinder` and resolve it before implementation.
3. Do **not** use `/wayfinder` for trivial naming/style decisions that can be chosen safely using standard engineering practice.
4. Once the major decisions are settled:
   - create the project workspace,
   - write the long-term implementation plan,
   - create the folder/schema foundations,
   - begin implementation in phases.
5. Keep the project continuously runnable and testable.
6. Do not jump straight to UI polish before the recognition pipeline is proven.
7. Preserve a clear handoff trail so Antigravity or another coding agent can continue later without rediscovering architecture.

### Codex should act as

- project architect,
- engineering lead,
- test owner,
- technical documentation owner,
- initial implementation owner.

Antigravity may later work as a secondary coding/operator agent. Therefore architectural decisions, test contracts, data schemas, assumptions, and known limitations must be written down in the repository.

---

# 1. Product Goal

Build an **offline desktop exam-grading application** for teachers using the existing paper answer sheet supplied by the user.

The application must:

- work without cloud APIs,
- run on macOS and Windows,
- accept photographed/scanned answer sheets,
- detect the student's handwritten number,
- detect answers marked in the existing grid,
- compare them with a teacher-approved answer key,
- calculate the score,
- produce a visibly marked-up copy of each student's answer sheet,
- organize evidence/results into predictable folders,
- create an Excel score summary,
- surface uncertain detections for human review instead of silently guessing,
- preserve original images unchanged.

The final goal is a normal installable program, not a developer script.

---

# 2. Settled Product Decisions

Treat these as current product requirements unless implementation evidence shows a serious technical blocker.

## 2.1 Existing paper format must remain usable

Do **not** redesign the answer sheet around QR codes, barcodes, or bubble student IDs as a requirement.

The system must work with the existing sheet.

Future optional enhancements may support custom templates, but the first production path targets the supplied paper format.

## 2.2 Answer detection should not use general OCR

Use deterministic computer vision / OMR-style analysis for marked answer cells.

Preferred direction:

- OpenCV
- NumPy
- geometric registration
- perspective correction
- grid / region-of-interest extraction
- ink-density and mark-shape features
- blank/template comparison where useful
- confidence thresholds
- explicit states for blank / single-mark / multiple-mark / uncertain

OCR/AI should not be the primary mechanism for answers.

## 2.3 Handwritten student number is a narrow recognition task

Do **not** OCR the whole sheet.

Preferred pipeline:

1. register page to canonical template,
2. crop only the handwritten `เลขที่` region,
3. preprocess the crop,
4. segment/read digits,
5. use a small local digit-recognition model,
6. export/run through ONNX Runtime if appropriate,
7. attach confidence,
8. request teacher review when confidence is insufficient.

Tesseract may be retained as:

- a benchmark,
- fallback,
- debugging comparison,

but should not automatically become the production recognizer unless benchmarks show it is superior on the real dataset.

## 2.4 Human review is a first-class feature

The program must **never silently invent certainty**.

Examples that should enter review:

- low-confidence student number,
- duplicate student number,
- missing expected number,
- ambiguous mark,
- multiple marked choices,
- extremely faint mark,
- severe alignment failure,
- cropped/incomplete paper,
- inconsistent answer count,
- image quality below threshold.

Teachers should review only uncertain cases, not every sheet.

## 2.5 Originals are immutable

Never draw on or overwrite the input image.

Always produce a derived checked image.

---

# 3. Target User Workflow

## 3.1 Create / open an exam

Teacher launches the application.

Teacher selects or creates:

- academic year,
- class/grade,
- room,
- subject,
- exam name,
- exam date if needed.

Example:

```text
Academic Year: 2569
Grade: M.4
Room: 1
Subject: Mathematics
Exam: Midterm 1
```

The software creates or reuses the appropriate structured workspace.

---

## 3.2 Create the answer key

Teacher chooses:

**Create Answer Key**

Then:

1. upload / drag in a photographed completed answer sheet,
2. program normalizes orientation,
3. program detects the paper boundary,
4. corrects perspective,
5. aligns the page to the canonical template,
6. reads answer cells,
7. shows the detected answer key in a review UI.

Example:

```text
1  B
2  D
3  A
...
60 C
```

Teacher must be able to:

- inspect every answer,
- click/change answers,
- see uncertain detections,
- approve/save the key.

Only the **teacher-confirmed key** becomes authoritative.

Store the answer key in a machine-readable format such as JSON/SQLite and optionally export a human-readable version.

---

## 3.3 Import student answer sheets

Teacher selects:

**Import Student Sheets**

Support:

- single images,
- multiple selected images,
- folder import,
- drag-and-drop.

Likely formats:

- `.jpg`
- `.jpeg`
- `.png`
- `.heic`
- `.heif`
- `.tif`
- `.tiff`
- possibly `.webp`

Do not promise a format until the decoding library and packaging tests prove it works on both target OSes.

For each input image:

1. decode full-quality source,
2. apply EXIF orientation,
3. perform paper detection,
4. perform geometric normalization,
5. align to canonical template,
6. locate number region,
7. recognize student number,
8. detect answers,
9. calculate detection confidence,
10. classify as:
   - ready,
   - needs review,
   - failed / unusable.

---

## 3.4 Teacher review queue

Provide a clear queue such as:

```text
Ready                34
Needs review          3
Failed                1
```

Potential review cards:

```text
Image: IMG_2041.HEIC
Detected number: 17
Confidence: 0.97
Status: Ready
```

```text
Image: IMG_2042.HEIC
Detected number: 12
Confidence: 0.68
Reason: digit 2/7 ambiguity
Status: Review
```

```text
Image: IMG_2048.JPG
Detected number: 17
Reason: duplicate student number
Status: Review
```

Teacher can correct the student number and/or ambiguous answers before final grading.

---

## 3.5 Grade

After unresolved items have been handled:

Teacher presses:

**Grade / Generate Results**

For every accepted sheet:

- compare detected answers with approved key,
- calculate score,
- create a checked image,
- preserve source-to-output traceability.

Checked image should overlay, without obscuring evidence:

- detected answer indication,
- correct / incorrect indication,
- optional correct answer for missed questions,
- unanswered / multi-mark indication,
- student number,
- score such as `47 / 60`,
- optionally exam metadata.

Overlay coordinates must be generated from canonical sheet geometry and transformed accurately.

---

# 4. Output Structure

Exact naming can evolve, but the architecture must be stable, sanitized, collision-safe, and cross-platform.

Conceptual structure:

```text
ExamData/
└── 2569/
    └── M4/
        └── Room-1/
            └── Mathematics/
                └── Midterm-1/
                    ├── exam.json
                    ├── answer-key/
                    │   ├── source/
                    │   ├── normalized/
                    │   └── answer_key.json
                    │
                    ├── input/
                    │   └── originals/
                    │
                    ├── working/
                    │   ├── normalized/
                    │   ├── crops/
                    │   └── diagnostics/
                    │
                    ├── review/
                    │
                    ├── results/
                    │   ├── checked/
                    │   │   ├── 01_checked.jpg
                    │   │   ├── 02_checked.jpg
                    │   │   └── ...
                    │   ├── scores.xlsx
                    │   └── results.json
                    │
                    └── logs/
```

### Important

The application should not create huge permanent intermediate directories unless useful for:

- diagnostics,
- reproducibility,
- user-selected debug mode.

Normal operation should clean safe temporary files automatically.

---

# 5. Data Model

Prefer SQLite for internal application state.

The filesystem remains the human-visible evidence store.

Design a schema with migrations.

Potential entities:

```text
app_settings
classes
subjects
exams
answer_keys
answer_key_items
imports
source_images
students_or_sheet_identities
detections
detected_answers
review_items
grading_runs
grading_results
export_runs
```

Each important derived result should retain provenance:

```text
source image
→ normalized image
→ template/alignment version
→ recognizer version
→ detected number
→ detected answer
→ human correction if any
→ answer-key version
→ final score
→ checked image
```

Do not over-engineer student personal data for v1. A recognized student number may be sufficient unless the user later asks for name/roster integration.

---

# 6. Suggested Technology Stack

This is the current preferred direction, but benchmark and validate before permanently locking choices.

## Desktop

- Python 3
- PySide6 / Qt

## Computer vision

- OpenCV
- NumPy

## Image decoding / conversion

- Pillow
- `pillow-heif` or another proven HEIC solution if packaging is reliable

## Handwritten number recognition

Preferred candidate:

- small digit model
- ONNX Runtime

Evaluate alternatives before final lock.

## Excel

- openpyxl

## Database

- SQLite

## Packaging

Investigate:

- PyInstaller
- Nuitka

Choose based on:

- macOS reliability,
- Windows reliability,
- ONNX native library packaging,
- OpenCV packaging,
- HEIC packaging,
- startup speed,
- installer size,
- antivirus false positives,
- maintainability.

## Installer

Final distribution should feel like normal software.

macOS target:

```text
.dmg / .pkg
→ drag/install app
→ open
```

Windows target:

```text
Setup.exe / .msi
→ next
→ install
→ shortcut
→ open
```

The end user should **not** manually install:

- Python,
- pip packages,
- OpenCV,
- ONNX Runtime,
- command-line tools.

Bundle required runtime dependencies with the application where licensing permits.

---

# 7. Repository / Folder Architecture

Codex should create a clean architecture early.

Recommended starting structure:

```text
[project-name]/
├── README.md
├── LICENSE-or-NOTICE.md
├── pyproject.toml
├── .gitignore
│
├── docs/
│   ├── PRODUCT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md
│   ├── DATA_MODEL.md
│   ├── IMAGE_PIPELINE.md
│   ├── OMR_SPEC.md
│   ├── DIGIT_RECOGNITION.md
│   ├── TEST_STRATEGY.md
│   ├── PACKAGING.md
│   ├── RELEASE_CHECKLIST.md
│   ├── AGENT_HANDOFF.md
│   └── ROADMAP.md
│
├── src/
│   └── exam_grader/
│       ├── app/
│       ├── ui/
│       ├── domain/
│       ├── storage/
│       ├── imaging/
│       ├── registration/
│       ├── omr/
│       ├── recognition/
│       ├── grading/
│       ├── review/
│       ├── rendering/
│       ├── export/
│       ├── diagnostics/
│       └── platform/
│
├── models/
│   ├── README.md
│   └── digit/
│
├── templates/
│   └── answer_sheet_v1/
│       ├── template.json
│       ├── masks/
│       └── reference/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   ├── golden/
│   ├── edge_cases/
│   ├── performance/
│   ├── packaging/
│   ├── fixtures/
│   │   ├── originals/
│   │   ├── synthetic/
│   │   ├── expected/
│   │   └── corrupted/
│   └── helpers/
│
├── tools/
│   ├── dataset/
│   ├── synthetic/
│   ├── benchmark/
│   ├── inspect/
│   └── release/
│
├── scripts/
│   ├── dev/
│   ├── build/
│   └── release/
│
├── resources/
│   ├── icons/
│   ├── fonts/
│   └── ui/
│
├── build/
│   └── .gitkeep
│
└── dist/
    └── .gitkeep
```

Adjust names if justified, but preserve strong separation of:

- domain logic,
- computer vision,
- UI,
- persistence,
- tests,
- fixtures,
- packaging.

---

# 8. Template System

Do not scatter magic pixel coordinates through source code.

Build a versioned answer-sheet template definition.

Example conceptual schema:

```json
{
  "template_id": "thai-answer-sheet-v1",
  "canonical_width": 2000,
  "canonical_height": 2400,
  "anchors": {},
  "student_number_roi": {},
  "answer_groups": [],
  "score_roi": {},
  "version": 1
}
```

Coordinates should preferably use normalized units or a canonical coordinate system.

Template version must be written into grading provenance.

Later custom sheet formats should be possible without rewriting the application core.

---

# 9. Image Pipeline

Develop this independently from the UI and prove it with tests.

Proposed stages:

```text
Decode original
↓
Read EXIF orientation
↓
Image quality inspection
↓
Paper boundary detection
↓
Orientation classification / correction
↓
Perspective transform
↓
Fine registration to canonical template
↓
ROI extraction
├── student number
└── answer cells
↓
Recognition
↓
Confidence / anomaly detection
↓
Grade
↓
Overlay in canonical coordinates
↓
Transform/render result
↓
Export
```

### Accuracy principle

Do not resize/compress source images before recognition merely to save storage.

It is acceptable to create a temporary working resolution if benchmark evidence proves there is no meaningful loss.

Final checked images can be intelligently compressed after recognition.

---

# 10. OMR Detection Design

The existing form uses answer cells and handwritten/gapped marks rather than a standardized optical bubble scanner form.

Design robust mark detection using multiple signals.

Potential features:

- local grayscale statistics,
- adaptive threshold,
- ink ratio,
- difference from expected blank-cell structure,
- center/shape occupation,
- connected components,
- stroke geometry,
- morphology,
- relative score against the other options in the same question,
- page/region lighting normalization.

Output should not merely be `A/B/C/D/E`.

Use a structured result:

```text
question
selected choices
confidence
classification
features/diagnostics
```

Possible classification:

```text
blank
single_mark
multiple_mark
uncertain
invalid_region
```

---

# 11. Student Number Recognition

The task is deliberately constrained to a tiny ROI.

Benchmark at least:

1. Tesseract numeric-only configuration,
2. small CNN / digit classifier,
3. segmentation + classifier,
4. sequence recognizer if segmentation proves unreliable.

Use real examples from the user's forms.

### Important validation

The model must be evaluated on:

- Thai students' handwriting,
- ballpoint pen,
- pencil if relevant,
- narrow digits,
- joined digits,
- badly spaced digits,
- 1 vs 7,
- 3 vs 8,
- 5 vs 6,
- faint writing,
- overwritten/corrected number.

Do not claim high production accuracy based only on MNIST.

If training is needed, establish a local dataset pipeline with clear consent/data boundaries.

---

# 12. Test Strategy — Mandatory

Testing is part of the product, not a cleanup phase.

## 12.1 Golden fixtures

For every known real answer sheet:

- retain immutable original,
- store expected page registration,
- expected number,
- expected selected answers,
- expected score.

Automated regression tests should fail if behavior changes unexpectedly.

---

## 12.2 Synthetic answer-sheet generator

This is a core project tool.

When the user provides a blank or representative answer sheet:

1. geometrically normalize it,
2. create a clean reference/template,
3. programmatically simulate markings,
4. generate expected truth automatically.

Generate many virtual answer sheets from the same base.

Examples:

```text
all blank
all A
all E
alternating patterns
random answers
perfect score
zero score
single wrong answer
multi-mark answers
faint X marks
heavy X marks
marks near cell borders
erased/replaced answers
```

Keep the truth metadata next to each synthetic image.

---

## 12.3 Image degradation / edge-case generator

Automatically generate variants:

- rotation ±1°, ±3°, ±5°, ±10°
- perspective skew
- page farther from camera
- strong crop
- mild crop
- partial sheet
- shadow
- brightness shifts
- low contrast
- warm/cool lighting
- blur
- motion blur
- JPEG artifacts
- HEIC conversion
- downsized images
- oversized camera photos
- slight paper bend approximation
- background clutter
- partial hand/finger occlusion
- transparent plastic glare if representative of real usage

Every transform should have deterministic seeds where possible.

---

## 12.4 Mark edge cases

Test:

- very small X,
- very large X,
- off-center X,
- light pencil,
- thick marker,
- check mark instead of X,
- scribble,
- circled option,
- two answers,
- crossing answer-cell boundary,
- erased answer,
- corrected answer.

The desired behavior does not always have to be "recognize automatically."

Correct behavior can be:

**flag for review.**

---

## 12.5 Identity edge cases

Test:

- missing number,
- unreadable number,
- duplicate number,
- number outside expected class range if a range is configured,
- multiple sheets with same number,
- blank number field,
- number written in unexpected portion of the field.

---

## 12.6 File edge cases

Test:

- corrupted image,
- unsupported image,
- zero-byte file,
- duplicate file,
- same photo imported twice,
- filenames containing Thai,
- Unicode filenames,
- long filenames,
- spaces,
- Windows-illegal filename characters in generated output,
- readonly destination,
- insufficient disk space where reasonably testable.

---

# 13. Performance Requirements

Do not optimize blindly.

Create benchmarks.

Track at least:

- decode time,
- registration time,
- OMR time,
- number-recognition time,
- overlay render time,
- average end-to-end sheet time,
- memory usage,
- batch throughput.

Target user experience:

- interactive UI remains responsive during batch processing,
- processing runs in worker thread/process,
- progress is visible,
- cancellation is safe,
- one failed image does not kill the batch.

Avoid unnecessary ML inference for the full image.

---

# 14. Compression / Storage Policy

Principle:

**Accuracy first during detection, efficient storage after detection.**

Suggested approach:

- preserve original user file,
- decode original quality for analysis,
- keep intermediate images temporary by default,
- checked result may be JPEG/WebP/PNG depending content and packaging support,
- expose quality setting only if useful,
- Excel/JSON are tiny and should not be aggressively optimized.

Never use destructive compression before detection without benchmark proof.

---

# 15. Checked Image / Evidence Rendering

Rendering must be reproducible.

Suggested overlay semantics:

- answer detected,
- correct answer,
- incorrect answer,
- blank,
- multiple-mark,
- low-confidence review marker,
- score.

Do not rely solely on color because:

- printers may be grayscale,
- accessibility,
- evidence clarity.

Use shapes/icons/labels as needed.

Keep overlays visually lightweight enough to inspect the original marks beneath them.

Store enough structured data that checked images can be regenerated later.

---

# 16. Excel Export

`scores.xlsx` should at minimum contain:

| No. | Score | Max | Status | Source File |
|---|---:|---:|---|---|

Potential future columns:

- student name,
- percentage,
- number of correct,
- wrong,
- blank,
- multi-mark,
- teacher correction count.

Do not make the spreadsheet the primary database.

It is an export artifact.

---

# 17. UI Principles

Teacher-facing, not developer-facing.

Prioritize:

- large obvious actions,
- minimal setup friction,
- clear progress,
- clear review queue,
- predictable folder outputs,
- understandable error messages.

Core screens may be:

```text
Home
Exams
Create/Open Exam
Answer Key
Import
Review
Results
Settings
```

Avoid showing internal CV/ML jargon unless in diagnostics mode.

Teacher should see:

```text
"ภาพนี้เอียงมากเกินไป กรุณาตรวจสอบ"
```

rather than:

```text
"homography confidence below threshold"
```

---

# 18. Reliability / Recovery

A batch may process dozens or hundreds of images.

Therefore:

- save state incrementally,
- do not require starting the batch over after application crash,
- use atomic writes where appropriate,
- retain import provenance,
- allow safe re-run,
- avoid duplicate results,
- version answer keys.

If the answer key changes after grading, the program must clearly handle whether results are stale and require re-grading.

---

# 19. Cross-Platform Rules

Code must avoid assumptions tied only to the developer Mac.

Test:

- macOS path semantics,
- Windows path semantics,
- Unicode/Thai paths,
- different DPI/display scaling,
- platform-specific app-data locations.

Use a platform abstraction for:

- config storage,
- logs,
- temp files,
- user data directory,
- opening folders,
- file dialogs.

Do not hardcode `/Users/...` inside the runtime application.

The `/Users/zubinpijit/private/[project-name]` path is only the **development workspace**.

---

# 20. Packaging / Installer Goal

Final acceptance requires real installers.

## macOS

Aim for:

- signed app eventually if distribution requires it,
- `.app`,
- `.dmg` or `.pkg`,
- no terminal usage.

Investigate Apple Gatekeeper/notarization implications and document them separately from core functionality.

## Windows

Aim for:

- bundled executable/app directory,
- installer `.exe` or `.msi`,
- start-menu shortcut,
- clean uninstall,
- no Python dependency exposed to user.

### Startup self-check

On first launch, program should verify internal runtime health such as:

- writable app-data directory,
- bundled model exists,
- SQLite initializes,
- OpenCV loads,
- image codecs load,
- required resources/templates exist.

Do **not** make the teacher manually install missing Python packages.

If a bundled component is corrupt/missing, provide a user-friendly error and diagnostics.

---

# 21. Proposed Development Phases

Codex should refine this into a concrete roadmap.

## Phase 0 — Discovery / decisions

- inspect tools/environment,
- inspect supplied form,
- run `/wayfinder` only for unsettled material decisions,
- freeze architecture v1,
- write decision log.

**Gate:** major architecture agreed/documented.

---

## Phase 1 — Project foundation

- repository/folder structure,
- configuration,
- logging,
- SQLite + migrations,
- template schema,
- test harness,
- CI where practical.

**Gate:** empty desktop app + tests run cleanly.

---

## Phase 2 — Canonical form registration

- page detection,
- rotation,
- perspective correction,
- canonical registration,
- diagnostic visualization,
- golden tests.

**Gate:** representative images align reliably.

---

## Phase 3 — OMR core

- cell ROI definitions,
- mark features,
- answer classification,
- blank/multiple/uncertain states,
- confidence,
- synthetic tests.

**Gate:** answer detection meets benchmark threshold on validated test corpus.

---

## Phase 4 — Student number recognition

- ROI extraction,
- baseline Tesseract numeric benchmark,
- local digit-model benchmark,
- production recognizer,
- confidence/review integration.

**Gate:** recognition evaluated on real handwritten data, not only generic datasets.

---

## Phase 5 — Grading engine

- answer-key schema,
- comparison,
- scoring,
- result provenance,
- stale-key handling.

**Gate:** deterministic grading unit/integration tests pass.

---

## Phase 6 — Evidence renderer

- checked image,
- score overlay,
- answer overlays,
- reproducible rendering,
- image export.

**Gate:** visual golden tests approved.

---

## Phase 7 — Teacher workflow UI

- exam creation,
- answer key review,
- batch import,
- review queue,
- grading,
- results,
- folder reveal.

**Gate:** full workflow usable without terminal.

---

## Phase 8 — Export / folder lifecycle

- folder structure,
- checked images,
- Excel,
- JSON metadata,
- safe naming,
- duplicate detection.

**Gate:** generated exam package is complete and inspectable outside app.

---

## Phase 9 — Edge-case hardening

- synthetic degradation suite,
- real bad photos,
- duplicate/no-number cases,
- crash recovery,
- performance.

**Gate:** unresolved uncertainty is flagged rather than silently misgraded.

---

## Phase 10 — macOS packaging

- bundle,
- installer,
- clean-machine install test,
- first-launch self-check.

**Gate:** non-developer Mac installs and runs.

---

## Phase 11 — Windows packaging

- bundle,
- installer,
- clean Windows install test,
- image codec verification,
- ONNX/OpenCV verification.

**Gate:** non-developer Windows PC installs and runs.

---

## Phase 12 — Release candidate

- regression suite,
- fixture archive,
- performance report,
- release notes,
- user guide,
- known limitations,
- version tagging.

**Gate:** production-ready v1.

---

# 22. Engineering Loop

For every meaningful phase/task:

```text
Inspect
↓
State assumptions
↓
Design
↓
Implement
↓
Run focused tests
↓
Run relevant regression tests
↓
Inspect outputs
↓
Document decisions / known issues
↓
Commit checkpoint
```

Avoid massive unreviewable changes.

Do not alter unrelated functionality during bug fixes.

---

# 23. Agent Collaboration Contract

Because Codex starts the project and Antigravity may continue later, maintain:

## `docs/AGENT_HANDOFF.md`

Keep current:

- current phase,
- last completed milestone,
- exact run/test commands,
- architecture summary,
- known bugs,
- unresolved decisions,
- current benchmark numbers,
- paths to sample fixtures,
- packaging status,
- next 3 recommended tasks.

## `docs/DECISIONS.md`

For every important architectural decision record:

```text
Date
Decision
Why
Alternatives considered
Consequences
Revisit condition
```

This prevents later agents from accidentally replacing deliberate design choices.

---

# 24. Definition of Done — v1

The project is **not done** merely because detection works on one image.

v1 is done when:

- normal teacher can install it on supported macOS,
- normal teacher can install it on supported Windows,
- no Python/manual dependency installation is needed,
- existing answer-sheet format is supported,
- teacher can create/open an exam,
- teacher can select class/room/subject,
- teacher can import an answer key,
- answer key is machine-read and teacher-confirmed,
- teacher can import a batch of student sheets,
- handwritten number recognition works with confidence/review fallback,
- answers are detected locally,
- uncertain cases enter review,
- duplicate student numbers are detected,
- teacher can correct recognition errors,
- scoring is deterministic,
- originals remain unchanged,
- checked images are generated,
- score is visibly written to derived image,
- result images correspond to the corrected student number,
- Excel summary is generated,
- result metadata is preserved,
- app does not freeze during normal batch processing,
- failures do not corrupt the whole batch,
- regression/edge-case test corpus exists,
- synthetic marking tests exist,
- synthetic image-degradation tests exist,
- packaging tests exist,
- clean-install tests have been performed on both OS families,
- architecture/docs are sufficiently complete for another agent to maintain the project.

---

# 25. Explicit Non-Goals for Initial v1

Unless required later:

- cloud OCR,
- web backend,
- account system,
- subscription billing,
- online sync,
- student portal,
- LMS integration,
- recognition of full handwritten Thai names,
- redesigning the paper form,
- automatic modification of original images.

Keep v1 focused.

---

# 26. Important Principle

The core product should be:

> **Computer vision first, narrow ML only where it earns its complexity, human review whenever confidence is insufficient.**

The teacher must be able to trust why a score was produced and inspect the evidence afterward.

---

# 27. First Deliverables Expected From Codex

Before substantial implementation, Codex should leave these artifacts in the project:

```text
README.md
docs/PRODUCT_SPEC.md
docs/ARCHITECTURE.md
docs/DECISIONS.md
docs/ROADMAP.md
docs/TEST_STRATEGY.md
docs/AGENT_HANDOFF.md
```

Then establish the skeleton repository and test harness.

If `/wayfinder` is invoked, summarize the decisions it settles into `docs/DECISIONS.md`.

Do not wait for every future detail to be perfect before starting. Resolve only the decisions that materially block a clean architecture, then proceed phase by phase.

---

# 28. Initial Questions Codex May Need to Resolve

Use `/wayfinder` or ask the Product Owner only where these actually block implementation:

- canonical supported number of questions for v1: fixed 60 vs configurable,
- exact mapping of Thai choices `ก ข ค ง จ`,
- whether a crossed-out/corrected answer should always require human review,
- how student-number ranges are defined per class,
- whether teacher wants roster import in v1,
- preferred output image format/quality,
- exact visual annotation semantics,
- minimum supported macOS/Windows versions,
- app name/icon/branding.

Technical implementation details that can be benchmarked should be benchmarked rather than pushed back to the Product Owner.

---

# 29. Product Owner Intent

This project is expected to evolve from:

```text
Codex
→ establishes architecture + core
→ Antigravity may assist implementation/polish/testing
→ both agents follow the same documented contracts
→ final result is a finished installable desktop application
```

Optimize for long-term maintainability, reproducibility, testability, and trustworthy grading — not for a one-off demo.

