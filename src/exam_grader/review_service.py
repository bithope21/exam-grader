"""Exception-only review, explicit batch identities, and automatic clear answers.

Machine decisions remain distinguishable from teacher edits. Legacy observations
are never silently promoted; only the current version's per-question decision
contract is eligible. Existing teacher/key revisions remain append-only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from exam_grader.imaging import OMR_PIPELINE_VERSION
from exam_grader.imports import ImportService
from exam_grader.workflow import RESOLVED, Workflow


def normalize_number(value: str) -> str:
    value = value.strip().translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
    if not value.isascii() or not value.isdigit() or len(value) > 6 or int(value) < 1:
        raise ValueError("เลขที่ต้องเป็นตัวเลข 1–6 หลักและมากกว่า 0")
    return str(int(value))


class ReviewService:
    def __init__(self, database):
        self.flow = Workflow(database)
        self.importer = ImportService(database)

    def state(self, source: dict) -> dict:
        with self.flow.connection() as con:
            detection = con.execute("SELECT id,payload FROM detections WHERE source_id=? ORDER BY rowid DESC LIMIT 1", (source["id"],)).fetchone()
            identity = con.execute("SELECT * FROM identities WHERE source_id=? ORDER BY rowid DESC LIMIT 1", (source["id"],)).fetchone()
        review = self.flow.latest_review(source["id"])
        number = identity["student_number"] if identity else None
        if review and (not identity or review["created_at"] > identity["created_at"]):
            number = review["student_number"]
        return {"source": source, "detection_id": detection["id"] if detection else None,
                "detection": json.loads(detection["payload"]) if detection else {},
                "number": number, "review": review}

    def states(self, exam_id: str) -> list[dict]:
        return [self.state(s) for s in self.importer.list_sources(exam_id) if s["purpose"] == "student"]

    @staticmethod
    def machine_answers(detection: dict, count: int) -> list[str | None]:
        if detection.get("pipeline_version") != OMR_PIPELINE_VERSION or "registration" not in detection:
            return [None] * count
        answers = []
        for item in detection.get("answers", [])[:count]:
            value = None
            if item.get("auto_resolved"):
                if item["classification"] == "single_mark" and len(item["selected"]) == 1:
                    value = item["selected"][0]
                elif item["classification"] in {"blank", "multiple", "boundary_cross"}:
                    value = item["classification"]
            answers.append(value)
        return answers + [None] * (count - len(answers))

    def answers(self, state: dict, key: dict) -> list[str | None]:
        review = state["review"]
        if review and review["key_id"] == key["id"]:
            return list(review["answers"])
        answers = self.machine_answers(state["detection"], len(key["answers"]))
        with self.flow.connection() as con:
            for row in con.execute("SELECT question,answer FROM answer_overrides WHERE source_id=? AND key_id=? AND detection_id IS ? ORDER BY rowid", (state["source"]["id"], key["id"], state["detection_id"])):
                answers[row["question"] - 1] = row["answer"]
        return answers

    def auto_key(self, exam_id: str) -> bool:
        try:
            self.flow.current_key(exam_id)
            return False  # never replace an existing key silently
        except ValueError:
            pass
        sources = [s for s in self.importer.list_sources(exam_id) if s["purpose"] == "key"]
        if not sources:
            return False
        state = self.state(sources[-1])
        answers = self.machine_answers(state["detection"], self.flow.question_count(exam_id))
        if not all(a in ("A", "B", "C", "D", "E") for a in answers):
            return False
        self.flow.approve_key(exam_id, [a for a in answers if a is not None], sources[-1]["id"], origin="machine", detection_id=state["detection_id"])
        return True

    def finalize(self, exam_id: str) -> None:
        try:
            key = self.flow.confirmed_key(exam_id)
        except ValueError:
            return
        states = self.states(exam_id)
        numbers = [int(s["number"]) for s in states if s["number"]]
        with self.flow.connection() as con:
            maximum = con.execute("SELECT expected_number_max FROM exams WHERE id=?", (exam_id,)).fetchone()[0]
        for state in states:
            review = state["review"]
            if review and review["key_id"] != key["id"]:
                continue  # identity-only edits cannot refresh stale answers
            if not state["number"] or numbers.count(int(state["number"])) != 1:
                continue
            if maximum and int(state["number"]) > maximum:
                continue
            answers = self.answers(state, key)
            if any(a not in RESOLVED for a in answers):
                continue
            if review and review["student_number"] == state["number"] and review["answers"] == answers:
                continue
            with self.flow.connection() as con:
                edited = con.execute("SELECT 1 FROM answer_overrides WHERE source_id=? AND key_id=? AND detection_id IS ? LIMIT 1", (state["source"]["id"], key["id"], state["detection_id"])).fetchone()
            origin = "teacher_edited" if edited else "machine_with_teacher_identity"
            self.flow.review(state["source"]["id"], state["number"], [a for a in answers if a is not None], key["id"], origin=origin, detection_id=state["detection_id"])

    def adopt_numbers(self, exam_id: str) -> dict:
        """Explicit user batch action; conflicts stay unresolved, no forced gaps."""
        self.flow.confirmed_key(exam_id)
        states = self.states(exam_id)
        used = {int(s["number"]) for s in states if s["number"]}
        proposed = {}
        for state in states:
            if state["number"]:
                continue
            observation = state["detection"].get("student_number_observation") or {}
            candidate = observation.get("candidate")
            choices = observation.get("candidates") or []
            # An OCR candidate is usable in bulk only when it is the sole
            # candidate. Ambiguous handwriting stays in review until a teacher
            # resolves it; a later unique candidate may disambiguate it.
            if candidate and choices == [candidate]:
                proposed[state["source"]["id"]] = candidate
        observations = {s["source"]["id"]: s["detection"].get("student_number_observation", {}) for s in states}
        # A single unambiguous 4 can eliminate 4 from another sheet's explicit
        # [1,4] candidates. Never invent a number merely because a roster has a gap.
        anchored = used | {int(o["candidate"]) for o in observations.values()
                           if o.get("candidate") and o.get("candidates") == [o["candidate"]]}
        for state in states:
            sid = state["source"]["id"]
            if state["number"] or sid in proposed:
                continue
            observation = observations[sid]
            candidate = observation.get("candidate")
            choices = observation.get("candidates", [])
            if candidate and len(choices) > 1:
                remaining = [v for v in choices if int(v) not in anchored]
                if len(remaining) == 1:
                    proposed[sid] = remaining[0]
        applied, skipped = [], []
        for state in states:
            sid = state["source"]["id"]
            if sid not in proposed:
                continue
            value = proposed[sid]
            if not value or int(value) in used or list(proposed.values()).count(value) > 1:
                skipped.append(sid)
                continue
            self.set_number(state["source"], value, expected_detection=state["detection_id"], origin="teacher_bulk")
            used.add(int(value))
            applied.append(sid)
        self.finalize(exam_id)
        return {"applied": applied, "skipped": skipped}

    def set_number(self, source: dict, value: str, *, expected_detection: str | None, origin: str = "teacher") -> None:
        number = normalize_number(value)
        current = self.state(source)
        if current["detection_id"] != expected_detection:
            raise ValueError("ผลอ่านเปลี่ยนแล้ว กรุณาโหลดรายการใหม่")
        with self.flow.connection() as con:
            active = con.execute("SELECT 1 FROM sources WHERE id=? AND archived_at IS NULL AND purpose='student'", (source["id"],)).fetchone()
            if active is None:
                raise ValueError("ภาพนี้ถูกเก็บถาวรแล้ว กรุณากู้คืนก่อนแก้ไข")
            con.execute("INSERT INTO identities VALUES (?,?,?,?,?,?)", (str(uuid4()), source["id"], number, expected_detection, origin, datetime.now(timezone.utc).isoformat()))

    def resolve_answer(self, source: dict, question: int, answer: str, *, key_id: str, detection_id: str | None) -> None:
        key = self.flow.current_key(source["exam_id"])
        state = self.state(source)
        with self.flow.connection() as con:
            if con.execute("SELECT 1 FROM sources WHERE id=? AND archived_at IS NULL AND purpose='student'", (source["id"],)).fetchone() is None:
                raise ValueError("ภาพนี้ถูกเก็บถาวรแล้ว กรุณากู้คืนก่อนแก้ไข")
        if key["id"] != key_id or state["detection_id"] != detection_id:
            raise ValueError("เฉลยหรือผลอ่านเปลี่ยนแล้ว กรุณาโหลดรายการใหม่")
        if not 1 <= question <= len(key["answers"]) or answer not in RESOLVED:
            raise ValueError("คำตอบหรือข้อไม่ถูกต้อง")
        with self.flow.connection() as con:
            con.execute("INSERT INTO answer_overrides VALUES (?,?,?,?,?,?,?)", (str(uuid4()), source["id"], key_id, detection_id, question, answer, datetime.now(timezone.utc).isoformat()))
        # A complete teacher review is immutable; append a new review when edited.
        if state["review"] and state["review"]["key_id"] == key_id:
            answers = list(state["review"]["answers"])
            answers[question - 1] = answer
            self.flow.review(source["id"], state["number"], answers, key_id, origin="teacher", detection_id=detection_id)
        self.finalize(source["exam_id"])

    def set_attendance(self, exam_id: str, number: str, status: str) -> None:
        number = normalize_number(number)
        if status not in {"pending", "absent", "excused", "skipped"}:
            raise ValueError("สถานะไม่ถูกต้อง")
        if status != "pending" and any(s["number"] and int(s["number"]) == int(number) for s in self.states(exam_id)):
            raise ValueError("มีภาพนักเรียนเลขที่นี้แล้ว ไม่สามารถระบุว่าขาดสอบได้")
        with self.flow.connection() as con:
            if status == "skipped":
                con.execute("INSERT OR IGNORE INTO skipped_numbers VALUES (?,?)", (exam_id, int(number)))
                return
            con.execute("DELETE FROM skipped_numbers WHERE exam_id=? AND student_number=?", (exam_id, int(number)))
            con.execute("INSERT INTO attendance VALUES (?,?,?,?) ON CONFLICT(exam_id,student_number) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at", (exam_id, int(number), status, datetime.now(timezone.utc).isoformat()))

    def skip_missing(self, exam_id: str) -> int:
        missing = [i for i in self.issues(exam_id) if i["kind"] == "attendance" and i["source"] is None]
        for issue in missing:
            self.set_attendance(exam_id, issue["number"], "skipped")
        return len(missing)

    def issues(self, exam_id: str) -> list[dict]:
        states = self.states(exam_id)
        try:
            key = self.flow.confirmed_key(exam_id)
        except ValueError:
            return []  # The key page owns this blocking step.
        numbers = [int(s["number"]) for s in states if s["number"]]
        with self.flow.connection() as con:
            maximum = con.execute("SELECT expected_number_max FROM exams WHERE id=?", (exam_id,)).fetchone()[0]
            attendance = {r["student_number"]: r["status"] for r in con.execute("SELECT * FROM attendance WHERE exam_id=?", (exam_id,))}
            skipped = {r[0] for r in con.execute("SELECT student_number FROM skipped_numbers WHERE exam_id=?", (exam_id,))}
        issues = []
        for state in states:
            number = state["number"]
            base = {"source": state["source"], "number": number, "detection_id": state["detection_id"], "key_id": key["id"] if key else None}
            if not state["detection"] or state["detection"].get("failure"):
                issues.append({**base, "kind": "image", "label": "ภาพอ่านไม่ได้ · ตรวจภาพต้นฉบับ"})
                continue
            candidate = (state["detection"].get("student_number_observation") or {}).get("candidate")
            if not number or numbers.count(int(number)) > 1 or (maximum and int(number) > maximum):
                reason = "ยังไม่ยืนยันเลขที่" if not number else "เลขที่ซ้ำ" if numbers.count(int(number)) > 1 else "เลขที่เกินช่วง"
                choices = (state["detection"].get("student_number_observation") or {}).get("candidates", [])
                if not candidate and choices:
                    reason += " · อาจเป็น " + " / ".join(choices)
                issues.append({**base, "kind": "number", "label": reason, "candidate": candidate})
            if number and attendance.get(int(number)) in {"absent", "excused"}:
                issues.append({**base, "kind": "attendance", "label": "พบภาพหลังระบุขาดสอบ", "candidate": "pending"})
            if key:
                if state["review"] and state["review"]["key_id"] != key["id"]:
                    issues.append({**base, "kind": "stale", "label": "เฉลยเปลี่ยน · ยืนยันใช้คำตอบเดิมอีกครั้ง"})
                else:
                    for index, answer in enumerate(self.answers(state, key), 1):
                        if answer is None:
                            observation = state["detection"].get("answers", [])
                            selected = observation[index - 1].get("selected", []) if index <= len(observation) else []
                            issues.append({**base, "kind": "answer", "question": index, "label": f"ข้อ {index} · รอยคำตอบไม่ชัด", "candidate": selected[0] if len(selected) == 1 else None})
        # A sparse upload is not a roster. Only explicit expected ranges create gaps.
        bound = maximum or 0
        for number in range(1, bound + 1):
            if number not in numbers and number not in skipped and attendance.get(number, "pending") == "pending":
                issues.append({"source": None, "number": str(number), "kind": "attendance", "label": "ยังไม่พบกระดาษ · ระบุสถานะ", "candidate": "pending"})
        for failure in self.importer.list_failures(exam_id):
            issues.append({"source": None, "number": None, "kind": "import", "label": "นำเข้าไม่ได้ · " + failure["error"], "failure": failure})
        return sorted(issues, key=lambda i: (int(i["number"]) if i["number"] else 10**9, i.get("question", 0)))
