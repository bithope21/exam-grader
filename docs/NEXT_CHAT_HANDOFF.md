# Fresh-Chat Handoff: Exam Grader v1.0.1 Published & Live

- **Repository**: `D:\AI\projects\exam-grader\exam-grader` (Branch: `main`)
- **Release Tag**: `v1.0.1`
- **Release URL**: https://github.com/bithope21/exam-grader/releases/tag/v1.0.1
- **Release ID**: `387664293`
- **Current Status**: **RELEASE v1.0.1 PUBLISHED & 100% VERIFIED LIVE OVER HTTP GET**

---

## 📌 DEFERRED Tasks (งานที่ชะลอไว้ทำรอบถัดไป)

บันทึกงานที่เลื่อนไปทำในรอบหน้าตามที่ User กำหนด:

1. **Task 1 — ตัดขอบขาวของ LOGO**:
   - Master artwork / logo ยังมีขอบขาวที่ยังไม่ได้ตัดออกให้เนี้ยบ ต้องทำขอบโปร่งใส/ตัดขอบขาวออกให้เรียบร้อยสมบูรณ์

2. **Task 2 — ปรับปรุง Algorithm Prefill ให้ดีเหมือนบน Mac**:
   - Polish algorithm การ prefill เลขที่นักเรียน (student number / candidate prefill) บน Windows ให้แม่นยำและเสถียรทัดเทียมกับบน macOS

3. **Task 3 — แก้ช่องกรอก "ป." กินหัว ป ปลา (Text Clipping)**:
   - ช่องกรอกระดับชั้น "ป." มีปัญหา layout/padding ทำให้ตัดหรือกินหัวตัวอักษร "ป" (font ascent clipping) เกิดขึ้นทั้งบน **macOS และ Windows**

---

## 1. Verified Release Artifacts & SHA-256 Checksums

| Asset Name | Size | SHA-256 Checksum | HTTP GET Verification |
|------------|------|------------------|-----------------------|
| `Exam-Grader-v1.0.1-macOS-Apple-Silicon.dmg` | 113,086,354 bytes (~108 MB) | `d90919cc6fd7f2952eacfbd53dd6c4d589b9d4def6710b11c8795762b206433f` | HTTP 200 (MATCH) |
| `Exam-Grader-v1.0.1-macOS-Apple-Silicon.dmg.sha256` | 109 bytes | N/A | HTTP 200 (MATCH) |
| `Exam-Grader-v1.0.1-Windows-Setup.exe` | 77,919,326 bytes (~74 MB) | `b618fe15646290cd73eb3ee6238beddefd7081c581835c39fa780e26c7cd19ec` | HTTP 200 (MATCH) |
| `Exam-Grader-v1.0.1-Windows-Setup.exe.sha256` | 104 bytes | N/A | HTTP 200 (MATCH) |

*Local Windows Standalone Build Artifact:*
- Path: `dist\Exam-Grader-v1.0.1-Windows-Setup.exe` (76,187,127 bytes, SHA-256: `b2286970fd3e235e910b871c27216b9c8eaaaf68314922122abb420913ec0615`)
- Installed Target: `%LOCALAPPDATA%\Programs\ExamGrader\ExamGrader.exe`

---

## 2. สรุปผลการทดสอบ Final Windows UAT v1.0.1

| รายการทดสอบ | ผลการทดสอบ | รายละเอียด Evidence |
| :--- | :---: | :--- |
| **`ExamGrader.exe --self-check`** | **PASS** | Exit code 0, version 1.0.1, SQLite storage integrity พร้อมทำงาน |
| **`ExamGrader.exe --smoke-settings`** | **PASS** | Exit code 0, โหลดแม่แบบ Default #1, #2, #3 พร้อม reference images สมบูรณ์ |
| **`ExamGrader.exe --smoke-ui`** | **PASS** | Exit code 0, GUI เปิดและปิดสมบูรณ์ |
| **Settings → Template Management** | **PASS** | เปิด Dialog ได้ทันที ไม่ crash, ไม่ติด `KeyError: reference_sha256` |
| **Grade → Save Results + Excel** | **PASS** | ทำงานบน path ภาษาไทย `Documents\ทดสอบตรวจข้อสอบ_ไทย_๒๕๖๙` สำเร็จ ไม่มี `[WinError 5]` |
| **Output Integrity** | **PASS** | Excel `scores.xlsx` มี sheet Scores & Info ครบถ้วน, ภาพ checked `.jpg` ครบ, ไม่มี `.staging-*` ค้าง, ภาพต้นฉบับ SHA-256 ไม่เปลี่ยนแปลง |
| **Automated UAT Suite** | **PASS** | `tests/test_windows_uat.py` (3/3 PASS) |
| **Quality Gates** | **PASS** | `ruff check src tests` (0 errors), `mypy src` (0 errors across 20 source files) |

---

## 3. ผลการทดสอบ Benchmark & Performance Optimization

- **Default #1 (100 ข้อ)**: ~1.44s
- **Default #2 (กระดาษชมพู)**: ~3.46s (**เร็วขึ้นกว่า 4.7 เท่า** จากเดิม 35s+ ด้วย scaled ECC + SIFT fallback)
- **Default #3 (กระดาษเขียว)**: ~1.04s
- **Feature & Reference Cache**: แคชภาพและ keypoints ใน RAM ทำงานได้ผลจริง
- **Accuracy Ground Truth**: ผ่านการทดสอบ OMR & Registration เทียบกับ Golden Labels และ Ground Truth 100% ไม่มี accuracy regression

---

## 4. GitHub Actions CI Architecture Note

- Windows installer build is automated via `.github/workflows/release.yml` with dynamic filename and version detection (avoiding hardcoded release strings).
- Completed Windows Runner Run ID: `34711082160` (Artifact ID: `10302829066`).
