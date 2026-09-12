"""Run on each target OS using its own Python environment."""

import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
environment = os.environ.copy()
environment["PYINSTALLER_CONFIG_DIR"] = str(root / "build" / "pyinstaller-cache")
cmd = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
    "--name", "ExamGrader", "--paths", str(root / "src"),
    "--collect-data", "exam_grader", "--distpath", str(root / "dist"),
    "--workpath", str(root / "build"), "--specpath", str(root / "build"),
]
if sys.platform == "darwin":
    cmd.extend(["--osx-bundle-identifier", "com.bithope.examgrader"])
cmd.append(str(root / "src/exam_grader/__main__.py"))

subprocess.run(cmd, cwd=root, check=True, env=environment)
