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
from exam_grader.student_number_constraints import resolve_student_number_constraint
from exam_grader.workflow import RESOLVED, Workflow


def normalize_number(value: str) -> str:
    value = value.strip().translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
    if not value.isascii() or not value.isdigit() or len(value) > 6 or int(value) < 1:
        raise ValueError("เลขที่ต้องเป็นตัวเลข 1–6 หลักและมากกว่า 0")
    return str(int(value))


class ReviewService:
    def __init__(self, database, room_id: str | None = None):
        self.flow = Workflow(database)
        self.importer = ImportService(database)
        self.room_id = room_id

    def state(self, source: dict) -> dict:
        with self.flow.connection() as con:
            detection = con.execute(
                "SELECT id,payload FROM detections WHERE source_id=? ORDER BY rowid DESC LIMIT 1",
                (source["id"],),
            ).fetchone()
            identity = con.execute(
                "SELECT * FROM identities WHERE source_id=? ORDER BY rowid DESC LIMIT 1",
                (source["id"],),
            ).fetchone()
        review = self.flow.latest_review(source["id"])
        detection_id = detection["id"] if detection else None
        # A teacher-confirmed identity is an explicit durable decision and may
        # survive a re-read of the same immutable source. Answer reviews are
        # different: their machine evidence must still match this detection.
        if review and review.get("detection_id") != detection_id:
            review = None
        number = identity["student_number"] if identity else None
        if review and (not identity or review["created_at"] > identity["created_at"]):
            number = review["student_number"]
        return {
            "source": source,
            "detection_id": detection_id,
            "detection": json.loads(detection["payload"]) if detection else {},
            "number": number,
            "review": review,
        }

    def states(self, exam_id: str) -> list[dict]:
        return [
            self.state(s)
            for s in self.importer.list_sources(exam_id, self.room_id)
            if s["purpose"] == "student"
        ]

    @staticmethod
    def machine_answers(detection: dict, count: int) -> list[str | None]:
        if (
            detection.get("pipeline_version") != OMR_PIPELINE_VERSION
            or "registration" not in detection
        ):
            return [None] * count
        answers = []
        for item in detection.get("answers", [])[:count]:
            value = None
            if item.get("auto_resolved"):
                if item["classification"] == "single_mark" and len(item["selected"]) == 1:
                    value = item["selected"][0]
                elif item["classification"] == "blank" and not item.get("blank_abnormal", False):
                    value = item["classification"]
            answers.append(value)
        return answers + [None] * (count - len(answers))

    def answers(self, state: dict, key: dict) -> list[str | None]:
        review = state["review"]
        if review and review["key_id"] == key["id"]:
            return list(review["answers"])
        answers = self.machine_answers(state["detection"], len(key["answers"]))
        with self.flow.connection() as con:
            for row in con.execute(
                "SELECT question,answer FROM answer_overrides WHERE source_id=? AND key_id=? AND detection_id IS ? ORDER BY rowid",
                (state["source"]["id"], key["id"], state["detection_id"]),
            ):
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
        self.flow.approve_key(
            exam_id,
            [a for a in answers if a is not None],
            sources[-1]["id"],
            origin="machine",
            detection_id=state["detection_id"],
        )
        return True

    def finalize(self, exam_id: str) -> None:
        try:
            key = self.flow.confirmed_key(exam_id)
        except ValueError:
            return
        states = self.states(exam_id)
        numbers = [int(s["number"]) for s in states if s["number"]]
        with self.flow.connection() as con:
            maximum = resolve_student_number_constraint(
                con, exam_id, self.room_id
            ).maximum
        for state in states:
            review = state["review"]
            if review and review["key_id"] != key["id"]:
                continue  # identity-only edits cannot refresh stale answers
            if not state["number"] or numbers.count(int(state["number"])) != 1:
                continue
            if maximum is not None and int(state["number"]) > maximum:
                continue
            answers = self.answers(state, key)
            if any(a not in RESOLVED for a in answers):
                continue
            if (
                review
                and review["student_number"] == state["number"]
                and review["answers"] == answers
            ):
                continue
            with self.flow.connection() as con:
                edited = con.execute(
                    "SELECT 1 FROM answer_overrides WHERE source_id=? AND key_id=? AND detection_id IS ? LIMIT 1",
                    (state["source"]["id"], key["id"], state["detection_id"]),
                ).fetchone()
            origin = "teacher_edited" if edited else "machine_with_teacher_identity"
            self.flow.review(
                state["source"]["id"],
                state["number"],
                [a for a in answers if a is not None],
                key["id"],
                origin=origin,
                detection_id=state["detection_id"],
            )

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
            if observation.get("requires_review"):
                continue
            candidate = observation.get("candidate")
            choices = observation.get("candidates") or []
            confidence = observation.get("confidence")
            margin = observation.get("confidence_margin")
            calibrated_auto_accept = bool(
                (observation.get("diagnostics") or {}).get("selective_auto_accept")
            )
            # Recognizer evidence comes first: adopt if it is either the sole
            # candidate or has strong evidence (high confidence >= 80 and clear margin >= 15).
            is_unambiguous = candidate and choices == [candidate]
            is_confident = (
                candidate is not None
                and confidence is not None
                and confidence >= 80.0
                and (margin is None or margin >= 15.0)
            )
            if calibrated_auto_accept or is_unambiguous or is_confident:
                proposed[state["source"]["id"]] = candidate
        observations = {
            s["source"]["id"]: s["detection"].get("student_number_observation", {}) for s in states
        }
        # Anchored numbers are uniquely identified sheets; eliminate them from other ambiguous sheets.
        # Never invent a number merely because a roster has a gap.
        anchored = used | {int(v) for v in proposed.values() if v is not None}
        for state in states:
            sid = state["source"]["id"]
            if state["number"] or sid in proposed:
                continue
            observation = observations[sid]
            if observation.get("requires_review"):
                continue
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
            self.set_number(
                state["source"],
                value,
                expected_detection=state["detection_id"],
                origin="teacher_bulk",
            )
            used.add(int(value))
            applied.append(sid)
        self.finalize(exam_id)
        return {"applied": applied, "skipped": skipped}

    def set_number(
        self, source: dict, value: str, *, expected_detection: str | None, origin: str = "teacher"
    ) -> None:
        number = normalize_number(value)
        current = self.state(source)
        if current["detection_id"] != expected_detection:
            raise ValueError("ผลอ่านเปลี่ยนแล้ว กรุณาโหลดรายการใหม่")
        with self.flow.connection() as con:
            active = con.execute(
                "SELECT 1 FROM sources WHERE id=? AND archived_at IS NULL AND purpose='student'",
                (source["id"],),
            ).fetchone()
            if active is None:
                raise ValueError("ภาพนี้ถูกเก็บถาวรแล้ว กรุณากู้คืนก่อนแก้ไข")
            con.execute(
                "INSERT INTO identities VALUES (?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    source["id"],
                    number,
                    expected_detection,
                    origin,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        self.finalize(source["exam_id"])

    def resolve_answer(
        self, source: dict, question: int, answer: str, *, key_id: str, detection_id: str | None
    ) -> None:
        key = self.flow.current_key(source["exam_id"])
        state = self.state(source)
        with self.flow.connection() as con:
            if (
                con.execute(
                    "SELECT 1 FROM sources WHERE id=? AND archived_at IS NULL AND purpose='student'",
                    (source["id"],),
                ).fetchone()
                is None
            ):
                raise ValueError("ภาพนี้ถูกเก็บถาวรแล้ว กรุณากู้คืนก่อนแก้ไข")
        if key["id"] != key_id or state["detection_id"] != detection_id:
            raise ValueError("เฉลยหรือผลอ่านเปลี่ยนแล้ว กรุณาโหลดรายการใหม่")
        if not 1 <= question <= len(key["answers"]) or answer not in RESOLVED:
            raise ValueError("คำตอบหรือข้อไม่ถูกต้อง")
        with self.flow.connection() as con:
            con.execute(
                "INSERT INTO answer_overrides VALUES (?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    source["id"],
                    key_id,
                    detection_id,
                    question,
                    answer,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        # A complete teacher review is immutable; append a new review when edited.
        if state["review"] and state["review"]["key_id"] == key_id:
            answers = list(state["review"]["answers"])
            answers[question - 1] = answer
            self.flow.review(
                source["id"],
                state["number"],
                answers,
                key_id,
                origin="teacher",
                detection_id=detection_id,
            )
        self.finalize(source["exam_id"])

    def bulk_resolve(self, exam_id: str, operations: list[dict]) -> dict:
        """Atomically apply and persist resolutions for multiple issues in a single transaction."""
        if not operations:
            return {"applied": 0, "total": 0}
        key = self.flow.confirmed_key(exam_id)
        room_id = self.flow.resolve_room_id(exam_id, self.room_id)
        states = {state["source"]["id"]: state for state in self.states(exam_id)}
        now = datetime.now(timezone.utc).isoformat()
        applied = 0
        applied_indexes: list[int] = []
        with self.flow.connection() as con:
            for index, op in enumerate(operations):
                issue = op["issue"]
                value = op["value"]
                if not value:
                    continue
                kind = issue.get("kind")
                if kind == "answer":
                    if value not in RESOLVED:
                        continue
                    q = issue["question"]
                    if not (1 <= q <= len(key["answers"])):
                        continue
                    sid = issue["source"]["id"]
                    det_id = issue["detection_id"]
                    con.execute(
                        "INSERT INTO answer_overrides VALUES (?,?,?,?,?,?,?)",
                        (str(uuid4()), sid, key["id"], det_id, q, value, now),
                    )
                    applied += 1
                    applied_indexes.append(index)
                elif kind == "attendance":
                    if value not in {"pending", "absent", "excused", "skipped"}:
                        continue
                    num = int(normalize_number(issue["number"]))
                    if value == "skipped":
                        con.execute(
                            "INSERT OR IGNORE INTO skipped_numbers VALUES (?,?,?)",
                            (exam_id, room_id, num),
                        )
                    else:
                        con.execute(
                            "DELETE FROM skipped_numbers WHERE room_id=? AND student_number=?",
                            (room_id, num),
                        )
                        con.execute(
                            "INSERT INTO attendance VALUES (?,?,?,?,?) ON CONFLICT(room_id,student_number) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at",
                            (exam_id, room_id, num, value, now),
                        )
                    applied += 1
                    applied_indexes.append(index)
                elif kind == "number":
                    ident_num = normalize_number(value)
                    sid = issue["source"]["id"]
                    det_id = issue["detection_id"]
                    con.execute(
                        "INSERT INTO identities VALUES (?,?,?,?,?,?)",
                        (str(uuid4()), sid, ident_num, det_id, "teacher", now),
                    )
                    applied += 1
                    applied_indexes.append(index)
                elif kind == "stale" and value == "reuse":
                    sid = issue["source"]["id"]
                    state = states.get(sid)
                    previous = state.get("review") if state else None
                    if (
                        state is None
                        or previous is None
                        or previous["key_id"] == key["id"]
                        or state["detection_id"] != issue.get("detection_id")
                        or state["number"] is None
                        or len(previous["answers"]) != len(key["answers"])
                        or any(answer not in RESOLVED for answer in previous["answers"])
                    ):
                        continue
                    con.execute(
                        "INSERT INTO reviews (id,source_id,key_id,student_number,answers,created_at,detection_id,origin) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (
                            str(uuid4()),
                            sid,
                            key["id"],
                            state["number"],
                            json.dumps(previous["answers"]),
                            now,
                            issue.get("detection_id"),
                            "teacher_reuse",
                        ),
                    )
                    applied += 1
                    applied_indexes.append(index)
        self.finalize(exam_id)
        return {
            "applied": applied,
            "total": len(operations),
            "applied_indexes": applied_indexes,
        }

    def bulk_dismiss(self, exam_id: str, issues: list[dict]) -> dict:
        """Resolve selected failed rows without deleting any original bytes."""

        if not issues:
            return {"applied": 0, "total": 0, "errors": []}
        now = datetime.now(timezone.utc).isoformat()
        applied = 0
        applied_indexes: list[int] = []
        errors: list[str] = []
        with self.flow.connection() as con:
            for index, issue in enumerate(issues):
                label = issue.get("label", "รายการ")
                if issue.get("kind") == "import":
                    failure = issue.get("failure") or {}
                    failure_id = failure.get("id")
                    if not failure_id:
                        errors.append(f"{label}: ไม่พบรหัสรายการนำเข้า")
                        continue
                    changed = con.execute(
                        "UPDATE import_failures SET resolved_at=? "
                        "WHERE id=? AND exam_id=? AND resolved_at IS NULL "
                        "AND (room_id IS ? OR room_id=?)",
                        (now, failure_id, exam_id, self.room_id, self.room_id),
                    ).rowcount
                elif issue.get("kind") == "image":
                    source = issue.get("source") or {}
                    changed = con.execute(
                        "UPDATE sources SET archived_at=? "
                        "WHERE id=? AND exam_id=? AND purpose='student' "
                        "AND archived_at IS NULL AND (room_id IS ? OR room_id=?)",
                        (now, source.get("id"), exam_id, self.room_id, self.room_id),
                    ).rowcount
                else:
                    errors.append(f"{label}: รายการนี้ลบแบบกลุ่มไม่ได้")
                    continue
                if changed:
                    applied += 1
                    applied_indexes.append(index)
                else:
                    errors.append(f"{label}: รายการถูกแก้ไขไปแล้วหรือไม่พบรายการ")
        self.finalize(exam_id)
        return {
            "applied": applied,
            "total": len(issues),
            "applied_indexes": applied_indexes,
            "errors": errors,
        }

    @staticmethod
    def prefilled_value(issue: dict) -> str | None:
        """Return only a measured value or known status for this review row."""
        value = issue.get("prefill")
        if isinstance(value, str) and value:
            return value
        if issue.get("kind") == "answer" and issue.get("status") in {
            "blank",
            "multiple",
            "boundary_cross",
        }:
            return issue["status"]
        return None

    @staticmethod
    def student_number_recommendation(state: dict) -> str | None:
        """Return the pipeline's best unconfirmed number recommendation only."""
        if state.get("number"):
            return None
        observation = (state.get("detection") or {}).get("student_number_observation") or {}
        candidate = observation.get("candidate")
        return str(candidate) if candidate else None

    def confirm_prefilled(self, exam_id: str, issues: list[dict]) -> dict:
        """Teacher-confirm measured row values without forcing one value on all rows.

        This is deliberately separate from ``adopt_numbers``: selecting this action
        is the teacher's explicit confirmation, and no roster gap or range is used to
        invent an identity.
        """
        key = self.flow.confirmed_key(exam_id)
        states = {state["source"]["id"]: state for state in self.states(exam_id)}
        used_numbers = {
            int(state["number"]) for state in states.values() if state.get("number")
        }
        maximum = None
        with self.flow.connection() as con:
            maximum = resolve_student_number_constraint(
                con, exam_id, self.room_id
            ).maximum

        applied: list[dict] = []
        skipped: list[dict] = []
        now = datetime.now(timezone.utc).isoformat()
        pending_numbers: set[int] = set()
        with self.flow.connection() as con:
            for issue in issues:
                value = self.prefilled_value(issue)
                source = issue.get("source")
                if not value or not source or source.get("id") not in states:
                    skipped.append({"issue": issue, "reason": "ไม่มีค่าที่ระบบอ่านไว้"})
                    continue
                sid = source["id"]
                detection_id = issue.get("detection_id")
                if issue.get("kind") == "answer":
                    if value not in RESOLVED or not issue.get("question"):
                        skipped.append({"issue": issue, "reason": "ค่าคำตอบไม่ถูกต้อง"})
                        continue
                    con.execute(
                        "INSERT INTO answer_overrides VALUES (?,?,?,?,?,?,?)",
                        (
                            str(uuid4()),
                            sid,
                            key["id"],
                            detection_id,
                            int(issue["question"]),
                            value,
                            now,
                        ),
                    )
                    applied.append(issue)
                elif issue.get("kind") == "number":
                    try:
                        number = int(normalize_number(value))
                    except ValueError:
                        skipped.append({"issue": issue, "reason": "เลขที่ไม่ถูกต้อง"})
                        continue
                    if (
                        number in used_numbers
                        or number in pending_numbers
                        or (maximum is not None and number > maximum)
                    ):
                        skipped.append({"issue": issue, "reason": "เลขที่ซ้ำหรือเกินช่วง"})
                        continue
                    con.execute(
                        "INSERT INTO identities VALUES (?,?,?,?,?,?)",
                        (str(uuid4()), sid, str(number), detection_id, "teacher_prefilled", now),
                    )
                    pending_numbers.add(number)
                    applied.append(issue)
                else:
                    skipped.append({"issue": issue, "reason": "รายการนี้ไม่มี prefill ที่ยืนยันได้"})
        self.finalize(exam_id)
        return {"applied": applied, "skipped": skipped, "total": len(issues)}

    def set_attendance(self, exam_id: str, number: str, status: str) -> None:
        number = normalize_number(number)
        if status not in {"pending", "absent", "excused", "skipped"}:
            raise ValueError("สถานะไม่ถูกต้อง")
        if status != "pending" and any(
            s["number"] and int(s["number"]) == int(number) for s in self.states(exam_id)
        ):
            raise ValueError("มีภาพนักเรียนเลขที่นี้แล้ว ไม่สามารถระบุว่าขาดสอบได้")
        room_id = self.flow.resolve_room_id(exam_id, self.room_id)
        with self.flow.connection() as con:
            if status == "skipped":
                con.execute(
                    "INSERT OR IGNORE INTO skipped_numbers VALUES (?,?,?)",
                    (exam_id, room_id, int(number)),
                )
                return
            con.execute(
                "DELETE FROM skipped_numbers WHERE room_id=? AND student_number=?",
                (room_id, int(number)),
            )
            con.execute(
                "INSERT INTO attendance VALUES (?,?,?,?,?) ON CONFLICT(room_id,student_number) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at",
                (exam_id, room_id, int(number), status, datetime.now(timezone.utc).isoformat()),
            )

    def skip_missing(self, exam_id: str) -> int:
        missing = [
            i for i in self.issues(exam_id) if i["kind"] == "attendance" and i["source"] is None
        ]
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
        room_id = self.flow.resolve_room_id(exam_id, self.room_id)
        with self.flow.connection() as con:
            maximum = resolve_student_number_constraint(con, exam_id, room_id).maximum
            attendance = {
                r["student_number"]: r["status"]
                for r in con.execute("SELECT * FROM attendance WHERE room_id=?", (room_id,))
            }
            skipped = {
                r[0]
                for r in con.execute(
                    "SELECT student_number FROM skipped_numbers WHERE room_id=?", (room_id,)
                )
            }
        issues = []
        for state in states:
            number = state["number"]
            base = {
                "source": state["source"],
                "number": number,
                "detection_id": state["detection_id"],
                "key_id": key["id"] if key else None,
            }
            if not state["detection"] or state["detection"].get("failure"):
                issues.append({**base, "kind": "image", "label": "ภาพอ่านไม่ได้ · ตรวจภาพต้นฉบับ"})
                continue
            candidate = (state["detection"].get("student_number_observation") or {}).get(
                "candidate"
            )
            if (
                not number
                or numbers.count(int(number)) > 1
                or (maximum is not None and int(number) > maximum)
            ):
                if not number:
                    status = "uncertain"
                    reason = "ยังไม่ยืนยันเลขที่"
                elif numbers.count(int(number)) > 1:
                    status = "duplicate"
                    reason = "เลขที่ซ้ำ"
                else:
                    status = "out_of_range"
                    reason = "เลขที่เกินช่วง"
                choices = (state["detection"].get("student_number_observation") or {}).get(
                    "candidates", []
                )
                if not candidate and choices:
                    reason += " · อาจเป็น " + " / ".join(choices)
                issues.append(
                    {
                        **base,
                        "kind": "number",
                        "status": status,
                        "label": reason,
                        "candidate": candidate,
                        "prefill": candidate,
                    }
                )
            if number and attendance.get(int(number)) in {"absent", "excused"}:
                issues.append(
                    {
                        **base,
                        "kind": "attendance",
                        "label": "พบภาพหลังระบุขาดสอบ",
                        "candidate": "pending",
                    }
                )
            if key:
                if state["review"] and state["review"]["key_id"] != key["id"]:
                    issues.append(
                        {**base, "kind": "stale", "label": "เฉลยเปลี่ยน · ยืนยันใช้คำตอบเดิมอีกครั้ง"}
                    )
                else:
                    for index, answer in enumerate(self.answers(state, key), 1):
                        if answer is None:
                            observation = state["detection"].get("answers", [])
                            observed = observation[index - 1] if index <= len(observation) else {}
                            selected = observed.get("selected", [])
                            classification = observed.get("classification", "uncertain")
                            prefill = None
                            if classification == "single_mark" and len(selected) == 1:
                                # A single mark blocked only by registration/geometry
                                # review is evidence to inspect, not an auto decision.
                                prefill = selected[0] if observed.get("auto_resolved") else None
                            elif classification in {"multiple", "boundary_cross"}:
                                prefill = classification
                            elif classification == "blank" and not observed.get("blank_abnormal"):
                                prefill = "blank"
                            if classification == "multiple" and selected:
                                label = f"ข้อ {index} · อ่านหลายคำตอบ ({', '.join(selected)}) · ต้องยืนยัน"
                            elif classification == "boundary_cross":
                                label = f"ข้อ {index} · รอยคาบเส้น · ต้องตรวจ geometry"
                            elif classification == "single_mark" and selected:
                                label = (
                                    f"ข้อ {index} · ระบบอ่านได้ {selected[0]} "
                                    "แต่ geometry ต้องยืนยัน"
                                )
                            elif classification == "blank":
                                label = f"ข้อ {index} · อ่านเป็นว่าง · ตรวจว่าตั้งใจเว้นว่าง"
                            else:
                                label = f"ข้อ {index} · รอยคำตอบไม่ชัด"
                            issues.append(
                                {
                                    **base,
                                    "kind": "answer",
                                    "question": index,
                                    "label": label,
                                    "status": classification,
                                    "candidate": selected[0]
                                    if classification == "single_mark" and len(selected) == 1
                                    else None,
                                    "prefill": prefill,
                                }
                            )
        # A sparse upload is not a roster. Only explicit expected ranges create gaps.
        bound = maximum or 0
        for number in range(1, bound + 1):
            if (
                number not in numbers
                and number not in skipped
                and attendance.get(number, "pending") == "pending"
            ):
                issues.append(
                    {
                        "source": None,
                        "number": str(number),
                        "kind": "attendance",
                        "status": "missing",
                        "label": "ยังไม่พบกระดาษ · ระบุสถานะ",
                        "candidate": "pending",
                    }
                )
        for failure in self.importer.list_failures(exam_id, self.room_id):
            issues.append(
                {
                    "source": None,
                    "number": None,
                    "kind": "import",
                    "label": "นำเข้าไม่ได้ · " + failure["error"],
                    "failure": failure,
                }
            )
        return sorted(
            issues, key=lambda i: (int(i["number"]) if i["number"] else 10**9, i.get("question", 0))
        )

    def skip_summary(
        self,
        exam_id: str,
        *,
        answer_edits: dict[str, dict[int, str]] | None = None,
        identity_edits: dict[str, str] | None = None,
    ) -> dict[str, int]:
        """Count unresolved decisions for the explicit skip confirmation dialog."""
        key = self.flow.confirmed_key(exam_id)
        answer_edits = answer_edits or {}
        identity_edits = identity_edits or {}
        states = self.states(exam_id)
        numbers: dict[str, str | None] = {}
        for state in states:
            sid = state["source"]["id"]
            value = identity_edits.get(sid, state["number"])
            try:
                numbers[sid] = normalize_number(value) if value else None
            except ValueError:
                numbers[sid] = None
        counts: dict[str, int] = {}
        for value in numbers.values():
            if value:
                counts[value] = counts.get(value, 0) + 1

        with self.flow.connection() as con:
            maximum = resolve_student_number_constraint(
                con, exam_id, self.room_id
            ).maximum

        unknown_ids: set[str] = set()
        unclear_questions: set[tuple[str, int]] = set()
        pending_sheets: set[str] = set()
        for state in states:
            sid = state["source"]["id"]
            number = numbers[sid]
            if (
                number is None
                or counts.get(number, 0) > 1
                or (maximum is not None and int(number) > maximum)
            ):
                unknown_ids.add(sid)
                pending_sheets.add(sid)
            if state["detection"].get("failure"):
                pending_sheets.add(sid)
            review = state["review"]
            reviewed_key = bool(review and review["key_id"] == key["id"])
            answers = self.answers(state, key)
            observations = state["detection"].get("answers", [])
            with self.flow.connection() as con:
                overridden = {
                    int(row[0])
                    for row in con.execute(
                        "SELECT question FROM answer_overrides WHERE source_id=? AND key_id=? AND detection_id IS ?",
                        (sid, key["id"], state["detection_id"]),
                    )
                }
            for index, answer in enumerate(answers, start=1):
                if index in answer_edits.get(sid, {}):
                    continue
                teacher_confirmed = (
                    reviewed_key and review["origin"] == "teacher"
                ) or index in overridden
                classification = (
                    observations[index - 1].get("classification")
                    if index <= len(observations)
                    else None
                )
                if not teacher_confirmed and (
                    answer is None or classification in {"uncertain", "multiple"}
                ):
                    unclear_questions.add((sid, index))
                    pending_sheets.add(sid)
            if review is None or not reviewed_key:
                pending_sheets.add(sid)

        return {
            "unconfirmed_identities": len(unknown_ids),
            "unclear_answers": len(unclear_questions),
            "unresolved_sheets": len(pending_sheets),
        }

    def skip_remaining(
        self,
        exam_id: str,
        *,
        answer_edits: dict[str, dict[int, str]] | None = None,
        identity_edits: dict[str, str] | None = None,
    ) -> dict[str, int]:
        """Persist a fail-closed partial snapshot and stable labels for unknown identities."""
        key = self.flow.confirmed_key(exam_id)
        answer_edits = answer_edits or {}
        identity_edits = identity_edits or {}
        states = self.states(exam_id)
        room_id = self.flow.resolve_room_id(exam_id, self.room_id)
        state_by_id = {state["source"]["id"]: state for state in states}
        normalized_edits = {
            sid: normalize_number(value) for sid, value in identity_edits.items() if value
        }
        if any(sid not in state_by_id for sid in (*normalized_edits, *answer_edits)):
            raise ValueError("รายการเปลี่ยนแล้ว กรุณาเปิดตรวจทานใหม่")

        answers_by_source: dict[str, list[str | None]] = {}
        overridden_by_source: dict[str, set[int]] = {}
        for sid, state in state_by_id.items():
            answers_by_source[sid] = self.answers(state, key)
            overridden_by_source[sid] = set()
            for question, answer in answer_edits.get(sid, {}).items():
                if not 1 <= int(question) <= len(key["answers"]) or answer not in RESOLVED:
                    raise ValueError("คำตอบที่แก้ไขไม่ถูกต้อง")
                answers_by_source[sid][int(question) - 1] = answer
                overridden_by_source[sid].add(int(question))
            with self.flow.connection() as con:
                overridden_by_source[sid].update(
                    int(row[0])
                    for row in con.execute(
                        "SELECT question FROM answer_overrides WHERE source_id=? AND key_id=? AND detection_id IS ?",
                        (sid, key["id"], state["detection_id"]),
                    )
                )

        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        unknown_count = 0
        with self.flow.connection() as con:
            current_key = self.flow._key(con, exam_id)
            if current_key["id"] != key["id"]:
                raise ValueError("เฉลยเปลี่ยนแล้ว กรุณาเปิดตรวจทานใหม่")
            active_sources = {
                row["id"]
                for row in con.execute(
                    "SELECT id FROM sources WHERE exam_id=? AND purpose='student' AND room_id=? AND archived_at IS NULL",
                    (exam_id, room_id),
                )
            }
            if active_sources != set(state_by_id):
                raise ValueError("รายการภาพเปลี่ยนแล้ว กรุณาโหลดรายการใหม่")
            for sid, state in state_by_id.items():
                latest = con.execute(
                    "SELECT id FROM detections WHERE source_id=? ORDER BY rowid DESC LIMIT 1",
                    (sid,),
                ).fetchone()
                if (latest["id"] if latest else None) != state["detection_id"]:
                    raise ValueError("ผลอ่านเปลี่ยนแล้ว กรุณาโหลดรายการใหม่")

            for sid, value in normalized_edits.items():
                con.execute(
                    "INSERT INTO identities VALUES (?,?,?,?,?,?)",
                    (str(uuid4()), sid, value, state_by_id[sid]["detection_id"], "teacher", now),
                )
            for sid, questions in answer_edits.items():
                for question, answer in questions.items():
                    con.execute(
                        "INSERT INTO answer_overrides VALUES (?,?,?,?,?,?,?)",
                        (
                            str(uuid4()),
                            sid,
                            key["id"],
                            state_by_id[sid]["detection_id"],
                            int(question),
                            answer,
                            now,
                        ),
                    )

            maximum = resolve_student_number_constraint(con, exam_id, room_id).maximum
            attendance = {
                int(row["student_number"]): row["status"]
                for row in con.execute(
                    "SELECT student_number,status FROM attendance WHERE room_id=?", (room_id,)
                )
            }
            number_for_source: dict[str, str | None] = {}
            for sid, state in state_by_id.items():
                number = normalized_edits.get(sid, state["number"])
                try:
                    number_for_source[sid] = normalize_number(number) if number else None
                except ValueError:
                    number_for_source[sid] = None
            number_counts: dict[str, int] = {}
            for number in number_for_source.values():
                if number:
                    number_counts[number] = number_counts.get(number, 0) + 1

            prior_rows = list(
                con.execute(
                    "SELECT source_id,student_number,identity_confirmed FROM partial_reviews"
                )
            )
            used_unknown_ordinals = [
                int(row["student_number"].rsplit("#", 1)[1])
                for row in prior_rows
                if not row["identity_confirmed"]
                and row["student_number"].startswith("ไม่ทราบเลขที่ #")
                and row["student_number"].rsplit("#", 1)[1].isdigit()
            ]
            next_unknown = max(used_unknown_ordinals, default=0) + 1

            for sid, state in state_by_id.items():
                source_issues = []
                identity_value = number_for_source[sid]
                identity_valid = bool(
                    identity_value
                    and number_counts.get(identity_value, 0) == 1
                    and (maximum is None or int(identity_value) <= maximum)
                )
                identity_conflict = bool(
                    identity_value and number_counts.get(identity_value, 0) > 1
                )
                out_of_range = bool(
                    identity_value
                    and maximum is not None
                    and int(identity_value) > maximum
                )
                current_review = state["review"]
                reviewed_key = bool(current_review and current_review["key_id"] == key["id"])
                is_teacher_review = bool(reviewed_key and current_review["origin"] == "teacher")
                answers = list(answers_by_source[sid])
                observations = state["detection"].get("answers", [])
                provenance = []
                needs_attention = not reviewed_key
                if state["detection"].get("failure"):
                    source_issues.append("alignment_needs_review")
                    needs_attention = True

                for index, machine_answer in enumerate(answers, start=1):
                    observation = observations[index - 1] if index <= len(observations) else {}
                    classification = observation.get("classification")
                    teacher_confirmed = is_teacher_review or index in overridden_by_source[sid]
                    if machine_answer is None:
                        answers[index - 1] = "unresolved"
                        provenance.append({"question": index, "origin": "review_skipped"})
                        source_issues.append(f"Q{index} unresolved")
                        needs_attention = True
                    else:
                        origin = "teacher_confirmed" if teacher_confirmed else "machine_decision"
                        provenance.append({"question": index, "origin": origin})
                        if classification == "multiple" and not teacher_confirmed:
                            source_issues.append(f"Q{index} ambiguous")
                            needs_attention = True

                if not identity_valid:
                    needs_attention = True
                    if identity_conflict:
                        source_issues.append("identity_conflict")
                    elif out_of_range:
                        source_issues.append("identity_out_of_range")
                    else:
                        source_issues.append("identity_unknown")
                elif identity_value and attendance.get(int(identity_value)) in {
                    "absent",
                    "excused",
                }:
                    source_issues.append("attendance_conflict")
                    needs_attention = True

                if not needs_attention:
                    continue
                source_issues.insert(0, "review_skipped")
                if identity_valid and identity_value is not None:
                    student_number = identity_value
                    identity_confirmed = True
                    identity_origin = "teacher_confirmed"
                    latest_identity = con.execute(
                        "SELECT origin FROM identities WHERE source_id=? ORDER BY rowid DESC LIMIT 1",
                        (sid,),
                    ).fetchone()
                    if latest_identity:
                        identity_origin = latest_identity["origin"]
                else:
                    previous_partial = con.execute(
                        "SELECT student_number,identity_confirmed FROM partial_reviews WHERE source_id=? ORDER BY rowid DESC LIMIT 1",
                        (sid,),
                    ).fetchone()
                    if (
                        previous_partial
                        and not previous_partial["identity_confirmed"]
                        and previous_partial["student_number"].startswith("ไม่ทราบเลขที่ #")
                    ):
                        student_number = previous_partial["student_number"]
                    else:
                        student_number = f"ไม่ทราบเลขที่ #{next_unknown}"
                        next_unknown += 1
                    identity_confirmed = False
                    identity_origin = "unknown"
                    unknown_count += 1

                con.execute(
                    "INSERT INTO partial_reviews "
                    "(id,source_id,key_id,detection_id,student_number,identity_confirmed,identity_origin,answers,answer_provenance,review_issues,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        sid,
                        key["id"],
                        state["detection_id"],
                        student_number,
                        int(identity_confirmed),
                        identity_origin,
                        json.dumps(answers),
                        json.dumps(provenance),
                        json.dumps(list(dict.fromkeys(source_issues)), ensure_ascii=False),
                        now,
                    ),
                )
                inserted += 1

        return {"partial_sheets": inserted, "unknown_identities": unknown_count}
