"""Single source of truth for room-aware Student Number validity."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class StudentNumberConstraint:
    room_id: str
    maximum: int | None
    source: str

    @property
    def is_known(self) -> bool:
        return self.maximum is not None

    def allows(self, value: int) -> bool:
        return value > 0 and (self.maximum is None or value <= self.maximum)

    def filter_candidates(
        self, candidates: Iterable[str], scores: Mapping[str, float]
    ) -> list[str]:
        values = [
            candidate
            for candidate in candidates
            if candidate.isascii() and candidate.isdigit() and self.allows(int(candidate))
        ]
        return sorted(set(values), key=lambda value: (-scores.get(value, 0.0), value))


def resolve_student_number_constraint(
    connection: sqlite3.Connection,
    exam_id: str,
    room_id: str | None = None,
) -> StudentNumberConstraint:
    """Resolve explicit room max, then the migrated legacy initial-room max.

    Schema v16 backfills the first room selected by the same stable ordering
    used by room resolution. A newly added room remains unknown when its own
    max is NULL, even if another room in the exam has a max.
    """
    if room_id is None:
        room = connection.execute(
            "SELECT id,expected_number_max,sort_order FROM exam_rooms "
            "WHERE exam_id=? ORDER BY sort_order,id LIMIT 1",
            (exam_id,),
        ).fetchone()
    else:
        room = connection.execute(
            "SELECT id,expected_number_max,sort_order FROM exam_rooms "
            "WHERE id=? AND exam_id=?",
            (room_id, exam_id),
        ).fetchone()
    if room is None:
        raise ValueError("ห้องไม่ตรงกับข้อสอบ")

    room_max = room["expected_number_max"]
    if room_max is not None:
        return StudentNumberConstraint(str(room["id"]), int(room_max), "room")

    first_room = connection.execute(
        "SELECT id FROM exam_rooms WHERE exam_id=? ORDER BY sort_order,id LIMIT 1",
        (exam_id,),
    ).fetchone()
    legacy = connection.execute(
        "SELECT expected_number_max FROM exams WHERE id=?", (exam_id,)
    ).fetchone()
    if first_room is not None and str(first_room["id"]) == str(room["id"]) and legacy[0] is not None:
        return StudentNumberConstraint(str(room["id"]), int(legacy[0]), "legacy_exam")
    return StudentNumberConstraint(str(room["id"]), None, "unknown")
