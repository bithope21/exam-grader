# TASK — Custom Answer-Sheet Template / Calibration System
## Production Requirements + Built-in Default #2 + Annotation Style Settings

> **Project:** Offline Cross-Platform Exam Grader  
> **Scope:** Extend the existing application without regressing proven grading behavior.  
> **Execution rule:** **Inspect → propose implementation plan → Product Owner confirms/adjusts plan → only then implement.**

---

## 0. Non-Negotiable Rules

1. **Do not rewrite or fork proven grading business logic.**
2. Custom/built-in sheet formats must feed the existing grading pipeline through a **template geometry/registration adapter**.
3. Preserve existing behavior for:
   - teacher-approved authoritative answer key,
   - authoritative question count / current supported max,
   - current OMR local-background/local-darkness logic,
   - blank / single / multiple / uncertain classifications,
   - fail-closed review behavior,
   - student-number workflow,
   - duplicate-number detection,
   - scoring and score rendering,
   - background processing / progress / failure journal / retry,
   - output directory + per-exam override,
   - result/export lifecycle,
   - provenance,
   - original source immutability.
4. Everything must remain **fully offline**.
5. Do not weaken thresholds/tests merely to make a new template pass.
6. If implementation would materially alter an existing contract, **stop and document the reason before proceeding**.

Conceptually:

```text
existing grading business logic
            ↑
template geometry / registration adapter
            ↑
Built-in Default #1 / Built-in Default #2 / Custom Template
```

---

# 1. Product Goal

Add a teacher-facing **Answer Sheet Templates** system under **⚙️ Settings**.

Teacher must be able to:

- select an existing answer-sheet template,
- set the default template,
- use either built-in default,
- add a custom template from a blank/representative photo,
- edit a custom template,
- duplicate a template where appropriate,
- test/preview a template,
- delete **user-created** templates when provenance rules allow,
- keep historical exams bound to the exact template/version used,
- configure default visual annotation colors for checked results.

Normal grading semantics must remain unchanged regardless of template.

---

# 2. Built-in Templates

The application must ship with **two first-class built-in templates**.

## Default #1

The current production/default answer-sheet format.

Requirements:

- preserve current geometry/behavior,
- migrate/represent it safely in the versioned template system,
- remain a permanent regression fixture,
- must not regress after this feature is introduced.

## Default #2 — New Required Built-in Fixture

Use this real image as the authoritative calibration fixture:

```text
/exam-grader/docs/new-features/settings/default#2.JPG
```

The supplied sheet visibly contains:

- **60 questions**,
- **4 choices per question**,
- **3 answer blocks**:
  - 1–20,
  - 21–40,
  - 41–60,
- Thai choice headers **ก ข ค ง**,
- corresponding Latin labels **A B C D**,
- corresponding numeric labels **1 2 3 4**,
- handwritten student-number field labeled **เลขที่** in the header,
- score box labeled **คะแนน** in the upper-right area.

### Required Default #2 workflow

Agents must:

1. add the supplied image as a real fixture in the repository using an appropriate stable fixture/reference path,
2. inspect and normalize it with the real image pipeline,
3. run template discovery against it,
4. calibrate the proposed geometry,
5. visually inspect overlays,
6. iterate until answer cells, question mapping, student-number region, and score region align correctly,
7. validate it through preview/test,
8. create a stable versioned built-in template definition from the proven geometry,
9. register it in Settings as **Default #2**,
10. run real-fixture grading/UAT using this template,
11. preserve Default #1 non-regression.

Do **not** hard-code one-off pixel coordinates directly into grading code. Geometry belongs in the template definition/version.

---

# 3. Settings UX — Answer Sheet Templates

Add a clean section under **⚙️ Settings → รูปแบบกระดาษคำตอบ**.

Expected structure:

```text
รูปแบบกระดาษคำตอบ

● Default #1 — กระดาษคำตอบมาตรฐาน
○ Default #2 — 60 ข้อ · 4 ตัวเลือก · 3 ชุด
○ โรงเรียน A — 40 ข้อ · 4 ตัวเลือก
○ โรงเรียน B — 50 ข้อ · 5 ตัวเลือก

[ + เพิ่มรูปแบบกระดาษคำตอบ ]
```

Actions as appropriate:

- ตั้งเป็นค่าเริ่มต้น
- แก้ไข
- ทำสำเนา
- ทดสอบ
- ลบ

Rules:

- built-in Default #1 and Default #2 **cannot be destructively deleted**,
- user-created templates may be deleted only when doing so cannot invalidate historical provenance,
- if a template/version is referenced by an exam/result, protect it or retain the referenced immutable version,
- editing a template must create/use a safe versioning strategy rather than silently mutating historical grading geometry,
- existing exams must continue opening and grading reproducibly.

---

# 4. Custom Template Creation Flow

Teacher chooses:

```text
+ เพิ่มรูปแบบกระดาษคำตอบ
```

Flow:

1. upload blank or representative answer-sheet image,
2. decode through the existing supported image pipeline,
3. apply EXIF orientation,
4. detect paper boundary,
5. correct rotation/perspective,
6. normalize into a canonical coordinate system,
7. inspect page structure locally,
8. propose answer regions and metadata,
9. visually show the proposal,
10. allow manual calibration,
11. run preview/test,
12. save only after validation succeeds.

Required philosophy:

```text
Auto Detect
↓
Visual Confirmation
↓
Manual Calibration
↓
Preview Test
↓
Save
```

Auto-detection must never be treated as infallible.

---

# 5. Automatic Template Discovery

Implement a bounded, deterministic/local discovery pipeline using existing CV infrastructure wherever practical.

No cloud API.

## 5.1 Paper

Attempt to identify:

- page boundary,
- orientation,
- perspective,
- usable page area,
- canonical transform / registration.

## 5.2 Answer areas / grids

Attempt to locate:

- one or multiple answer blocks,
- block boundaries,
- horizontal/vertical table structure,
- question rows,
- answer columns,
- answer-cell centers/ROIs.

Must support multi-block layouts, including the supplied Default #2 with 3 blocks.

Do not assume a sheet contains only one continuous table.

## 5.3 Choice headers

Attempt to detect common labels such as:

- ก ข ค ง
- ก ข ค ง จ
- A B C D
- A B C D E
- a b c d
- a b c d e

Latin case should not matter.

OCR may assist **template discovery only**. It must not become the normal answer-mark detector.

Tesseract/local OCR is acceptable because:

- processing remains offline,
- it runs during calibration/template creation,
- failure can fall back to teacher confirmation.

OCR failure must not make template creation impossible.

## 5.4 Choice count

Infer choice count from combined evidence such as:

- detected columns,
- headers,
- grid structure.

Support **2–5 choices** only where consistent with current engine capability.

Never silently expand existing grading limits.

## 5.5 Question range/count

Attempt to infer:

- first question number,
- last question number,
- total question count,
- per-block question ranges.

If current product maximum remains 60, discovery must not silently exceed 60.

Low-confidence numbering requires teacher confirmation.

## 5.6 Student Number Region

Search for likely text/layout cues such as:

- เลขที่
- เลขที่:
- No.
- No
- Number

Propose a student-number region, but always allow editing.

At grading time this region feeds the **existing narrow student-number recognition pipeline**. Do not add whole-page OCR.

## 5.7 Score Region

Attempt to identify optional score fields such as:

- คะแนน
- Score
- คะแนนรวม

The score region is optional template metadata used by the existing result renderer.

It must be detected/calibrated for Default #2 because the supplied sheet has a visible score box.

---

# 6. Calibration UI

After discovery, show a dedicated stable calibration screen.

Overlay the normalized sheet with at minimum:

- page/canonical boundary,
- answer-block boundaries,
- question rows,
- answer-cell ROIs/centers,
- choice labels/order,
- question ranges,
- student-number region,
- optional score region.

Example teacher-facing summary:

```text
ตรวจพบ

จำนวนข้อ: 60
ตัวเลือก: 4
รูปแบบ: ก ข ค ง
ชุดคำตอบ: 3
เลขที่: พบ
คะแนน: พบ

ความมั่นใจในการตรวจโครงสร้าง: 94%
```

Do not expose low-level jargon such as homography, Hough transform, ROI matrix, or OCR tensors in normal UI.

---

# 7. Manual Calibration

Teacher must be able to correct the proposal.

Support suitable operations such as:

- drag/resize answer-block boundary,
- adjust student-number region,
- adjust score region,
- change question count,
- change choice count,
- correct choice labels/order,
- correct question start/end,
- add/remove answer block,
- fine-adjust geometry where genuinely needed.

Prefer **high-level geometry editing** rather than requiring teachers to drag every cell.

Example:

```text
answer block
+ rows = 20
+ columns = 4
→ regenerate cell geometry
```

Invalid geometry must be rejected.

---

# 8. Preview / Test Before Save

A custom template cannot be saved until a preview/test validates it.

Provide:

```text
ทดสอบการอ่าน / Preview Test
```

Show:

- every answer cell that will be read,
- row/question mapping,
- choice mapping,
- student-number crop,
- score region if configured,
- validation diagnostics.

Example:

```text
60 questions mapped
240 answer cells mapped
3 answer blocks valid
Student number region valid
Score region valid
No overlapping answer cells
All regions inside canonical page
```

If the overlay is visibly wrong, the task is not complete.

---

# 9. Template Persistence and Versioning

Use/extend the existing versioned template architecture.

Conceptually:

```json
{
  "template_id": "...",
  "name": "...",
  "kind": "builtin|custom",
  "version": 1,
  "canonical_width": 2000,
  "canonical_height": 2400,
  "choice_labels": ["A", "B", "C", "D"],
  "question_count": 60,
  "answer_blocks": [],
  "student_number_roi": {},
  "score_roi": {},
  "registration": {},
  "created_at": "...",
  "updated_at": "..."
}
```

Exact schema must follow the current repository architecture.

Requirements:

- stable template ID,
- explicit template version,
- canonical/normalized coordinates,
- no scattered magic coordinates,
- grading provenance records template ID + version,
- built-ins represented safely,
- existing exams/data migrated compatibly,
- later edits must not silently alter old exams/results.

If DB/schema changes are required:

- add proper migration,
- test migration from existing state,
- preserve old exams/results,
- add migration regression coverage.

---

# 10. Runtime Grading Integration

After template selection, runtime processing remains conceptually:

```text
source image
↓
existing image normalization
↓
registration against selected template/version
↓
template-defined geometry/ROIs
↓
existing student-number recognizer
↓
existing OMR features/classifier
↓
existing confidence/review logic
↓
existing teacher-approved answer-key comparison
↓
existing score logic
↓
existing checked-result renderer/export
```

The template system owns:

- geometry,
- registration,
- mapping,
- calibration metadata.

It does **not** own a new grading engine.

---

# 11. Annotation Style Settings

Add a second teacher-facing Settings capability for the appearance of **generated checked-result annotations**.

At minimum allow configuring default colors for:

- **ถูก / Correct**
- **ผิด / Incorrect**
- **อื่นๆ / Review / blank / multiple / uncertain** as appropriate to existing renderer semantics
- **คะแนน / Score**

Requirements:

- provide sensible built-in defaults,
- allow user to choose and save their preferred default colors,
- persist settings using the existing app-settings mechanism,
- apply the selected defaults to newly rendered checked results,
- do not recolor or mutate original source images,
- preserve existing non-color visual semantics (shape/icon/text) so meaning does not rely on color alone,
- keep annotations readable on both light and dark portions of photographed paper,
- do not let style settings alter grading logic, confidence, answer classification, or score calculation,
- if per-exam overrides already fit the architecture naturally, they may be supported, but global Settings defaults are the required baseline.

Example Settings grouping:

```text
สีรอยตรวจ

ถูก        [ color ]
ผิด        [ color ]
อื่นๆ      [ color ]
คะแนน      [ color ]

[ คืนค่าเริ่มต้น ]
```

Include visual preview if practical and consistent with the current Settings design.

---

# 12. Confidence / Fail-Closed Rules

Discovery must represent uncertainty.

Examples:

```text
Answer grid        0.97
Choice headers     0.78
Student number     0.93
Question numbering 0.66
```

Engineering may choose the exact scoring model, but:

- low confidence must not become silent certainty,
- conflicting evidence must require teacher confirmation,
- overlapping regions must block save,
- out-of-page regions must block save,
- impossible row/column geometry must block save,
- ambiguous mapping must be surfaced clearly.

---

# 13. Offline / Dependency Rules

Everything must continue working without network access.

Allowed examples:

- OpenCV
- NumPy
- Tesseract/local OCR
- ONNX Runtime
- existing application libraries

Do not introduce required:

- cloud OCR,
- OpenAI/Gemini APIs,
- remote recognition services,
- network-based template services.

If Tesseract/local OCR becomes a packaged runtime dependency, the application self-check and packaging tests must explicitly verify it.

---

# 14. UI Stability

The Settings/template/calibration UI must not jump, shift, or resize unpredictably.

Avoid:

- panel-width changes,
- controls moving when validation appears,
- image-load layout shift,
- overlay changing container geometry,
- loading/error states with different control placement,
- clipped Thai labels,
- horizontal overflow.

Reserve stable space for:

- progress,
- validation,
- confidence,
- errors.

Test supported display sizes and DPI/scaling.

---

# 15. Performance / Threading

Template analysis may be expensive.

Use the project’s existing background worker/task pattern.

Requirements:

- never block the main Qt UI thread,
- progress remains visible,
- errors are contained,
- worker failure does not crash the app,
- cancellation may be added if consistent with existing architecture,
- do not create a second unrelated threading framework.

---

# 16. Mandatory Engineer Loop

For every meaningful slice:

```text
Inspect
↓
Identify existing contracts
↓
Form hypothesis
↓
Implement smallest coherent change
↓
Run focused tests
↓
Launch real app
↓
Capture screenshot(s)
↓
Inspect screenshots visually
↓
Compare with requirement
↓
Fix if needed
↓
Run regression tests
↓
Repeat
```

Do not perform this as one blind large change.

---

# 17. Screenshot-Driven Verification

Screenshots are acceptance evidence.

At minimum capture and inspect:

## Settings

- two built-in templates visible,
- selected/default state,
- no-custom-template state,
- custom-template actions,
- annotation color settings,
- restored/default color state.

## Template creation/calibration

- upload,
- analysis/loading,
- successful detection,
- low-confidence,
- calibration,
- manual adjustment,
- preview/test,
- validation error,
- saved custom template.

## Default #2

- normalized fixture,
- detected three answer blocks,
- cell overlays aligned to printed cells,
- question ranges 1–20 / 21–40 / 41–60,
- student-number region,
- score box,
- final checked result.

## Regression

Inspect affected existing screens/shared components.

Explicitly verify:

- no clipping,
- no overlap,
- no horizontal overflow,
- no truncated labels,
- stable controls/panels,
- correct image aspect ratio,
- overlays align with real printed cells,
- Thai text renders correctly,
- high-DPI remains usable.

If screenshot evidence is ambiguous, investigate rather than assume correctness.

---

# 18. Real-Fixture UAT

Synthetic tests are insufficient.

Required real-fixture paths include:

1. current Default #1 real answer-sheet fixture(s),
2. supplied Default #2 fixture:
   ```text
   /exam-grader/docs/new-features/settings/default#2.JPG
   ```

For Default #2 validate end-to-end:

```text
real image
→ discovery
→ calibration
→ saved/built-in template geometry
→ answer-key processing
→ student processing
→ grading
→ checked result
```

The UAT must prove:

- all 3 blocks register correctly,
- all 60 rows map correctly,
- all 4 choices per row map correctly,
- student-number crop is correct,
- score region is correct,
- no unexplained Default #1 regression.

---

# 19. Testing Strategy

Add focused tests.

## Unit

- template schema,
- canonical coordinates,
- answer-block geometry,
- 2–5 choice mapping,
- question mapping,
- validation,
- versioning,
- built-in/custom distinction,
- default template selection,
- protected deletion,
- annotation style persistence/default reset.

## CV / discovery

- paper boundary,
- grid/block candidates,
- multi-block discovery,
- column count,
- question numbering,
- header OCR mapping,
- student-number candidate,
- score-region candidate,
- Default #2 three-block geometry.

## Integration

```text
template → registration → ROI mapping → existing OMR
```

## Regression

- Default #1 behavior before/after,
- answer key,
- student number,
- score,
- rendering,
- result/export.

## Golden / visual

- overlay geometry where feasible,
- checked-result annotation placement/style.

## Real fixture

Mandatory for Default #1 and Default #2.

---

# 20. Playwright / E2E Decision

Do not add Playwright by default.

This is a native PySide6/Qt desktop application.

Prefer:

- Qt tests,
- offscreen rendering,
- real app smoke tests,
- screenshot inspection,
- real interaction where practical.

Use Playwright only if inspection proves the relevant UI is actually web-based/embedded and Playwright exercises the real product surface.

Document the decision.

---

# 21. Mandatory Quality Gates

Before claiming completion, independently run and report:

```text
pytest           PASS/FAIL
ruff             PASS/FAIL
mypy             PASS/FAIL
build            PASS/FAIL
codesign         PASS/FAIL
self-check       PASS/FAIL
smoke-ui         PASS/FAIL
real-fixture UAT PASS/FAIL
```

Rules:

- use existing project-specific commands where available,
- include new feature tests + relevant regression tests,
- prove any pre-existing unrelated failure rather than hiding it,
- macOS build/codesign must pass,
- self-check must include newly required bundled OCR/resources if applicable,
- smoke-ui must reach the Settings/template feature,
- do not claim Windows production readiness unless Windows was actually validated.

---

# 22. Documentation Updates

Inspect/update as applicable:

```text
docs/PRODUCT_SPEC.md
docs/ARCHITECTURE.md
docs/DECISIONS.md
docs/IMAGE_PIPELINE.md
docs/OMR_SPEC.md
docs/TEST_STRATEGY.md
docs/AGENT_HANDOFF.md
```

Document only material details:

- template architecture,
- built-in Default #1 and #2,
- custom-template lifecycle,
- immutable/versioned strategy,
- discovery limits,
- confidence/fail-closed behavior,
- annotation color settings,
- test strategy,
- supported question/choice ranges,
- known limitations.

---

# 23. Mandatory Plan/Confirmation Gate — Before Implementation

**Do not begin implementation immediately.**

First perform a read-only inspection and return a concrete implementation plan for Product Owner confirmation.

The plan must include:

1. current template/registration architecture,
2. exact existing contracts that will remain untouched,
3. proposed template schema/versioning changes,
4. migration/backward-compatibility strategy,
5. how Default #1 will be represented,
6. how `default#2.JPG` will be converted from fixture → calibrated geometry → built-in Default #2,
7. custom-template discovery/calibration architecture,
8. Settings UX changes,
9. annotation color settings architecture,
10. test/fixture additions,
11. screenshot/UAT plan,
12. packaging/self-check implications,
13. exact implementation slices/order,
14. risks or genuinely unsettled decisions.

Then **STOP and wait for Product Owner confirmation or requested changes**.

Do not modify production code, migrations, or app state before that confirmation unless the Product Owner explicitly authorizes implementation.

---

# 24. Completion Report Required

When implementation is eventually complete, provide:

## A. Architecture
What was added and how it feeds existing grading logic.

## B. Files changed
Grouped by:

- domain/schema,
- CV/discovery,
- UI,
- storage/migration,
- rendering/settings,
- tests,
- docs.

## C. Discovery behavior
What is currently detected automatically vs teacher-confirmed.

## D. Default #2 evidence
Report actual calibration/UAT evidence for:

- 60 questions,
- 4 choices,
- 3 blocks,
- student-number region,
- score region.

## E. Screenshot evidence
List each inspected state and what was visually verified.

## F. Real-fixture evidence
Meaningful results for Default #1 and Default #2.

## G. Non-regression evidence
Explicit Default #1 and existing grading-contract results.

## H. Quality gates

```text
pytest           PASS/FAIL
ruff             PASS/FAIL
mypy             PASS/FAIL
build            PASS/FAIL
codesign         PASS/FAIL
self-check       PASS/FAIL
smoke-ui         PASS/FAIL
real-fixture UAT PASS/FAIL
```

## I. Remaining limitations
Precise and evidence-based.

Do not claim production-ready unless proven.

---

# 25. Definition of Done

Complete only when all are true:

- Settings shows **Default #1 + Default #2**,
- teacher can select and set a default template,
- Default #2 is calibrated from the supplied real fixture,
- Default #2 correctly represents 60 questions / 4 choices / 3 blocks,
- teacher can add a custom template,
- local auto-discovery proposes geometry,
- teacher can manually calibrate,
- 2–5 choices are supported where existing engine permits,
- Thai/Latin choice headers are handled as specified,
- multi-block sheets are supported,
- student-number region can be proposed/adjusted,
- score region can be proposed/adjusted,
- preview shows exactly what will be read,
- invalid geometry cannot be silently saved,
- templates are persisted/versioned,
- custom templates can be deleted safely when unreferenced,
- historical template provenance cannot be broken,
- annotation colors for correct/incorrect/other/score are configurable and persistent,
- annotation style does not change grading semantics,
- existing OMR/review/scoring pipeline remains intact,
- Default #1 does not regress,
- app remains fully offline,
- UI remains stable,
- screenshots are inspected,
- real fixtures are tested,
- checked outputs are visually inspected,
- all mandatory quality gates pass.

**Most important:** if geometry, real-fixture behavior, checked-result rendering, or existing Default #1 behavior is still wrong, do not close the task. Continue the engineer loop until correct or report a genuine blocker with evidence.
