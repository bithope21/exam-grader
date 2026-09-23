import hashlib

import pytest
from PySide6.QtGui import QImage

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.imports import ImportService


def setup_exam(tmp_path):
    app = initialize(tmp_path / "data")
    exam = app.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "วิชา"))
    source = tmp_path / "ภาพ.png"
    image = QImage(30, 40, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(source))
    return app, exam, source


def test_import_is_immutable_idempotent_and_survives_restart(tmp_path):
    app, exam, source = setup_exam(tmp_path)
    before = source.read_bytes()
    service = ImportService(app.exams.path)
    first = service.import_file(exam.id, source)
    second = service.import_file(exam.id, source)
    assert first["id"] == second["id"]
    assert source.read_bytes() == before
    source.unlink()
    restarted = ImportService(initialize(app.data_dir).exams.path)
    records = restarted.list_sources(exam.id)
    assert len(records) == 1
    assert restarted.original_path(records[0]).read_bytes() == before
    assert records[0]["sha256"] == hashlib.sha256(before).hexdigest()


def test_extensionless_stored_original_can_be_reprocessed(tmp_path):
    app, exam, source = setup_exam(tmp_path)
    service = ImportService(app.exams.path)
    first = service.import_file(exam.id, source)

    stored_original = service.original_path(first)
    assert stored_original.suffix == ""
    replay = service.import_file(exam.id, stored_original)

    assert replay["id"] == first["id"]
    assert service.verified_bytes(replay) == source.read_bytes()


def test_invalid_file_does_not_create_record(tmp_path):
    app, exam, source = setup_exam(tmp_path)
    source.write_bytes(b"corrupt")
    service = ImportService(app.exams.path)
    with pytest.raises(ValueError):
        service.import_file(exam.id, source)
    assert service.list_sources(exam.id) == []


def test_unknown_exam_rejected_and_tampering_detected(tmp_path):
    app, exam, source = setup_exam(tmp_path)
    service = ImportService(app.exams.path)
    with pytest.raises(ValueError):
        service.import_file("missing", source)
    record = service.import_file(exam.id, source)
    original = source.read_bytes()
    service.original_path(record).write_bytes(b"tamper")
    with pytest.raises(ValueError, match="เปลี่ยน"):
        service.verified_bytes(record)
    source.write_bytes(original)
    repaired = service.import_file(exam.id, source)
    assert service.verified_bytes(repaired) == original
    assert list((app.data_dir / "input" / "quarantine").glob("*"))
