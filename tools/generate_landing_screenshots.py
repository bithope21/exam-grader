import os
import shutil
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.exam_ui import ExamDialog
from exam_grader.imaging import OMR_PIPELINE_VERSION
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.ui import MainWindow
from exam_grader.workflow import Workflow

app_qt = QApplication.instance() or QApplication([])

dest_dir = Path('/Users/zubinpijit/bithope/apps/bithope-web/public/exam-grader/screenshots')
dest_dir.mkdir(parents=True, exist_ok=True)

temp_dir = Path('/tmp/exam_grader_screenshots_gen')
if temp_dir.exists():
    shutil.rmtree(temp_dir)
temp_dir.mkdir(parents=True)

storage = initialize(temp_dir)

# Create 3 realistic exams
exam1 = storage.exams.create(
    ExamDetails(
        name="ม.4 สอบกลางภาค ชีววิทยา (วิทยาศาสตร์ชีวภาพ)",
        academic_year="2569",
        subject="ชีววิทยา",
        grade="ม.4",
        room="1",
        question_count=10,
        template_id="default-1",
    )
)
exam2 = storage.exams.create(
    ExamDetails(
        name="ม.5 ฟิสิกส์พื้นฐาน การเคลื่อนที่และแรง",
        academic_year="2569",
        subject="ฟิสิกส์",
        grade="ม.5",
        room="2",
        question_count=20,
        template_id="default-1",
    )
)
exam3 = storage.exams.create(
    ExamDetails(
        name="ม.6 ภาษาไทย เตรียมสอบเข้ามหาวิทยาลัย",
        academic_year="2569",
        subject="ภาษาไทย",
        grade="ม.6",
        room="4",
        question_count=10,
        template_id="default-1",
    )
)

importer = ImportService(storage.exams.path)
flow = Workflow(storage.exams.path)

# Teacher key
key_path = temp_dir / "key.png"
key_img = np.full((818, 836, 3), 255, dtype=np.uint8)
cv2.imwrite(str(key_path), key_img)
k_src = importer.import_file(exam1.id, key_path, "key")
flow.approve_key(exam1.id, ["A", "B", "C", "D", "E", "A", "B", "C", "D", "E"], k_src["id"])

# Add student sheets with varied status
for num in ["12", "15", "23", "07", "34"]:
    s_path = temp_dir / f"s_{num}.png"
    s_img = key_img.copy()
    s_img[0, int(num)] = 100
    cv2.imwrite(str(s_path), s_img)
    s_src = importer.import_file(exam1.id, s_path, "student")
    
    is_uncertain = num in ["12", "15", "23"]
    answers = []
    for q_idx in range(10):
        if is_uncertain and q_idx < 2:
            answers.append({"classification": "uncertain", "selected": [], "auto_resolved": False})
        else:
            answers.append({"classification": "single_mark", "selected": ["ABCDE"[q_idx % 5]], "auto_resolved": True})
            
    det = {
        "pipeline_version": OMR_PIPELINE_VERSION,
        "registration": {"matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], "inliers": 100},
        "student_number_observation": {"candidate": num, "candidates": [num]},
        "answers": answers,
    }
    flow.save_detection(s_src["id"], det)
    service = ReviewService(storage.exams.path)
    service.set_number(s_src, num, expected_detection=service.state(s_src)["detection_id"])

# 1. MainWindow Screenshot
win = MainWindow(storage)
win.resize(1140, 720)
win.show()
app_qt.processEvents()
win.grab().save(str(dest_dir / "exam-grader-dashboard.png"))
print("Saved exam-grader-dashboard.png")

# 2. Review Tab Screenshot
dialog = ExamDialog(storage, exam1)
dialog.resize(1180, 750)
dialog.tabs.setCurrentIndex(2) # Review
dialog.show()
app_qt.processEvents()

# Select rows 0 and 1 to showcase the multi-select bulk edit feature
if dialog.issue_table.rowCount() >= 2:
    item0 = dialog.issue_table.item(0, 0)
    item1 = dialog.issue_table.item(1, 0)
    if item0: item0.setCheckState(Qt.CheckState.Checked)
    if item1: item1.setCheckState(Qt.CheckState.Checked)
    b_idx = dialog.bulk_combo.findData("blank")
    if b_idx >= 0:
        dialog.bulk_combo.setCurrentIndex(b_idx)
app_qt.processEvents()
dialog.grab().save(str(dest_dir / "exam-grader-review.png"))
print("Saved exam-grader-review.png")

# 3. Results / Overview Screenshot
dialog.tabs.setCurrentIndex(0) # Overview / Summary
app_qt.processEvents()
dialog.grab().save(str(dest_dir / "exam-grader-overview.png"))
print("Saved exam-grader-overview.png")

dialog.tabs.setCurrentIndex(3) # Export Tab
app_qt.processEvents()
dialog.grab().save(str(dest_dir / "exam-grader-export.png"))
print("Saved exam-grader-export.png")

print("All screenshots generated successfully!")
