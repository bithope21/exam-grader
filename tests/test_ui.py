import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLineEdit, QMessageBox, QPushButton

import exam_grader.imaging as imaging
import exam_grader.review_ui as review_ui
from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.imaging import OMR_PIPELINE_VERSION
from exam_grader.imports import ImportService
from exam_grader.preferences import apply_appearance_theme
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
    exam = application.exams.create(dialog.details)
    application.exams.create_room(exam.id, "ป.1/2")
    window.refresh()
    window.show()
    qt.processEvents()
    assert window.exam_list.count() == 1
    assert "กลางภาค" in window.exam_list.item(0).text()
    assert "ห้องเริ่มต้น 1 · รวม 2 ห้อง" in window.exam_list.item(0).text()
    assert not hasattr(window, "delete_exam_button")
    row = window.exam_list.itemWidget(window.exam_list.item(0))
    assert row is not None
    assert any(
        isinstance(child, QPushButton)
        and child.text() == ""
        and child.property("kind") == "icon"
        and child.accessibleName() == "ย้ายไปถังขยะ"
        and not child.icon().isNull()
        and child.iconSize().width() == 19
        for child in row.findChildren(QPushButton)
    )
    assert window.exam_list.item(0).sizeHint().height() == 44
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


def test_manual_crop_reruns_from_original_and_reopens_review_without_approving_key(
    tmp_path, monkeypatch
):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ป.1", "1", "วิชา", 2))
    key_path = tmp_path / "key.png"
    image = QImage(120, 160, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    image.save(str(key_path))
    importer = ImportService(application.exams.path)
    source = importer.import_file(exam.id, key_path, "key")
    flow = Workflow(application.exams.path)
    flow.save_detection(source["id"], {"failure": "จัดแนวไม่สำเร็จ", "pipeline_version": OMR_PIPELINE_VERSION})
    original_bytes = importer.verified_bytes(source)
    chosen_corners = [[10, 10], [110, 10], [110, 150], [10, 150]]

    class AcceptedCrop:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def accepted_corners(self):
            return chosen_corners

    def fake_analyze(data, **kwargs):
        assert data == original_bytes
        assert kwargs["manual_corners"] == chosen_corners
        return {
            "pipeline_version": OMR_PIPELINE_VERSION,
            "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "answers": [
                {"question": 1, "classification": "uncertain", "selected": [], "auto_resolved": False},
                {"question": 2, "classification": "uncertain", "selected": [], "auto_resolved": False},
            ],
            "manual_test_corners": kwargs["manual_corners"],
        }

    monkeypatch.setattr(review_ui, "ManualCropDialog", AcceptedCrop)
    monkeypatch.setattr(imaging, "analyze", fake_analyze)
    dialog = ReviewDialog(application.exams.path, source)

    dialog.adjust_corners_button.click()

    assert dialog.normalization_updated is True
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert flow.latest_detection(source["id"])["manual_test_corners"] == chosen_corners
    assert importer.verified_bytes(source) == original_bytes
    import pytest

    with pytest.raises(ValueError):
        flow.current_key(exam.id)
    dialog.close()


def test_new_exam_dialog_template_selection(tmp_path):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    window = MainWindow(application)
    dialog = NewExamDialog(window)

    assert dialog.template_combo.count() >= 2
    # Find Default #2
    d2_idx = -1
    for i in range(dialog.template_combo.count()):
        if "Default #2" in dialog.template_combo.itemText(i):
            d2_idx = i
            break
    assert d2_idx >= 0
    dialog.template_combo.setCurrentIndex(d2_idx)

    for name, value in dict(
        name="ข้อสอบ Default 2", academic_year="2569", grade="ม.1", room="2", subject="ภาษาไทย"
    ).items():
        field = dialog.fields[name]
        if isinstance(field, QComboBox):
            field.setCurrentText(value)
        else:
            field.setText(value)

    dialog.accept()
    assert dialog.details.template_id == "default-2"
    assert dialog.details.template_version == 1
    assert dialog.details.question_count == 60
    exam = application.exams.create(dialog.details)
    assert exam.details.template_id == "default-2"
    dialog.close()
    window.close()


def test_review_dialog_respects_4_choice_template(tmp_path):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(
        ExamDetails("สอบ 4 ตัวเลือก", "2569", "ป.4", "1", "วิชา", 5, template_id="default-2")
    )
    key_path = tmp_path / "key.png"
    image = QImage(30, 40, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    image.save(str(key_path))
    importer = ImportService(application.exams.path)
    key_source = importer.import_file(exam.id, key_path, "key")
    flow = Workflow(application.exams.path)
    flow.save_detection(
        key_source["id"],
        {
            "pipeline_version": OMR_PIPELINE_VERSION,
            "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "answers": [{"classification": "single_mark", "selected": ["A"], "auto_resolved": True}]
            * 5,
        },
    )
    flow.approve_key(exam.id, ["A", "B", "C", "D", "A"], key_source["id"])

    student_path = tmp_path / "student.png"
    student_img = QImage(30, 40, QImage.Format.Format_RGB32)
    student_img.fill(0xFFEEFFEE)
    student_img.save(str(student_path))
    source = importer.import_file(exam.id, student_path, "student")
    flow.save_detection(
        source["id"],
        {
            "pipeline_version": OMR_PIPELINE_VERSION,
            "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "answers": [
                {"classification": "single_mark", "selected": ["A"], "auto_resolved": True},
                {"classification": "blank", "selected": [], "auto_resolved": True},
                {"classification": "single_mark", "selected": ["D"], "auto_resolved": True},
                {"classification": "blank", "selected": [], "auto_resolved": True},
                {"classification": "blank", "selected": [], "auto_resolved": True},
            ],
        },
    )
    dialog = ReviewDialog(application.exams.path, source)
    # Check combo options for student answer
    combo = dialog.combos[0]
    assert isinstance(combo, QComboBox)
    items = [combo.itemText(i) for i in range(combo.count())]
    # Should include ก / A, ข / B, ค / C, ง / D but NOT จ / E
    assert any("ก / A" in it or "A" in it for it in items)
    assert any("ง / D" in it or "D" in it for it in items)
    assert not any("จ / E" in it for it in items)
    dialog.close()


def test_skip_remaining_review_button_confirms_partial_results(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบบางส่วน", "2569", "ม.4", "1", "วิชา", 2))
    key_path, student_path = tmp_path / "key.png", tmp_path / "student.png"
    for path, color in ((key_path, 0xFFFFFFFF), (student_path, 0xFFF5F5F5)):
        image = QImage(30, 40, QImage.Format.Format_RGB32)
        image.fill(color)
        image.save(str(path))
    importer = ImportService(application.exams.path)
    key_source = importer.import_file(exam.id, key_path, "key")
    student_source = importer.import_file(exam.id, student_path, "student")
    flow = Workflow(application.exams.path)
    flow.approve_key(exam.id, ["A", "B"], key_source["id"])
    flow.save_detection(
        student_source["id"],
        {
            "pipeline_version": OMR_PIPELINE_VERSION,
            "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "student_number_observation": {"candidate": None, "candidates": []},
            "answers": [
                {"classification": "single_mark", "selected": ["A"], "auto_resolved": True},
                {"classification": "uncertain", "selected": ["B"], "auto_resolved": False},
            ],
        },
    )
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    dialog = ReviewDialog(application.exams.path, student_source)
    dialog.skip_remaining_button.click()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert warnings and warnings[-1][2] == "โปรดยืนยันข้อมูลก่อนข้ามรายการที่เหลือ"

    prompts = []

    def confirm(*args):
        prompts.append(args[2])
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    dialog.confirmed.setChecked(True)
    dialog.skip_remaining_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.skip_remaining_completed
    assert "เลขที่ยังไม่ยืนยัน: 1" in prompts[0]
    assert "คำตอบ/ข้อที่ยังไม่ชัด: 1" in prompts[0]
    assert "กระดาษที่ยังมีรายการค้าง: 1" in prompts[0]
    result = flow.snapshot(exam.id)["results"][0]
    assert result["student_number"] == "ไม่ทราบเลขที่ #1"
    assert result["answers"] == ["A", "unresolved"]
    assert result["score"] == 1


def test_parse_key_answer_thai_and_bounds():
    import pytest

    from exam_grader.review_ui import parse_key_answer

    # 5-choice standard
    assert parse_key_answer("A") == "A"
    assert parse_key_answer("ก") == "A"
    assert parse_key_answer("ก,ข") == ["A", "B"]
    assert parse_key_answer("จ") == "E"

    # 4-choice template
    assert parse_key_answer("ก,ง", choice_count=4) == ["A", "D"]
    with pytest.raises(ValueError, match="เฉลยต้องเป็น"):
        parse_key_answer("E", choice_count=4)
    with pytest.raises(ValueError, match="เฉลยต้องเป็น"):
        parse_key_answer("จ", choice_count=4)


def test_template_settings_dialog_lists_and_sets_default(tmp_path):
    from exam_grader.preferences import default_template_id
    from exam_grader.settings_ui import TemplateSettingsDialog

    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    dialog = TemplateSettingsDialog(application)
    assert dialog.table.rowCount() >= 2
    # Check default-1 and default-2 in list
    tids = [t.template_id for t in dialog.templates_list]
    assert "default-1" in tids
    assert "default-2" in tids

    # Select default-2 row and set as default
    d2_row = tids.index("default-2")
    dialog.table.selectRow(d2_row)
    dialog._on_selection_changed()
    assert dialog.selected_template is not None
    assert dialog.selected_template.template_id == "default-2"
    dialog._set_as_default()
    assert default_template_id() == "default-2"
    dialog.close()


def test_annotation_color_settings_dialog():
    from exam_grader.preferences import annotation_colors, reset_annotation_colors
    from exam_grader.settings_ui import AnnotationColorSettingsDialog

    QApplication.instance() or QApplication([])
    reset_annotation_colors()
    dialog = AnnotationColorSettingsDialog()
    assert "correct" in dialog.current_colors
    # Simulate picking a color for 'correct'
    dialog.current_colors["correct"] = (0, 255, 0, 255)
    dialog._save_and_close()
    saved = annotation_colors()
    assert saved["correct"] == (0, 255, 0, 255)
    reset_annotation_colors()


def test_settings_and_template_buttons_visibility(tmp_path):
    from exam_grader.exam_ui import ExamDialog
    from exam_grader.settings_ui import TemplateSettingsDialog

    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    window = MainWindow(application)

    # 1. MainWindow settings control uses compact native-style affordances
    assert hasattr(window, "settings_button")
    assert window.settings_button.text() == "ตั้งค่า"
    menu = window.settings_button.menu()
    assert menu is not None
    actions_text = [a.text() for a in menu.actions()]
    assert any("กระดาษคำตอบ" in t for t in actions_text)
    assert any("สีรอยตรวจ" in t for t in actions_text)

    # 2. NewExamDialog manage templates button
    dialog = NewExamDialog(window)
    assert hasattr(dialog, "manage_template_button")
    assert dialog.manage_template_button.text() == "จัดการแม่แบบ…"
    assert dialog.manage_template_button.isEnabled()
    dialog.close()

    # 3. TemplateSettingsDialog buttons
    template_dlg = TemplateSettingsDialog(application)
    assert hasattr(template_dlg, "add_custom_btn")
    assert template_dlg.add_custom_btn.text() == "สร้างแม่แบบใหม่จากภาพ…"
    assert hasattr(template_dlg, "duplicate_btn")
    assert template_dlg.duplicate_btn.text() == "สร้างแม่แบบใหม่จากแม่แบบนี้…"
    assert hasattr(template_dlg, "edit_btn")
    assert template_dlg.edit_btn.text() == "แก้ไข/ปรับเทียบ…"
    template_dlg.close()

    # 4. ExamDialog results tab color button
    exam = application.exams.create(ExamDetails("ทดสอบ", "2569", "ป.1", "1", "วิชา", 10))
    exam_dlg = ExamDialog(application, exam)
    assert hasattr(exam_dlg, "color_button")
    assert exam_dlg.color_button.text() == "สีรอยตรวจ…"
    exam_dlg.close()
    window.close()


def test_shared_control_style_and_stepperless_spinbox_keyboard(tmp_path):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    window = MainWindow(application)
    dialog = NewExamDialog(window)

    assert window.camera_help_button.text() == "ⓘ"
    assert window.camera_help_button.property("kind") == "icon"
    assert window.camera_help_button.size().width() == 36
    assert window.camera_help_button.size().height() == 36
    apply_appearance_theme(QApplication.instance(), "light")
    stylesheet = QApplication.instance().styleSheet()
    assert "QComboBox::drop-down" in stylesheet
    assert "QComboBox::down-arrow" in stylesheet
    assert "QSpinBox::up-button" in stylesheet
    assert "QSpinBox::down-button" in stylesheet
    assert "min-height: 36px" in stylesheet
    assert "QListWidget::item:selected" in stylesheet
    dialog.question_count.ensurePolished()
    assert 35 <= dialog.question_count.sizeHint().height() <= 40
    assert dialog.question_count.lineEdit() is not None

    dialog.question_count.setValue(10)
    dialog.question_count.setFocus()
    QTest.keyClick(dialog.question_count, Qt.Key.Key_Up)
    assert dialog.question_count.value() == 11
    QTest.keyClick(dialog.question_count, Qt.Key.Key_Down)
    assert dialog.question_count.value() == 10

    dialog.close()
    window.close()


def test_student_list_action_is_compact_and_unclipped(tmp_path):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ป.1", "1", "วิชา", 3))
    from exam_grader.exam_ui import ExamDialog

    dialog = ExamDialog(application, exam)
    assert dialog.student_button.menu() is not None
    assert [action.text() for action in dialog.student_button.menu().actions()] == [
        "เลือกไฟล์…",
        "เลือกโฟลเดอร์…",
    ]
    assert dialog.photo_guidance_button.text() == "ⓘ"
    assert dialog.photo_guidance_button.property("kind") == "icon"
    assert dialog.photo_guidance_button.size().width() == 36
    assert dialog.photo_guidance_button.size().height() == 36
    dialog._add_student_item("IMG_0001.jpg\nต้องตรวจทาน", {"id": "source-1"})

    item = dialog.student_list.item(0)
    row = dialog.student_list.itemWidget(item)
    assert item.sizeHint().height() == 44
    remove = row.findChildren(QPushButton)[0]
    assert remove.text() == "ลบ"
    assert remove.property("kind") == "compact"
    assert remove.minimumHeight() == 32
    assert remove.maximumHeight() == 32
    assert remove.accessibleName() == "ลบกระดาษนักเรียน"
    dialog.close()


def test_settings_controls_open_and_stale_detection_requests_current_pipeline(tmp_path, monkeypatch):
    from exam_grader import settings_ui
    from exam_grader.exam_ui import ExamDialog

    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    window = MainWindow(application)

    # The entire settings control must be a menu target, not only a native arrow.
    assert window.settings_button.menu() is not None
    assert window.settings_button.popupMode().name == "InstantPopup"

    opened = []

    class FakeTemplateSettingsDialog:
        selected_template = None
        last_created_template_id = None

        def __init__(self, *args, **kwargs):
            opened.append(True)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(settings_ui, "TemplateSettingsDialog", FakeTemplateSettingsDialog)
    new_exam = NewExamDialog(window)
    new_exam.manage_template_button.click()
    assert opened
    new_exam.close()

    exam = application.exams.create(ExamDetails("ทดสอบ pipeline", "2569", "ป.1", "1", "วิชา", 3))
    importer = ImportService(application.exams.path)
    key_path = tmp_path / "key.png"
    student_path = tmp_path / "student.png"
    image = QImage(100, 100, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    image.save(str(key_path))
    image.fill(0xFFF0F0F0)
    image.save(str(student_path))
    key_source = importer.import_file(exam.id, key_path, "key")
    student_source = importer.import_file(exam.id, student_path, "student")
    flow = Workflow(application.exams.path)
    flow.save_detection(
        key_source["id"],
        {
            "pipeline_version": OMR_PIPELINE_VERSION,
            "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "answers": [],
        },
    )
    flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    flow.save_detection(
        student_source["id"],
        {"pipeline_version": "omr-illumination-v9-document-normalization-v1"},
    )

    dialog = ExamDialog(application, exam)
    calls = []
    monkeypatch.setattr(
        dialog,
        "start_import",
        lambda paths, purpose: calls.append((list(paths), purpose)),
    )
    dialog._ensure_current_pipeline()
    assert calls == [
        ([application.exams.path.parent / student_source["relative_path"]], "student")
    ]
    dialog.close()
    window.close()


def test_student_import_shows_nonblocking_photo_guidance(tmp_path):
    from exam_grader.exam_ui import PHOTO_GUIDANCE_TEXT, ExamDialog

    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("ทดสอบ", "2569", "ป.1", "1", "วิชา", 10))
    dialog = ExamDialog(application, exam)

    guidance = dialog.photo_guidance_button
    assert guidance.accessibleName() == "คำแนะนำการถ่ายภาพ"
    assert guidance.toolTip() == PHOTO_GUIDANCE_TEXT
    assert "ครบ 4 มุม" in guidance.toolTip()
    assert "ตารางคำตอบ" in guidance.toolTip()
    assert "แสงสะท้อน" in guidance.toolTip()
    assert "รอยกากบาท" in guidance.toolTip()

    dialog.close()


def test_review_tab_bulk_edit_ui(tmp_path):
    """Test multi-row checkbox selection and bulk edit in Review tab."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from exam_grader.app import initialize
    from exam_grader.domain import ExamDetails
    from exam_grader.exam_ui import ExamDialog
    from exam_grader.imports import ImportService
    from exam_grader.review_service import ReviewService
    from exam_grader.workflow import Workflow

    app = initialize(tmp_path / "app_data")
    exam = app.exams.create(
        ExamDetails(
            name="Bulk Edit UI Test",
            academic_year="2569",
            subject="ทดสอบ",
            grade="ป.1",
            room="1",
            question_count=5,
            template_id="default-1",
        )
    )

    importer = ImportService(app.exams.path)
    flow = Workflow(app.exams.path)

    # Teacher key
    key_img = tmp_path / "key.png"
    key_img.write_bytes(b"fake_key_bytes")
    # Create simple dummy PNG for imports
    from PySide6.QtGui import QImage

    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFF)
    img.save(str(key_img))

    k_src = importer.import_file(exam.id, key_img, "key")
    flow.approve_key(exam.id, ["A", "B", "C", "D", "E"], k_src["id"])

    # Student 1 with 3 uncertain answers
    s_img = tmp_path / "s1.png"
    img2 = QImage(100, 100, QImage.Format.Format_RGB32)
    img2.fill(0xEEEEEE)
    img2.save(str(s_img))
    s_src = importer.import_file(exam.id, s_img, "student")

    from exam_grader.imaging import OMR_PIPELINE_VERSION

    det = {
        "pipeline_version": OMR_PIPELINE_VERSION,
        "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "inliers": 100},
        "student_number_observation": {"candidate": "1", "candidates": ["1"]},
        "answers": [
            {"classification": "uncertain", "selected": [], "auto_resolved": False},
            {"classification": "uncertain", "selected": [], "auto_resolved": False},
            {"classification": "uncertain", "selected": [], "auto_resolved": False},
            {"classification": "single_mark", "selected": ["D"], "auto_resolved": True},
            {"classification": "single_mark", "selected": ["E"], "auto_resolved": True},
        ],
    }
    flow.save_detection(s_src["id"], det)
    service = ReviewService(app.exams.path)
    service.set_number(s_src, "1", expected_detection=service.state(s_src)["detection_id"])

    dialog = ExamDialog(app, exam)
    dialog.tabs.setCurrentIndex(2)  # Review tab

    # 1. Verify 6 columns
    assert dialog.issue_table.columnCount() == 6
    assert dialog.issue_table.horizontalHeaderItem(0).text() == "เลือก"
    print(
        "Issues in dialog:",
        [(i.get("kind"), i.get("question"), i.get("label")) for i in dialog.issue_rows],
    )
    assert dialog.issue_table.rowCount() == 3

    # 2. Test Select All
    dialog.select_all_btn.click()
    assert all(
        dialog.issue_table.item(r, 0).checkState() == Qt.CheckState.Checked for r in range(3)
    )
    assert "เลือก 3 รายการ" in dialog.selection_label.text()

    # 3. Test Clear Selection
    dialog.clear_selection_btn.click()
    assert all(
        dialog.issue_table.item(r, 0).checkState() == Qt.CheckState.Unchecked for r in range(3)
    )
    assert "เลือก 0 รายการ" in dialog.selection_label.text()
    assert not dialog.bulk_apply_btn.isEnabled()

    # 4. Select only rows 0 and 1, set to 'blank', and apply
    dialog.issue_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    dialog.issue_table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert "เลือก 2 รายการ" in dialog.selection_label.text()

    # Select 'blank' in bulk combo
    blank_idx = dialog.bulk_combo.findData("blank")
    assert blank_idx >= 0
    dialog.bulk_combo.setCurrentIndex(blank_idx)
    assert dialog.bulk_apply_btn.isEnabled()


    # Apply bulk edit without dialog popups blocking
    from unittest.mock import patch

    with patch("PySide6.QtWidgets.QMessageBox.information"):
        dialog.apply_bulk_edit()

    # 5. Verify 2 issues were resolved and only 1 remains (question 3)
    remaining_issues = service.issues(exam.id)
    assert len(remaining_issues) == 1
    assert remaining_issues[0]["question"] == 3

    # Verify answers for Q1 and Q2 were set to blank, Q4 and Q5 kept, Q3 still None
    state = service.state(s_src)
    key = flow.current_key(exam.id)
    answers = service.answers(state, key)
    assert answers[0] == "blank"
    assert answers[1] == "blank"
    assert answers[2] is None
    assert answers[3] == "D"
    assert answers[4] == "E"

    # Dialog table should now have 1 row
    assert dialog.issue_table.rowCount() == 1
    assert dialog.issue_table.item(0, 1).text() == "1"
    assert "ข้อ 3" in dialog.issue_table.item(0, 2).text()


def test_confirmed_student_number_refreshes_students_without_answer_confirmation(tmp_path):
    from exam_grader.exam_ui import ExamDialog
    from exam_grader.review_service import ReviewService
    from exam_grader.workflow import Workflow

    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("เลขที่รีเฟรช", "2569", "ป.1", "1", "วิชา", 1))
    importer = ImportService(application.exams.path)
    flow = Workflow(application.exams.path)

    key_path = tmp_path / "key.png"
    student_path = tmp_path / "student.png"
    image = QImage(100, 100, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    image.save(str(key_path))
    image.fill(0xFFFEFEFE)
    image.save(str(student_path))
    key_source = importer.import_file(exam.id, key_path, "key")
    flow.approve_key(exam.id, ["A"], key_source["id"])
    student_source = importer.import_file(exam.id, student_path, "student")
    detection = {
        "pipeline_version": OMR_PIPELINE_VERSION,
        "registration": {
            "matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "inverse_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        },
        "student_number_observation": {
            "candidate": "7",
            "candidates": ["7"],
            "requires_review": True,
        },
        "answers": [
            {
                "question": 1,
                "classification": "single_mark",
                "selected": ["A"],
                "auto_resolved": True,
            }
        ],
    }
    flow.save_detection(student_source["id"], detection)

    dialog = ExamDialog(application, exam)
    dialog.tabs.setCurrentIndex(1)
    before = dialog.student_list.item(0).text()
    assert "ต้องตรวจทาน" in before
    assert [issue["kind"] for issue in dialog.issue_rows] == ["number"]

    editor = dialog.issue_table.cellWidget(0, 4)
    assert isinstance(editor, QLineEdit)
    editor.setText("7")
    dialog.save_issue(dialog.issue_rows[0], editor)

    after = dialog.student_list.item(0).text()
    assert after != before
    assert "เลขที่ 7" in after
    assert flow.latest_review(student_source["id"]) is not None
    assert ReviewService(flow.database).state(student_source)["number"] == "7"
    dialog.close()


def test_review_tab_checkbox_delegate_ux_and_state_preservation(tmp_path):
    app = initialize(tmp_path)
    importer = ImportService(app.exams.path)
    exam = app.exams.create(
        ExamDetails("ทดสอบ Checkbox UX", "2569", "ป.4", "1", "วิชา", 5, template_id="default-2")
    )
    flow = Workflow(app.exams.path)

    # Teacher key
    key_img = tmp_path / "key.png"
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFF)
    img.save(str(key_img))
    k_src = importer.import_file(exam.id, key_img, "key")
    flow.approve_key(exam.id, ["A", "B", "C", "D", "E"], k_src["id"])

    # Student 1 with 3 uncertain answers
    s_img = tmp_path / "s1.png"
    img2 = QImage(100, 100, QImage.Format.Format_RGB32)
    img2.fill(0xEEEEEE)
    img2.save(str(s_img))
    s_src = importer.import_file(exam.id, s_img, "student")

    det = {
        "pipeline_version": OMR_PIPELINE_VERSION,
        "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "inliers": 100},
        "student_number_observation": {"candidate": "1", "candidates": ["1"]},
        "answers": [
            {"classification": "uncertain", "selected": [], "auto_resolved": False},
            {"classification": "uncertain", "selected": [], "auto_resolved": False},
            {"classification": "uncertain", "selected": [], "auto_resolved": False},
            {"classification": "single_mark", "selected": ["D"], "auto_resolved": True},
            {"classification": "single_mark", "selected": ["E"], "auto_resolved": True},
        ],
    }
    flow.save_detection(s_src["id"], det)
    from exam_grader.review_service import ReviewService

    service = ReviewService(app.exams.path)
    service.set_number(s_src, "1", expected_detection=service.state(s_src)["detection_id"])

    from exam_grader.exam_ui import ExamDialog

    dialog = ExamDialog(app, exam)
    dialog.tabs.setCurrentIndex(2)  # Review tab
    dialog.resize(900, 600)
    dialog.show()
    QApplication.processEvents()

    assert dialog.issue_table.rowCount() == 3
    assert dialog.issue_table.columnWidth(0) == 52

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    # --- 1. Mouse Click UX (wide hit target & no double-trigger) ---
    rect0 = dialog.issue_table.visualRect(dialog.issue_table.model().index(0, 0))
    pt_center = rect0.center()
    pt_edge = rect0.topLeft() + QPoint(4, 4)

    # Click center: Unchecked -> Checked
    QTest.mouseClick(
        dialog.issue_table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        pt_center,
    )
    assert dialog.issue_table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert "เลือก 1 รายการ" in dialog.selection_label.text()

    # Click center again: Checked -> Unchecked
    QTest.mouseClick(
        dialog.issue_table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        pt_center,
    )
    assert dialog.issue_table.item(0, 0).checkState() == Qt.CheckState.Unchecked
    assert "เลือก 0 รายการ" in dialog.selection_label.text()

    # Click near edge (wide hit area): Unchecked -> Checked
    QTest.mouseClick(
        dialog.issue_table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        pt_edge,
    )
    assert dialog.issue_table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert "เลือก 1 รายการ" in dialog.selection_label.text()

    # Right-click does NOT toggle
    QTest.mouseClick(
        dialog.issue_table.viewport(),
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
        pt_center,
    )
    assert dialog.issue_table.item(0, 0).checkState() == Qt.CheckState.Checked

    # Keyboard Space key on Row 1 toggles
    dialog.issue_table.setCurrentCell(1, 0)
    QTest.keyClick(dialog.issue_table, Qt.Key.Key_Space)
    assert dialog.issue_table.item(1, 0).checkState() == Qt.CheckState.Checked
    assert "เลือก 2 รายการ" in dialog.selection_label.text()

    # --- 2. State Preservation across Refresh ---
    # Rows 0 and 1 are checked. Call refresh()
    dialog.refresh()
    assert dialog.issue_table.rowCount() == 3
    assert dialog.issue_table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert dialog.issue_table.item(1, 0).checkState() == Qt.CheckState.Checked
    assert dialog.issue_table.item(2, 0).checkState() == Qt.CheckState.Unchecked
    assert "เลือก 2 รายการ" in dialog.selection_label.text()

    # --- 3. Uncheck Row 1 after refresh ---
    rect1 = dialog.issue_table.visualRect(dialog.issue_table.model().index(1, 0))
    QTest.mouseClick(
        dialog.issue_table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        rect1.center(),
    )
    assert dialog.issue_table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert dialog.issue_table.item(1, 0).checkState() == Qt.CheckState.Unchecked
    assert "เลือก 1 รายการ" in dialog.selection_label.text()

    # --- 4. Bulk Save of Row 0 ---
    blank_idx = dialog.bulk_combo.findData("blank")
    dialog.bulk_combo.setCurrentIndex(blank_idx)
    assert dialog.bulk_apply_btn.isEnabled()

    from unittest.mock import patch

    with patch("PySide6.QtWidgets.QMessageBox.information"):
        dialog.apply_bulk_edit()

    # --- 5. Post-Save Refresh verification ---
    # Row 0 was Question 1, which got resolved. Remaining issues should be 2 (Questions 2 and 3).
    assert dialog.issue_table.rowCount() == 2
    # The resolved key should no longer be in selected_issue_keys
    assert len(dialog.selected_issue_keys) == 0
    assert "เลือก 0 รายการ" in dialog.selection_label.text()
    assert not dialog.bulk_apply_btn.isEnabled()
