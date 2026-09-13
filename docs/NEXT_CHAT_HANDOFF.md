# Fresh-Chat Handoff: Polish Algorithm ระบบปรับเทียบ (Template Calibration)

## 1. Quick Context & Current Repo State
- **Active Workspace:** `/Users/zubinpijit/private/exam-grader` (Branch: `main`)
- **Previous Tasks Completed & Pushed:**
  - `bithope21/exam-grader` (`3c118a0`): Auto-release hardening, `USER_MANUAL.md`, README sync.
  - `bithope21/bithope-web` (`719d0da`): Server-side GitHub latest release resolution, Crayon Support/Donate modal (PromptPay, Bitcoin Lightning, Stripe toggle), and `/docs/exam-grader`.
- **Baseline Tests:** 130 passed, 3 skipped via `uv run pytest tests/`.

---

## 2. Next Mission: Polish Algorithm ในระบบปรับเทียบ (Template Calibration System)
- **Goal:** ปรับปรุงและเพิ่มความแม่นยำของ Algorithm ในระบบปรับเทียบและสร้างแม่แบบกระดาษคำตอบ (Template Calibration System)
- **Status:** พร้อมรับ Requirement และรายละเอียดเฉพาะจาก User ใน Chat ใหม่ทันที

---

## 3. Key Files & Architecture Pointers

### Core Algorithm:
- [`src/exam_grader/template_discovery.py`](file:///Users/zubinpijit/private/exam-grader/src/exam_grader/template_discovery.py):
  - `detect_paper(...)`: ตรวจจับขอบกระดาษคำตอบและดึงระนาบ Perspective
  - `normalize_illumination(...)`: ปรับความสว่างและคอนทราสต์
  - `extract_line_masks(...)`: สกัดเส้นตารางแนวนอนและแนวตั้ง
  - `cluster_coordinates(...)`: จัดกลุ่มเส้นพิกัด
  - `infer_grid_in_area(...)`: อนุมานโครงสร้างตารางคำตอบตามพื้นที่
  - `discover_template(...)`: ฟังก์ชันหลักสำหรับ Auto-Discovery และสร้าง `TemplateDefinition`

### UI & Interaction:
- [`src/exam_grader/calibration_ui.py`](file:///Users/zubinpijit/private/exam-grader/src/exam_grader/calibration_ui.py):
  - `CalibrationDialog`: หน้าต่างหลักของระบบปรับเทียบ
  - `CalibrationCanvas`: แคนวาสวาด Overlay, จัดการ Interactive Drag / Resize / Handles
  - `CalibrationTestDialog`: การทดสอบความเข้ากันได้ของแม่แบบกับภาพจริง

### Tests & Real Fixtures:
- [`tests/test_calibration_system.py`](file:///Users/zubinpijit/private/exam-grader/tests/test_calibration_system.py): ชุดการทดสอบของระบบ Calibration
- `tests/fixtures/real/vol.7/`:
  - `tests/fixtures/real/vol.7/ถ่ายในห้อง/`
  - `tests/fixtures/real/vol.7/ถ่ายในที่แจ้ง/` (ภาพถ่ายจริงสำหรับทดสอบชุดฟอร์มใหม่)

---

## 4. Prompt Template for New Chat
```text
เรากำลังทำ task: Polish Algorithm ในส่วนของระบบปรับเทียบและสร้างแม่แบบกระดาษคำตอบ (Template Calibration System)
อ่าน docs/NEXT_CHAT_HANDOFF.md เพื่อดึง context ล่าสุด จากนั้นเตรียมรับรายละเอียดที่เราจะระบุต่อไปนี้:
[...ระบุรายละเอียดที่ต้องการ polish...]
```
