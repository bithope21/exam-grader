# Exam Grader

โปรแกรมตรวจข้อสอบจากภาพกระดาษคำตอบแบบเดิม ทำงาน offline บน macOS และ Windows

สถานะ 2026-09-08: **working prototype** มี desktop workflow สำหรับนำเข้าภาพ, ตรวจทาน, ให้คะแนน และ export หลักฐาน; production accuracy, digit model และ Windows installer ยังไม่ผ่านการรับรอง

## เริ่มอ่าน

1. [Product contract](docs/PRODUCT_SPEC.md)
2. [Wayfinder map](docs/WAYFINDER_MAP.md)
3. [Roadmap และ gates](docs/ROADMAP.md)
4. [Architecture](docs/ARCHITECTURE.md)
5. [Test strategy](docs/TEST_STRATEGY.md)
6. [งานถัดไปสำหรับ Antigravity](docs/AGENT_HANDOFF.md)

Codex เป็น architect / planner / independent reviewer; Antigravity เป็น implementer; Product Owner ตัดสิน product rules และรับรอง teacher UAT ตามคำสั่งล่าสุด ซึ่งแทนบทบาท initial implementer ใน handoff เดิม

`CODEX_EXAM_GRADER_PROJECT_HANDOFF.md` เป็น source requirements; เก็บไว้ไม่แก้ไข ภาพใน `answer-sheet/` เป็น reference inputs ห้ามเขียนทับ ยังไม่ใช่ชุดทดสอบความแม่นยำที่รับรองแล้ว

## Development

ใช้ Python 3.11–3.13 และ uv; dependency versions อยู่ใน `uv.lock`

```sh
rtk proxy uv sync --frozen --extra dev
rtk proxy uv run --frozen exam-grader
rtk proxy uv run --frozen exam-grader --self-check
rtk proxy uv run --frozen pytest -q
```

ถ้า sandbox จำกัด cache ให้เพิ่ม `--cache-dir /private/tmp/exam-grader-uv` หลัง `uv`.

`--data-dir PATH` ใช้เลือกโฟลเดอร์ข้อมูลทดสอบได้ ค่า default ใช้ app-data location ของ OS โดยไม่เขียนลง source tree ตัว self-check ตรวจ storage เท่านั้น ไม่รับรอง CV/model/codecs/packaging

## Current modules

Reference inventory tool (read-only inputs):

```sh
rtk proxy .venv/bin/python tools/inspect/reference_inventory.py --source answer-sheet --output docs/evidence/AG-001
```

See [reference evidence](docs/evidence/AG-001/REPORT.md). Current source suite: 45
passing on the development Mac; production geometry/recognition and Windows release
evidence remain pending.

- `domain.py`: immutable exam metadata
- `storage.py`: SQLite versioned initialization through schema v5, stable IDs
- `imports.py`: JPEG/PNG validation, content-addressed immutable originals and quarantine recovery
- `imaging.py`: experimental registration/OMR with explicit review-required status
- `workflow.py`: approved key versions, append-only reviews, deterministic scoring
- `review_ui.py` / `exam_ui.py`: teacher review, batch import, cancellation and failure isolation
- `exporting.py`: versioned checked images, Excel, JSON and manifest
- `preferences.py`: cross-platform default output-folder preference
- `diagnostics.py` / `scripts/build/`: runtime health and per-OS PyInstaller build

The current macOS workflow stores an authoritative 1–60 question count when an exam
is created, separates `เฉลย / นักเรียน / ตรวจทาน / ผลลัพธ์`, processes imports in a
background worker, and keeps failed imports retryable. Real-fixture engineering
evidence is in [REAL_UAT](docs/evidence/REAL_UAT.md); it is not an accuracy claim.

## Current limits

เลขที่นักเรียนมี numeric-only baseline candidate แบบ review-required แล้ว แต่ยังไม่มี
ground-truth handwriting corpus หรือ calibrated model จึงห้ามถือ candidate เป็นเลขที่จริง
โดยอัตโนมัติ OMR บันทึก margin/diagnostics เพิ่มขึ้นแต่ยังบังคับครูตรวจทุกภาพและไม่มี
auto-accept ภาพอ้างอิงปัจจุบันเป็น PNG screenshot ไม่ใช่ clean production template

ผลลัพธ์สร้าง checked copy แบบมี annotation สีแดงและ score ROI จาก canonical geometry
โดยไม่แก้ originals มี export registry, human-readable index และ exam archive/restore
แบบกู้คืนได้; path ภายในเดิมยังคงไว้เพื่อความเข้ากันได้กับผลลัพธ์เก่า

macOS arm64 bundle สร้างและ smoke-test แล้วจาก `scripts/build/build.py`; Windows ต้อง build/test บน Windows เองตามข้อจำกัดของ PyInstaller และ Inno Setup script ยังไม่ผ่าน clean-machine UAT รายละเอียดอยู่ใน [evidence](docs/evidence/FOUNDATION.md) และ [code review](docs/evidence/CODE_REVIEW.md)
