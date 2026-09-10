import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.imaging import OMR_PIPELINE_VERSION
from exam_grader.imports import ImportService
from exam_grader.review_ui import ReviewDialog
from exam_grader.ui import MainWindow, NewExamDialog
from exam_grader.workflow import Workflow


def test_desktop_shell_displays_persisted_exam(tmp_path):
    qt = QApplication.instance() or QApplication([])
    application = initialize(tmp_path)
    window = MainWindow(application)
    dialog = NewExamDialog(window)
    for name, value in dict(
        name="กลางภาค", academic_year="2569", grade="ม.4", room="1", subject="คณิตศาสตร์"
    ).items():
        field = dialog.fields[name]
        if isinstance(field, QComboBox):
            field.setCurrentText(value)
        else:
            field.setText(value)
    dialog.accept()
    application.exams.create(dialog.details)
    window.refresh()
    window.show()
    qt.processEvents()
    assert window.exam_list.count() == 1
    assert "กลางภาค" in window.exam_list.item(0).text()
    assert not hasattr(window, "delete_exam_button")
    row = window.exam_list.itemWidget(window.exam_list.item(0))
    assert row is not None
    assert any(isinstance(child, QPushButton) and "ลบข้อสอบ" in child.text() for child in row.findChildren(QPushButton))
    window.close()
    dialog.close()


def test_key_review_prefills_clear_multi_answer_for_teacher_confirmation(tmp_path):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ป.1", "1", "วิชา", 3))
    key_path = tmp_path / "key.png"
    image = QImage(30, 40, QImage.Format.Format_RGB32)
    image.fill(0xFFFDFFFF)
    image.save(str(key_path))
    source = ImportService(application.exams.path).import_file(exam.id, key_path, "key")
    Workflow(application.exams.path).save_detection(
        source["id"],
        {
            "pipeline_version": OMR_PIPELINE_VERSION,
            "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "answers": [
                {"classification": "single_mark", "selected": ["A"], "auto_resolved": True},
                {"classification": "multiple", "selected": ["B", "C"], "auto_resolved": False},
                {"classification": "single_mark", "selected": ["D"], "auto_resolved": True},
            ],
        },
    )
    dialog = ReviewDialog(application.exams.path, source)
    assert isinstance(dialog.combos[1], QLineEdit)
    assert dialog.combos[1].text() == "B,C"
    assert "เติมหลายคำตอบ" in dialog.notice.text()
    assert not dialog.confirmed.isChecked()
    assert dialog.result() == 0
    dialog.close()
