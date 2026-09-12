"""Generate production macOS .icns and Windows multi-resolution .ico from master artwork."""

import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MASTER_ARTWORK = ROOT / "docs" / "landing page" / "logo.png"
ICONS_DIR = ROOT / "resources" / "icons"
SRC_RESOURCES_DIR = ROOT / "src" / "exam_grader" / "resources"

ICONS_DIR.mkdir(parents=True, exist_ok=True)
SRC_RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

print(f"Loading master artwork: {MASTER_ARTWORK}")
img = Image.open(MASTER_ARTWORK).convert("RGBA")

# 1. Save standard PNG icons
png_512 = ICONS_DIR / "icon.png"
img.resize((512, 512), Image.Resampling.LANCZOS).save(png_512, "PNG")
shutil.copy(png_512, SRC_RESOURCES_DIR / "icon.png")
print(f"Saved PNG icon: {png_512} and {SRC_RESOURCES_DIR / 'icon.png'}")

# 2. Generate Windows Multi-resolution ICO (16, 24, 32, 48, 64, 128, 256)
ico_path = ICONS_DIR / "icon.ico"
ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(ico_path, format="ICO", sizes=ico_sizes)
print(f"Saved Windows multi-res ICO: {ico_path} with sizes {ico_sizes}")

# 3. Generate macOS .icns using iconutil
iconset_dir = ICONS_DIR / "icon.iconset"
iconset_dir.mkdir(exist_ok=True)

iconset_specs = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

for filename, size in iconset_specs:
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(iconset_dir / filename, "PNG")

icns_path = ICONS_DIR / "icon.icns"
subprocess.run(
    ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
    check=True
)
shutil.rmtree(iconset_dir)
print(f"Saved macOS ICNS: {icns_path} ({os.path.getsize(icns_path)} bytes)")
