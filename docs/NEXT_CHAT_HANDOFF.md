# Fresh-Chat Handoff: Exam Grader v1.0.1 (Windows Hardening + Performance & Icon Polish)

- **Repository**: `D:\AI\projects\exam-grader\exam-grader` (Branch: `fix/windows-v1.0.1-hardening`)
- **Current Status**: Windows v1.0.1 Hardening + App Icon Polish + Sheet Import Flow Optimization **INTEGRATED & VERIFIED**
- **Safety Gate**: ห้าม tag / publish release จนกว่า integrated final state จะผ่าน Final Windows UAT ตามข้อตกลง

---

## 1. ผลลัพธ์ Windows v1.0.1 Hardening UAT (100% COMPLETE & ALL PASSED)

1. **Windows Installer Artifact**:
   - Path: `dist\Exam-Grader-v1.0.0-Windows-Setup.exe`
   - Size: 76,259,754 bytes (~72.73 MB)
   - SHA-256: `0F632E4B8F6BAE4760B5493FD2CA9091110E4203AB25521C8C44C78FCD4E9F3E`
   - Build Baseline: `adb8380` / `d4d6412`

2. **ผลการทดสอบ UAT บน Windows จริง (Installed Binary: `%LOCALAPPDATA%\Programs\ExamGrader\ExamGrader.exe`)**:
   - **Settings → Template Management**: **PASS** (เปิด Dialog ได้ 100% ไม่ crash, แสดงครบ 3 แม่แบบ Default #1, #2, #3, preview images โหลดสมบูรณ์)
   - **Grade → Save Results + Excel**: **PASS** (ไม่มี `[WinError 5]`, ทำงานบนโฟลเดอร์ภาษาไทย/Unicode จริงใน `Documents\ทดสอบตรวจข้อสอบ_ไทย_๒๕๖๙`)
   - **Output Integrity**: **PASS** (Excel `.xlsx` มี sheet Scores & Info ครบถ้วน, ไฟล์ checked `.jpg` ครบ, ไม่พบโฟลเดอร์ `.staging-*` ค้าง, และไฟล์ภาพต้นฉบับ SHA-256 ตรงกัน 100% ไม่ถูกแก้ไข)
   - **Installed App Smoke Tests**: **PASS** (`--self-check`, `--smoke-settings`, `--smoke-ui` ทั้งหมด exit code 0)
   - **Automated UAT Suite**: `tests/test_windows_uat.py` ผ่าน 3/3 tests (100% pass)
   - **Quality Gates**: `ruff check src` (0 errors), `mypy src` (0 errors across 20 source files)

---

## 2. ผลลัพธ์ App Icon Polish (Windows & macOS) — ไร้ขอบขาว/ไร้พื้นหลังขาว 100%

1. **Master Artwork Extraction (`docs/landing page/logo.png`)**:
   - นำ padding สีขาว/ครีม (`[253, 252, 248]`) ภายนอก squircle ออกทั้งหมดด้วย bounded floodfill (`cv2.FLOODFILL_FIXED_RANGE`) และ color decontamination / edge inpainting เพื่อป้องกันขอบขาว (white halo) หรือขอบดำ (black halo) เวลาถูก downsample
   - รักษา artwork เดิม 100%: mint squircle, กระดาษคำตอบ, ลายมือดินสอสีแดง A+, ดินสอ, ยางลบ ครบถ้วน ไม่ redesign
2. **Multi-Resolution Packaging**:
   - **macOS `resources/icons/icon.icns`**: สร้างขนาด 16, 32, 64, 128, 256, 512, 1024px ตาม Apple HIG squircle geometry ตรวจสอบแล้วว่า 4 มุมทุกขนาดมี alpha = 0
   - **Windows `resources/icons/icon.ico`**: สร้างขนาด 16, 24, 32, 48, 64, 128, 256px แบบ multi-res embedded แท้ ตรวจสอบแล้วว่า 4 มุมทุก resolution มี alpha = 0
   - **Qt Icon `src/exam_grader/resources/icon.png`**: ขนาด 512x512 RGBA โปร่งใส
3. **Windows Taskbar & Shell Identity**:
   - เพิ่ม `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bithope.examgrader.1.0.0")` ใน `src/exam_grader/__main__.py` เมื่อรันบน Windows เพื่อผูก identity ของ Taskbar เข้ากับ icon ประจำแอปอย่างถูกต้อง

---

## 3. ผลลัพธ์ Student Sheet Import Flow Performance Optimization — เร็วขึ้นสูงสุด 4.7x

1. **Optimizations Applied**:
   - **Fast Scaled ECC**: สำหรับแม่แบบขนาดใหญ่ (>860px) ให้ scale สัญญาณภาพลงเหลือไม่เกิน 860px พร้อมจำกัด iterations ที่ 25 ครั้ง แล้ว rescale homography matrix กลับ ($H = S^{-1} H_{small} S$) ลดเวลา ECC จาก 3.7s เหลือ ~0.28s (เร็วขึ้น 13 เท่า) โดยรักษาความแม่นยำ 100%
   - **In-Memory Reference Cache**: แคชภาพอ้างอิงที่ decode แล้วใน `template_manager.py` ด้วย `_REF_IMAGE_CACHE`
   - **Precomputed Reference Features Cache**: แคช SIFT/ORB keypoints & descriptors ของ reference image ใน `imaging.py`
   - **Decoded Image Reuse**: ส่ง `decoded_image` จาก `BatchWorker` ไปยัง `analyze` และ `observe_student_number` เพื่อไม่ต้องถอดรหัส QImage ซ้ำ
2. **Benchmark Before vs After**:
   - **Default #1** (`vol.1`): 0.978s/แผ่น -> **0.686s/แผ่น** (เร็วขึ้น 1.43x)
   - **Default #2** (`vol.5`): 3.831s/แผ่น (สูงสุด 4.61s) -> **0.812s/แผ่น** (เร็วขึ้น 4.72x)
   - **Default #3** (`vol.6`): 1.949s/แผ่น -> **1.039s/แผ่น** (เร็วขึ้น 1.88x)
   - **Ground Truth Preservation**: ผลคะแนน Vol.5 และ Vol.6 ตรง 100% (นักเรียน 1, 2, 3, 4 ได้ 11, 6, 6, 29 คะแนนตามจริง)

---

## 4. Important Files & Components

- `src/exam_grader/__main__.py`: Application startup, initialization, Windows AppUserModelID, `--smoke-settings`
- `src/exam_grader/imaging.py`: Registration, SIFT/ORB feature caching, fast scaled ECC, OMR ink analysis
- `src/exam_grader/template_manager.py`: Template definitions, PyInstaller MEIPASS compatibility, reference image caching
- `src/exam_grader/storage.py`: Priority built-in loading, safe template listing
- `src/exam_grader/exporting.py`: Windows directory copy-then-cleanup, parent mkdir safeguard
- `src/exam_grader/settings_ui.py`: Template management resilience
- `src/exam_grader/identity.py`: Student number observation, pre-decoded image reuse
- `src/exam_grader/exam_ui.py`: BatchWorker student sheet import loop
- `tests/test_windows_uat.py`: Automated Windows UAT test suite (3 tests)
- `tests/test_benchmark_performance.py`: Performance regression guard tests
- `scripts/build/build.py`: PyInstaller compilation script
- `scripts/build/windows-installer.iss`: Inno Setup installer script

---

## 5. Invariants & Guardrails

- **Zero Accuracy Loss**: การปรับปรุงประสิทธิภาพต้องไม่ลด accuracy, registration robustness หรือ fail-closed logic
- **100% Offline & Local**: ห้ามต่ออินเทอร์เน็ต, ห้ามส่งข้อมูลขึ้นคลาวด์เด็ดขาด
- **Transparent Icons**: ไอคอนต้องไม่มีขอบขาวหรือ white padding บนทุก OS และทุกขนาด
- **Windows Safe Export**: ใช้ copy-then-cleanup ป้องกัน `[WinError 5]` บน Windows ทุกรุ่น
