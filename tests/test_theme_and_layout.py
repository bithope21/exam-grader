"""Tests for centralized theme palette, stylesheet design tokens, and responsive dialog layouts."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QFormLayout

from exam_grader.app import initialize
from exam_grader.calibration_ui import CalibrationDialog
from exam_grader.preferences import (
    appearance_mode,
    apply_appearance_theme,
    create_theme_palette,
    get_theme_stylesheet,
    save_appearance_mode,
)
from exam_grader.settings_ui import TemplateSettingsDialog
from exam_grader.template_manager import load_builtin_template


@pytest.fixture(autouse=True)
def ensure_qapp():
    return QApplication.instance() or QApplication([])


def test_theme_palette_and_stylesheet():
    """Verify Light and Dark theme palettes and stylesheets provide correct semantic colors."""
    # Dark Mode
    dark_pal = create_theme_palette("dark")
    assert isinstance(dark_pal, QPalette)
    # Dark window background should be dark (RGB values < 50)
    win_color = dark_pal.color(QPalette.ColorRole.Window)
    assert win_color.red() < 50 and win_color.green() < 50 and win_color.blue() < 50

    dark_qss = get_theme_stylesheet("dark")
    assert "QMenu {" in dark_qss
    assert "QListWidget {" in dark_qss
    assert "QTableWidget {" in dark_qss
    assert "#0F172A" in dark_qss  # Slate 900
    assert "#1E293B" in dark_qss  # Slate 800

    # Light Mode
    light_pal = create_theme_palette("light")
    assert isinstance(light_pal, QPalette)
    light_win = light_pal.color(QPalette.ColorRole.Window)
    assert light_win.red() > 200 and light_win.green() > 200 and light_win.blue() > 200

    light_qss = get_theme_stylesheet("light")
    assert "QMenu {" in light_qss
    assert "#F8FAFC" in light_qss  # Slate 50
    assert "#FFFFFF" in light_qss


def test_apply_appearance_theme_modes():
    """Verify applying light, dark, and system appearance modes."""
    app = QApplication.instance()
    assert app is not None

    save_appearance_mode("light")
    apply_appearance_theme(app, "light")
    assert appearance_mode() == "light"

    save_appearance_mode("dark")
    apply_appearance_theme(app, "dark")
    assert appearance_mode() == "dark"

    save_appearance_mode("system")
    apply_appearance_theme(app, "system")
    assert appearance_mode() == "system"


def test_template_settings_dialog_responsive_layout(tmp_path):
    """Verify TemplateSettingsDialog has 2-column table and proper split layout."""
    app = initialize(tmp_path)
    dlg = TemplateSettingsDialog(app)

    # Table columns: Name (0), Kind (1)
    assert dlg.table.columnCount() == 2
    assert dlg.table.horizontalHeaderItem(0).text() == "ชื่อแม่แบบ"
    assert dlg.table.horizontalHeaderItem(1).text() == "ชนิด"

    # All 3 built-ins must be listed
    template_names = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
    assert any("Default #1" in name for name in template_names)
    assert any("Default #2" in name for name in template_names)
    assert any("Default #3" in name for name in template_names)

    # Built-in template selected: edit and delete must be disabled
    dlg.table.selectRow(0)
    dlg._on_selection_changed()
    assert not dlg.edit_btn.isEnabled()
    assert not dlg.delete_btn.isEnabled()
    assert dlg.duplicate_btn.isEnabled()
    assert dlg.test_omr_btn.isEnabled()

    dlg.close()


def test_calibration_dialog_containment_and_controls(tmp_path):
    """Verify CalibrationDialog opens with responsive size within available screen bounds."""
    app = initialize(tmp_path)
    t3 = load_builtin_template("default-3")

    dlg = CalibrationDialog(app, edit_template=t3)

    # Screen available geometry check
    screen = QApplication.primaryScreen()
    if screen:
        avail = screen.availableGeometry()
        assert dlg.width() <= avail.width()
        assert dlg.height() <= avail.height()

    # Verify key UI components exist and are properly wired
    assert dlg.controls_scroll is not None
    assert dlg.canvas is not None
    assert dlg.save_btn is not None
    assert dlg.test_btn is not None

    # Default #3 has 3 blocks
    assert len(dlg.current_template_def.answer_blocks) == 3

    dlg.close()


def test_trash_dialog_lifecycle_and_destructive_styling(tmp_path):
    """Verify TrashDialog populates archived exams and configures destructive purge button."""
    from exam_grader.domain import ExamDetails
    from exam_grader.ui import MainWindow, TrashDialog

    app = initialize(tmp_path)
    exam = app.exams.create(
        ExamDetails(
            name="วิชาที่ถูกลบ",
            academic_year="2569",
            subject="ไทย",
            grade="ป.1",
            room="1",
            question_count=30,
        )
    )
    app.exams.archive(exam.id)

    win = MainWindow(app)
    dlg = TrashDialog(win)

    assert dlg.listing.count() == 1
    assert "วิชาที่ถูกลบ" in dlg.listing.item(0).text()
    assert dlg.purge_btn.property("destructive") is True
    assert dlg.minimumWidth() >= 500

    dlg.close()
    win.close()


def test_new_exam_dialog_dimensions_and_controls(tmp_path):
    """Verify NewExamDialog has sufficient width, comfortable margins, and non-cramped fields."""
    from exam_grader.ui import MainWindow, NewExamDialog

    app = initialize(tmp_path)
    win = MainWindow(app)
    dlg = NewExamDialog(win)

    assert dlg.minimumWidth() >= 500
    assert "name" in dlg.fields
    assert "grade" in dlg.fields
    assert dlg.fields["grade"].minimumContentsLength() >= 8
    assert dlg.template_combo.count() >= 3

    # Verify label is "จำนวนข้อของข้อสอบ"
    layout = dlg.layout()
    labels = []
    for row in range(layout.rowCount()):
        item = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
        if item and item.widget():
            labels.append(item.widget().text())
    assert "จำนวนข้อของข้อสอบ" in labels

    dlg.close()
    win.close()


def test_is_dark_mode_detection():
    """Verify is_dark_mode accurately reflects appearance mode preference."""
    from exam_grader.preferences import is_dark_mode

    save_appearance_mode("dark")
    assert is_dark_mode() is True

    save_appearance_mode("light")
    assert is_dark_mode() is False
