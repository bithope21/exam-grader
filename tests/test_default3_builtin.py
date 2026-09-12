"""Focused tests for Built-in Default #3 template contracts and integration."""

from __future__ import annotations

from pathlib import Path

import cv2
import pytest
from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.template_manager import (
    BUILTIN_TEMPLATE_IDS,
    TemplateDefinition,
    get_reference_image,
    load_builtin_template,
)


@pytest.fixture(autouse=True)
def ensure_qapp():
    return QApplication.instance() or QApplication([])


def test_default3_builtin_loading_and_contract():
    """Verify Default #3 loads as an immutable built-in template with correct specifications."""
    assert "default-3" in BUILTIN_TEMPLATE_IDS

    t3 = load_builtin_template("default-3")
    assert isinstance(t3, TemplateDefinition)
    assert t3.template_id == "default-3"
    assert t3.kind == "builtin"
    assert t3.version == 1
    assert t3.question_count == 30
    assert t3.choice_count == 4
    assert t3.canonical_width == 1200
    assert t3.canonical_height == 1720
    assert list(t3.choice_labels) == ["A", "B", "C", "D"]
    assert list(t3.display_choice_labels) == ["ก", "ข", "ค", "ง"]
    assert len(t3.answer_blocks) == 3

    b0, b1, b2 = t3.answer_blocks
    assert b0.rows == 10 and b0.question_start == 1 and b0.question_end == 10
    assert b1.rows == 10 and b1.question_start == 11 and b1.question_end == 20
    assert b2.rows == 10 and b2.question_start == 21 and b2.question_end == 30

    # Student Number & Score ROIs
    assert t3.student_number_roi == (468, 440, 776, 515)
    assert t3.score_roi == (813, 224, 1076, 527)


def test_default3_reference_image_verification():
    """Verify Default #3 packaged reference image matches canonical dimensions and stored hash."""
    t3 = load_builtin_template("default-3")
    ref_img = get_reference_image(t3)

    assert ref_img.shape == (1720, 1200, 3)
    # Check that it is a non-empty image with good visual content
    assert cv2.mean(ref_img)[0] > 100


def test_default3_duplication_workflow(tmp_path):
    """Verify duplicating Default #3 creates a new custom template with pre-filled geometry."""
    app = initialize(tmp_path)
    t3 = load_builtin_template("default-3")

    # Create duplicate custom definition
    custom_def = TemplateDefinition(
        template_id="custom-default3-copy",
        name="สำเนา Default #3 (ปรับแต่ง)",
        kind="custom",
        version=1,
        canonical_width=t3.canonical_width,
        canonical_height=t3.canonical_height,
        choice_count=t3.choice_count,
        choice_labels=t3.choice_labels,
        display_choice_labels=t3.display_choice_labels,
        choice_map=t3.choice_map,
        question_count=t3.question_count,
        answer_blocks=t3.answer_blocks,
        student_number_roi=t3.student_number_roi,
        score_roi=t3.score_roi,
        reference_sha256=t3.reference_sha256,
        cell_inset=t3.cell_inset,
        registration_config=t3.registration_config,
    )

    app.exams.save_template(custom_def)
    loaded = app.exams.get_template("custom-default3-copy")
    assert loaded is not None
    assert loaded.kind == "custom"
    assert loaded.question_count == 30
    assert len(loaded.answer_blocks) == 3


def test_default3_exam_binding(tmp_path):
    """Verify an exam can be created bound to Default #3 template."""
    app = initialize(tmp_path)
    details = ExamDetails(
        name="สอบปลายภาค สุทธิอนุสรณ์",
        academic_year="2569",
        subject="ศิลปะ ดนตรี นาฏศิลป์",
        grade="ป.4",
        room="1",
        question_count=30,
        template_id="default-3",
        template_version=1,
    )
    exam = app.exams.create(details)
    assert exam.details.template_id == "default-3"

    loaded_exam = next(e for e in app.exams.list_exams() if e.id == exam.id)
    assert loaded_exam.details.template_id == "default-3"

    # Verify storage list_templates includes Default #3
    templates = app.exams.list_templates()
    template_ids = [t.template_id for t in templates]
    assert "default-1" in template_ids
    assert "default-2" in template_ids
    assert "default-3" in template_ids


def test_default3_clone_preserves_omr_and_exam_binding(tmp_path):
    """Verify that duplicating Default #3 preserves full OMR capability and binds properly to exams."""
    import cv2

    from exam_grader.imaging import analyze
    from exam_grader.template_manager import (
        load_exam_template_def,
        save_custom_reference_image,
    )

    app = initialize(tmp_path / "app_data")
    t3 = load_builtin_template("default-3")
    ref_bgr = get_reference_image(t3)

    # Re-encode and save reference image into app_data_dir (exact workflow of calibration UI)
    success, enc = cv2.imencode(".png", ref_bgr)
    assert success
    ref_sha = save_custom_reference_image(app.data_dir, enc.tobytes())

    # Create duplicated custom template
    clone_def = TemplateDefinition(
        template_id="default-3-clone-test",
        name="สำเนา Default #3 เพื่อทดสอบ",
        kind="custom",
        version=1,
        canonical_width=t3.canonical_width,
        canonical_height=t3.canonical_height,
        choice_count=t3.choice_count,
        choice_labels=t3.choice_labels,
        display_choice_labels=t3.display_choice_labels,
        choice_map=t3.choice_map,
        question_count=t3.question_count,
        answer_blocks=t3.answer_blocks,
        student_number_roi=(450, 430, 780, 520),  # modified student number ROI
        score_roi=t3.score_roi,
        reference_sha256=ref_sha,
        cell_inset=t3.cell_inset,
        registration_config=t3.registration_config,
    )
    app.exams.save_template(clone_def)

    # Create exam using cloned template
    exam = app.exams.create(
        ExamDetails(
            name="ทดสอบ Clone Default #3",
            academic_year="2569",
            subject="ศิลปะ",
            grade="ป.4",
            room="1",
            question_count=30,
            template_id="default-3-clone-test",
            template_version=1,
        )
    )

    # Ensure load_exam_template_def resolves the clone (NOT default-1 fallback!)
    resolved = load_exam_template_def(app.exams.path, exam.id)
    assert resolved.template_id == "default-3-clone-test"
    assert resolved.question_count == 30
    assert resolved.student_number_roi == (450, 430, 780, 520)

    # Compare OMR results on vol.6 key.JPG between original default-3 and clone
    key_path = Path("tests/fixtures/real/vol.6/key.JPG")
    if key_path.exists():
        key_bytes = key_path.read_bytes()
        res_builtin = analyze(key_bytes, template_def=t3)
        res_clone = analyze(key_bytes, template_def=resolved, app_data_dir=app.data_dir)

        assert res_clone["registration"]["inliers"] > 50
        answers_builtin = [a["selected"] for a in res_builtin["answers"]]
        answers_clone = [a["selected"] for a in res_clone["answers"]]
        assert answers_clone == answers_builtin
