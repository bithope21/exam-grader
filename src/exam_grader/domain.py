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
    template_id: str = "default-1"
    template_version: int = 1

    def __post_init__(self) -> None:
        for field in ("name", "academic_year", "grade", "subject"):
            value = getattr(self, field).strip()
            if not value:
                raise ValueError("กรุณากรอกข้อมูลข้อสอบให้ครบ")
            if len(value) > 200:
                raise ValueError("ข้อมูลแต่ละช่องต้องไม่เกิน 200 ตัวอักษร")
            object.__setattr__(self, field, value)
        room = self.room.strip()
        if len(room) > 200:
            raise ValueError("ข้อมูลแต่ละช่องต้องไม่เกิน 200 ตัวอักษร")
        object.__setattr__(self, "room", room)
        if not 1 <= self.question_count <= 60:
            raise ValueError("จำนวนข้อต้องอยู่ระหว่าง 1 ถึง 60 ข้อ")
        if self.expected_number_max is not None and not 1 <= self.expected_number_max <= 9999:
            raise ValueError("เลขที่คาดหวังต้องอยู่ระหว่าง 1 ถึง 9999")
        template_id = (self.template_id or "default-1").strip()
        if not template_id:
            raise ValueError("รหัสรูปแบบกระดาษคำตอบต้องไม่ว่าง")
        object.__setattr__(self, "template_id", template_id)
        template_version = int(self.template_version or 1)
        if template_version < 1:
            raise ValueError("เวอร์ชันของรูปแบบกระดาษคำตอบต้องเป็นจำนวนเต็มบวก")
        object.__setattr__(self, "template_version", template_version)


@dataclass(frozen=True)
class Exam:
    id: str
    details: ExamDetails
    created_at: str


@dataclass(frozen=True)
class ExamRoom:
    id: str
    exam_id: str
    label: str
    sort_order: int
    created_at: str
    updated_at: str
    expected_number_max: int | None = None

    def __post_init__(self) -> None:
        label = self.label.strip()
        if not label:
            raise ValueError("ชื่อห้องต้องไม่ว่าง")
        if len(label) > 200:
            raise ValueError("ชื่อห้องต้องไม่เกิน 200 ตัวอักษร")
        object.__setattr__(self, "label", label)
        if self.expected_number_max is not None and not 1 <= self.expected_number_max <= 9999:
            raise ValueError("เลขที่คาดหวังต้องอยู่ระหว่าง 1 ถึง 9999")
