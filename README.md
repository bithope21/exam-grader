# Exam Grader (v1.0.0)

โปรแกรมตรวจข้อสอบจากภาพถ่ายกระดาษคำตอบ ทำงานแบบ **ออฟไลน์ 100%** สำหรับคุณครูและสถานศึกษา รองรับทั้ง **macOS (Apple Silicon)** และ **Windows (64-bit)**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/bithope21/exam-grader)](https://github.com/bithope21/exam-grader/releases)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)

---

## จุดเด่นสำคัญ (Key Features)

- **100% Offline & Private:** ประมวลผลบนเครื่องคอมพิวเตอร์ของคุณครูโดยตรง ไม่ส่งภาพกระดาษคำตอบหรือข้อมูลนักเรียนขึ้น Cloud ใด ๆ ทั้งสิ้น
- **รองรับฟอร์มกระดาษคำตอบมาตรฐานและกำหนดเอง:**
  - รูปแบบมาตรฐาน Default #1 (60 ข้อ)
  - รูปแบบมาตรฐาน Default #2 (40 ข้อ)
  - รูปแบบมาตรฐาน Default #3 (30 ข้อ)
  - ระบบ **Template Calibration** ปรับเทียบพิกัดสำหรับกระดาษคำตอบรูปแบบเฉพาะของโรงเรียน
- **Computer Vision OMR:** ตรวจจับรอยกากบาท/ฝนคำตอบด้วย OpenCV พร้อมระบุสถานะ ชัดเจน / ตอบหลายข้อ / เว้นว่าง / ไม่แน่ใจ
- **ระบบตรวจทานแบบ Side-by-Side:** แสดงภาพต้นฉบับคู่กับผลการอ่าน สามารถ Zoom / Pan และแก้ไขผลตรวจรายบุคคลหรือแบบกลุ่ม (Bulk Edit)
- **Export ผลลัพธ์ครบถ้วน:** 
  - สรุปคะแนนเป็นไฟล์ **Excel (.xlsx)** พร้อมสูตรคำนวณและสถิติ
  - บันทึกภาพกระดาษคำตอบที่ตรวจแล้วพร้อมวงเฉลยสีเขียว/แดง และพิมพ์คะแนนลงบนภาพอย่างชัดเจน

---

## ดาวน์โหลดและติดตั้ง (Installation)

ดาวน์โหลดตัวติดตั้งเวอร์ชันล่าสุดได้จาก [GitHub Releases](https://github.com/bithope21/exam-grader/releases) หรือที่หน้าเว็บ [bithope.app/exam-grader](https://bithope.app/exam-grader)

### macOS (Apple Silicon: M1/M2/M3/M4)
1. ดาวน์โหลดไฟล์ `Exam-Grader-v1.0.0-macOS-Apple-Silicon.dmg`
2. ดับเบิลคลิกไฟล์ `.dmg` แล้วลากไอคอน **Exam Grader** ไปยังโฟลเดอร์ **Applications**
3. **การเปิดใช้งานครั้งแรก:** เนื่องจากเป็นซอฟต์แวร์ Open Source อิสระที่ไม่ได้ผ่าน Mac App Store หาก macOS Gatekeeper ขึ้นแจ้งเตือน ให้ไปที่ **System Settings** → **Privacy & Security** แล้วกด **Open Anyway**

### Windows (10 / 11 64-bit)
1. ดาวน์โหลดไฟล์ `Exam-Grader-v1.0.0-Windows-Setup.exe`
2. ดับเบิลคลิกเปิดตัวติดตั้งและทำตามขั้นตอนบนหน้าจอ
3. เปิดใช้งานโปรแกรมได้จาก Start Menu หรือ Desktop Shortcut

---

## การพัฒนาและทดสอบ (Development)

ต้องใช้ Python 3.11–3.13 แนะนำให้ใช้ [uv](https://github.com/astral-sh/uv) ในการจัดการ environment:

```sh
# ติดตั้ง dependencies
uv sync --extra dev

# รันโปรแกรมในโหมดพัฒนา
uv run exam-grader

# รันการตรวจสอบระบบ (Self-Check)
uv run exam-grader --self-check

# รันชุดแบบทดสอบอัตโนมัติ (126 tests)
uv run pytest
```

### การตรวจสอบคุณภาพโค้ด (Quality Gates)
```sh
uv run ruff check src tests
uv run mypy src tests
```

### การ Build ตัวติดตั้ง (Packaging)
- **macOS:** `python scripts/build/build.py` แล้วรัน `scripts/build/package_dmg.sh`
- **Windows:** รัน `python scripts/build/build.py` แล้วคอมไพล์ด้วย Inno Setup ผ่าน `scripts/build/windows-installer.iss`

---

## สิทธิ์การใช้งาน (License)

ซอฟต์แวร์นี้เผยแพร่ภายใต้สัญญาอนุญาต [Apache License 2.0](LICENSE)

