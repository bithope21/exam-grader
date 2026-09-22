import json
import sqlite3
import unicodedata
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from exam_grader.domain import Exam, ExamDetails, ExamRoom
from exam_grader.template_manager import TemplateDefinition, default_1_template_definition


class ExamStore:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size > 0:
            with closing(sqlite3.connect(self.path)) as check_conn:
                v = check_conn.execute("PRAGMA user_version").fetchone()[0]
                if 0 < v < 16:
                    backup_path = self.path.with_name(f"{self.path.name}.v{v}.bak")
                    if not backup_path.exists():
                        with closing(sqlite3.connect(backup_path)) as bck_conn:
                            check_conn.backup(bck_conn)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 16:
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
                connection.execute(
                    "ALTER TABLE reviews ADD COLUMN detection_id TEXT REFERENCES detections(id)"
                )
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
                connection.execute(
                    "ALTER TABLE answer_keys ADD COLUMN origin TEXT NOT NULL DEFAULT 'teacher'"
                )
                connection.execute(
                    "ALTER TABLE answer_keys ADD COLUMN detection_id TEXT REFERENCES detections(id)"
                )
                connection.execute(
                    "ALTER TABLE reviews ADD COLUMN origin TEXT NOT NULL DEFAULT 'teacher'"
                )
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
                connection.execute(
                    "CREATE TABLE skipped_numbers (exam_id TEXT NOT NULL REFERENCES exams(id), student_number INTEGER NOT NULL, PRIMARY KEY(exam_id,student_number))"
                )
                connection.execute("PRAGMA user_version = 11")
            if version < 12:
                connection.execute("ALTER TABLE sources ADD COLUMN archived_at TEXT")
                connection.execute("PRAGMA user_version = 12")
            if version < 13:
                connection.execute("""CREATE TABLE templates (
                    id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('builtin','custom')),
                    definition TEXT NOT NULL,
                    reference_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    PRIMARY KEY (id, version)
                )""")
                connection.execute(
                    "ALTER TABLE exams ADD COLUMN template_id TEXT NOT NULL DEFAULT 'default-1'"
                )
                connection.execute(
                    "ALTER TABLE exams ADD COLUMN template_version INTEGER NOT NULL DEFAULT 1"
                )
                connection.execute(
                    "UPDATE exams SET template_id='default-1', template_version=1 WHERE template_id IS NULL"
                )
                d1 = default_1_template_definition()
                connection.execute(
                    "INSERT OR IGNORE INTO templates (id, version, name, kind, definition, reference_sha256, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        d1.template_id,
                        d1.version,
                        d1.name,
                        d1.kind,
                        json.dumps(d1.to_dict(), ensure_ascii=False),
                        d1.reference_sha256,
                        d1.created_at,
                        d1.updated_at,
                    ),
                )
                connection.execute("PRAGMA user_version = 13")
            if version < 14:
                connection.execute("""CREATE TABLE partial_reviews (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(id),
                    key_id TEXT NOT NULL REFERENCES answer_keys(id),
                    detection_id TEXT REFERENCES detections(id),
                    student_number TEXT NOT NULL,
                    identity_confirmed INTEGER NOT NULL CHECK(identity_confirmed IN (0,1)),
                    identity_origin TEXT NOT NULL,
                    answers TEXT NOT NULL,
                    answer_provenance TEXT NOT NULL,
                    review_issues TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )""")
                connection.execute(
                    "CREATE INDEX partial_reviews_source_latest ON partial_reviews(source_id, created_at)"
                )
                connection.execute("PRAGMA user_version = 14")
            if version < 15:
                connection.execute(
                    """CREATE TABLE exam_rooms (
                        id TEXT PRIMARY KEY,
                        exam_id TEXT NOT NULL REFERENCES exams(id),
                        room_label TEXT NOT NULL,
                        sort_order INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(exam_id, room_label)
                    )"""
                )
                now = datetime.now(timezone.utc).isoformat()
                for exam_row in connection.execute("SELECT id, room FROM exams").fetchall():
                    room_label = (exam_row[1] or "").strip() or "ห้อง 1"
                    connection.execute(
                        "INSERT INTO exam_rooms (id,exam_id,room_label,sort_order,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (str(uuid4()), exam_row[0], room_label, 0, now, now),
                    )
                connection.execute("ALTER TABLE sources ADD COLUMN room_id TEXT REFERENCES exam_rooms(id)")
                connection.execute(
                    "UPDATE sources SET room_id=(SELECT id FROM exam_rooms WHERE exam_id=sources.exam_id ORDER BY sort_order,id LIMIT 1) "
                    "WHERE purpose='student'"
                )
                connection.execute("ALTER TABLE import_failures ADD COLUMN room_id TEXT REFERENCES exam_rooms(id)")
                connection.execute(
                    "UPDATE import_failures SET room_id=(SELECT id FROM exam_rooms WHERE exam_id=import_failures.exam_id ORDER BY sort_order,id LIMIT 1)"
                )
                connection.execute("ALTER TABLE export_runs ADD COLUMN room_id TEXT REFERENCES exam_rooms(id)")
                connection.execute(
                    "UPDATE export_runs SET room_id=(SELECT id FROM exam_rooms WHERE exam_id=export_runs.exam_id ORDER BY sort_order,id LIMIT 1)"
                )

                connection.execute(
                    """CREATE TABLE attendance_v15 (
                        exam_id TEXT NOT NULL REFERENCES exams(id),
                        room_id TEXT NOT NULL REFERENCES exam_rooms(id),
                        student_number INTEGER NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('pending','absent','excused')),
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(room_id, student_number)
                    )"""
                )
                connection.execute(
                    "INSERT INTO attendance_v15 (exam_id,room_id,student_number,status,updated_at) "
                    "SELECT a.exam_id,r.id,a.student_number,a.status,a.updated_at FROM attendance a "
                    "JOIN exam_rooms r ON r.exam_id=a.exam_id AND r.sort_order=0"
                )
                connection.execute("DROP TABLE attendance")
                connection.execute("ALTER TABLE attendance_v15 RENAME TO attendance")

                connection.execute(
                    """CREATE TABLE skipped_numbers_v15 (
                        exam_id TEXT NOT NULL REFERENCES exams(id),
                        room_id TEXT NOT NULL REFERENCES exam_rooms(id),
                        student_number INTEGER NOT NULL,
                        PRIMARY KEY(room_id, student_number)
                    )"""
                )
                connection.execute(
                    "INSERT INTO skipped_numbers_v15 (exam_id,room_id,student_number) "
                    "SELECT s.exam_id,r.id,s.student_number FROM skipped_numbers s "
                    "JOIN exam_rooms r ON r.exam_id=s.exam_id AND r.sort_order=0"
                )
                connection.execute("DROP TABLE skipped_numbers")
                connection.execute("ALTER TABLE skipped_numbers_v15 RENAME TO skipped_numbers")
                connection.execute("""CREATE TABLE assessment_indicators (
                    id TEXT PRIMARY KEY,
                    exam_id TEXT NOT NULL REFERENCES exams(id),
                    position INTEGER NOT NULL,
                    identifier TEXT NOT NULL,
                    from_question INTEGER NOT NULL,
                    to_question INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exam_id, identifier),
                    UNIQUE(exam_id, position)
                )""")
                connection.execute("PRAGMA user_version = 15")
            if version < 16:
                connection.execute("ALTER TABLE exam_rooms ADD COLUMN expected_number_max INTEGER")
                connection.execute(
                    "UPDATE exam_rooms SET expected_number_max=("
                    "SELECT expected_number_max FROM exams WHERE exams.id=exam_rooms.exam_id) "
                    "WHERE id=(SELECT first_room.id FROM exam_rooms AS first_room "
                    "WHERE first_room.exam_id=exam_rooms.exam_id ORDER BY sort_order,id LIMIT 1)"
                )
                connection.execute("PRAGMA user_version = 16")

    def create(self, details: ExamDetails) -> Exam:
        room_label = details.room.strip() or "ห้อง 1"
        exam = Exam(
            str(uuid4()), replace(details, room=room_label), datetime.now(timezone.utc).isoformat()
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            now = exam.created_at
            connection.execute(
                "INSERT INTO exams "
                "(id, name, academic_year, grade, room, subject, question_count, expected_number_max, template_id, template_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    exam.id,
                    details.name,
                    details.academic_year,
                    details.grade,
                    room_label,
                    details.subject,
                    details.question_count,
                    details.expected_number_max,
                    details.template_id,
                    details.template_version,
                    exam.created_at,
                ),
            )
            connection.execute(
                "INSERT INTO exam_rooms (id,exam_id,room_label,sort_order,created_at,updated_at,expected_number_max) "
                "VALUES (?,?,?,?,?,?,?)",
                (str(uuid4()), exam.id, room_label, 0, now, now, details.expected_number_max),
            )
        return exam

    @staticmethod
    def _room_key(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).strip().split()).casefold()

    def list_rooms(self, exam_id: str) -> list[ExamRoom]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT id,exam_id,room_label,sort_order,created_at,updated_at,expected_number_max FROM exam_rooms "
                "WHERE exam_id=? ORDER BY sort_order,id",
                (exam_id,),
            ).fetchall()
        return [ExamRoom(*row) for row in rows]

    def get_room(self, room_id: str) -> ExamRoom:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT id,exam_id,room_label,sort_order,created_at,updated_at,expected_number_max FROM exam_rooms WHERE id=?",
                (room_id,),
            ).fetchone()
        if row is None:
            raise ValueError("ไม่พบห้องเรียน")
        return ExamRoom(*row)

    def create_room(
        self, exam_id: str, label: str, expected_number_max: int | None = None
    ) -> ExamRoom:
        label = unicodedata.normalize("NFKC", label).strip()
        label = " ".join(label.split())
        if not label:
            raise ValueError("กรุณาระบุชื่อห้องเรียน")
        if len(label) > 200:
            raise ValueError("ชื่อห้องต้องไม่เกิน 200 ตัวอักษร")
        if expected_number_max is not None and not 1 <= expected_number_max <= 9999:
            raise ValueError("เลขที่คาดหวังต้องอยู่ระหว่าง 1 ถึง 9999")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            if not connection.execute("SELECT 1 FROM exams WHERE id=?", (exam_id,)).fetchone():
                raise ValueError("ไม่พบข้อสอบ")
            rows = connection.execute(
                "SELECT room_label FROM exam_rooms WHERE exam_id=?", (exam_id,)
            ).fetchall()
            if any(self._room_key(row[0]) == self._room_key(label) for row in rows):
                raise ValueError("มีห้องชื่อนี้ในข้อสอบแล้ว")
            now = datetime.now(timezone.utc).isoformat()
            room_id = str(uuid4())
            sort_order = connection.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM exam_rooms WHERE exam_id=?",
                (exam_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO exam_rooms (id,exam_id,room_label,sort_order,created_at,updated_at,expected_number_max) "
                "VALUES (?,?,?,?,?,?,?)",
                (room_id, exam_id, label, sort_order, now, now, expected_number_max),
            )
        return self.get_room(room_id)

    def list_exams(self) -> list[Exam]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT id, name, academic_year, grade, room, subject, question_count, "
                "expected_number_max, created_at, template_id, template_version FROM exams WHERE archived_at IS NULL "
                "ORDER BY created_at DESC, id"
            ).fetchall()
        return [
            Exam(
                row[0],
                ExamDetails(
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                    template_id=row[9] or "default-1",
                    template_version=row[10] or 1,
                ),
                row[8],
            )
            for row in rows
        ]

    def list_archived(self) -> list[Exam]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT id, name, academic_year, grade, room, subject, question_count, "
                "expected_number_max, created_at, template_id, template_version FROM exams WHERE archived_at IS NOT NULL "
                "ORDER BY archived_at DESC, id"
            ).fetchall()
        return [
            Exam(
                row[0],
                ExamDetails(
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                    template_id=row[9] or "default-1",
                    template_version=row[10] or 1,
                ),
                row[8],
            )
            for row in rows
        ]

    def set_expected_number_max(self, exam_id: str, maximum: int | None) -> None:
        if maximum is not None and not 1 <= maximum <= 9999:
            raise ValueError("เลขที่คาดหวังต้องอยู่ระหว่าง 1 ถึง 9999")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE exams SET expected_number_max=? WHERE id=?", (maximum, exam_id)
            )
            connection.execute(
                "UPDATE exam_rooms SET expected_number_max=? WHERE id=("
                "SELECT id FROM exam_rooms WHERE exam_id=? ORDER BY sort_order,id LIMIT 1)",
                (maximum, exam_id),
            )

    def set_room_expected_number_max(self, room_id: str, maximum: int | None) -> None:
        if maximum is not None and not 1 <= maximum <= 9999:
            raise ValueError("เลขที่คาดหวังต้องอยู่ระหว่าง 1 ถึง 9999")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            changed = connection.execute(
                "UPDATE exam_rooms SET expected_number_max=?,updated_at=? WHERE id=?",
                (maximum, datetime.now(timezone.utc).isoformat(), room_id),
            ).rowcount
            if not changed:
                raise ValueError("ไม่พบห้องเรียน")

    def get(self, exam_id: str) -> Exam:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT id, name, academic_year, grade, room, subject, question_count, "
                "expected_number_max, created_at, template_id, template_version FROM exams WHERE id=?",
                (exam_id,),
            ).fetchone()
            if not row:
                raise ValueError("ไม่พบข้อสอบ")
            return Exam(
                row[0],
                ExamDetails(
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                    template_id=row[9] or "default-1",
                    template_version=row[10] or 1,
                ),
                row[8],
            )

    def update_exam_template(
        self,
        exam_id: str,
        template_id: str,
        template_version: int = 1,
        question_count: int | None = None,
    ) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            if question_count is not None:
                connection.execute(
                    "UPDATE exams SET template_id=?, template_version=?, question_count=? WHERE id=?",
                    (template_id, template_version, question_count, exam_id),
                )
            else:
                connection.execute(
                    "UPDATE exams SET template_id=?, template_version=? WHERE id=?",
                    (template_id, template_version, exam_id),
                )

    def set_output_root(self, exam_id: str, path: Path | None) -> None:
        value = str(path.expanduser().resolve()) if path is not None else None
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE exams SET output_root=? WHERE id=?", (value, exam_id))

    def output_root(self, exam_id: str) -> Path | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT output_root FROM exams WHERE id=?", (exam_id,)
            ).fetchone()
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
                "UPDATE exams SET archived_at=NULL WHERE id=? AND archived_at IS NOT NULL",
                (exam_id,),
            ).rowcount
            if not changed:
                raise ValueError("ไม่พบข้อสอบที่ถูกเก็บถาวร")

    def purge(self, exam_id: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            sources_to_check = connection.execute(
                "SELECT sha256, relative_path FROM sources WHERE exam_id=?", (exam_id,)
            ).fetchall()
            unique_paths = []
            for row in sources_to_check:
                other = connection.execute(
                    "SELECT 1 FROM sources WHERE sha256=? AND exam_id != ? LIMIT 1",
                    (row["sha256"], exam_id),
                ).fetchone()
                if not other:
                    unique_paths.append(row["relative_path"])

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "DELETE FROM answer_overrides WHERE key_id IN (SELECT id FROM answer_keys WHERE exam_id=?) "
                "OR source_id IN (SELECT id FROM sources WHERE exam_id=?)",
                (exam_id, exam_id),
            )
            connection.execute(
                "DELETE FROM reviews WHERE key_id IN (SELECT id FROM answer_keys WHERE exam_id=?) "
                "OR source_id IN (SELECT id FROM sources WHERE exam_id=?)",
                (exam_id, exam_id),
            )
            connection.execute(
                "DELETE FROM identities WHERE source_id IN (SELECT id FROM sources WHERE exam_id=?)",
                (exam_id,),
            )
            connection.execute("DELETE FROM answer_keys WHERE exam_id=?", (exam_id,))
            connection.execute(
                "DELETE FROM detections WHERE source_id IN (SELECT id FROM sources WHERE exam_id=?)",
                (exam_id,),
            )
            connection.execute("DELETE FROM sources WHERE exam_id=?", (exam_id,))
            connection.execute("DELETE FROM import_failures WHERE exam_id=?", (exam_id,))
            connection.execute("DELETE FROM export_runs WHERE exam_id=?", (exam_id,))
            connection.execute("DELETE FROM assessment_indicators WHERE exam_id=?", (exam_id,))
            connection.execute("DELETE FROM attendance WHERE exam_id=?", (exam_id,))
            connection.execute("DELETE FROM skipped_numbers WHERE exam_id=?", (exam_id,))
            connection.execute("DELETE FROM exam_rooms WHERE exam_id=?", (exam_id,))
            changed = connection.execute("DELETE FROM exams WHERE id=?", (exam_id,)).rowcount
            if not changed:
                raise ValueError("ไม่พบข้อสอบที่ต้องการลบ")

        for rel_path in unique_paths:
            file_path = (self.path.parent / rel_path).resolve()
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                pass

    def export_runs(self, exam_id: str, room_id: str | None = None) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            query = "SELECT * FROM export_runs WHERE exam_id=?"
            params: list[object] = [exam_id]
            if room_id is not None:
                query += " AND room_id=?"
                params.append(room_id)
            query += " ORDER BY created_at DESC, id"
            return [
                dict(row)
                for row in connection.execute(query, params)
            ]

    def summary(self, exam_id: str) -> dict[str, int]:
        with closing(sqlite3.connect(self.path)) as connection:
            return {
                "sources": int(
                    connection.execute(
                        "SELECT count(*) FROM sources WHERE exam_id=? AND archived_at IS NULL",
                        (exam_id,),
                    ).fetchone()[0]
                ),
                "reviews": int(
                    connection.execute(
                        "SELECT count(*) FROM reviews WHERE source_id IN (SELECT id FROM sources WHERE exam_id=? AND archived_at IS NULL)",
                        (exam_id,),
                    ).fetchone()[0]
                ),
                "exports": int(
                    connection.execute(
                        "SELECT count(*) FROM export_runs WHERE exam_id=?", (exam_id,)
                    ).fetchone()[0]
                ),
            }

    def save_template(self, template_def: TemplateDefinition) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            existing = connection.execute(
                "SELECT definition FROM templates WHERE id=? AND version=?",
                (template_def.template_id, template_def.version),
            ).fetchone()
            if existing is not None:
                existing_dict = json.loads(existing[0])
                current_dict = template_def.to_dict()
                # Ignore created_at/updated_at comparison
                existing_dict.pop("created_at", None)
                existing_dict.pop("updated_at", None)
                current_copy = dict(current_dict)
                current_copy.pop("created_at", None)
                current_copy.pop("updated_at", None)
                if existing_dict != current_copy:
                    raise ValueError("ห้ามแก้ไขแม่แบบเดิมในเวอร์ชันเดิม กรุณาสร้างเวอร์ชันใหม่")
                connection.execute(
                    "UPDATE templates SET name=?, updated_at=? WHERE id=? AND version=?",
                    (
                        template_def.name,
                        datetime.now(timezone.utc).isoformat(),
                        template_def.template_id,
                        template_def.version,
                    ),
                )
                return

            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                "INSERT INTO templates (id, version, name, kind, definition, reference_sha256, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    template_def.template_id,
                    template_def.version,
                    template_def.name,
                    template_def.kind,
                    json.dumps(template_def.to_dict(), ensure_ascii=False),
                    template_def.reference_sha256,
                    template_def.created_at or now,
                    template_def.updated_at or now,
                ),
            )

    def get_template(
        self, template_id: str, version: int | None = None
    ) -> TemplateDefinition | None:
        from exam_grader.template_manager import BUILTIN_TEMPLATE_IDS, load_builtin_template

        if template_id in BUILTIN_TEMPLATE_IDS:
            try:
                builtin = load_builtin_template(template_id)
                if version is not None and builtin.version != version:
                    return None
                return builtin
            except (ValueError, FileNotFoundError):
                pass

        with closing(sqlite3.connect(self.path)) as connection:
            if version is not None:
                row = connection.execute(
                    "SELECT definition FROM templates WHERE id=? AND version=? AND deleted_at IS NULL",
                    (template_id, version),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT definition FROM templates WHERE id=? AND deleted_at IS NULL ORDER BY version DESC LIMIT 1",
                    (template_id,),
                ).fetchone()
        if row is not None:
            try:
                return TemplateDefinition.from_dict(json.loads(row[0]))
            except Exception:
                pass
        return None

    def list_templates(self, include_deleted: bool = False) -> list[TemplateDefinition]:
        with closing(sqlite3.connect(self.path)) as connection:
            where = "" if include_deleted else "WHERE deleted_at IS NULL "
            rows = connection.execute(
                f"SELECT definition FROM templates {where}ORDER BY kind ASC, created_at ASC, id ASC, version DESC"
            ).fetchall()
        seen: set[str] = set()
        templates: list[TemplateDefinition] = []
        for row in rows:
            try:
                td = TemplateDefinition.from_dict(json.loads(row[0]))
            except Exception:
                continue
            if td.template_id not in seen:
                seen.add(td.template_id)
                templates.append(td)
        # Ensure built-in templates (default-1, default-2, default-3) are present
        from exam_grader.template_manager import BUILTIN_TEMPLATE_IDS, load_builtin_template

        for b_id in BUILTIN_TEMPLATE_IDS:
            if b_id not in seen:
                try:
                    templates.append(load_builtin_template(b_id))
                    seen.add(b_id)
                except (ValueError, FileNotFoundError):
                    pass
        return templates

    def is_template_referenced(self, template_id: str, version: int | None = None) -> bool:
        with closing(sqlite3.connect(self.path)) as connection:
            if version is not None:
                row = connection.execute(
                    "SELECT 1 FROM exams WHERE template_id=? AND template_version=? LIMIT 1",
                    (template_id, version),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT 1 FROM exams WHERE template_id=? LIMIT 1",
                    (template_id,),
                ).fetchone()
        return row is not None

    def delete_template(self, template_id: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute(
                "SELECT kind FROM templates WHERE id=? AND deleted_at IS NULL LIMIT 1",
                (template_id,),
            ).fetchone()
            if row is None:
                raise ValueError("ไม่พบรูปแบบกระดาษคำตอบที่ต้องการลบ")
            if row[0] == "builtin":
                raise ValueError("ไม่สามารถลบรูปแบบกระดาษคำตอบมาตรฐานของระบบได้")
            if self.is_template_referenced(template_id):
                raise ValueError("ไม่สามารถลบรูปแบบกระดาษคำตอบที่ถูกใช้งานในข้อสอบแล้ว")
            connection.execute(
                "UPDATE templates SET deleted_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), template_id),
            )
