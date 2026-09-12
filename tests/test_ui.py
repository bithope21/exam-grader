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
    assert any(
        isinstance(child, QPushButton) and "ย้ายไปถังขยะ" in child.text()
        for child in row.findChildren(QPushButton)
    )
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

    # 1. MainWindow settings gear button
    assert hasattr(window, "settings_button")
    assert "⚙️" in window.settings_button.text()
    menu = window.settings_button.menu()
    assert menu is not None
    actions_text = [a.text() for a in menu.actions()]
    assert any("กระดาษคำตอบ" in t for t in actions_text)
    assert any("สีรอยตรวจ" in t for t in actions_text)

    # 2. NewExamDialog manage templates button
    dialog = NewExamDialog(window)
    assert hasattr(dialog, "manage_template_button")
    assert "⚙️" in dialog.manage_template_button.text()
    assert dialog.manage_template_button.isEnabled()
    dialog.close()

    # 3. TemplateSettingsDialog buttons
    template_dlg = TemplateSettingsDialog(application)
    assert hasattr(template_dlg, "add_custom_btn")
    assert "➕" in template_dlg.add_custom_btn.text()
    assert hasattr(template_dlg, "duplicate_btn")
    assert "📋" in template_dlg.duplicate_btn.text()
    assert hasattr(template_dlg, "edit_btn")
    assert "✏️" in template_dlg.edit_btn.text()
    template_dlg.close()

    # 4. ExamDialog results tab color button
    exam = application.exams.create(ExamDetails("ทดสอบ", "2569", "ป.1", "1", "วิชา", 10))
    exam_dlg = ExamDialog(application, exam)
    assert hasattr(exam_dlg, "color_button")
    assert "🎨" in exam_dlg.color_button.text()
    exam_dlg.close()
    window.close()


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
    print("Issues in dialog:", [(i.get("kind"), i.get("question"), i.get("label")) for i in dialog.issue_rows])
    assert dialog.issue_table.rowCount() == 3

    # 2. Test Select All
    dialog.select_all_btn.click()
    assert all(
        dialog.issue_table.item(r, 0).checkState() == Qt.CheckState.Checked
        for r in range(3)
    )
    assert "เลือก 3 รายการ" in dialog.selection_label.text()

    # 3. Test Clear Selection
    dialog.clear_selection_btn.click()
    assert all(
        dialog.issue_table.item(r, 0).checkState() == Qt.CheckState.Unchecked
        for r in range(3)
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
    QTest.mouseClick(dialog.issue_table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt_center)
    assert dialog.issue_table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert "เลือก 1 รายการ" in dialog.selection_label.text()

    # Click center again: Checked -> Unchecked
    QTest.mouseClick(dialog.issue_table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt_center)
    assert dialog.issue_table.item(0, 0).checkState() == Qt.CheckState.Unchecked
    assert "เลือก 0 รายการ" in dialog.selection_label.text()

    # Click near edge (wide hit area): Unchecked -> Checked
    QTest.mouseClick(dialog.issue_table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt_edge)
    assert dialog.issue_table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert "เลือก 1 รายการ" in dialog.selection_label.text()

    # Right-click does NOT toggle
    QTest.mouseClick(dialog.issue_table.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, pt_center)
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
    QTest.mouseClick(dialog.issue_table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, rect1.center())
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
