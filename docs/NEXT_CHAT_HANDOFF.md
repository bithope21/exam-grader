# Fresh-Chat Handoff: Exam Grader v1.0.0 App Icon & Performance Polish

- **Primary Repository**: `/Users/zubinpijit/private/exam-grader` (Branch: `main`)
- **Web Repository**: `/Users/zubinpijit/bithope/apps/bithope-web` (Branch: `main`)
- **Current Status**: App Icon Polish (macOS + Windows) & Sheet Import Flow Optimization Completed.

---

## 1. ผลลัพธ์ที่ทำเสร็จสมบูรณ์ (Completed Milestones)

### A. App Icon Polish (Windows & macOS) — ไร้ขอบขาว/ไร้พื้นหลังขาว 100%
1. **Master Artwork Extraction (`docs/landing page/logo.png`)**:
   - นำ padding สีขาว/ครีม (`[253, 252, 248]`) ภายนอก squircle ออกทั้งหมดด้วย bounded floodfill (`cv2.FLOODFILL_FIXED_RANGE`) และ color decontamination / edge inpainting เพื่อป้องกันขอบขาว (white halo) หรือขอบดำ (black halo) เวลาถูก downsample
   - รักษา artwork เดิม 100%: mint squircle, กระดาษคำตอบ, ลายมือดินสอสีแดง A+, ดินสอ, ยางลบ ครบถ้วน ไม่ redesign
2. **Multi-Resolution Packaging**:
   - **macOS `resources/icons/icon.icns`**: สร้างขนาด 16, 32, 64, 128, 256, 512, 1024px ตาม Apple HIG squircle geometry ตรวจสอบแล้วว่า 4 มุมทุกขนาดมี alpha = 0
   - **Windows `resources/icons/icon.ico`**: สร้างขนาด 16, 24, 32, 48, 64, 128, 256px แบบ multi-res embedded แท้ ตรวจสอบแล้วว่า 4 มุมทุก resolution มี alpha = 0
   - **Qt Icon `src/exam_grader/resources/icon.png`**: ขนาด 512x512 RGBA โปร่งใส
3. **Windows Taskbar & Shell Identity**:
   - เพิ่ม `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bithope.examgrader.1.0.0")` ใน `src/exam_grader/__main__.py` เมื่อรันบน Windows เพื่อผูก identity ของ Taskbar เข้ากับ icon ประจำแอปอย่างถูกต้อง

### B. Student Sheet Import Flow Performance Optimization — เร็วขึ้นสูงสุด 4.7x
1. **Root Cause Analysis**:
   - **Root Cause 1 (ECC Scale)**: `findTransformECC` ใน `imaging.py:register(refined=True)` รันบนภาพ float32 ความละเอียดเต็ม 1200x1720 (2 ล้านพิกเซล) นานถึง 60 iterations กินเวลา 3.2–3.7 วินาทีต่อแผ่น
   - **Root Cause 2 (Redundant Reference Decode & Hash)**: `get_reference_image()` อ่านไฟล์และคำนวณ sha256 + `cv2.imdecode` ซ้ำ 3–5 ครั้งต่อแผ่น (เสียเวลา ~150ms)
   - **Root Cause 3 (Feature Extraction)**: Re-detect SIFT/ORB features บน static reference image ทุกแผ่น (SIFT เสียเวลา ~175ms)
   - **Root Cause 4 (Image Decode Reuse)**: `analyze` (ตอน rescue) และ `observe_student_number` เรียก `decode(data)` ซ้ำ ทั้งที่มี decoded array อยู่แล้ว (เสียเวลา ~70ms ต่อครั้ง)
2. **Optimizations Applied**:
   - **Fast Scaled ECC**: สำหรับแม่แบบขนาดใหญ่ (>860px) ให้ scale สัญญาณภาพลงเหลือไม่เกิน 860px พร้อมจำกัด iterations ที่ 25 ครั้ง แล้ว rescale homography matrix กลับ ($H = S^{-1} H_{small} S$) ลดเวลา ECC จาก 3.7s เหลือ ~0.28s (เร็วขึ้น 13 เท่า) โดยรักษาความแม่นยำ 100%
   - **In-Memory Reference Cache**: แคชภาพอ้างอิงที่ decode แล้วใน `template_manager.py` ด้วย `_REF_IMAGE_CACHE`
   - **Precomputed Reference Features Cache**: แคช SIFT/ORB keypoints & descriptors ของ reference image ใน `imaging.py`
   - **Decoded Image Reuse**: ส่ง `decoded_image` จาก `BatchWorker` ไปยัง `analyze` และ `observe_student_number` เพื่อไม่ต้องถอดรหัส QImage ซ้ำ
3. **Benchmark Before vs After**:
   - **Default #1** (`vol.1`): 0.978s/แผ่น -> **0.686s/แผ่น** (เร็วขึ้น 1.43x)
   - **Default #2** (`vol.5`): 3.831s/แผ่น (สูงสุด 4.61s) -> **0.812s/แผ่น** (เร็วขึ้น 4.72x)
   - **Default #3** (`vol.6`): 1.949s/แผ่น -> **1.039s/แผ่น** (เร็วขึ้น 1.88x)
   - **Ground Truth Preservation**: ผลคะแนน Vol.5 และ Vol.6 ตรง 100% (นักเรียน 1, 2, 3, 4 ได้ 11, 6, 6, 29 คะแนนตามจริง)

### C. Automated Test & Packaging
- **Unit & Integration Tests**: 127/127 passed (`.venv/bin/pytest tests/` 100% pass)
- **Performance Regression Guard**: เพิ่ม `tests/test_benchmark_performance.py` คุมเกณฑ์ความเร็วไม่ให้ถอยกลับ
- **Linter & Types**: `ruff check` 0 errors, `mypy src` 0 errors
- **macOS Build**: `scripts/build/build.py` + `codesign --verify --deep --strict` + `--self-check` + `--smoke-ui` + `scripts/build/package_dmg.sh` สร้าง `Exam-Grader-v1.0.0-macOS-Apple-Silicon.dmg` เรียบร้อย

---

## 2. Important Files & Components

- `src/exam_grader/__main__.py`: Application startup, initialization, Windows AppUserModelID
- `src/exam_grader/imaging.py`: Registration, SIFT/ORB feature caching, fast scaled ECC, OMR ink analysis
- `src/exam_grader/template_manager.py`: Template definitions, reference image caching
- `src/exam_grader/identity.py`: Student number observation, pre-decoded image reuse
- `src/exam_grader/exam_ui.py`: BatchWorker student sheet import loop
- `scripts/build/build.py`: PyInstaller compilation script
- `scripts/build/package_dmg.sh`: macOS DMG packaging script
- `scripts/build/windows-installer.iss`: Inno Setup installer script
- `.github/workflows/release.yml`: Release workflow (Windows + macOS)

---

## 3. Invariants & Guardrails

- **Zero Accuracy Loss**: การปรับปรุงประสิทธิภาพต้องไม่ลด accuracy, registration robustness หรือ fail-closed logic
- **100% Offline & Local**: ห้ามต่ออินเทอร์เน็ต, ห้ามส่งข้อมูลขึ้นคลาวด์เด็ดขาด
- **Transparent Icons**: ไอคอนต้องไม่มีขอบขาวหรือ white padding บนทุก OS และทุกขนาด
