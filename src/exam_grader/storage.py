"""SQLite adapter. No recognition or scoring policy lives here."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from exam_grader.domain import Exam, ExamDetails


class ExamStore:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 12:
                raise RuntimeError("ฐานข้อมูลเป็นรุ่นใหม่กว่าแอปนี้ กรุณาใช้แอปรุ่นใหม่")
            if version == 0:
                connection.execute("""
                    CREATE TABLE exams (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        academic_year TEXT NOT NULL,
                        grade TEXT NOT NULL,
                        room TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                connection.execute("PRAGMA user_version = 1")
            if version < 2:
                connection.execute("""CREATE TABLE sources (
                    id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id),
                    sha256 TEXT NOT NULL, original_name TEXT NOT NULL,
                    relative_path TEXT NOT NULL, width INTEGER NOT NULL,
                    height INTEGER NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(exam_id, sha256))""")
                connection.execute("PRAGMA user_version = 2")
            if version < 3:
                connection.execute(
                    "ALTER TABLE sources ADD COLUMN purpose TEXT NOT NULL DEFAULT 'student'"
                )
                connection.execute("""CREATE TABLE answer_keys (
                    id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id),
                    source_id TEXT NOT NULL REFERENCES sources(id), answers TEXT NOT NULL,
                    created_at TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE reviews (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                    key_id TEXT NOT NULL REFERENCES answer_keys(id), student_number TEXT NOT NULL,
                    answers TEXT NOT NULL, created_at TEXT NOT NULL)""")
                connection.execute("PRAGMA user_version = 3")
            if version < 4:
                connection.execute("""CREATE TABLE detections (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                    payload TEXT NOT NULL, created_at TEXT NOT NULL)""")
                connection.execute("PRAGMA user_version = 4")
            if version < 5:
                connection.execute("ALTER TABLE reviews ADD COLUMN detection_id TEXT REFERENCES detections(id)")
                connection.execute("PRAGMA user_version = 5")
            if version < 6:
                connection.execute(
                    "ALTER TABLE exams ADD COLUMN question_count INTEGER NOT NULL DEFAULT 60"
                )
                connection.execute("PRAGMA user_version = 6")
            if version < 7:
                connection.execute("""CREATE TABLE import_failures (
                    id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id),
                    path TEXT NOT NULL, purpose TEXT NOT NULL, error TEXT NOT NULL,
                    created_at TEXT NOT NULL, resolved_at TEXT
                )""")
                connection.execute("PRAGMA user_version = 7")
            if version < 8:
                connection.execute("ALTER TABLE exams ADD COLUMN expected_number_max INTEGER")
                connection.execute("ALTER TABLE exams ADD COLUMN archived_at TEXT")
                connection.execute("ALTER TABLE exams ADD COLUMN output_root TEXT")
                connection.execute("PRAGMA user_version = 8")
            if version < 9:
                connection.execute("""CREATE TABLE export_runs (
                    id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id),
                    path TEXT NOT NULL, run_id TEXT NOT NULL, snapshot_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'published'
                )""")
                connection.execute("PRAGMA user_version = 9")
            if version < 10:
                connection.execute("ALTER TABLE answer_keys ADD COLUMN origin TEXT NOT NULL DEFAULT 'teacher'")
                connection.execute("ALTER TABLE answer_keys ADD COLUMN detection_id TEXT REFERENCES detections(id)")
                connection.execute("ALTER TABLE reviews ADD COLUMN origin TEXT NOT NULL DEFAULT 'teacher'")
                connection.execute("""CREATE TABLE identities (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                    student_number TEXT NOT NULL, detection_id TEXT REFERENCES detections(id),
                    origin TEXT NOT NULL, created_at TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE answer_overrides (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                    key_id TEXT NOT NULL REFERENCES answer_keys(id), detection_id TEXT REFERENCES detections(id),
                    question INTEGER NOT NULL, answer TEXT NOT NULL, created_at TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE attendance (
                    exam_id TEXT NOT NULL REFERENCES exams(id), student_number INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','absent','excused')),
                    updated_at TEXT NOT NULL, PRIMARY KEY(exam_id, student_number))""")
                connection.execute("PRAGMA user_version = 10")
            if version < 11:
                connection.execute("CREATE TABLE skipped_numbers (exam_id TEXT NOT NULL REFERENCES exams(id), student_number INTEGER NOT NULL, PRIMARY KEY(exam_id,student_number))")
                connection.execute("PRAGMA user_version = 11")
            if version < 12:
                connection.execute("ALTER TABLE sources ADD COLUMN archived_at TEXT")
                connection.execute("PRAGMA user_version = 12")

    def create(self, details: ExamDetails) -> Exam:
        exam = Exam(str(uuid4()), details, datetime.now(timezone.utc).isoformat())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO exams "
                "(id, name, academic_year, grade, room, subject, question_count, expected_number_max, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    exam.id,
                    details.name,
                    details.academic_year,
                    details.grade,
                    details.room,
                    details.subject,
                    details.question_count,
                    details.expected_number_max,
                    exam.created_at,
                ),
            )
        return exam

    def list_exams(self) -> list[Exam]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT id, name, academic_year, grade, room, subject, question_count, "
                "expected_number_max, created_at FROM exams WHERE archived_at IS NULL "
                "ORDER BY created_at DESC, id"
            ).fetchall()
        return [Exam(row[0], ExamDetails(*row[1:8]), row[8]) for row in rows]

    def list_archived(self) -> list[Exam]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT id, name, academic_year, grade, room, subject, question_count, "
                "expected_number_max, created_at FROM exams WHERE archived_at IS NOT NULL "
                "ORDER BY archived_at DESC, id"
            ).fetchall()
        return [Exam(row[0], ExamDetails(*row[1:8]), row[8]) for row in rows]

    def set_expected_number_max(self, exam_id: str, maximum: int | None) -> None:
        if maximum is not None and not 1 <= maximum <= 9999:
            raise ValueError("เลขที่คาดหวังต้องอยู่ระหว่าง 1 ถึง 9999")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE exams SET expected_number_max=? WHERE id=?", (maximum, exam_id))

    def set_output_root(self, exam_id: str, path: Path | None) -> None:
        value = str(path.expanduser().resolve()) if path is not None else None
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE exams SET output_root=? WHERE id=?", (value, exam_id))

    def output_root(self, exam_id: str) -> Path | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT output_root FROM exams WHERE id=?", (exam_id,)).fetchone()
        return Path(row[0]) if row and row[0] else None

    def archive(self, exam_id: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            changed = connection.execute(
                "UPDATE exams SET archived_at=? WHERE id=? AND archived_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), exam_id),
            ).rowcount
            if not changed:
                raise ValueError("ไม่พบข้อสอบที่ยังใช้งานอยู่")

    def restore(self, exam_id: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            changed = connection.execute(
                "UPDATE exams SET archived_at=NULL WHERE id=? AND archived_at IS NOT NULL", (exam_id,)
            ).rowcount
            if not changed:
                raise ValueError("ไม่พบข้อสอบที่ถูกเก็บถาวร")

    def export_runs(self, exam_id: str) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(
                "SELECT * FROM export_runs WHERE exam_id=? ORDER BY created_at DESC, id", (exam_id,)
            )]

    def summary(self, exam_id: str) -> dict[str, int]:
        with closing(sqlite3.connect(self.path)) as connection:
            return {
                "sources": int(connection.execute("SELECT count(*) FROM sources WHERE exam_id=? AND archived_at IS NULL", (exam_id,)).fetchone()[0]),
                "reviews": int(connection.execute("SELECT count(*) FROM reviews WHERE source_id IN (SELECT id FROM sources WHERE exam_id=? AND archived_at IS NULL)", (exam_id,)).fetchone()[0]),
                "exports": int(connection.execute("SELECT count(*) FROM export_runs WHERE exam_id=?", (exam_id,)).fetchone()[0]),
            }
