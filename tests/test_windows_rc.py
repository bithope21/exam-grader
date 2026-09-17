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


def test_digit_model_primary_avoids_tesseract_calls(monkeypatch):
    from exam_grader import identity
    import subprocess

    popen_calls = []
    orig_popen = subprocess.Popen

    def fake_popen(*args, **kwargs):
        popen_calls.append(args[0] if args else kwargs.get("args"))
        return orig_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    # Even if find_tesseract returns a binary path, bundled model should be primary
    monkeypatch.setattr(identity, "find_tesseract", lambda: r"C:\fake\tesseract.exe")

    img_path = Path("tests/fixtures/real/vol.9/IMG_1070.jpg")
    if not img_path.exists():
        pytest.skip("Test image not found")
    source_bytes = img_path.read_bytes()
    from exam_grader.imaging import decode, analyze
    decoded = decode(source_bytes)
    analysis = analyze(source_bytes, decoded_image=decoded)
    matrix = analysis.get("registration", {}).get("matrix")

    obs = identity.observe(source_bytes, matrix, image=decoded)
    # Zero Tesseract calls when bundled model succeeds
    assert len(popen_calls) == 0, f"Expected 0 subprocess calls, got {len(popen_calls)}"
    assert obs.get("candidate") == "13"
    assert obs.get("confidence") == 60.0


def test_set_number_finalizes_and_enables_snapshot(tmp_path):
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ป.1", "1", "วิชา", 3))

    from exam_grader.imaging import OMR_PIPELINE_VERSION
    from exam_grader.imports import ImportService
    from exam_grader.workflow import Workflow
    from exam_grader.review_service import ReviewService

    key_img_path = tmp_path / "key.png"
    img = QImage(200, 300, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    img.save(str(key_img_path))

    importer = ImportService(application.exams.path)
    flow = Workflow(application.exams.path)
    service = ReviewService(application.exams.path)

    key_source = importer.import_file(exam.id, key_img_path, "key")
    flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])

    stu_img_path = tmp_path / "stu.png"
    img2 = QImage(200, 300, QImage.Format.Format_RGB32)
    img2.fill(0xFFEEFFEE)
    img2.save(str(stu_img_path))
    stu_source = importer.import_file(exam.id, stu_img_path, "student")

    flow.save_detection(
        stu_source["id"],
        {
            "pipeline_version": OMR_PIPELINE_VERSION,
            "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "answers": [
                {"classification": "single_mark", "selected": ["A"], "auto_resolved": True},
                {"classification": "single_mark", "selected": ["B"], "auto_resolved": True},
                {"classification": "single_mark", "selected": ["C"], "auto_resolved": True},
            ],
            "student_number_observation": {"candidate": "01"},
        },
    )

    # Initially before number confirmation, issues has kind='number'
    issues = service.issues(exam.id)
    assert len(issues) == 1
    assert issues[0]["kind"] == "number"

    # Teacher sets number via set_number
    service.set_number(stu_source, "1", expected_detection=issues[0]["detection_id"])

    # Issues must be resolved
    assert len(service.issues(exam.id)) == 0

    # Workflow snapshot must SUCCEED without "ยังมีภาพที่ไม่ได้ตรวจทาน หรือเฉลยเปลี่ยน" error!
    snapshot = flow.snapshot(exam.id)
    assert len(snapshot["results"]) == 1
    assert str(snapshot["results"][0]["student_number"]) == "1"



def test_student_item_dynamic_size_hint(tmp_path):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ป.1", "1", "วิชา", 3))

    from exam_grader.exam_ui import ExamDialog
    dlg = ExamDialog(application, exam)
    source = {"id": "test-id", "original_name": "student_01.jpg", "purpose": "student"}
    text = "student_01.jpg\nพร้อม · เลขที่ 1"
    dlg._add_student_item(text, source)

    item = dlg.student_list.item(0)
    hint = item.sizeHint()
    fm = dlg.student_list.fontMetrics()
    expected_min = 2 * fm.lineSpacing() + 16
    assert hint.height() >= expected_min
    assert hint.height() >= 44
    dlg.close()


