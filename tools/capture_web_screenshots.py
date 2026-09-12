import subprocess
from pathlib import Path

out_dir = Path('/Users/zubinpijit/.gemini/antigravity-ide/brain/94ffabfb-de58-46e3-a786-b257709e80b5/inspections')
out_dir.mkdir(parents=True, exist_ok=True)

chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

sizes = [
    ("desktop_full", 1280, 2400),
    ("tablet_full", 768, 2400),
    ("mobile_full", 375, 3000),
    ("mobile_414", 414, 3000)
]

for name, w, h in sizes:
    dest = out_dir / f"{name}.png"
    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        f"--screenshot={dest}",
        f"--window-size={w},{h}",
        "--hide-scrollbars",
        "http://localhost:3055/exam-grader"
    ]
    subprocess.run(cmd, check=True)
    print(f"Captured {name}: {dest.stat().st_size} bytes")

print("All inspection screenshots captured!")
