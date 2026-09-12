from copy import deepcopy

import pytest
from PySide6.QtGui import QImage
from test_workflow import prepare

from exam_grader.imaging import OMR_PIPELINE_VERSION, classify_ink
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService


def observation(answers=("A", "B", "C"), number="1"):
    return {
        "pipeline_version": OMR_PIPELINE_VERSION,
        "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        "student_number_observation": {"candidate": number, "candidates": [number]},
        "answers": [
            {"classification": "single_mark", "selected": [a], "auto_resolved": True}
            for a in answers
        ],
    }


def test_spill_is_resolved_but_faint_competitor_stays_uncertain():
    assert classify_ink([0.178, 0, 0.045, 0, 0], [0.347, 0, 0.007, 0, 0])[:2] == (
        ["A"],
        "single_mark",
    )
    assert classify_ink([0.178, 0, 0.045, 0, 0], [0.347, 0, 0.15, 0, 0])[1] == "uncertain"
    assert classify_ink([0.11, 0.12, 0, 0, 0], [0.1, 0.1, 0, 0, 0])[1] == "multiple"
    assert classify_ink([0] * 5, [0] * 5)[1] == "blank"
    assert classify_ink([0.02, 0, 0, 0, 0], [0.03, 0, 0, 0, 0])[1] == "uncertain"


def setup_auto(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    service = ReviewService(flow.database)
    flow.save_detection(key_source["id"], observation())
    flow.save_detection(source["id"], observation())
    assert service.auto_key(exam.id)
    flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    return flow, exam, source, service


def test_one_bulk_action_finalizes_clear_answers_without_teacher_claim(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    assert service.issues(exam.id)[0]["kind"] == "number"
    assert service.adopt_numbers(exam.id)["applied"] == [source["id"]]
    assert service.issues(exam.id) == []
    result = flow.snapshot(exam.id)["results"][0]
    assert result["score"] == 3
    assert result["decision_origin"] == "machine_with_teacher_identity"
    assert flow.current_key(exam.id)["origin"] == "teacher"
    assert not service.auto_key(exam.id)
    assert service.adopt_numbers(exam.id)["applied"] == []


def test_legacy_detections_not_promoted():
    legacy = observation()
    legacy["pipeline_version"] = "draft-omr-v2"
    assert ReviewService.machine_answers(legacy, 3) == [None] * 3


def test_inline_answer_is_bound_to_current_detection_and_key(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    uncertain = observation()
    uncertain["answers"][1]["auto_resolved"] = False
    flow.save_detection(source["id"], uncertain)
    service.adopt_numbers(exam.id)
    issue = service.issues(exam.id)[0]
    assert issue["question"] == 2
    newer = deepcopy(uncertain)
    flow.save_detection(source["id"], newer)
    with pytest.raises(ValueError, match="เปลี่ยน"):
        service.resolve_answer(
            source, 2, "B", key_id=issue["key_id"], detection_id=issue["detection_id"]
        )
    issue = service.issues(exam.id)[0]
    service.resolve_answer(
        source, 2, "B", key_id=issue["key_id"], detection_id=issue["detection_id"]
    )
    assert service.issues(exam.id) == []
    assert flow.snapshot(exam.id)["results"][0]["decision_origin"] == "teacher_edited"


def test_identity_edit_does_not_refresh_stale_key(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    service.adopt_numbers(exam.id)
    flow.approve_key(exam.id, ["C"] * 3, flow.current_key(exam.id)["source_id"])
    service.set_number(source, "2", expected_detection=service.state(source)["detection_id"])
    service.finalize(exam.id)
    assert any(i["kind"] == "stale" for i in service.issues(exam.id))
    with pytest.raises(ValueError):
        flow.snapshot(exam.id)


def test_attendance_conflict_blocks_export_and_can_be_restored(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    service.set_attendance(exam.id, "1", "absent")
    service.adopt_numbers(exam.id)
    assert any(i["kind"] == "attendance" for i in service.issues(exam.id))
    with pytest.raises(ValueError, match="ขาดสอบ"):
        flow.snapshot(exam.id)
    service.set_attendance(exam.id, "1", "pending")
    assert flow.snapshot(exam.id)["results"][0]["score"] == 3
    with pytest.raises(ValueError):
        service.set_attendance(exam.id, "1", "absent")


def test_out_of_range_identity_cannot_export(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    service.adopt_numbers(exam.id)
    with flow.connection() as con:
        con.execute("UPDATE exams SET expected_number_max=5 WHERE id=?", (exam.id,))
    service.set_number(source, "50", expected_detection=service.state(source)["detection_id"])
    service.finalize(exam.id)
    assert any(i["label"] == "เลขที่เกินช่วง" for i in service.issues(exam.id))
    with pytest.raises(ValueError):
        flow.snapshot(exam.id)


def test_unreadable_image_is_one_issue_not_thirty(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    flow.save_detection(source["id"], {"failure": "bad registration"})
    assert [i["kind"] for i in service.issues(exam.id)] == ["image"]


def another_student(flow, exam, tmp_path, name="other.png"):
    path = tmp_path / name
    pixels = QImage(35, 45, QImage.Format.Format_RGB32)
    shade = 0x80 + sum(name.encode()) % 32
    pixels.fill((0xFF << 24) | (shade << 16) | (shade << 8) | shade)
    pixels.save(str(path))
    return ImportService(flow.database).import_file(exam.id, path, "student")


def test_ambiguous_one_four_uses_explicit_alternative_with_clear_four(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    other = another_student(flow, exam, tmp_path)
    ambiguous = observation(number="4")
    ambiguous["student_number_observation"]["candidates"] = ["4", "1"]
    flow.save_detection(source["id"], ambiguous)
    flow.save_detection(other["id"], observation(number="4"))
    result = service.adopt_numbers(exam.id)
    assert len(result["applied"]) == 2
    assert service.state(source)["number"] == "1"
    assert service.state(other)["number"] == "4"


def test_bulk_adoption_resolves_domains_after_known_numbers(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    known_four = another_student(flow, exam, tmp_path, "known-four.png")
    known_two = another_student(flow, exam, tmp_path, "known-two.png")
    ambiguous_three = another_student(flow, exam, tmp_path, "ambiguous-three.png")
    ambiguous_fourteen = another_student(flow, exam, tmp_path, "ambiguous-fourteen.png")
    ambiguous_twenty_four = another_student(flow, exam, tmp_path, "ambiguous-twenty-four.png")
    flow.save_detection(known_four["id"], observation(number="4"))
    flow.save_detection(known_two["id"], observation(number="2"))
    for student, choices, candidate in (
        (ambiguous_three, ["3", "4"], "3"),
        (ambiguous_fourteen, ["14", "4"], "14"),
        (ambiguous_twenty_four, ["24", "4", "2"], "24"),
    ):
        detected = observation(number=candidate)
        detected["student_number_observation"]["candidates"] = choices
        flow.save_detection(student["id"], detected)

    result = service.adopt_numbers(exam.id)
    assert len(result["applied"]) == 6
    assert service.state(ambiguous_three)["number"] == "3"
    assert service.state(ambiguous_fourteen)["number"] == "14"
    assert service.state(ambiguous_twenty_four)["number"] == "24"


def test_duplicate_candidates_never_assigned_from_missing_sequence(tmp_path):
    flow, exam, source, service = setup_auto(tmp_path)
    other = another_student(flow, exam, tmp_path)
    flow.save_detection(other["id"], observation(number="1"))
    result = service.adopt_numbers(exam.id)
    assert not result["applied"]
    assert len(result["skipped"]) == 2
    assert service.state(source)["number"] is None
    assert service.state(other)["number"] is None


def test_bulk_resolve_atomic_transaction(tmp_path):
    """Verify bulk_resolve atomically applies multiple answer/attendance edits."""
    flow, exam, source, service = setup_auto(tmp_path)
    other = another_student(flow, exam, tmp_path)

    # Make questions uncertain for both students
    det1 = observation(answers=["A", "B", "C"])
    det1["answers"][0] = {"classification": "uncertain", "selected": [], "auto_resolved": False}
    det1["answers"][1] = {"classification": "uncertain", "selected": [], "auto_resolved": False}
    flow.save_detection(source["id"], det1)

    det2 = observation(answers=["A", "B", "C"])
    det2["answers"][0] = {"classification": "uncertain", "selected": [], "auto_resolved": False}
    flow.save_detection(other["id"], det2)

    # Set teacher identities
    service.set_number(source, "1", expected_detection=service.state(source)["detection_id"])
    service.set_number(other, "2", expected_detection=service.state(other)["detection_id"])

    flow.confirmed_key(exam.id)
    # Both students have uncertain answers
    issues_before = service.issues(exam.id)
    answer_issues = [i for i in issues_before if i["kind"] == "answer"]
    assert len(answer_issues) == 3

    # Select only the first 2 answer issues to resolve as 'blank'
    chosen_issues = answer_issues[:2]
    unselected_issues = answer_issues[2:]

    operations = [{"issue": issue, "value": "blank"} for issue in chosen_issues]
    result = service.bulk_resolve(exam.id, operations)
    assert result["applied"] == 2

    # Verify chosen issues are resolved and unselected issues remain
    issues_after = service.issues(exam.id)
    assert len(issues_after) == len(issues_before) - 2

    for unsel in unselected_issues:
        key_tuple = (unsel["source"]["id"], unsel["question"])
        assert any(
            i.get("source", {}).get("id") == key_tuple[0] and i.get("question") == key_tuple[1]
            for i in issues_after
        ), f"Unselected issue {key_tuple} must not be overwritten"
