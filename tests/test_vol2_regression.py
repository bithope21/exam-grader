import hashlib
import json
from pathlib import Path

import pytest
from test_automation import observation, setup_auto
from test_workflow import prepare

from exam_grader.exam_ui import BatchWorker
from exam_grader.identity import observe
from exam_grader.imaging import analyze
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService


@pytest.mark.parametrize("volume,truth_file", [(1, "docs/evidence/automation/teacher-run.json"), (2, "docs/evidence/vol2/teacher-results.json")])
def test_real_volume_has_no_wrong_automatic_decisions(volume, truth_file):
    truth = json.loads(Path(truth_file).read_text())
    root = Path(f"tests/fixtures/real/vol.{volume}")
    for expected in truth["results"]:
        data = (root / expected["source"]["original_name"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected["source"]["sha256"]
        result = analyze(data)
        answers = ReviewService.machine_answers(result, len(expected["answers"]))
        unresolved = [i + 1 for i, (actual, target) in enumerate(zip(answers, expected["answers"])) if actual != target]
        if expected["source"]["original_name"] == "IMG_0805.jpg":
            # The supplied teacher label is historical evidence only.  The
            # current PO rule resolves a mark spanning two cells as an
            # explicit zero-credit state instead of silently selecting B.
            assert unresolved == [25]
            assert answers[24] == "boundary_cross"
            assert result["answers"][24]["classification"] == "boundary_cross"
        else:
            assert unresolved == []
            assert all(a is None or a == b for a, b in zip(answers, expected["answers"]))
    key = analyze(next(root.glob("key.*")).read_bytes())
    for q, (answer, target) in enumerate(zip(key["answers"], truth["key"]["answers"]), 1):
        if volume == 2 and q == 28:
            assert answer["classification"] == "multiple"
            assert answer["selected"] == ["B", "E"]
        else:
            assert answer["classification"] == "single_mark"
            assert answer["selected"] == [target]


def test_vol2_number_roi_recovers_clipped_digits_without_guessing_ten():
    root = Path("tests/fixtures/real/vol.2")
    for name, expected in (("IMG_0803.jpg", "1"), ("IMG_0804.jpg", "14"), ("IMG_0805.jpg", "17"), ("IMG_0806.jpg", "24"), ("IMG_0807.jpg", None)):
        data = (root / name).read_bytes()
        detection = analyze(data)
        result = observe(data, detection["registration"]["matrix"])
        assert result["candidate"] == expected
        if expected is None:
            assert set(result["candidates"]) == {"10", "40"}


def test_student_batch_cannot_run_before_explicit_key_confirmation(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    flow.save_detection(key_source["id"], observation())
    service = ReviewService(flow.database)
    service.auto_key(exam.id)
    with pytest.raises(ValueError, match="ยืนยัน"):
        service.adopt_numbers(exam.id)
    with pytest.raises(ValueError, match="ยืนยัน"):
        flow.snapshot(exam.id)
    before = ImportService(flow.database).list_sources(exam.id)
    worker = BatchWorker(flow.database, exam.id, [tmp_path / "does-not-exist.png"], "student")
    worker.run()
    assert ImportService(flow.database).list_sources(exam.id) == before
    assert not ImportService(flow.database).list_failures(exam.id)


def test_sparse_roster_and_explicit_skip_are_persistent(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    service.set_number(source, "24", expected_detection=service.state(source)["detection_id"])
    service.finalize(exam.id)
    assert service.issues(exam.id) == []
    with flow.connection() as con:
        con.execute("UPDATE exams SET expected_number_max=24 WHERE id=?", (exam.id,))
    assert len(service.issues(exam.id)) == 23
    assert service.skip_missing(exam.id) == 23
    assert ReviewService(flow.database).issues(exam.id) == []
    snapshot = flow.snapshot(exam.id)
    assert snapshot["skipped_numbers"] == list(range(1, 24))
    assert len(snapshot["results"]) == 1
    assert snapshot["attendance"] == []
    service.set_attendance(exam.id, "10", "pending")
    assert [i["number"] for i in service.issues(exam.id)] == ["10"]
