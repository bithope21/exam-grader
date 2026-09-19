"""Immutable content-addressed inputs. Qt is used only for local image decoding."""

import hashlib
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PySide6.QtGui import QImage


class ImportService:
    def __init__(self, database: Path):
        self.database = database
        self.root = database.parent

    def list_sources(self, exam_id: str, room_id: str | None = None) -> list[dict]:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            query = "SELECT * FROM sources WHERE exam_id=? AND archived_at IS NULL"
            params: list[object] = [exam_id]
            if room_id is not None:
                query += " AND (purpose='key' OR room_id=?)"
                params.append(room_id)
            query += " ORDER BY created_at, id"
            return [
                dict(row)
                for row in connection.execute(query, params)
            ]

    def list_archived_sources(
        self, exam_id: str, purpose: str | None = None, room_id: str | None = None
    ) -> list[dict]:
        """Return recoverable source tombstones for the archive UI."""
        query = "SELECT * FROM sources WHERE exam_id=? AND archived_at IS NOT NULL"
        params: list[object] = [exam_id]
        if purpose is not None:
            query += " AND purpose=?"
            params.append(purpose)
        if room_id is not None:
            query += " AND (purpose='key' OR room_id=?)"
            params.append(room_id)
        query += " ORDER BY archived_at DESC, id"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(query, params)]

    def archive_source(self, source_id: str) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            changed = connection.execute(
                "UPDATE sources SET archived_at=? WHERE id=? AND archived_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), source_id),
            ).rowcount
            if not changed:
                raise ValueError("ไม่พบภาพที่ยังใช้งานอยู่")

    def restore_source(self, source_id: str) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            changed = connection.execute(
                "UPDATE sources SET archived_at=NULL WHERE id=? AND archived_at IS NOT NULL",
                (source_id,),
            ).rowcount
            if not changed:
                raise ValueError("ไม่พบภาพที่ถูกเก็บถาวร")

    def list_failures(self, exam_id: str, room_id: str | None = None) -> list[dict]:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            query = "SELECT * FROM import_failures WHERE exam_id=? AND resolved_at IS NULL"
            params: list[object] = [exam_id]
            if room_id is not None:
                query += " AND (purpose='key' OR room_id=?)"
                params.append(room_id)
            query += " ORDER BY created_at, id"
            return [
                dict(row)
                for row in connection.execute(query, params)
            ]

    def record_failure(
        self, exam_id: str, source: Path, purpose: str, error: str, room_id: str | None = None
    ) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                "INSERT INTO import_failures (id,exam_id,path,purpose,error,created_at,resolved_at,room_id) "
                "VALUES (?,?,?,?,?,?,NULL,?)",
                (
                    str(uuid4()),
                    exam_id,
                    str(source.resolve()),
                    purpose,
                    error,
                    datetime.now(timezone.utc).isoformat(),
                    room_id,
                ),
            )

    def clear_failure(
        self, exam_id: str, source: Path, purpose: str, room_id: str | None = None
    ) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                "UPDATE import_failures SET resolved_at=? WHERE exam_id=? AND path=? "
                "AND purpose=? AND (room_id IS ? OR room_id=?) AND resolved_at IS NULL",
                (
                    datetime.now(timezone.utc).isoformat(),
                    exam_id,
                    str(source.resolve()),
                    purpose,
                    room_id,
                    room_id,
                ),
            )

    def original_path(self, record: dict) -> Path:
        path = (self.root / record["relative_path"]).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("ตำแหน่งภาพไม่ถูกต้อง")
        return path

    def verified_bytes(self, record: dict) -> bytes:
        data = self.original_path(record).read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("ต้นฉบับที่เก็บไว้ถูกเปลี่ยนแปลง กรุณานำเข้าจากต้นฉบับใหม่")
        return data

    def import_file(
        self, exam_id: str, source: Path, purpose: str = "student", room_id: str | None = None
    ) -> dict:
        if purpose not in {"student", "key"}:
            raise ValueError("ประเภทภาพไม่ถูกต้อง")
        with closing(sqlite3.connect(self.database)) as connection:
            if not connection.execute("SELECT 1 FROM exams WHERE id=?", (exam_id,)).fetchone():
                raise ValueError("ไม่พบข้อสอบ")
            if purpose == "student":
                if room_id is None:
                    room_id = connection.execute(
                        "SELECT id FROM exam_rooms WHERE exam_id=? ORDER BY sort_order,id LIMIT 1",
                        (exam_id,),
                    ).fetchone()[0]
                elif not connection.execute(
                    "SELECT 1 FROM exam_rooms WHERE id=? AND exam_id=?", (room_id, exam_id)
                ).fetchone():
                    raise ValueError("ห้องไม่ตรงกับข้อสอบ")
            else:
                room_id = None
        if source.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            raise ValueError("รุ่นนี้รับเฉพาะ JPEG และ PNG")
        data = source.read_bytes()
        image = QImage.fromData(data)
        if image.isNull():
            raise ValueError("อ่านภาพไม่ได้ หรือไฟล์เสีย")
        digest = hashlib.sha256(data).hexdigest()
        # No user-controlled name is used as an output path.
        relative = Path("input/originals") / digest[:2] / digest
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id,purpose,room_id,archived_at FROM sources WHERE exam_id=? AND sha256=?",
                (exam_id, digest),
            ).fetchone()
            if existing and existing[1] != purpose:
                raise ValueError("ภาพนี้ถูกนำเข้าเป็นอีกประเภทแล้ว กรุณาเลือกภาพอื่น")
            if existing and purpose == "student" and existing[2] != room_id:
                raise ValueError("ภาพนี้ถูกนำเข้าในห้องอื่นแล้ว กรุณาเลือกภาพอื่น")
            destination_is_valid = (
                destination.exists()
                and hashlib.sha256(destination.read_bytes()).hexdigest() == digest
            )
            if not destination_is_valid:
                if destination.exists():
                    quarantine = self.root / "input" / "quarantine" / f"{digest}-{uuid4()}"
                    quarantine.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(destination, quarantine)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=destination.parent, delete=False
                    ) as handle:
                        temporary = Path(handle.name)
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, destination)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
            # If DB commit fails the content blob is harmless and reused on retry.
            connection.execute(
                "INSERT OR IGNORE INTO sources "
                "(id,exam_id,sha256,original_name,relative_path,width,height,created_at,purpose,archived_at,room_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,NULL,?)",
                (
                    str(uuid4()),
                    exam_id,
                    digest,
                    source.name,
                    relative.as_posix(),
                    image.width(),
                    image.height(),
                    datetime.now(timezone.utc).isoformat(),
                    purpose,
                    room_id,
                ),
            )
            if existing and existing[2] is not None:
                connection.execute("UPDATE sources SET archived_at=NULL WHERE id=?", (existing[0],))
            connection.row_factory = sqlite3.Row
            return dict(
                connection.execute(
                    "SELECT * FROM sources WHERE exam_id=? AND sha256=?", (exam_id, digest)
                ).fetchone()
            )
