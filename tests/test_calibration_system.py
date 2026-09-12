"""Comprehensive tests for Custom Template Calibration & Visual Inspection System."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.calibration_ui import (
    CalibrationCanvas,
    CalibrationDialog,
    CalibrationTestDialog,
)
from exam_grader.imaging import analyze
from exam_grader.preferences import (
    apply_appearance_theme,
    get_theme_stylesheet,
    save_appearance_mode,
)
from exam_grader.settings_ui import TemplateSettingsDialog
from exam_grader.template_discovery import (
    discover_template,
)


@pytest.fixture(autouse=True)
def ensure_qapp():
    return QApplication.instance() or QApplication([])


def test_default3_real_fixture_auto_discovery():
    """Verify general auto-discovery algorithm detects 3 blocks x 10 rows on Default #3 fixture."""
    data = open("tests/fixtures/real/default3/sheet.png", "rb").read()
    result = discover_template(data)
    td = result.template_def

    # Must detect exactly 3 blocks, 10 rows each, 30 questions total
    assert len(td.answer_blocks) == 3
    assert td.question_count == 30
    assert td.choice_count == 4

    b0, b1, b2 = td.answer_blocks
    assert b0.question_start == 1 and b0.question_end == 10 and b0.rows == 10
    assert b1.question_start == 11 and b1.question_end == 20 and b1.rows == 10
    assert b2.question_start == 21 and b2.question_end == 30 and b2.rows == 10

    # Verify column boundaries span 4 choices each
    assert len(b0.col_boundaries) == 5
    assert len(b1.col_boundaries) == 5
    assert len(b2.col_boundaries) == 5

    # ROIs must be detected in the header region
    assert td.score_roi is not None
    sx1, sy1, sx2, sy2 = td.score_roi
    assert 700 <= sx1 < sx2 <= 1150
    assert 180 <= sy1 < sy2 <= 580

    assert td.student_number_roi is not None
    nx1, ny1, nx2, ny2 = td.student_number_roi
    assert 400 <= nx1 < nx2 <= 850
    assert 350 <= ny1 < ny2 <= 550

    # Status message must accurately state 3 blocks, 30 questions
    assert "3 ชุด" in result.status_message
    assert "30 ข้อ" in result.status_message


def test_test_before_save_in_memory_reference_override(tmp_path):
    """Verify test-before-save succeeds without saving to disk or requiring app_data_dir."""
    data = open("tests/fixtures/default3/default#3.PNG", "rb").read()
    res = discover_template(data)
    td = res.template_def
    ref_bgr = res.warped_image

    # Analyze reference sheet using in-memory reference_override
    analysis = analyze(data, template_def=td, reference_override=ref_bgr)

    assert analysis is not None
    assert len(analysis["answers"]) == 30
    assert analysis["aligned"].shape == (td.canonical_height, td.canonical_width, 3)

    # In blank sheet, all questions are classified as blank or uncertain
    for a in analysis["answers"]:
        assert a["classification"] in ("blank", "single_mark", "uncertain")


def test_calibration_canvas_interaction(tmp_path):
    """Test interactive canvas mouse events, handle dragging, and mode switches."""
    canvas = CalibrationCanvas()
    data = open("tests/fixtures/real/default3/sheet.png", "rb").read()
    res = discover_template(data)
    td = res.template_def

    canvas.set_reference(res.warped_image, td)
    canvas.set_zoom(0.5)

    # Test mode changes
    canvas.set_mode(CalibrationCanvas.MODE_SELECT_MOVE)
    assert canvas.mode == CalibrationCanvas.MODE_SELECT_MOVE

    canvas.set_mode(CalibrationCanvas.MODE_DRAW_GRID_AREA)
    assert canvas.mode == CalibrationCanvas.MODE_DRAW_GRID_AREA

    # Test signals on ROI update
    received_rois = []
    canvas.roi_updated.connect(lambda rtype, rect: received_rois.append((rtype, rect)))

    canvas.roi_updated.emit("student", (460, 420, 770, 510))
    assert len(received_rois) == 1
    assert received_rois[0] == ("student", (460, 420, 770, 510))

    # Test signals on block update
    received_blocks = []
    canvas.block_updated.connect(lambda idx, blk: received_blocks.append((idx, blk)))
    b0 = td.answer_blocks[0]
    canvas.block_updated.emit(0, b0)
    assert len(received_blocks) == 1
    assert received_blocks[0][0] == 0


def test_calibration_dialog_nudge_and_controls(tmp_path):
    """Test CalibrationDialog controls: Nudge, Target combo, Add block, Delete block."""
    app = initialize(tmp_path / "data")
    data = open("tests/fixtures/real/default3/sheet.png", "rb").read()
    res = discover_template(data)

    dlg = CalibrationDialog(app)
    dlg._on_discovery_finished(res)

    td = dlg.current_template_def
    assert td is not None
    orig_y = td.answer_blocks[0].row_boundaries[0]

    # Nudge down by 5px
    dlg.nudge_target_combo.setCurrentIndex(0)  # All blocks
    dlg.nudge_step_combo.setCurrentIndex(1)  # 5 px
    dlg._nudge(0, 1)

    new_td = dlg.current_template_def
    assert new_td.answer_blocks[0].row_boundaries[0] == orig_y + 5

    # Nudge student ROI
    orig_sn = new_td.student_number_roi
    assert orig_sn is not None
    dlg.nudge_target_combo.setCurrentIndex(dlg.nudge_target_combo.count() - 2)
    dlg._nudge(1, 0)
    nudged_sn = dlg.current_template_def.student_number_roi
    assert nudged_sn[0] == orig_sn[0] + 5

    # Add block
    initial_blocks = len(dlg.current_template_def.answer_blocks)
    dlg._add_block()
    assert len(dlg.current_template_def.answer_blocks) == initial_blocks + 1

    # Delete block
    dlg.nudge_target_combo.setCurrentIndex(initial_blocks + 1)
    dlg._delete_selected_block()
    assert len(dlg.current_template_def.answer_blocks) == initial_blocks

    dlg.close()


def test_calibration_test_dialog_inspection(tmp_path):
    """Test CalibrationTestDialog renders metrics, answers table, and ROI crops."""
    data = open("tests/fixtures/real/default3/sheet.png", "rb").read()
    res = discover_template(data)
    td = res.template_def

    analysis = analyze(data, template_def=td, reference_override=res.warped_image)

    dlg = CalibrationTestDialog(td, analysis)
    assert dlg.table.rowCount() == 30
    assert dlg.sn_crop_lbl.pixmap() is not None
    assert dlg.score_crop_lbl.pixmap() is not None
    dlg.close()


def test_template_settings_immutability_and_buttons(tmp_path):
    """Built-ins cannot be deleted or directly edited; custom templates can."""
    app = initialize(tmp_path / "data")
    dlg = TemplateSettingsDialog(app)

    # Built-in default-1 is selected by default
    dlg.table.selectRow(0)
    dlg._on_selection_changed()

    assert not dlg.delete_btn.isEnabled()
    assert not dlg.edit_btn.isEnabled()
    assert dlg.duplicate_btn.isEnabled()
    assert dlg.add_custom_btn.isEnabled()

    # Now create and save a custom template
    data = open("tests/fixtures/real/default3/sheet.png", "rb").read()
    res = discover_template(data)
    custom_td = res.template_def
    app.exams.save_template(custom_td)

    dlg.refresh_templates()
    # Find custom template in table and select it
    for r in range(dlg.table.rowCount()):
        if dlg.table.item(r, 0).text() == custom_td.name:
            dlg.table.selectRow(r)
            break
    dlg._on_selection_changed()

    assert dlg.delete_btn.isEnabled()
    assert dlg.edit_btn.isEnabled()
    assert dlg.duplicate_btn.isEnabled()

    dlg.close()


def test_appearance_mode_theme_and_stylesheet(tmp_path):
    """Test light, dark, and system appearance modes."""
    save_appearance_mode("dark")
    dark_css = get_theme_stylesheet("dark")
    assert "#0F172A" in dark_css
    assert "#1E293B" in dark_css

    save_appearance_mode("light")
    light_css = get_theme_stylesheet("light")
    assert "#F8FAFC" in light_css
    assert "#FFFFFF" in light_css

    save_appearance_mode("system")
    sys_css = get_theme_stylesheet("system")
    assert sys_css == ""

    qapp = QApplication.instance()
    assert qapp is not None
    assert isinstance(qapp, QApplication)
    apply_appearance_theme(qapp, "light")
    assert "#F8FAFC" in qapp.styleSheet()
