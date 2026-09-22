from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import quote

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.calibration_ui import CalibrationDialog
from exam_grader.domain import ExamDetails
from exam_grader.exam_ui import BatchWorker, ExamDialog, MobileUploadDialog, qr_pixmap
from exam_grader.imports import ImportService
from exam_grader.local_upload import UploadLimits, UploadSession


def _image_bytes(tmp_path: Path, suffix: str = ".png") -> bytes:
    path = tmp_path / f"source{suffix}"
    image = QImage(24, 24, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(path))
    return path.read_bytes()


def _post(session: UploadSession, data: bytes, filename: str, content_type: str = "image/png"):
    request = urllib.request.Request(
        session.url,
        data=data,
        headers={
            "Content-Type": content_type,
            "X-File-Name": quote(filename),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_session_accepts_streamed_image_and_reuses_existing_import(tmp_path):
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "วิชา"))
    session = UploadSession(
        "student",
        exam.id,
        limits=UploadLimits(max_file_bytes=1024 * 1024, max_session_bytes=2 * 1024 * 1024),
    )
    session.start(host="127.0.0.1")
    try:
        status, payload = _post(session, _image_bytes(tmp_path), "../ภาพนักเรียน.png")
        assert status == 201
        assert payload["ok"] is True
        staged_paths = list(session.staging_dir.rglob("*.png"))
        assert len(staged_paths) == 1
        staged = staged_paths[0]
        assert staged.exists()
        assert staged.parent.parent == session.staging_dir
        imported = ImportService(application.exams.path).import_file(exam.id, staged, "student")
        assert imported["original_name"] == "ภาพนักเรียน.png"
        assert ImportService(application.exams.path).verified_bytes(imported) == _image_bytes(tmp_path)
    finally:
        session.cleanup()


def test_uploaded_file_enters_existing_batch_worker(tmp_path):
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "วิชา"))
    session = UploadSession("key", exam.id, limits=UploadLimits(max_file_bytes=1024 * 1024))
    session.start(host="127.0.0.1")
    try:
        assert _post(session, _image_bytes(tmp_path), "เฉลย.png")[0] == 201
        staged = next(session.staging_dir.rglob("*.png"))
        worker = BatchWorker(application.exams.path, exam.id, [staged], "key")
        worker.start()
        assert worker.wait(15000)
        sources = ImportService(application.exams.path).list_sources(exam.id)
        assert len(sources) == 1
        assert sources[0]["purpose"] == "key"
        assert sources[0]["original_name"] == "เฉลย.png"
    finally:
        session.cleanup()


def test_session_supports_multiple_files_and_enforces_file_and_batch_limits(tmp_path):
    session = UploadSession(
        "student",
        "exam-id",
        limits=UploadLimits(max_file_bytes=100, max_session_bytes=150, max_files_per_session=2),
    )
    session.start(host="127.0.0.1")
    try:
        payload = b"\x89PNG\r\n\x1a\n" + b"x" * 42
        assert _post(session, payload, "one.png")[0] == 201
        assert _post(session, payload, "two.png")[0] == 201
        status, response = _post(session, payload, "three.png")
        assert status == 413
        assert "ครบจำนวน" in response["error"]
        assert session.counts()[0] == 2
    finally:
        session.cleanup()


def test_session_rejects_invalid_file_and_expired_token(tmp_path):
    session = UploadSession(
        "key",
        "exam-id",
        limits=UploadLimits(max_file_bytes=100, max_session_bytes=100, session_ttl_seconds=60),
    )
    session.start(host="127.0.0.1")
    try:
        status, response = _post(session, b"not-an-image", "answer.jpg", "image/jpeg")
        assert status == 415
        assert "ภาพ" in response["error"]
        assert session.counts() == (0, 0)
        session._expires_at = time.time() - 1
        request = urllib.request.Request(session.url)
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        assert error.value.code == 410
    finally:
        session.cleanup()


def test_template_session_is_single_image_and_uses_template_label(tmp_path):
    session = UploadSession("template", "template-calibration")
    session.start(host="127.0.0.1")
    try:
        with urllib.request.urlopen(session.url, timeout=5) as response:
            page = response.read().decode("utf-8")
        assert "ภาพแม่แบบ" in page
        assert " multiple>" not in page
        assert session.max_files == 1
    finally:
        session.cleanup()


def test_template_upload_enters_calibration_discovery_with_received_bytes(tmp_path):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    dialog = CalibrationDialog(application)
    session = UploadSession("template", "template-calibration")
    staged = tmp_path / "template.png"
    staged.write_bytes(_image_bytes(tmp_path))
    dialog.mobile_upload_session = session
    dialog._start_discovery_from_bytes = Mock()
    session.files_received.connect(dialog._on_mobile_upload_files)
    try:
        session.accept(staged, staged.stat().st_size)
        dialog._start_discovery_from_bytes.assert_called_once_with(_image_bytes(tmp_path))
        assert dialog.mobile_upload_session is None
    finally:
        session.cleanup()
        dialog.close()


def test_upload_page_and_desktop_qr_controls_are_local_and_mobile_ready(tmp_path):
    session = UploadSession("student", "exam-id")
    key_session = UploadSession("key", "exam-id")
    session.start(host="127.0.0.1")
    key_session.start(host="127.0.0.1")
    try:
        with urllib.request.urlopen(session.url, timeout=5) as response:
            page = response.read().decode("utf-8")
        assert "เครือข่ายเดียวกัน" in page
        assert "capture=" not in page
        assert " multiple>" in page
        assert session.max_files == 200
        assert "XMLHttpRequest" in page
        assert "qrcode" not in page.lower()
        with urllib.request.urlopen(key_session.url, timeout=5) as response:
            key_page = response.read().decode("utf-8")
        assert " multiple>" not in key_page
        assert key_session.max_files == 1
    finally:
        session.cleanup()
        key_session.cleanup()

    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "วิชา"))
    dialog = ExamDialog(application, exam)
    try:
        assert dialog.key_mobile_button.accessibleName() == "เพิ่มเฉลยผ่านมือถือ"
        assert dialog.student_mobile_button.accessibleName() == "เพิ่มกระดาษคำตอบผ่านมือถือ"
        assert not qr_pixmap("http://127.0.0.1:12345/upload/test").isNull()
        student_session = UploadSession("student", exam.id)
        student_dialog = MobileUploadDialog(student_session, dialog)
        assert student_dialog.windowTitle() == "เพิ่มกระดาษคำตอบนักเรียนผ่านมือถือ"
        assert "กระดาษคำตอบนักเรียน" in student_dialog.status_label.text()
        student_dialog.close()
        student_session.cleanup()
        template_session = UploadSession("template", exam.id)
        template_dialog = MobileUploadDialog(template_session, dialog)
        assert template_dialog.windowTitle() == "เพิ่มภาพแม่แบบผ่านมือถือ"
        template_dialog.close()
        template_session.cleanup()
    finally:
        dialog.close()


def test_key_mobile_session_closes_after_first_image_enters_import_pipeline(tmp_path):
    QApplication.instance() or QApplication([])
    application = initialize(tmp_path / "data")
    exam = application.exams.create(ExamDetails("สอบ", "2569", "ม.4", "1", "วิชา"))
    dialog = ExamDialog(application, exam)
    session = UploadSession("key", exam.id)
    session.start(host="127.0.0.1")
    staged = tmp_path / "staged.png"
    staged.write_bytes(_image_bytes(tmp_path))
    mobile_dialog = Mock()
    dialog.mobile_upload_session = session
    dialog.mobile_upload_purpose = "key"
    dialog.mobile_upload_dialog = mobile_dialog
    dialog.start_import = Mock()
    session.files_received.connect(dialog._on_mobile_upload_files)
    try:
        session.accept(staged, staged.stat().st_size)
        dialog.start_import.assert_called_once_with([staged], "key")
        mobile_dialog.close.assert_called_once_with()
    finally:
        session.cleanup()
        dialog.close()
