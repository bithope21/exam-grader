"""Regression tests for ExamStore.purge() and foreign key constraints."""

import json
import sqlite3
from contextlib import closing

from PySide6.QtGui import QImage

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.imports import ImportService
from exam_grader.workflow import Workflow


def test_purge_with_full_relations_and_detection_fk(tmp_path):
    answers_json = json.dumps(["A"])
    """Verify purge() succeeds with PRAGMA foreign_keys=ON when answer_keys has detection_id."""
    app = initialize(tmp_path / "data")
    exam = app.exams.create(ExamDetails("สอบปลายภาค", "2569", "ม.4", "1", "วิทย์", 10))
    service = ImportService(app.exams.path)

    key_path = tmp_path / "key.png"
    image = QImage(30, 40, QImage.Format.Format_RGB32)
    image.fill(0xFFFDFFFF)
    image.save(str(key_path))
    key = service.import_file(exam.id, key_path, "key")

    std_path = tmp_path / "student.png"
    std_img = QImage(30, 40, QImage.Format.Format_RGB32)
    std_img.fill(0xFF000000)
    std_img.save(str(std_path))
    std = service.import_file(exam.id, std_path, "student")

    with closing(sqlite3.connect(app.exams.path)) as conn, conn:
        conn.execute(
            "INSERT INTO detections (id, source_id, payload, created_at) VALUES ('det-key', ?, '{}', '2026-09-11T00:00:00')",
            (key["id"],),
        )
        conn.execute(
            "INSERT INTO detections (id, source_id, payload, created_at) VALUES ('det-std', ?, '{}', '2026-09-11T00:00:00')",
            (std["id"],),
        )
        conn.execute(
            "INSERT INTO answer_keys (id, exam_id, source_id, answers, origin, detection_id, created_at) VALUES ('ak-1', ?, ?, ?, 'scan', 'det-key', '2026-09-11T00:00:00')",
            (exam.id, key["id"], answers_json),
        )
        conn.execute(
            "INSERT INTO reviews (id, source_id, key_id, detection_id, student_number, answers, origin, created_at) VALUES ('rev-1', ?, 'ak-1', 'det-std', '1', ?, 'teacher', '2026-09-11T00:00:00')",
            (std["id"], answers_json),
        )
        conn.execute(
            "INSERT INTO answer_overrides (id, source_id, key_id, detection_id, question, answer, created_at) VALUES ('ao-1', ?, 'ak-1', 'det-std', 1, 'B', '2026-09-11T00:00:00')",
            (std["id"],),
        )
        conn.execute(
            "INSERT INTO identities (id, source_id, student_number, detection_id, origin, created_at) VALUES ('id-1', ?, '1', 'det-std', 'manual', '2026-09-11T00:00:00')",
            (std["id"],),
        )
        conn.execute(
            "INSERT INTO import_failures (id, exam_id, path, purpose, error, created_at) VALUES ('if-1', ?, '/bad/path.png', 'student', 'corrupt', '2026-09-11T00:00:00')",
            (exam.id,),
        )
        conn.execute(
            "INSERT INTO export_runs (id, exam_id, path, run_id, snapshot_fingerprint, created_at) VALUES ('er-1', ?, '/export/dir', 'run-1', 'fp-1', '2026-09-11T00:00:00')",
            (exam.id,),
        )
        conn.execute(
            "INSERT INTO attendance (exam_id, student_number, status, updated_at) VALUES (?, 1, 'absent', '2026-09-11T00:00:00')",
            (exam.id,),
        )
        conn.execute(
            "INSERT INTO skipped_numbers (exam_id, student_number) VALUES (?, 99)", (exam.id,)
        )

    app.exams.archive(exam.id)
    app.exams.purge(exam.id)

    assert not any(e.id == exam.id for e in app.exams.list_exams())
    assert not any(e.id == exam.id for e in app.exams.list_archived())


def test_purge_preserves_shared_source_files(tmp_path):
    """Verify that if two exams share the same image (same sha256), purging one does not delete the file."""
    app = initialize(tmp_path / "data")
    exam1 = app.exams.create(ExamDetails("สอบ 1", "2569", "ม.1", "1", "วิทย์", 10))
    exam2 = app.exams.create(ExamDetails("สอบ 2", "2569", "ม.1", "2", "วิทย์", 10))
    service = ImportService(app.exams.path)

    shared_img_path = tmp_path / "shared.png"
    img = QImage(30, 40, QImage.Format.Format_RGB32)
    img.fill(0xFFAABBCC)
    img.save(str(shared_img_path))

    s1 = service.import_file(exam1.id, shared_img_path, "student")
    service.import_file(exam2.id, shared_img_path, "student")

    stored_file = (app.exams.path.parent / s1["relative_path"]).resolve()
    assert stored_file.exists()

    app.exams.purge(exam1.id)
    assert stored_file.exists()

    app.exams.purge(exam2.id)
    assert not stored_file.exists()


def test_purge_cross_exam_isolation(tmp_path):
    """Verify purging exam A does not affect exam B's sources, keys, or reviews."""
    app = initialize(tmp_path / "data")
    exam_a = app.exams.create(ExamDetails("สอบ A", "2569", "ม.1", "1", "วิทย์", 10))
    exam_b = app.exams.create(ExamDetails("สอบ B", "2569", "ม.1", "2", "วิทย์", 10))
    service = ImportService(app.exams.path)

    p_a = tmp_path / "a.png"
    img_a = QImage(30, 40, QImage.Format.Format_RGB32)
    img_a.fill(0xFF112233)
    img_a.save(str(p_a))

    p_b = tmp_path / "b.png"
    img_b = QImage(30, 40, QImage.Format.Format_RGB32)
    img_b.fill(0xFF445566)
    img_b.save(str(p_b))

    s_a = service.import_file(exam_a.id, p_a, "key")
    s_b = service.import_file(exam_b.id, p_b, "key")

    flow = Workflow(app.exams.path)
    flow.approve_key(exam_a.id, ["A"] * 10, s_a["id"])
    flow.approve_key(exam_b.id, ["C"] * 10, s_b["id"])

    app.exams.purge(exam_a.id)

    # Exam B must be completely intact
    assert any(e.id == exam_b.id for e in app.exams.list_exams())
    summary_b = app.exams.summary(exam_b.id)
    assert summary_b["sources"] == 1
    # Check that exam B's key still exists
    with closing(sqlite3.connect(app.exams.path)) as conn:
        key_row = conn.execute(
            "SELECT id, answers FROM answer_keys WHERE exam_id=?", (exam_b.id,)
        ).fetchone()
        assert key_row is not None
        assert json.loads(key_row[1]) == ["C"] * 10
