"""Qt-free domain contracts for the foundation milestone."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExamDetails:
    name: str
    academic_year: str
    grade: str
    room: str
    subject: str
    question_count: int = 60
    expected_number_max: int | None = None

    def __post_init__(self) -> None:
        for field in ("name", "academic_year", "grade", "room", "subject"):
            value = getattr(self, field).strip()
            if not value:
                raise ValueError("กรุณากรอกข้อมูลข้อสอบให้ครบ")
            if len(value) > 200:
                raise ValueError("ข้อมูลแต่ละช่องต้องไม่เกิน 200 ตัวอักษร")
            object.__setattr__(self, field, value)
        if not 1 <= self.question_count <= 60:
            raise ValueError("จำนวนข้อต้องอยู่ระหว่าง 1 ถึง 60 ข้อ")
        if self.expected_number_max is not None and not 1 <= self.expected_number_max <= 9999:
            raise ValueError("เลขที่คาดหวังต้องอยู่ระหว่าง 1 ถึง 9999")


@dataclass(frozen=True)
class Exam:
    id: str
    details: ExamDetails
    created_at: str
