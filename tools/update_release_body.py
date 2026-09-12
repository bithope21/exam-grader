import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

with open('/Users/zubinpijit/.git-credentials') as f:
    for line in f:
        if 'github.com' in line:
            token = urllib.parse.urlparse(line.strip()).password

sha_path = ROOT / 'dist' / 'Exam-Grader-v1.0.0-macOS-Apple-Silicon.dmg.sha256'
with open(sha_path) as f:
    sha = f.read().split()[0]

win_sha = "0f45f359e9966216b54cf2e13e9a4108c3e7c34b3585aa51d96830f1b62d8e01"

release_id = 387446800

bt = '`'
body = f"""## Exam Grader v1.0.0 — Production Launch

Official release of Exam Grader — a 100% offline exam grading desktop application for teachers.

### Highlights
- **100% Offline & Private:** Runs entirely on-device; no cloud dependencies or student data transmission.
- **Official Master Icon:** Clean, multi-resolution transparent icons for macOS (.icns) and Windows (.ico) without white borders or padding.
- **Multiple Built-in Templates:** Default #1 (60 questions), Default #2 (40 questions), Default #3 (30 questions).
- **High-Performance Import Flow:** Accelerated OMR registration with fast scaled ECC, precomputed feature caching, and instant image reuse.
- **Custom Template Calibration:** Calibrate and save custom answer sheet layouts for school-specific paper formats.
- **Side-by-Side Review:** Fast inspector with pan/zoom and bulk editing capabilities.
- **Excel & Visual Export:** Detailed .xlsx gradebook + marked answer sheets with green/red verification checks and printed scores.

### Download Artifacts
- **macOS (Apple Silicon M1–M4):** {bt}Exam-Grader-v1.0.0-macOS-Apple-Silicon.dmg{bt} (108 MB)
  - SHA-256: {bt}{sha}{bt}
- **Windows (10/11 64-bit):** {bt}Exam-Grader-v1.0.0-Windows-Setup.exe{bt} (74 MB)
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
