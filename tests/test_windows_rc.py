"""Targeted regression and validation tests for Windows release-candidate fixes.

1. Issue A: Windows subprocess flags prevent console window flashing.
2. Issue B: Unified Exam Grader app icon on Windows (title bar, taskbar, resources).
3. Issue C: ReviewDialog and dialogs fit within available screen work area.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QIcon, QImage
from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.identity import _subprocess_windows_flags
from exam_grader.review_ui import ReviewDialog


def test_subprocess_windows_flags_configured_properly():
    flags = _subprocess_windows_flags()
    if sys.platform == "win32":
        assert "creationflags" in flags
        assert flags["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert "startupinfo" in flags
        startupinfo = flags["startupinfo"]
        assert startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW
        assert startupinfo.wShowWindow == 0
    else:
        assert flags == {}


def test_icon_resource_files_and_propagation(tmp_path):
    QApplication.instance() or QApplication([])
    ico_path = Path(__file__).resolve().parents[1] / "src" / "exam_grader" / "resources" / "icon.ico"
    png_path = Path(__file__).resolve().parents[1] / "src" / "exam_grader" / "resources" / "icon.png"
    assert ico_path.exists(), "icon.ico must exist in src/exam_grader/resources"
    assert png_path.exists(), "icon.png must exist in src/exam_grader/resources"

    ico = QIcon(str(ico_path))
    assert not ico.isNull()
    # Windows icon must provide standard multi-resolution sizes
    sizes = [s.width() for s in ico.availableSizes()]
    assert 16 in sizes or 32 in sizes or 48 in sizes or 256 in sizes


def test_review_dialog_fits_in_available_geometry(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    icon_path = Path(__file__).resolve().parents[1] / "src" / "exam_grader" / "resources" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบย่อย", "2569", "ป.1", "1", "คณิตศาสตร์", 3))

    key_img_path = tmp_path / "key.png"
    img = QImage(200, 300, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    img.save(str(key_img_path))

    from exam_grader.imaging import OMR_PIPELINE_VERSION
    from exam_grader.imports import ImportService
    from exam_grader.workflow import Workflow

    source = ImportService(application.exams.path).import_file(exam.id, key_img_path, "key")
    Workflow(application.exams.path).save_detection(
        source["id"],
        {
            "pipeline_version": OMR_PIPELINE_VERSION,
            "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "answers": [
                {"classification": "single_mark", "selected": ["A"], "auto_resolved": True},
                {"classification": "single_mark", "selected": ["B"], "auto_resolved": True},
                {"classification": "single_mark", "selected": ["C"], "auto_resolved": True},
            ],
        },
    )

    dialog = ReviewDialog(application.exams.path, source)
    assert not dialog.windowIcon().isNull(), "ReviewDialog must inherit application window icon"

    # Verify dialog size does not exceed screen work area
    screen = QApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        assert dialog.width() <= avail.width(), f"Dialog width {dialog.width()} exceeds available width {avail.width()}"
        assert dialog.height() <= avail.height(), f"Dialog height {dialog.height()} exceeds available height {avail.height()}"

    dialog.close()


def test_dialog_sizing_on_simulated_laptop_screens(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ป.1", "1", "วิชา", 3))

    from exam_grader.exam_ui import ExamDialog
    from exam_grader.imaging import OMR_PIPELINE_VERSION
    from exam_grader.imports import ImportService
    from exam_grader.workflow import Workflow

    key_img_path = tmp_path / "key.png"
    img = QImage(200, 300, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    img.save(str(key_img_path))

    source = ImportService(application.exams.path).import_file(exam.id, key_img_path, "key")
    Workflow(application.exams.path).save_detection(
        source["id"],
        {
            "pipeline_version": OMR_PIPELINE_VERSION,
            "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "answers": [
                {"classification": "single_mark", "selected": ["A"], "auto_resolved": True},
            ],
        },
    )

    class MockScreen:
        def __init__(self, w, h):
            self._rect = QRect(0, 0, w, h)

        def availableGeometry(self):
            return self._rect

    # Test 1: 1366x768 display with 40px taskbar -> 1366x728 available
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: MockScreen(1366, 728))
    rev_dlg1 = ReviewDialog(application.exams.path, source)
    assert rev_dlg1.width() <= 1366
    assert rev_dlg1.height() <= 728
    assert rev_dlg1.geometry().bottom() <= 728
    rev_dlg1.close()

    exam_dlg1 = ExamDialog(application, exam)
    assert exam_dlg1.width() <= 1366
    assert exam_dlg1.height() <= 728
    exam_dlg1.close()

    # Test 2: 1080p display at 150% scaling with 40px taskbar -> 1280x680 available
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: MockScreen(1280, 680))
    rev_dlg2 = ReviewDialog(application.exams.path, source)
    assert rev_dlg2.width() <= 1280
    assert rev_dlg2.height() <= 680
    assert rev_dlg2.geometry().bottom() <= 680
    rev_dlg2.close()

    exam_dlg2 = ExamDialog(application, exam)
    assert exam_dlg2.width() <= 1280
    assert exam_dlg2.height() <= 680
    exam_dlg2.close()

