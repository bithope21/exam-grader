"""Approved keys, append-only human reviews and deterministic snapshots."""

import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

CHOICES = ("A", "B", "C", "D", "E")
RESOLVED = (*CHOICES, "blank", "multiple", "boundary_cross")
POLICY = "one-point-first-n-v2-accepted-set-boundary-v1"


def accepted_choices(answer) -> set[str]:
    """Return accepted key choices while reading legacy scalar keys."""
    if isinstance(answer, str):
        return {answer} if answer in CHOICES else set()
    if isinstance(answer, (list, tuple)):
        if not answer or any(choice not in CHOICES for choice in answer):
            return set()
        return set(answer)
    return set()


def score_answer(student_answer, key_answer) -> int:
    """Award one point only for a single student choice in the accepted set."""
    return int(student_answer in CHOICES and student_answer in accepted_choices(key_answer))


class Workflow:
    def __init__(self, database: Path):
        self.database = database

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection

    @staticmethod
    def _key(connection, exam_id):
        row = connection.execute(
            "SELECT answer_keys.* FROM answer_keys JOIN sources ON sources.id=answer_keys.source_id "
            "WHERE answer_keys.exam_id=? AND sources.archived_at IS NULL "
            "ORDER BY answer_keys.rowid DESC LIMIT 1", (exam_id,)
        ).fetchone()
        if row is None:
            raise ValueError("กรุณายืนยันเฉลยก่อน")
        key = dict(row)
        key["answers"] = json.loads(key["answers"])
        return key

    def current_key(self, exam_id: str) -> dict:
        with self.connection() as connection:
            return self._key(connection, exam_id)

    def confirmed_key(self, exam_id: str) -> dict:
        with self.connection() as connection:
            key = self._key(connection, exam_id)
            latest = connection.execute("SELECT id FROM sources WHERE exam_id=? AND purpose='key' AND archived_at IS NULL ORDER BY rowid DESC LIMIT 1", (exam_id,)).fetchone()
            if key["origin"] == "machine" or (latest and latest["id"] != key["source_id"]):
                raise ValueError("กรุณาตรวจและยืนยันเฉลยล่าสุดก่อนเพิ่มนักเรียน")
            return key

    def question_count(self, exam_id: str) -> int:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT question_count FROM exams WHERE id=?", (exam_id,)
            ).fetchone()
            if row is None:
                raise ValueError("ไม่พบข้อสอบ")
            return int(row["question_count"])

    def approve_key(self, exam_id: str, answers: list[object], source_id: str, *, origin: str = "teacher", detection_id: str | None = None) -> dict:
        with self.connection() as connection:
            exam = connection.execute(
                "SELECT question_count FROM exams WHERE id=?", (exam_id,)
            ).fetchone()
            source = connection.execute(
                "SELECT purpose FROM sources WHERE id=? AND exam_id=? AND archived_at IS NULL", (source_id, exam_id)
            ).fetchone()
            if exam is None:
                raise ValueError("ไม่พบข้อสอบ")
            if source is None or source["purpose"] != "key":
                raise ValueError("ภาพเฉลยไม่ตรงกับข้อสอบ")
            normalized_answers = []
            for answer in answers:
                choices = accepted_choices(answer)
                if not choices:
                    raise ValueError("เฉลยต้องเป็นคำตอบ ก–จ อย่างน้อยหนึ่งตัวเลือกต่อข้อ")
                normalized_answers.append(answer if isinstance(answer, str) else sorted(choices))
            if len(normalized_answers) != exam["question_count"]:
                raise ValueError(f"เฉลยต้องมีคำตอบครบ {exam['question_count']} ข้อ")
            connection.execute(
                "INSERT INTO answer_keys (id,exam_id,source_id,answers,created_at,origin,detection_id) VALUES (?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    exam_id,
                    source_id,
                    json.dumps(normalized_answers),
                    datetime.now(timezone.utc).isoformat(),
                    origin,
                    detection_id,
                ),
            )
            return self._key(connection, exam_id)

    def latest_review(self, source_id: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM reviews WHERE source_id=? ORDER BY rowid DESC LIMIT 1", (source_id,)
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["answers"] = json.loads(result["answers"])
            return result

    def save_detection(self, source_id: str, payload: dict) -> None:
        serializable = {key: value for key, value in payload.items() if key != "aligned"}
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO detections VALUES (?,?,?,?)",
                (
                    str(uuid4()),
                    source_id,
                    json.dumps(serializable),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def latest_detection(self, source_id: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload FROM detections WHERE source_id=? ORDER BY rowid DESC LIMIT 1",
                (source_id,),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def review(self, source_id: str, student_number: str, answers: list[str], key_id: str, *, origin: str = "teacher", detection_id: str | None = None) -> str:
        # Preserve display spelling, but normalize digit identity for duplicate detection.
        number = student_number.strip().translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
        if not number or not number.isascii() or not number.isdigit() or len(number) > 6:
            raise ValueError("กรุณาระบุเลขที่เป็นตัวเลข 1–6 หลัก")
        if int(number) < 1:
            raise ValueError("เลขที่ต้องมากกว่า 0")
        with self.connection() as connection:
            source = connection.execute("SELECT * FROM sources WHERE id=? AND archived_at IS NULL", (source_id,)).fetchone()
            if source is None or source["purpose"] != "student":
                raise ValueError("ไม่พบภาพนักเรียน")
            key = self._key(connection, source["exam_id"])
            if key["id"] != key_id:
                raise ValueError("เฉลยเปลี่ยนแล้ว กรุณาเปิดตรวจทานใหม่")
            if len(answers) != len(key["answers"]) or any(
                answer not in RESOLVED for answer in answers
            ):
                raise ValueError("กรุณาตรวจทานทุกข้อให้ครบก่อนยืนยัน")
            detection = connection.execute(
                "SELECT id FROM detections WHERE source_id=? ORDER BY rowid DESC LIMIT 1", (source_id,)
            ).fetchone()
            if detection_id is not None and (detection is None or detection["id"] != detection_id):
                raise ValueError("ผลอ่านเปลี่ยนแล้ว กรุณาโหลดรายการใหม่")
            revision = str(uuid4())
            connection.execute(
                "INSERT INTO reviews (id,source_id,key_id,student_number,answers,created_at,detection_id,origin) VALUES (?,?,?,?,?,?,?,?)",
                (
                    revision,
                    source_id,
                    key_id,
                    number,
                    json.dumps(answers),
                    datetime.now(timezone.utc).isoformat(),
                    detection["id"] if detection else None,
                    origin,
                ),
            )
            return revision

    def snapshot(self, exam_id: str) -> dict:
        self.confirmed_key(exam_id)
        with self.connection() as connection:
            key = self._key(connection, exam_id)
            exam = connection.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
            sources = connection.execute(
                "SELECT * FROM sources WHERE exam_id=? AND purpose='student' AND archived_at IS NULL", (exam_id,)
            ).fetchall()
            if not sources:
                raise ValueError("ยังไม่มีภาพนักเรียน")
            results, identities = [], set()
            for source in sources:
                review = connection.execute(
                    "SELECT * FROM reviews WHERE source_id=? ORDER BY rowid DESC LIMIT 1",
                    (source["id"],),
                ).fetchone()
                if review is None or review["key_id"] != key["id"]:
                    raise ValueError("ยังมีภาพที่ไม่ได้ตรวจทาน หรือเฉลยเปลี่ยน ต้องตรวจทานใหม่")
                identity_edit = connection.execute("SELECT student_number,created_at FROM identities WHERE source_id=? ORDER BY rowid DESC LIMIT 1", (source["id"],)).fetchone()
                if identity_edit and identity_edit["created_at"] > review["created_at"] and int(identity_edit["student_number"]) != int(review["student_number"]):
                    raise ValueError("เลขที่เปลี่ยนแล้ว กรุณาแก้รายการที่ยังมีปัญหาก่อนออกผล")
                identity = int(review["student_number"])
                if exam["expected_number_max"] and identity > exam["expected_number_max"]:
                    raise ValueError("เลขที่เกินช่วงที่กำหนด กรุณาแก้ก่อนออกผล")
                attendance = connection.execute("SELECT status FROM attendance WHERE exam_id=? AND student_number=?", (exam_id, identity)).fetchone()
                if attendance and attendance["status"] != "pending":
                    raise ValueError("พบภาพที่ระบุขาดสอบ กรุณาแก้สถานะก่อนออกผล")
                if identity in identities:
                    raise ValueError(f"เลขที่ซ้ำ: {review['student_number']} กรุณาแก้ไขก่อนออกผล")
                identities.add(identity)
                answers = json.loads(review["answers"])
                detection = None
                if review["detection_id"]:
                    detection = connection.execute(
                        "SELECT payload FROM detections WHERE id=?", (review["detection_id"],)
                    ).fetchone()
                results.append(
                    {
                        "source": dict(source),
                        "review_id": review["id"],
                        "detection_id": review["detection_id"],
                        "detection": json.loads(detection[0]) if detection else None,
                        "student_number": review["student_number"],
                        "answers": answers,
                        "score": sum(score_answer(a, b) for a, b in zip(answers, key["answers"], strict=True)),
                        "max": len(key["answers"]),
                        "status": "teacher_reviewed" if review["origin"] == "teacher" else review["origin"],
                        "decision_origin": review["origin"],
                    }
                )
            results.sort(key=lambda result: int(result["student_number"]))
            return {
                "schema_version": 1,
                "exam": dict(exam),
                "key": key,
                "scoring_policy": POLICY,
                "skipped_numbers": [row[0] for row in connection.execute("SELECT student_number FROM skipped_numbers WHERE exam_id=? ORDER BY student_number", (exam_id,)) if row[0] not in identities],
                "results": results,
                "attendance": [dict(row) for row in connection.execute(
                    "SELECT student_number,status,updated_at FROM attendance WHERE exam_id=? ORDER BY student_number", (exam_id,)
                )],
            }

    def record_export(self, exam_id: str, path: str, run_id: str, snapshot_fingerprint: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO export_runs (id, exam_id, path, run_id, snapshot_fingerprint, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(uuid4()), exam_id, path, run_id, snapshot_fingerprint,
                 datetime.now(timezone.utc).isoformat()),
            )

    def snapshot_fingerprint(self, snapshot: dict) -> str:
        canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def missing_numbers(self, exam_id: str) -> dict:
        snapshot = self.snapshot(exam_id)
        observed = sorted(int(item["student_number"]) for item in snapshot["results"])
        expected_max = snapshot["exam"].get("expected_number_max")
        if not observed:
            return {"observed": [], "missing_internal": [], "missing_expected": [], "expected_max": expected_max}
        internal = [value for value in range(observed[0], observed[-1] + 1) if value not in observed]
        expected = (
            [value for value in range(1, expected_max + 1) if value not in observed]
            if expected_max is not None else []
        )
        return {"observed": observed, "missing_internal": internal, "missing_expected": expected,
                "expected_max": expected_max}
