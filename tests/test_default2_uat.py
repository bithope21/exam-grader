"""End-to-end Real-Fixture UAT for Default #2 Answer-Sheet Template and Workflow."""

import json
from pathlib import Path

import cv2
import pytest

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.exporting import export_results
from exam_grader.imaging import analyze
from exam_grader.imports import ImportService
from exam_grader.template_manager import (
    cell_rect_for_template,
    get_reference_image,
    load_builtin_template,
)
from exam_grader.workflow import Workflow


def test_default2_real_fixture_blank_analysis():
    """Verify that real Default #2 fixture achieves high coverage and 100% blank answers."""
    fixture_path = Path("tests/fixtures/default2/sheet.jpg")
    if not fixture_path.exists():
        pytest.skip("Default #2 fixture not found")

    image_bytes = fixture_path.read_bytes()
    t2 = load_builtin_template("default-2")

    result = analyze(image_bytes, template_def=t2)
    reg = result["registration"]
    assert reg["table_coverage"] >= 0.99, f"Low table coverage: {reg['table_coverage']}"
    assert len(result["answers"]) == 60

    for idx, ans in enumerate(result["answers"]):
        assert ans["classification"] == "blank", (
            f"Question {idx + 1} expected blank, got {ans['classification']}: {ans}"
        )
        assert ans["selected"] == []
        # Ensure only 4 choices are analyzed, never 5
        assert len(ans["ink_density"]) == 4, (
            f"Q{idx + 1} has {len(ans['ink_density'])} densities, expected 4"
        )


def test_default2_synthetic_marks_accuracy():
    """Verify that synthetic pencil/pen marks on Default #2 are recognized accurately."""
    t2 = load_builtin_template("default-2")
    ref_bgr = get_reference_image(t2)
    marked = ref_bgr.copy()

    # Draw marks: Q1=A, Q15=B, Q20=C, Q21=multiple(B, C), Q40=D, Q60=D
    marks = [
        (1, [0]),  # Q1 = A
        (15, [1]),  # Q15 = B
        (20, [2]),  # Q20 = C
        (21, [1, 2]),  # Q21 = B, C (multiple)
        (40, [3]),  # Q40 = D
        (60, [3]),  # Q60 = D
    ]

    for q, choices in marks:
        for c in choices:
            x, y, w, h = cell_rect_for_template(t2, q, c)
            # Fill marked cell with dark ink
            cv2.rectangle(marked, (x + 3, y + 3), (x + w - 3, y + h - 3), (20, 20, 20), -1)

    ok, enc = cv2.imencode(".png", marked)
    assert ok
    result = analyze(enc.tobytes(), template_def=t2)

    answers = result["answers"]
    assert answers[0]["classification"] == "single_mark"
    assert answers[0]["selected"] == ["A"]

    assert answers[14]["classification"] == "single_mark"
    assert answers[14]["selected"] == ["B"]

    assert answers[19]["classification"] == "single_mark"
    assert answers[19]["selected"] == ["C"]

    assert answers[20]["classification"] == "multiple"
    assert set(answers[20]["selected"]) == {"B", "C"}

    assert answers[39]["classification"] == "single_mark"
    assert answers[39]["selected"] == ["D"]

    assert answers[59]["classification"] == "single_mark"
    assert answers[59]["selected"] == ["D"]

    # All other 54 questions must be blank
    marked_q = {1, 15, 20, 21, 40, 60}
    for q_num in range(1, 61):
        if q_num not in marked_q:
            assert answers[q_num - 1]["classification"] == "blank"


def test_default2_end_to_end_workflow_and_export(tmp_path: Path):
    """Full workflow: create exam with default-2, import key, import student, score, export."""
    app = initialize(tmp_path / "data")
    details = ExamDetails(
        name="สอบปลายภาค ม.3",
        academic_year="2569",
        grade="ม.3",
        room="1",
        subject="วิทยาศาสตร์",
        question_count=60,
        expected_number_max=50,
        template_id="default-2",
        template_version=1,
    )
    exam = app.exams.create(details)
    assert exam.details.template_id == "default-2"

    t2 = load_builtin_template("default-2")
    ref_bgr = get_reference_image(t2)

    # Prepare key image (all A)
    key_img = ref_bgr.copy()
    for q in range(1, 61):
        x, y, w, h = cell_rect_for_template(t2, q, 0)
        cv2.rectangle(key_img, (x + 3, y + 3), (x + w - 3, y + h - 3), (20, 20, 20), -1)
    key_path = tmp_path / "key.png"
    cv2.imwrite(str(key_path), key_img)

    importer = ImportService(app.exams.path)
    flow = Workflow(app.exams.path)

    key_src = importer.import_file(exam.id, key_path, "key")
    key_detection = analyze(key_path.read_bytes(), template_def=t2)
    flow.save_detection(key_src["id"], key_detection)

    # Approve key (60 questions all A)
    key_answers = ["A"] * 60
    flow.approve_key(exam.id, key_answers, key_src["id"])

    # Prepare student image (Q1..Q45 = A, Q46..Q60 = blank -> Score 45 / 60)
    stu_img = ref_bgr.copy()
    for q in range(1, 46):
        x, y, w, h = cell_rect_for_template(t2, q, 0)
        cv2.rectangle(stu_img, (x + 3, y + 3), (x + w - 3, y + h - 3), (20, 20, 20), -1)
    stu_path = tmp_path / "student_1.png"
    cv2.imwrite(str(stu_path), stu_img)

    stu_src = importer.import_file(exam.id, stu_path, "student")
    stu_detection = analyze(stu_path.read_bytes(), template_def=t2)
    flow.save_detection(stu_src["id"], stu_detection)

    # Student review
    stu_answers = [
        ans["selected"][0] if ans["selected"] else "blank" for ans in stu_detection["answers"]
    ]
    flow.review(
        stu_src["id"],
        "1",
        stu_answers,
        flow.current_key(exam.id)["id"],
    )

    # Export results
    output_dir = tmp_path / "results"
    export_path = export_results(flow, exam.id, output_root=output_dir)
    assert export_path.exists()

    # Verify score Excel
    xlsx_path = export_path / "scores.xlsx"
    assert xlsx_path.exists()

    # Verify checked image
    checked_files = list((export_path / "checked").glob("*.jpg"))
    assert len(checked_files) == 1
    checked_img = cv2.imread(str(checked_files[0]))
    assert checked_img is not None
    assert checked_img.shape[0] > 0 and checked_img.shape[1] > 0

    # Verify results JSON
    snapshot_path = export_path / "_system" / "results.json"
    assert snapshot_path.exists()
    snap_data = json.loads(snapshot_path.read_text())
    assert snap_data["exam"]["template_id"] == "default-2"
    assert snap_data["results"][0]["score"] == 45
    assert snap_data["results"][0]["max"] == 60
    assert snap_data["results"][0]["checked_provenance"]["template_id"] == "default-2"
