from pathlib import Path

import cv2
import numpy as np

brain_dir = Path('/Users/zubinpijit/.gemini/antigravity-ide/brain/94ffabfb-de58-46e3-a786-b257709e80b5')
out_dir = Path('/Users/zubinpijit/bithope/apps/bithope-web/public/exam-grader/illustrations')
icon_dir = Path('/Users/zubinpijit/bithope/apps/bithope-web/public/exam-grader/icons')
out_dir.mkdir(parents=True, exist_ok=True)
icon_dir.mkdir(parents=True, exist_ok=True)

def remove_white_bg(img_path: Path, out_path: Path, tol=248, feather=True):
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"Failed to read {img_path}")
        return
    # Convert BGR to BGRA
    bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    
    # Check outer borders to find background color (usually >= tol)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = gray < tol
    
    # Morphological clean up to avoid noisy edges
    kernel = np.ones((3, 3), np.uint8)
    mask_clean = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    
    # Floodfill from 4 corners to only remove outside white, not inside white (like paper or white clothes)
    h, w = gray.shape
    flood_mask = np.zeros((h + 2, w + 2), np.uint8)
    flood_img = gray.copy()
    
    # Fill from corners where color is bright
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    bg_mask = np.zeros((h, w), np.uint8)
    for cx, cy in corners:
        if gray[cy, cx] >= tol:
            cv2.floodFill(flood_img, flood_mask, (cx, cy), 0, loDiff=5, upDiff=5)
            
    # Where flood_img is 0 from corners is outer background
    is_outer_bg = (flood_img == 0) & (gray >= tol - 10)
    bgra[:, :, 3] = np.where(is_outer_bg, 0, 255).astype(np.uint8)
    
    # Soft alpha feather on boundary
    if feather:
        alpha = bgra[:, :, 3].astype(np.float32)
        alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
        bgra[:, :, 3] = alpha.astype(np.uint8)
        
    cv2.imwrite(str(out_path), bgra)
    print(f"Processed: {out_path.name}")

# Find generated image paths
teacher_img = next(brain_dir.glob("teacher_2d_*.jpg"))
student_img = next(brain_dir.glob("student_2d_*.jpg"))
board_img = next(brain_dir.glob("blackboard_2d_*.jpg"))
cat_img = next(brain_dir.glob("cat_2d_*.jpg"))
books_img = next(brain_dir.glob("books_stationery_2d_*.jpg"))
icon_img = next(brain_dir.glob("icon_examgrader_2d_*.jpg"))

remove_white_bg(teacher_img, out_dir / "teacher-2d.png")
remove_white_bg(student_img, out_dir / "student-2d.png")
remove_white_bg(board_img, out_dir / "blackboard-2d.png")
remove_white_bg(cat_img, out_dir / "cat-2d.png")
remove_white_bg(books_img, out_dir / "books-stationery-2d.png")
remove_white_bg(icon_img, icon_dir / "icon-examgrader.png", tol=250)

# Also copy icon to public/icon-examgrader.png for easy root access
import shutil

shutil.copy(icon_dir / "icon-examgrader.png", "/Users/zubinpijit/bithope/apps/bithope-web/public/icon-examgrader.png")

print("All 2D transparent assets ready!")
