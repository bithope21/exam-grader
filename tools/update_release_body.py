import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

with open('/Users/zubinpijit/.git-credentials') as f:
    for line in f:
        if 'github.com' in line:
            token = urllib.parse.urlparse(line.strip()).password

sha_path = ROOT / 'dist' / 'Exam-Grader-v1.0.1-macOS-Apple-Silicon.dmg.sha256'
with open(sha_path) as f:
    mac_sha = f.read().split()[0] if sha_path.exists() else 'PENDING'
win_sha_path = ROOT / 'dist' / 'Exam-Grader-v1.0.1-Windows-Setup.exe.sha256'
win_sha = win_sha_path.read_text().split()[0] if win_sha_path.exists() else 'b618fe15646290cd73eb3ee6238beddefd7081c581835c39fa780e26c7cd19ec'

release_id = 387664293

bt = '`'
body = f"""## Exam Grader v1.0.1 — Production Launch

Exam Grader (ระบบตรวจข้อสอบอัตโนมัติแบบออฟไลน์ 100%) สำหรับครูและสถานศึกษา

### Release Highlights
- **100% Offline Processing**: ไม่ส่งภาพหรือข้อมูลคะแนนออกนอกเครื่อง
- **Transparent Brand Icons**: ไอคอนแอปพลิเคชันคมชัด ไร้ขอบขาว ทั้งบน macOS และ Windows
- **High Performance Import**: ปรับปรุงความเร็วในการอ่านกระดาษคำตอบเร็วขึ้นสูงสุด 4.7x
- **Human-in-the-Loop Review**: ตรวจทานจุดที่ระบบไม่มั่นใจ และแก้ไขคำตอบหลายคนพร้อมกัน (Bulk Edit)
- **Custom Templates**: รองรับกระดาษคำตอบในตัว 3 รูปแบบ และสร้างแม่แบบเฉพาะของโรงเรียนได้
- **Comprehensive Export**: ส่งออกไฟล์ Excel (.xlsx) และภาพกระดาษคำตอบพร้อมรอยตรวจ (.jpg)
- **Windows Hardening**: แก้ไข [WinError 5] ระหว่างการส่งออก และ Template Management บน Windows

### Download & Checksums

- **macOS (Apple Silicon M1–M4):** {bt}Exam-Grader-v1.0.1-macOS-Apple-Silicon.dmg{bt} (108 MB)
  - SHA-256: {bt}{mac_sha}{bt}
- **Windows (10/11 64-bit):** {bt}Exam-Grader-v1.0.1-Windows-Setup.exe{bt} (74 MB)
  - SHA-256: {bt}{win_sha}{bt}

### First-Launch Guidance
- **macOS:** As an independent open-source release, macOS Gatekeeper may prompt on first launch. Go to **System Settings** → **Privacy & Security** and select **Open Anyway** (or right-click `ExamGrader.app` → Open).
- **Windows:** If Microsoft Defender SmartScreen prompts on first install, click **More info** → **Run anyway**.
"""

req = urllib.request.Request(
    f'https://api.github.com/repos/bithope21/exam-grader/releases/{release_id}',
    data=json.dumps({'body': body}).encode(),
    headers={
        'Authorization': f'token {token}',
        'User-Agent': 'Python',
        'Content-Type': 'application/json'
    },
    method='PATCH'
)
with urllib.request.urlopen(req) as resp:
    print('Release body updated successfully!')
