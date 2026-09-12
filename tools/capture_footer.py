import subprocess
from pathlib import Path

out_dir = Path('/Users/zubinpijit/.gemini/antigravity-ide/brain/94ffabfb-de58-46e3-a786-b257709e80b5/inspections')
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

cmd = [
    chrome,
    "--headless",
    "--disable-gpu",
    f"--screenshot={out_dir}/desktop_download_and_footer.png",
    "--window-size=1280,6000",
    "--hide-scrollbars",
    "http://localhost:3055/exam-grader#download"
]
subprocess.run(cmd, check=True)
print("Captured download and footer!")
