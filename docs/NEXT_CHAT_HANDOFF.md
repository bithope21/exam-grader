# Fresh-chat handoff

Repository: `/Users/zubinpijit/private/exam-grader`
App/Web Repository: `/Users/zubinpijit/bithope/apps/bithope-web`

อ่านก่อน: `progress.md`, `docs/DECISIONS.md`, `docs/landing page/EXAM_GRADER_LANDING_PAGE_AGENT_BRIEF.md`, `docs/NEXT_CHAT_HANDOFF.md`
Git baseline: `2f1479e` + uncommitted changes ใน working tree (local only, ห้าม push).

---

## สรุปสถานะล่าสุด (Exam Grader Landing Page Foundation & Redesign Ready)

ได้สร้างโครงสร้างพื้นฐานของหน้า Landing Page สำหรับ **Exam Grader** เรียบร้อยแล้วที่ route:
`https://bithope.app/exam-grader` (ในโค้ดคือ `/Users/zubinpijit/bithope/apps/bithope-web`)
ผู้ใช้ต้องการ **Redesign** หน้า Landing Page ใหม่ในแชทถัดไป โดยมีบริบทและทรัพยากรที่พร้อมใช้งานดังนี้:

1. **โครงสร้างโค้ดหน้าเว็บ (`bithope-web`)**:
   - Route หลัก: `src/app/exam-grader/page.tsx`
   - Config ลิงก์ส่วนกลาง: `src/app/exam-grader/constants.ts` (`EXAM_GRADER_LINKS`)
   - Components ย่อย: `src/app/exam-grader/components/` (`ExamGraderNav`, `HeroSection`, `AppPreviewSection`, `WorkflowSection`, `BenefitsSection`, `DownloadSection`, `CommunitySection`, `ExamGraderFooter`)
   - Build & Static Prerendering: Next.js 16.2.2 build ผ่าน 100%, 0 TypeScript errors, 0 Lint errors, Zero regression กับ route อื่น (`/`, `/daipay`, `/myrai`)

2. **Assets 2D & Screenshots ที่จัดเตรียมไว้แล้ว (`public/exam-grader/`)**:
   - `screenshots/`: ภาพจับหน้าจอจริงจาก native app ด้วย PySide6 (`exam-grader-dashboard.png`, `exam-grader-review.png`, `exam-grader-export.png`, `exam-grader-overview.png`)
   - `illustrations/`: ภาพ 2D โปร่งใส สไตล์ Notion editorial (`teacher-2d.png`, `student-2d.png`, `blackboard-2d.png`, `books-stationery-2d.png`, `cat-2d.png`, `paper-answer-sheet-2d.svg`)
   - `icons/`: ไอคอนแอปพลิเคชัน (`icon-examgrader.png`) และเวกเตอร์ขั้นตอน (`step-*.svg`)

3. **Invariants & Safety Gates**:
   - **Truthful Marketing Gate**: เคลมเฉพาะฟีเจอร์ที่มีจริงในแอป (Offline 100%, Human Review, Bulk Edit, Custom Template, Excel .xlsx & Checked .jpg export) ห้ามเคลม PDF, CSV หรือ Windows installer ที่ยังไม่เสร็จ
   - **Download Status**: macOS Apple Silicon เป็น Beta, ส่วน macOS Intel และ Windows เป็น Coming Soon
   - **Security Instructions**: อธิบายขั้นตอนความปลอดภัยผ่าน System Settings > Privacy & Security > Open Anyway อย่างถูกต้อง ไม่สอน bypass
   - **Zero Regression**: แก้ไขเฉพาะ `src/app/exam-grader/` และ `public/exam-grader/` ห้ามกระทบ shared logic ใน bithope-web

4. **งานถัดไป (Next Exact Action)**:
   - รับคำสั่ง/ทิศทาง Design ใหม่จากผู้ใช้ และดำเนินการ **Redesign** หน้า `/exam-grader` (ปรับ layout, hero composition, visual rhythm หรือ styling ตามที่ผู้ใช้ต้องการ)

---

## สรุปสถานะรอบก่อนหน้า (Completed: Review Multi-Select Checkbox UX Polish & State Synchronization)

งานพัฒนาและทดสอบทั้งหมดในรอบนี้เสร็จสมบูรณ์ 100% ครบถ้วนตามเป้าหมายและผ่าน 8 Quality Gates:

1. **Review — Multi-Select Checkbox Architecture & UX (`exam_ui.py`)**:
   - แก้ไขปัญหาคลิกติดบ้างไม่ติดบ้างและคลิกซ้ำเพื่อยกเลิกไม่ได้ ด้วยการยกเลิก `cellClicked` callback ที่ทำให้เกิด Double-Trigger Race Condition กับ Built-in Qt Delegate
   - พัฒนา `CheckBoxDelegate(QStyledItemDelegate)` สำหรับ Column 0 ของ `issue_table`:
     - ขยาย Hit Area เต็มความกว้างเซลล์ (52px) คลิกง่าย ไม่ต้องเล็งเฉพาะสี่เหลี่ยมเล็ก ๆ
     - จัดวาง Checkbox Indicator ให้อยู่กึ่งกลางเซลล์ทั้งแนวนอนและแนวตั้งอย่างประณีต
     - ดักจับเฉพาะ Left-Click Release และ Space Key พร้อมรักษา Native Qt Focus & Accessibility
     - ดักจับ Left-Click Press เพื่อป้องกันปัญหา Rubber-band/Row Drag Glitch
   - กำหนด Single Source of Truth ผ่าน Stable Issue Keys (`self.selected_issue_keys: set[tuple]`):
     - ป้องกันปัญหา Checkbox รีเซ็ตทิ้งเมื่อ Refresh หรือ Re-sort
     - ซิงค์ [เลือกทั้งหมด], [ล้างการเลือก], ป้ายนับจำนวน (`เลือก N รายการ`), และปุ่ม [นำไปใช้และบันทึกที่เลือก] อย่างแม่นยำ
     - เคลียร์เฉพาะแถวที่ถูก resolve ออกจาก selection อัตโนมัติหลังบันทึกชุด
   - เพิ่มชุดทดสอบครอบคลุม `test_review_tab_checkbox_delegate_ux_and_state_preservation` ใน `tests/test_ui.py` (10/10 pass)

---

## สรุปผล Quality Gates (8/8 Passed)

1. **Unit & Regression Tests**: 126/126 passed (`PYTHONPATH=. .venv/bin/pytest tests/` สำเร็จ 100% ใน 96 วินาที)
2. **Ruff Lint**: 0 errors (`.venv/bin/ruff check src tests` ผ่านหมด)
3. **Mypy Type Check**: 0 errors across 20 source files (`.venv/bin/mypy src` ผ่านหมด)
4. **PyInstaller Build**: Build สำเร็จเป็น macOS arm64 `.app` bundle (`scripts/build/build.py`)
5. **Strict Deep Codesign**: `codesign --verify --deep --strict dist/ExamGrader.app` ผ่าน (code 0)
6. **Packaged Self-Check**: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check` ผ่าน (code 0)
7. **Packaged Smoke-UI**: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui` ผ่าน (code 0)
8. **Visual QA**: ตรวจสอบภาพจับหน้าจอ Review Multi-Select Checkbox ใน Light และ Dark modes พบว่าจัดวางกึ่งกลางสวยงาม สถานะถูกต้องสมบูรณ์

---

## งานถัดไปที่แนะนำ (Next Recommended Action)
- ระบบ Review Multi-Select Checkbox UX มีเสถียรภาพสูง พร้อมใช้งานในเวอร์ชัน Production
- รอรับคำสั่งหรือฟีเจอร์ถัดไปจากผู้ใช้


## สรุปสถานะรอบก่อนหน้า (Completed: Review Bulk Edit, Student Number Hardening & Custom Template Overlay)

งานพัฒนาและทดสอบทั้งหมดในรอบนี้เสร็จสมบูรณ์ 100% ครบถ้วนตามเป้าหมายและผ่าน 8 Quality Gates:

1. **Review — Bulk Edit (`exam_ui.py`, `review_service.py`)**:
   - เพิ่ม Checkbox เลือกหลายแถวในคอลัมน์แรก (Col 0) ของตารางตรวจทาน (`issue_table`)
   - แถบ Bulk Action Toolbar: ปุ่ม [เลือกทั้งหมด], [ล้างการเลือก], ป้ายนับจำนวน (`เลือก N รายการ`), เมนูเลือกคำตอบ/สถานะ (`bulk_combo`), และปุ่มบันทึกชุด (`bulk_apply_btn`)
   - ระบบบันทึกแบบ Transaction-Safe ผ่าน `ReviewService.bulk_resolve(exam_id, operations)` รวบรวม answer_overrides, attendance, identities บันทึกใน transaction เดียว
   - ปลอดภัย ไม่เขียนทับแถวที่ไม่ได้เลือก (unselected rows untouched) และ refresh UI อัตโนมัติ ปรับสถานะนักเรียนที่ตรวจครบเป็น "พร้อม" ทันที
   - ผ่านการทดสอบ UI ใน `tests/test_ui.py::test_review_tab_bulk_edit_ui`

2. **Student Number Logic Hardening (`identity.py`, `review_service.py`)**:
   - Vol.6 ground truth (`tests/fixtures/real/vol.6/ground_truth.json`): `IMG_0911` -> `52`, `IMG_0912` -> `13`, `IMG_0913` -> `67`, `IMG_0914` -> `19`
   - ใช้หลักฐานจากตัวอ่านเป็นหลัก (Recognizer evidence first): คำนวณ confidence score และ confidence margin ใน `identity.py:observe()`
   - ตัด sub-segmentation fragments ที่ไม่สมบูรณ์เมื่อพบหลายหลัก (len(boxes) >= 2)
   - `ReviewService.adopt_numbers()` รับเลขเฉพาะที่มีความมั่นใจสูง (confidence >= 80.0, margin >= 15.0) หรือตัวเลือกเดี่ยว รายการเลขที่ขาดใช้เป็นเพียง tie-breaker constraint ห้ามเดาเลขจากช่องว่าง
   - เลขชนกันหรือความมั่นใจต่ำจะ fail closed ส่งไปหน้า Review พร้อมแยกสถานะชัดเจน (`duplicate`, `missing`, `uncertain`, `out_of_range`)
   - ผ่านการทดสอบ regression ใน `tests/test_vol6_uat.py` (2/2 pass)

3. **Custom Template Checked Overlay Alignment (`exporting.py`)**:
   - รักษาสัจพจน์ `detected cell == rendered overlay cell`
   - แก้ไข `exporting.py:export_results()` ให้โหลด template definition ที่แท้จริงของข้อสอบผ่าน `load_exam_template_def(flow.database, exam_id)` ไม่ตกหล่นไปเป็น Default #1 (836×818)
   - ส่ง `template_def` ต่อให้ `checked_image()`, snapshot export, และ render provenance ครบถ้วน
   - ผ่านการทดสอบ regression `test_custom_template_checked_overlay_alignment` ใน `tests/test_export.py` และตรวจ visual inspection ของภาพผลตรวจขนาด 1200×1720 ว่าตำแหน่ง ✓/✗ ตรงกลางช่องคำตอบ 100%

---

## สรุปผล Quality Gates (8/8 Passed)

1. **Unit & Regression Tests**: 125/125 passed (`.venv/bin/pytest tests/` สำเร็จ 100% ใน 98 วินาที)
2. **Ruff Lint**: 0 errors (`.venv/bin/ruff check .` ผ่านหมด)
3. **Mypy Type Check**: 0 errors across 20 source files (`.venv/bin/mypy src` ผ่านหมด)
4. **PyInstaller Build**: Build สำเร็จเป็น macOS arm64 `.app` bundle (`scripts/build/build.py`)
5. **Strict Deep Codesign**: `codesign --verify --deep --strict dist/ExamGrader.app` ผ่าน (code 0)
6. **Packaged Self-Check**: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check` ผ่าน (code 0)
7. **Packaged Smoke-UI**: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui` ผ่าน (code 0)
8. **Visual QA**: ตรวจสอบภาพจับหน้าจอ Review Bulk Edit (ก่อน/หลัง) และภาพ Checked Overlay บนแม่แบบกำหนดเอง ผ่านการตรวจเรียบร้อย


---

## ส่วนเสริมล่าสุด: Landing Page Redesign & Minimal Editorial Art Direction (bithope-web)

1. **Editorial Art Direction ("วาดน้อย แต่จำได้")**:
   - ปรับสไตล์ภาพประกอบทั้งหมดเป็น **Minimal Colored-Pencil / Crayon Editorial Illustration** (สไตล์หนังสือภาพ/บทความวรรณกรรม)
   - ใช้สีจำกัด 3-5 สี (forest green, warm orange, soft cream, charcoal, muted blue) พร้อม texture เกรนดินสอไม้
   - **Hero Illustration**: ครู + กระดาษคำตอบ + ดินสอส้ม (ตัด object รกทั้งหมด เช่น แอปเปิล แก้วดินสอ กองหนังสือ ออก 100%)
   - **Workflow 6 Steps (1 visual metaphor แต่ละข้อ)**:
     - 01 สร้างชุดข้อสอบ: กระดาษเปล่า + ดินสอไม้
     - 02 กำหนดและอนุมัติเฉลย: กระดาษคำตอบ + เครื่องหมายถูก ✓ สีส้ม
     - 03 นำเข้ากระดาษคำตอบ: กระดาษข้อสอบ 3 แผ่นซ้อนกัน
     - 04 ตรวจแบบ Offline: กระดาษ + laptop เล็ก ๆ + สัญลักษณ์ cloud-cross
     - 05 ตรวจทานจุดกำกวม: แว่นขยายส้ม + วงกลมที่มีเครื่องหมาย ?
     - 06 ส่งออกคะแนน Excel: ตาราง spreadsheet สีเขียว + กระดาษเฉลย
2. **Visual Polish & Noise Elimination**:
   - นำ pill tag สีเขียวออกจากทุก section header และ workflow card
   - นำ legacy floating assets 4 ชิ้นออกจาก Hero
   - Hero background ใช้เฉดเขียว sage ห้องเรียนอ่อน (#EEF4F0) เต็มหน้าจอแรก แล้วค่อย ๆ เฟดเนียนตาลงสู่ #FAF8F5
   - ปรับสถานะเป็น **"ฟรี 100%"** และ **"ดาวน์โหลดฟรี"** ทั้งหน้า (ตัดคำว่า Beta, Trial, Pricing ออกทั้งหมด)
   - เพิ่ม Modal ป๊อปอัปแบบ Interactive เมื่อคลิกแต่ละขั้นตอน แสดงภาพหน้าจอจริงจาก PySide6 App
   - ไดคัทโลโก้ Exam Grader ด้วย OpenCV flood fill ให้โปร่งใสคมชัดโดยไม่กินเนื้อกระดาษสีขาว
3. **Build & Quality Gates**:
   - Next.js 16.2.2 Static Build (npm run build in bithope-web) ผ่าน 100% (59/59 static pages prerendered, 0 TypeScript/lint errors)
   - รองรับทุก Viewport (Desktop 1280px, Tablet 768px, Mobile 375px/320px) พร้อมคำนวณ word-break ให้แสดงผลภาษาไทยสมบูรณ์
