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
        review_suggestions = [
            item.get("candidate")
            for item in obs.get("review_suggestions", [])
            if isinstance(item, dict)
        ]

        # The teacher label must remain visible. A selective auto-accept is
        # allowed only when it is itself the authoritative labeled number;
        # every other observation remains review-required.
        assert candidate == expected_num or expected_num in candidates or expected_num in review_suggestions, (
            f"{filename}: expected {expected_num} not in {candidates} or {review_suggestions}"
        )
        if not obs["requires_review"]:
            assert candidate == expected_num
            assert obs["diagnostics"]["candidate_disagreement"] is False
            assert obs["diagnostics"]["independent_agreement"] is True


def test_vol6_0913_alternative_67_uses_measured_digit_scores():
    path = Path("tests/fixtures/real/vol.6/IMG_0913.JPG")
    if not path.exists():
        pytest.skip("vol.6 identity fixture not found")
    data = path.read_bytes()
    template_def = load_builtin_template("default-3")
    result = analyze(data, template_def=template_def)
    observation = observe(data, result["registration"]["matrix"], template_def=template_def)

    assert "67" in observation["candidates"]
    digit_observations = observation["diagnostics"]["digit_observations"]
    first_digit_scores = [
        run["raw_score"]
        for run in digit_observations[0]["runs"]
        if run["candidate"] == "6" and run["raw_score"] is not None
    ]
    second_digit_scores = [
        run["raw_score"]
        for run in digit_observations[1]["runs"]
        if run["candidate"] == "7" and run["raw_score"] is not None
    ]
    assert first_digit_scores and second_digit_scores
    measured_score = min(max(first_digit_scores), max(second_digit_scores))
    assert (
        ("67", measured_score) in observation["diagnostics"]["segmented_alternatives"]
        or observation["diagnostics"]["segmented_candidate"] == ("67", measured_score)
    )
    if not observation["requires_review"]:
        assert observation["candidate"] == "67"
        assert observation["diagnostics"]["candidate_disagreement"] is False
        assert observation["diagnostics"]["independent_agreement"] is True


def test_vol6_full_exam_workflow_and_grading(tmp_path):
    """Test end-to-end import, key confirmation, and grading on vol.6 images."""
    app = initialize(tmp_path / "app_data")
    vol6_dir = Path("tests/fixtures/real/vol.6")
    if not (vol6_dir / "key.JPG").exists():
        pytest.skip("vol.6 images not found")
    gt = json.loads((vol6_dir / "ground_truth.json").read_text(encoding="utf-8"))

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

    # 3. Only observations that pass the selective fail-closed gate may be
    # batch-adopted; all other identities remain for teacher review.
    service = ReviewService(app.exams.path)
    adopt_result = service.adopt_numbers(exam.id)
    states_before_review = service.states(exam.id)
    safe_auto_ids = {
        state["source"]["id"]
        for state in states_before_review
        if not (state["detection"].get("student_number_observation") or {}).get(
            "requires_review", True
        )
    }
    assert set(adopt_result["applied"]) == safe_auto_ids
    assert len(adopt_result["skipped"]) == 0

    # Teacher-confirm the labeled identities so this workflow still checks
    # grading against the fixture without treating OCR as authoritative.
    states = service.states(exam.id)
    for state in states:
        name = state["source"]["original_name"]
        number = gt["student_numbers"].get(name)
        if number is not None:
            service.set_number(
                state["source"],
                number,
                expected_detection=state["detection_id"],
                origin="teacher",
            )
    by_name = {s["source"]["original_name"]: s["number"] for s in service.states(exam.id)}
    assert by_name["IMG_0911.JPG"] == "52"
    assert by_name["IMG_0912.JPG"] == "13"
    assert by_name["IMG_0913.JPG"] == "67"
    assert by_name["IMG_0914.JPG"] == "19"

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
