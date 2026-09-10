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
