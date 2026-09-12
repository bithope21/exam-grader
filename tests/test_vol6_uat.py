"""UAT benchmark and regression tests for real fixture vol.6 (Default #3)."""

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.identity import observe
from exam_grader.imaging import analyze
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.template_manager import load_builtin_template
from exam_grader.workflow import Workflow


@pytest.fixture(autouse=True)
def ensure_qapp():
    return QApplication.instance() or QApplication([])


def test_vol6_student_number_recognition_matches_ground_truth():
    """Verify all vol.6 student numbers are accurately recognized according to labeled ground truth."""
    gt_path = Path("tests/fixtures/real/vol.6/ground_truth.json")
    if not gt_path.exists():
        pytest.skip("vol.6 ground truth fixture not found")

    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    t3 = load_builtin_template(gt["exam_template"])
    vol6_dir = Path("tests/fixtures/real/vol.6")

    for filename, expected_num in gt["student_numbers"].items():
        if expected_num is None:
            continue
        file_path = vol6_dir / filename
        data = file_path.read_bytes()
        res = analyze(data, template_def=t3)
        assert res["registration"]["inliers"] > 50

        obs = observe(data, res["registration"]["matrix"], template_def=t3)
        candidate = obs.get("candidate")
        candidates = obs.get("candidates") or []

        # Ground truth must be either the top candidate or prominently available in candidates
        assert expected_num in candidates, (
            f"{filename}: expected {expected_num} not in {candidates}"
        )
        assert candidate == expected_num, (
            f"{filename}: expected top candidate {expected_num}, got {candidate}"
        )


def test_vol6_full_exam_workflow_and_grading(tmp_path):
    """Test end-to-end import, key confirmation, and grading on vol.6 images."""
    app = initialize(tmp_path / "app_data")
    vol6_dir = Path("tests/fixtures/real/vol.6")
    if not (vol6_dir / "key.JPG").exists():
        pytest.skip("vol.6 images not found")

    exam = app.exams.create(
        ExamDetails(
            name="สอบปลายภาค ป.4",
            academic_year="2569",
            subject="ศิลปะ",
            grade="ป.4",
            room="6",
            question_count=30,
            template_id="default-3",
            template_version=1,
        )
    )

    importer = ImportService(app.exams.path)
    flow = Workflow(app.exams.path)

    # 1. Import teacher key
    key_src = importer.import_file(exam.id, vol6_dir / "key.JPG", "key")
    key_res = analyze(
        importer.verified_bytes(key_src), template_def=load_builtin_template("default-3")
    )
    flow.save_detection(key_src["id"], key_res)

    # Derive answers for 30 questions (handling Q26 teacher multiple choice [A, C])
    key_answers = []
    for a in key_res["answers"]:
        if a["selected"]:
            key_answers.append(a["selected"] if len(a["selected"]) > 1 else a["selected"][0])
        else:
            key_answers.append("A")  # fallback for blank key questions in test

    approved_key = flow.approve_key(exam.id, key_answers, key_src["id"])

    # 2. Import student sheets with observations
    for fname in sorted(vol6_dir.glob("IMG_*.JPG")):
        src = importer.import_file(exam.id, fname, "student")
        data = importer.verified_bytes(src)
        res = analyze(data, template_def=load_builtin_template("default-3"))
        obs = observe(
            data,
            res["registration"]["matrix"],
            template_def=load_builtin_template("default-3"),
        )
        res["student_number_observation"] = obs
        flow.save_detection(src["id"], res)

    # 3. Adopt numbers from recognizer evidence without manual guessing
    service = ReviewService(app.exams.path)
    adopt_result = service.adopt_numbers(exam.id)
    assert len(adopt_result["applied"]) == 4
    assert len(adopt_result["skipped"]) == 0

    states = {s["source"]["original_name"]: s["number"] for s in service.states(exam.id)}
    assert states["IMG_0911.JPG"] == "52"
    assert states["IMG_0912.JPG"] == "13"
    assert states["IMG_0913.JPG"] == "67"
    assert states["IMG_0914.JPG"] == "19"

    # Resolve any remaining student answers and finalize
    for s in service.states(exam.id):
        res = s["detection"]
        student_answers = [a["selected"][0] if a["selected"] else "blank" for a in res["answers"]]
        flow.review(s["source"]["id"], s["number"], student_answers, approved_key["id"])

    snapshot = flow.snapshot(exam.id)
    assert len(snapshot["results"]) == 4
    for r in snapshot["results"]:
        assert r["student_number"] in ("13", "19", "52", "67")
        assert r["max"] == 30
        assert r["score"] > 0
