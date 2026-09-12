import pytest
from PySide6.QtGui import QImage

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.imports import ImportService
from exam_grader.workflow import Workflow


def prepare(tmp_path):
    app = initialize(tmp_path / "data")
    exam = app.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "วิชา", 3))
    service = ImportService(app.exams.path)
    key_path = tmp_path / "key.png"
    student_path = tmp_path / "student.png"
    image = QImage(30, 40, QImage.Format.Format_RGB32)
    image.fill(0xFFFDFFFF)
    image.save(str(key_path))
    student_image = QImage(30, 40, QImage.Format.Format_RGB32)
    student_image.fill(0xFF000000)
    student_image.save(str(student_path))
    key = service.import_file(exam.id, key_path, "key")
    student = service.import_file(exam.id, student_path, "student")
    return Workflow(app.exams.path), exam, key, student


def test_key_review_score_and_stale_invalidation(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    with pytest.raises(ValueError):
        flow.snapshot(exam.id)
    key = flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    with pytest.raises(ValueError):
        flow.snapshot(exam.id)
    flow.review(source["id"], "17", ["A", "blank", "multiple"], key["id"])
    snapshot = flow.snapshot(exam.id)
    assert snapshot["results"][0]["score"] == 1
    assert snapshot["results"][0]["max"] == 3
    flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    with pytest.raises(ValueError):
        flow.snapshot(exam.id)


def test_unresolved_duplicate_and_wrong_answer_count_block_export(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    key = flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    with pytest.raises(ValueError):
        flow.review(source["id"], "17", ["uncertain"], key["id"])
    with pytest.raises(ValueError):
        flow.review(source["id"], "17", ["A", "B"], key["id"])
    flow.review(source["id"], "17", ["A", "B", "C"], key["id"])
    # A different file in the same exam must not silently replace student 17.
    from PySide6.QtGui import QImage

    path = tmp_path / "other.png"
    image = QImage(20, 20, QImage.Format.Format_RGB32)
    image.fill(0xFF000000)
    image.save(str(path))
    other = ImportService(flow.database).import_file(exam.id, path)
    flow.review(other["id"], "17", ["A", "B", "C"], key["id"])
    with pytest.raises(ValueError, match="ซ้ำ"):
        flow.snapshot(exam.id)
    flow.review(other["id"], "18", ["B", "B", "B"], key["id"])
    assert len(flow.snapshot(exam.id)["results"]) == 2


def test_stale_key_and_cross_exam_key_rejected(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    first = flow.approve_key(exam.id, ["A", "A", "A"], key_source["id"])
    flow.approve_key(exam.id, ["B", "B", "B"], key_source["id"])
    with pytest.raises(ValueError):
        flow.review(source["id"], "17", ["A", "A", "A"], first["id"])


def test_review_keeps_the_detection_that_was_seen(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    key = flow.approve_key(exam.id, ["A", "A", "A"], key_source["id"])
    flow.save_detection(source["id"], {"version": "A"})
    flow.review(source["id"], "17", ["A", "A", "A"], key["id"])
    flow.save_detection(source["id"], {"version": "B"})
    snapshot = flow.snapshot(exam.id)
    assert snapshot["results"][0]["detection"]["version"] == "A"


def test_key_requires_one_choice_per_active_question(tmp_path):
    flow, exam, key_source, _ = prepare(tmp_path)
    for invalid in ([], ["blank"], ["A"] * 61):
        with pytest.raises(ValueError):
            flow.approve_key(exam.id, invalid, key_source["id"])


def test_missing_numbers_respects_optional_expected_range(tmp_path):
    app = initialize(tmp_path / "data")
    exam = app.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "วิชา", 1, 3))
    service = ImportService(app.exams.path)
    key_path = tmp_path / "key.png"
    student_paths = [tmp_path / "one.png", tmp_path / "three.png"]
    from PySide6.QtGui import QImage

    image = QImage(30, 40, QImage.Format.Format_RGB32)
    image.fill(0xFFFDFFFF)
    image.save(str(key_path))
    for index, path in enumerate(student_paths):
        variant = image.copy()
        variant.fill(0xFFFFFFFF if index == 0 else 0xFFFEFFFF)
        variant.save(str(path))
    key_source = service.import_file(exam.id, key_path, "key")
    sources = [service.import_file(exam.id, path, "student") for path in student_paths]
    flow = Workflow(app.exams.path)
    key = flow.approve_key(exam.id, ["A"], key_source["id"])
    flow.review(sources[0]["id"], "1", ["A"], key["id"])
    flow.review(sources[1]["id"], "3", ["A"], key["id"])
    missing = flow.missing_numbers(exam.id)
    assert missing["missing_internal"] == [2]
    assert missing["missing_expected"] == [2]
    app.exams.set_expected_number_max(exam.id, None)
    assert flow.missing_numbers(exam.id)["missing_expected"] == []


def test_archive_restore_keeps_exam_and_sources_recoverable(tmp_path):
    app = initialize(tmp_path / "data")
    exam = app.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "วิชา"))
    assert [item.id for item in app.exams.list_exams()] == [exam.id]
    app.exams.archive(exam.id)
    assert app.exams.list_exams() == []
    assert [item.id for item in app.exams.list_archived()] == [exam.id]
    app.exams.restore(exam.id)
    assert [item.id for item in app.exams.list_exams()] == [exam.id]
