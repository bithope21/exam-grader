import sqlite3
import subprocess
import sys

import pytest

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails


def test_exam_survives_restart_and_names_are_not_identity(tmp_path):
    directory = tmp_path / "ข้อสอบ ห้อง 1"
    app = initialize(directory)
    details = ExamDetails(" กลางภาค ", "2569", "ม.4", "1", "คณิตศาสตร์")
    first = app.exams.create(details)
    second = app.exams.create(details)
    assert first.id != second.id
    reopened = initialize(directory).exams.list_exams()
    assert {exam.id for exam in reopened} == {first.id, second.id}
    assert all(exam.details.name == "กลางภาค" for exam in reopened)


def test_exam_question_count_is_persisted_and_bounded(tmp_path):
    app = initialize(tmp_path)
    app.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "คณิต", 30))
    assert initialize(tmp_path).exams.list_exams()[0].details.question_count == 30
    for invalid in (0, 61):
        with pytest.raises(ValueError):
            ExamDetails("สอบ", "2569", "ม.4", "1", "คณิต", invalid)


def test_invalid_details_do_not_enter_storage(tmp_path):
    app = initialize(tmp_path)
    with pytest.raises(ValueError):
        app.exams.create(ExamDetails(" ", "2569", "ม.4", "1", "คณิต"))
    assert app.exams.list_exams() == []


def test_future_schema_is_rejected_without_downgrade(tmp_path):
    app = initialize(tmp_path)
    with sqlite3.connect(app.exams.path) as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError):
        initialize(tmp_path)
    with sqlite3.connect(app.exams.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 99


def test_failed_migration_rolls_back(tmp_path):
    database = tmp_path / "exam-grader.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE exams (legacy TEXT)")
        connection.execute("INSERT INTO exams VALUES ('preserve')")
    with pytest.raises(sqlite3.Error):
        initialize(tmp_path)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT legacy FROM exams").fetchone()[0] == "preserve"


def test_self_check_reports_storage_failure(tmp_path):
    blocked = tmp_path / "file-not-directory"
    blocked.write_text("preserve")
    result = subprocess.run(
        [sys.executable, "-m", "exam_grader", "--self-check", "--data-dir", str(blocked)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Startup failed" in result.stderr
    assert blocked.read_text() == "preserve"
