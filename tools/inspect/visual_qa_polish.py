"""Capture Visual QA screenshots for Review Bulk Edit and Custom Template Overlay."""
import os
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.exam_ui import ExamDialog
from exam_grader.exporting import export_results
from exam_grader.imaging import OMR_PIPELINE_VERSION
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.template_manager import load_builtin_template, save_custom_reference_image
from exam_grader.workflow import Workflow

out_dir = Path('/Users/zubinpijit/.gemini/antigravity-ide/brain/9e575193-90c2-4e9e-843c-244ac7f01ce3/visual_qa_polish')
out_dir.mkdir(parents=True, exist_ok=True)

app_qt = QApplication.instance() or QApplication([])

# --- 1. Review Bulk Edit Screenshots ---
app_data = Path('/tmp/exam_grader_qa_bulk')
import shutil

if app_data.exists():
    shutil.rmtree(app_data)

app = initialize(app_data)
exam = app.exams.create(
    ExamDetails(
        name="ม.4 สอบกลางภาค ชีววิทยา",
        academic_year="2569",
        subject="ชีววิทยา",
        grade="ม.4",
        room="1",
        question_count=10,
        template_id="default-1",
    )
)

importer = ImportService(app.exams.path)
flow = Workflow(app.exams.path)

# Teacher key
key_path = app_data / "key.png"
img = np.full((818, 836, 3), 255, dtype=np.uint8)
cv2.imwrite(str(key_path), img)
k_src = importer.import_file(exam.id, key_path, "key")
flow.approve_key(exam.id, ["A", "B", "C", "D", "E", "A", "B", "C", "D", "E"], k_src["id"])

# Add 3 student sheets with uncertain answers
for student_num in ["12", "15", "23"]:
    s_path = app_data / f"s_{student_num}.png"
    s_img = img.copy(); s_img[0, int(student_num)] = 100; cv2.imwrite(str(s_path), s_img)
    s_src = importer.import_file(exam.id, s_path, "student")
    det = {
        "pipeline_version": OMR_PIPELINE_VERSION,
        "registration": {"matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], "inliers": 100},
        "student_number_observation": {"candidate": student_num, "candidates": [student_num]},
        "answers": [
            {"classification": "uncertain", "selected": [], "auto_resolved": False},
            {"classification": "uncertain", "selected": [], "auto_resolved": False},
            {"classification": "single_mark", "selected": ["A"], "auto_resolved": True},
            {"classification": "single_mark", "selected": ["B"], "auto_resolved": True},
            {"classification": "single_mark", "selected": ["C"], "auto_resolved": True},
            {"classification": "single_mark", "selected": ["D"], "auto_resolved": True},
            {"classification": "single_mark", "selected": ["E"], "auto_resolved": True},
            {"classification": "single_mark", "selected": ["A"], "auto_resolved": True},
            {"classification": "single_mark", "selected": ["B"], "auto_resolved": True},
            {"classification": "single_mark", "selected": ["C"], "auto_resolved": True},
        ],
    }
    flow.save_detection(s_src["id"], det)
    service = ReviewService(app.exams.path)
    service.set_number(s_src, student_num, expected_detection=service.state(s_src)["detection_id"])

dialog = ExamDialog(app, exam)
dialog.resize(1150, 750)
dialog.tabs.setCurrentIndex(2)  # Review tab
dialog.show()
app_qt.processEvents()

# Select rows 0, 1, 2 (e.g. blanks to resolve together)
dialog.issue_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
dialog.issue_table.item(1, 0).setCheckState(Qt.CheckState.Checked)
dialog.issue_table.item(2, 0).setCheckState(Qt.CheckState.Checked)
b_idx = dialog.bulk_combo.findData("blank")
if b_idx >= 0:
    dialog.bulk_combo.setCurrentIndex(b_idx)
app_qt.processEvents()

# Capture Before
before_pix = dialog.grab()
before_pix.save(str(out_dir / "01_review_bulk_edit_selection.png"))
print("Saved 01_review_bulk_edit_selection.png")

# Apply bulk edit
from unittest.mock import patch

with patch("PySide6.QtWidgets.QMessageBox.information"):
    dialog.apply_bulk_edit()
app_qt.processEvents()

# Capture After
after_pix = dialog.grab()
after_pix.save(str(out_dir / "02_review_bulk_edit_applied.png"))
print("Saved 02_review_bulk_edit_applied.png")


# --- 2. Custom Template Checked Overlay Screenshot ---
import dataclasses

from exam_grader.template_manager import get_reference_image

app2_data = Path('/tmp/exam_grader_qa_custom')
if app2_data.exists():
    shutil.rmtree(app2_data)
app2 = initialize(app2_data)

t3 = load_builtin_template("default-3")
ref_img = get_reference_image(t3)
ref_bytes = cv2.imencode(".png", ref_img)[1].tobytes()
ref_sha = save_custom_reference_image(app2_data, ref_bytes)

custom_tmpl = dataclasses.replace(
    t3,
    template_id="custom-1200",
    name="Custom Template 1200x1720",
    kind="custom",
    reference_sha256=ref_sha,
)
app2.exams.save_template(custom_tmpl)

exam2 = app2.exams.create(
    ExamDetails(
        name="Custom 1200x1720 Geometry Exam",
        academic_year="2569",
        subject="ทดสอบ Overlay",
        grade="ม.1",
        room="1",
        question_count=10,
        template_id="custom-1200",
    )
)

imp2 = ImportService(app2.exams.path)
flow2 = Workflow(app2.exams.path)

k2_path = app2_data / "k2.png"
cv2.imwrite(str(k2_path), ref_img)
k2_src = imp2.import_file(exam2.id, k2_path, "key")
flow2.approve_key(exam2.id, ["A", "B", "C", "D", "E", "A", "B", "C", "D", "E"], k2_src["id"])

s2_path = app2_data / "s2.png"
# student filled A on Q1 (correct) and C on Q2 (incorrect, key was B)
s2_img = ref_img.copy()
cv2.circle(s2_img, (200, 300), 10, (40, 40, 40), -1)  # Q1 A filled
cv2.circle(s2_img, (200 + 2 * 35, 300 + 45), 10, (40, 40, 40), -1)  # Q2 C filled
s2_img[0, 0] = 50; cv2.imwrite(str(s2_path), s2_img)
s2_src = imp2.import_file(exam2.id, s2_path, "student")

answers2 = [
    {"classification": "single_mark", "selected": ["A"], "auto_resolved": True},
    {"classification": "single_mark", "selected": ["C"], "auto_resolved": True},
] + [
    {"classification": "single_mark", "selected": ["A"], "auto_resolved": True}
    for _ in range(8)
]

det2 = {
    "pipeline_version": OMR_PIPELINE_VERSION,
    "registration": {"matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], "inliers": 100},
    "student_number_observation": {"candidate": "1", "candidates": ["1"]},
    "answers": answers2,
}
flow2.save_detection(s2_src["id"], det2)
rev2 = ReviewService(app2.exams.path)
rev2.set_number(s2_src, "1", expected_detection=rev2.state(s2_src)["detection_id"])
rev2.finalize(exam2.id)

export_dir = app2_data / "export"
res_dir = export_results(flow2, exam2.id, export_dir)
checked_files = list(res_dir.rglob("*.png"))
print("Exported checked files in", res_dir, ":", checked_files)
if checked_files:
    shutil.copy(checked_files[0], out_dir / "03_custom_template_checked_overlay.png")
    print("Saved 03_custom_template_checked_overlay.png")
