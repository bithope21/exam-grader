import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.exam_ui import BatchWorker, ExamDialog
from exam_grader.exporting import export_results
from exam_grader.imaging import cell_rect, reference_image
from exam_grader.imports import ImportService
from exam_grader.review_ui import ReviewDialog
from exam_grader.workflow import Workflow


def make_sheet(path, choices):
    image = reference_image()
    for question, choice in enumerate(choices, 1):
        x, y, w, h = cell_rect(question, choice)
        cv2.line(image, (x + 4, y + 4), (x + w - 4, y + h - 4), (0, 0, 0), 3)
        cv2.line(image, (x + w - 4, y + 4), (x + 4, y + h - 4), (0, 0, 0), 3)
    path.write_bytes(cv2.imencode(".png", image)[1].tobytes())


def test_teacher_workflow_import_review_export_reopen(tmp_path, monkeypatch):
    qt = QApplication.instance() or QApplication([])
    app = initialize(tmp_path / "data")
    exam = app.exams.create(ExamDetails("กลางภาค", "2569", "ม.4", "1", "คณิต", 2))
    key_path, student_path = tmp_path / "key.png", tmp_path / "student.png"
    make_sheet(key_path, [0, 1])
    make_sheet(student_path, [0, 2])
    for path, purpose in ((key_path, "key"), (student_path, "student")):
        worker = BatchWorker(app.exams.path, exam.id, [path], purpose)
        worker.start()
        assert worker.wait(15000)
        if purpose == "key":
            key_source = ImportService(app.exams.path).list_sources(exam.id)[0]
            Workflow(app.exams.path).approve_key(exam.id, ["A", "B"], key_source["id"])
    importer = ImportService(app.exams.path)
    key_source = next(row for row in importer.list_sources(exam.id) if row["purpose"] == "key")
    student_source = next(
        row for row in importer.list_sources(exam.id) if row["purpose"] == "student"
    )
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    dialog = ReviewDialog(app.exams.path, key_source)
    dialog.count.setValue(2)
    dialog.accept()
    # Clear, non-ambiguous key reads are ready to save without a second
    # per-question confirmation click.
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not warnings
    dialog.confirmed.setChecked(True)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    review = ReviewDialog(app.exams.path, student_source)
    review.number.setText("17")
    detection = Workflow(app.exams.path).latest_detection(student_source["id"])
    assert [review.combos[i].currentData() for i in range(2)] != [None, None], (
        detection.get("failure"),
        detection.get("alignment_diagnostics"),
    )
    review.confirmed.setChecked(True)
    review.accept()
    assert review.result() == QDialog.DialogCode.Accepted, [
        (warning[1], warning[2]) for warning in warnings
    ]
    assert Workflow(app.exams.path).snapshot(exam.id)["results"][0]["score"] == 1
    output = export_results(Workflow(app.exams.path), exam.id)
    assert (output / "scores.xlsx").exists()
    reopened = ExamDialog(initialize(app.data_dir), exam)
    reopened.show()
    qt.processEvents()
    assert reopened.key_list.count() == 1
    assert reopened.student_list.count() == 1
    assert "พร้อม" in reopened.student_list.item(0).text()
    student_row = reopened.student_list.itemWidget(reopened.student_list.item(0))
    assert student_row is not None
    assert any(
        isinstance(child, QPushButton) and child.text() == "ลบ"
        for child in student_row.findChildren(QPushButton)
    )
    reopened.close()


def test_one_bad_image_does_not_abort_batch(tmp_path):
    app = initialize(tmp_path / "data")
    exam = app.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "คณิต"))
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"broken")
    good = tmp_path / "good.png"
    make_sheet(good, [1])
    key_path = tmp_path / "key.png"
    make_sheet(key_path, [0])
    key_source = ImportService(app.exams.path).import_file(exam.id, key_path, "key")
    Workflow(app.exams.path).approve_key(exam.id, ["B"] * 60, key_source["id"])
    worker = BatchWorker(app.exams.path, exam.id, [broken, good], "student")
    worker.start()
    assert worker.wait(15000)
    assert (
        len(
            [
                s
                for s in ImportService(app.exams.path).list_sources(exam.id)
                if s["purpose"] == "student"
            ]
        )
        == 1
    )
    assert len(ImportService(app.exams.path).list_failures(exam.id)) == 1

    make_sheet(broken, [2])
    retry = BatchWorker(app.exams.path, exam.id, [broken], "student")
    retry.start()
    assert retry.wait(15000)
    assert ImportService(app.exams.path).list_failures(exam.id) == []
