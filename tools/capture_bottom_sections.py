import subprocess
from pathlib import Path

out_dir = Path('/Users/zubinpijit/.gemini/antigravity-ide/brain/94ffabfb-de58-46e3-a786-b257709e80b5/inspections')
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# We can capture full page with Chrome headless using --screenshot on an element or full page
# Chrome has a trick: set a large height, e.g. 5000px, to capture the whole page!
cmd = [
    chrome,
    "--headless",
    "--disable-gpu",
    f"--screenshot={out_dir}/desktop_entire_page.png",
    "--window-size=1280,4200",
    "--hide-scrollbars",
    "http://localhost:3055/exam-grader"
]
subprocess.run(cmd, check=True)
print("Desktop entire page captured!")

cmd_mob = [
    chrome,
    "--headless",
    "--disable-gpu",
    f"--screenshot={out_dir}/mobile_entire_page.png",
    "--window-size=375,5600",
    "--hide-scrollbars",
    "http://localhost:3055/exam-grader"
]
subprocess.run(cmd_mob, check=True)
print("Mobile entire page captured!")
