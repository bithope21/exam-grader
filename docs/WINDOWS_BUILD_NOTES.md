# Windows Build & Runtime Checklist (`docs/WINDOWS_BUILD_NOTES.md`)

เอกสารสรุปบทเรียน Root Cause, ข้อจำกัดเฉพาะ Windows, การแก้ไข และ Checklist ขั้นตอนการ Build / Verification เพื่อใช้เป็นคู่มือสำหรับ Agent ในรอบถัดไป

---

## 1. ปัญหาที่พบ และ Root Cause (Issues & Root Causes)

| ปัญหา (Issue) | Root Cause หลัก |
| :--- | :--- |
| **1. Console Window กระพริบขณะรัน** | `subprocess.Popen` / `subprocess.run` ใน Tesseract/helper path ไม่ได้ตั้งค่า Windows subprocess creation flags (`CREATE_NO_WINDOW`) และ `STARTUPINFO` (`STARTF_USESHOWWINDOW`) ทำให้ OS สร้างหน้าต่าง `cmd.exe`/`tesseract.exe` ขึ้นมาแสดงบน UI |
| **2. Student Number Recognition อ่านแย่กว่า Mac และช้า ~6–19 วินาที/แผ่น** | `identity.py` ตรวจพบ Tesseract บน Windows (`AppData\Local\Programs\Tesseract-OCR\tesseract.exe`) จึงบายพาส Bundled Digit Model แล้วสั่งรัน Tesseract subprocess 17 ครั้ง + เขียนไฟล์ PNG 15 ไฟล์ลง Temp Disk ต่อ 1 แผ่น Tesseract (ซึ่ง train ด้วย Printed Latin fonts) อ่านตัวเลขลายมือไทยผิด/ล้มเหลว ส่งผลให้ตั้ง `segmentation_incomplete=True` หรือ `candidate_disagreement=True` แล้วล้าง candidate ทิ้งเป็น `None` |
| **3. Student Tab ไม่แสดง `พร้อม/ต้องตรวจ · เลขที่ X`** | (1) ผลจากข้อ 2 ทำให้ candidate กลายเป็น `None`<br>(2) เงื่อนไข `if not review and not source.get("student_number") ...` ข้ามการแสดงสถานะเมื่อเลขที่ถูก prefill<br>(3) Hardcode `item.setSizeHint(QSize(0, 44))` ทำให้ข้อความ 2 บรรทัดบน Windows Segoe UI font metrics โดนตัดตกขอบล่าง |
| **4. ตรวจทานจน List ว่าง แต่ Results บล็อกว่า "ยังมีภาพที่ไม่ได้ตรวจทาน..."** | `ReviewService.set_number()` บันทึกเฉพาะตาราง `identities` แต่ **ไม่ได้เรียก `self.finalize(exam_id)`** ทำให้ตาราง `reviews` ไม่มี record ของภาพนั้น แม้ UI คิวตรวจจะว่างแล้ว แต่ `Workflow.snapshot()` ที่เช็ค `reviews` Table Direct จะเจอ `review is None` แล้วไม่อนุญาตให้ออกผล |
| **5. โลโก้/ไอคอนแอปบน Taskbar และ Titlebar ไม่ถูกต้อง** | ไดอะล็อกและ Window ไม่ได้ตั้งค่า `setWindowIcon` จาก `QApplication.windowIcon()` และขาดการกำหนด `SetCurrentProcessExplicitAppUserModelID` สำหรับ Windows Taskbar Process Grouping |
| **6. หน้าต่าง modal ตรวจทานเปิดใหญ่เกินขอบจอ** | ไดอะล็อกคำนวณขนาดคงที่โดยไม่ได้จำกัดสัดส่วนกับ `QApplication.primaryScreen().availableGeometry()` บนจอ Windows ที่มี DPI scaling หรือความละเอียดต่ำ |

---

## 2. ข้อจำกัดเฉพาะ Windows (Windows-Specific Constraints)

1. **Subprocess Spawn Cost**: การสั่งรัน subprocess บน Windows มี overhead สูง (~200–500 ms ต่อครั้ง) ต่างจาก POSIX `fork` การเรียก subprocess ซ้ำหลายสิบครั้งต่อแผ่นจะทำให้ระบบช้าลงอย่างมาก
2. **Subprocess Windowing**: Windows GUI application จะแสดงหน้าต่าง Console สำหรับ subprocess ทุกครั้ง หากไม่ใส่ `creationflags=subprocess.CREATE_NO_WINDOW` และ `STARTUPINFO`
3. **OpenCV CPU Execution**: OpenCV บน Windows x86_64 ทำงานบน CPU Instruction Set ปกติ (ไม่มี Apple Accelerate / Metal Framework เหมือน Mac M-series) การทำ Homography/SIFT 5000 Keypoints 1 รอบใช้เวลา ~2.6–3.4 วินาที และหากมีข้อสอบคาบเส้นจนเกิด Rescue Pass (`refined=True`) จะรัน 2 รอบรวม ~6.0–6.6 วินาที
4. **Font Metrics & Line Height**: ฟอนต์ Segoe UI / Leelawadee UI บน Windows ใช้ความสูงต่อบรรทัดมากกว่า SF Pro บน Mac ข้อความ 2 บรรทัดต้องการความสูง 54–60px การ Hardcode `44px` จะทำให้ข้อความขอบล่างถูกกลืน
5. **Frozen Executable Resource Path**: PyInstaller ฝังไฟล์ไว้ใต้ `_internal/exam_grader/resources/` การอ้างอิง resource ต้องใช้ helper หรือ `bundled_digit_model_path()` ที่รองรับทั้ง dev mode และ frozen mode

---

## 3. การแก้ไขที่ทำไปแล้ว (Implemented Fixes)

- `src/exam_grader/identity.py`:
  - ปรับให้ **Bundled Digit Model (`student_number_digit_model.npz`) เป็น Primary Path บนทุก OS** หากโหลดและวิเคราะห์ตัวเลขได้ ให้คืนผลลัพธ์โมเดลทันที (<50ms, 0 Tesseract calls)
  - เก็บ Tesseract ไว้เป็น Fallback เฉพาะเมื่อไม่มีโมเดล หรือวิเคราะห์ไม่ได้จริงเท่านั้น
  - เพิ่ม `_subprocess_windows_flags()` (`CREATE_NO_WINDOW` + `STARTF_USESHOWWINDOW`) สำหรับ subprocess
- `src/exam_grader/review_service.py` & `src/exam_grader/exam_ui.py`:
  - เพิ่ม `self.finalize(source["exam_id"])` ใน `set_number()`, `_save_issue_value()`, และ `save_all_issues()` เพื่อสร้าง record ในตาราง `reviews` ทันทีเมื่อมีการบันทึกเลขที่/การแก้ไข
- `src/exam_grader/exam_ui.py`:
  - แก้เงื่อนไขสถานะ `if not review and number_observation.get("candidate"):` ให้แสดงเลขที่แม้จะถูก prefill
  - ปรับ `setSizeHint` ใน `_add_student_item` ให้คำนวณความสูงตาม Font Metrics (`fontMetrics().lineSpacing() * lines + 16`) รองรับทุก DPI
- `src/exam_grader/__main__.py` & UI Dialogs:
  - เพิ่ม `SetCurrentProcessExplicitAppUserModelID` และสั่ง `setWindowIcon` ให้ทุกไดอะล็อก
  - จำกัดขนาดไดอะล็อกไม่ให้เกิน `availableGeometry()` ของหน้าจอ

---

## 4. สิ่งที่ต้องทำ / ห้ามทำ ในการ Build ครั้งต่อไป (Build Checklist)

### สิ่งที่ต้องทำ (DOs):
- [ ] **Verify Provenance หลัง Build**: ตรวจสอบเสมอว่า `dist/ExamGrader/_internal/exam_grader/resources/student_number_digit_model.npz` มี SHA-256 ตรงกับไฟล์ต้นฉบับ (`aabeeb9bab4fdfad481facaa627c9efb521707e7783123746928776e74153502`)
- [ ] **ใช้ `_subprocess_windows_flags()`**: หากมีการเพิ่ม subprocess ใหม่บน Windows ต้องใส่ flag ซ่อนหน้าต่างเสมอ
- [ ] **เรียก `finalize()` เมื่อเปลี่ยน State**: ทุกครั้งที่มีการแก้ไข `identities`, `answer_overrides`, หรือ `attendance` ต้องแน่ใจว่ามีการเรียก `ReviewService.finalize()` เพื่อซิงค์ตาราง `reviews`
- [ ] **ใช้ Font Metrics สำหรับ UI Item Height**: คำนวณความสูงของ QListWidgetItem/QTableWidgetItem ด้วย `fontMetrics().lineSpacing()` เพื่อรองรับ DPI Scaling
- [ ] **ใช้สคริปต์ `scripts/build/build.py` ในการสั่ง Build PyInstaller**

### ห้ามทำ (DON'Ts):
- [ ] **ห้าม assume ว่า build ล่าสุดใช้ source ล่าสุด** — ต้อง verify executable timestamp และ resource hash เสมอ
- [ ] **ห้าม Hardcode ขนาดความสูง UI เป็น Pixel คงที่** (เช่น `44px` หรือ `56px`) สำหรับข้อความหลายบรรทัด
- [ ] **ห้ามปิด Validation ใน `Workflow.snapshot()`** — ต้องแก้ให้ DB State Transition ทำงานถูกต้องที่ต้นเหตุ
- [ ] **ห้ามแยก Logic การอ่านตัวเลขตาม OS (`sys.platform == 'win32'`)** — พฤติกรรมต้อง Deterministic เหมือนกันทุก OS
- [ ] **ห้ามรัน Tesseract OCR ซ้ำซ้อนเมื่อ Bundled Digit Model ใช้งานได้**
- [ ] **ห้ามจูน Model Weights, Ranking, OMR หรือ Crop Geometry** โดยไม่มีคำสั่งเฉพาะจาก Product Owner

---

## 5. คำสั่ง Build ที่พิสูจน์แล้วว่าใช้งานได้ (Proven Build Command)

รันคำสั่ง PyInstaller ผ่าน Python Environment ของโครงการ:

```powershell
.venv\Scripts\python.exe scripts/build/build.py
```

**ผลลัพธ์การ Build**:
- Executable Target: `dist/ExamGrader/ExamGrader.exe`
- Mode: `--windowed` (No main console), `--collect-data exam_grader`,ฝังไอคอน `resources/icons/icon.ico`

---

## 6. Quick Validation ขั้นต่ำหลัง Pull / Build (Minimal Verification Steps)

หลัง `git pull` หรือสั่ง Build ใหม่ ให้รันสคริปต์ตรวจสอบขั้นต่ำดังนี้:

1. **ตรวจสอบ Provenance และ Resource Hash**:
   ```powershell
   .venv\Scripts\python.exe -c "
   import hashlib
   from pathlib import Path
   p = Path('dist/ExamGrader/_internal/exam_grader/resources/student_number_digit_model.npz')
   print('PACKAGED_MODEL_HASH:', hashlib.sha256(p.read_bytes()).hexdigest())
   "
   ```
   *(ต้องได้ hash: `aabeeb9bab4fdfad481facaa627c9efb521707e7783123746928776e74153502`)*

2. **รัน Focused Test Suite (ใช้เวลา ~15–20 วินาที)**:
   ```powershell
   .venv\Scripts\pytest.exe tests/test_identity.py tests/test_workflow.py tests/test_windows_rc.py tests/test_windows_uat.py
   ```

3. **จุดที่ต้อง Verify จากการรัน**:
   - [ ] Tesseract Subprocess Calls = 0 เมื่อ Bundled Model ใช้งานได้
   - [ ] Identity Processing Time < 100 ms ต่อแผ่น
   - [ ] Student Tab แสดงข้อความสถานะ `พร้อม/ต้องตรวจ · เลขที่ X` ครบถ้วน
   - [ ] เมื่อคิว Review ว่าง สามารถเข้าหน้า Results และ Export Excel ได้โดยไม่เกิด `ValueError`
   - [ ] ไม่มีหน้าต่าง Command Prompt กระพริบขณะประมวลผล
