import pytest
from test_workflow import prepare

from exam_grader.imaging import OMR_PIPELINE_VERSION
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.workflow import score_answer


def test_key_accepts_alternatives_but_student_multiple_scores_zero(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    key = flow.approve_key(exam.id, [["A", "B"], "C", "D"], key_source["id"])
    flow.review(source["id"], "1", ["A", "multiple", "D"], key["id"])
    result = flow.snapshot(exam.id)["results"][0]
    assert result["score"] == 2
    assert score_answer("B", ["A", "B"]) == 1
    assert score_answer("multiple", ["A", "B"]) == 0


def test_malformed_key_alternatives_fail_closed(tmp_path):
    flow, exam, key_source, _ = prepare(tmp_path)
    with pytest.raises(ValueError):
        flow.approve_key(exam.id, [["A", "bad"], "C", "D"], key_source["id"])


def test_archived_student_is_excluded_and_same_sha_reimport_restores(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    key = flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    flow.review(source["id"], "1", ["A", "B", "C"], key["id"])
    importer = ImportService(flow.database)
    importer.archive_source(source["id"])
    assert importer.list_sources(exam.id) == [key_source]
    with pytest.raises(ValueError):
        flow.snapshot(exam.id)
    restored = importer.import_file(exam.id, tmp_path / "student.png", "student")
    assert restored["id"] == source["id"]
    assert restored["archived_at"] is None
    assert flow.snapshot(exam.id)["results"][0]["student_number"] == "1"


def test_boundary_cross_is_a_resolved_zero_credit_student_state():
    detection = {
        "pipeline_version": OMR_PIPELINE_VERSION,
        "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        "answers": [{"classification": "boundary_cross", "selected": [], "auto_resolved": True}],
    }
    assert ReviewService.machine_answers(detection, 1) == ["boundary_cross"]
    assert score_answer("boundary_cross", "A") == 0
