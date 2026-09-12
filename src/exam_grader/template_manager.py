"""Answer-sheet template definitions, geometry mapping, and lifecycle management."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# Canonical internal choices used across the entire grading engine.
CANONICAL_CHOICES = ("A", "B", "C", "D", "E")

DEFAULT_THAI_LABELS = ("ก", "ข", "ค", "ง", "จ")


@dataclass(frozen=True)
class AnswerBlock:
    """A contiguous grid of question rows and choice columns."""

    block_index: int
    question_start: int
    question_end: int
    rows: int
    choice_count: int
    col_boundaries: list[int]  # choice_count + 1 pixel values
    row_boundaries: list[int]  # rows + 1 pixel values

    def __post_init__(self) -> None:
        if self.choice_count < 2 or self.choice_count > 5:
            raise ValueError("จำนวนตัวเลือกในแต่ละชุดต้องอยู่ระหว่าง 2 ถึง 5 ตัวเลือก")
        if self.rows < 1:
            raise ValueError("จำนวนข้อในชุดต้องมากกว่า 0")
        expected_q_count = self.question_end - self.question_start + 1
        if expected_q_count != self.rows:
            raise ValueError(
                f"ช่วงข้อ ({self.question_start}–{self.question_end}) ไม่สอดคล้องกับจำนวนแถว ({self.rows})"
            )
        if len(self.col_boundaries) != self.choice_count + 1:
            raise ValueError(
                f"เส้นแบ่งคอลัมน์ต้องมี {self.choice_count + 1} ค่า (ได้รับ {len(self.col_boundaries)})"
            )
        if len(self.row_boundaries) != self.rows + 1:
            raise ValueError(f"เส้นแบ่งแถวต้องมี {self.rows + 1} ค่า (ได้รับ {len(self.row_boundaries)})")
        for i in range(len(self.col_boundaries) - 1):
            if self.col_boundaries[i] >= self.col_boundaries[i + 1]:
                raise ValueError("พิกัดคอลัมน์ต้องเรียงจากน้อยไปมาก")
        for i in range(len(self.row_boundaries) - 1):
            if self.row_boundaries[i] >= self.row_boundaries[i + 1]:
                raise ValueError("พิกัดแถวต้องเรียงจากน้อยไปมาก")


@dataclass(frozen=True)
class TemplateDefinition:
    """Versioned answer sheet geometry and metadata contract."""

    template_id: str
    name: str
    kind: str  # "builtin" | "custom"
    version: int
    canonical_width: int
    canonical_height: int
    choice_count: int  # 2 to 5
    choice_labels: list[str]  # Canonical internal labels e.g. ["A", "B", "C", "D"]
    display_choice_labels: list[str]  # e.g. ["ก", "ข", "ค", "ง"] or ["A", "B", "C", "D"]
    choice_map: dict[str, str]  # e.g. {"ก": "A", "ข": "B", "ค": "C", "ง": "D", "A": "A", ...}
    question_count: int
    answer_blocks: list[AnswerBlock]
    student_number_roi: tuple[int, int, int, int] | None  # (x1, y1, x2, y2)
    score_roi: tuple[int, int, int, int] | None  # (x1, y1, x2, y2)
    reference_sha256: str
    cell_inset: int = 4
    registration_config: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.template_id.strip():
            raise ValueError("รหัสรูปแบบกระดาษคำตอบต้องไม่ว่าง")
        if not self.name.strip():
            raise ValueError("ชื่อรูปแบบกระดาษคำตอบต้องไม่ว่าง")
        if self.kind not in ("builtin", "custom"):
            raise ValueError(f"ชนิดรูปแบบกระดาษคำตอบไม่ถูกต้อง: {self.kind}")
        if self.version < 1:
            raise ValueError("เวอร์ชันต้องเป็นจำนวนเต็มบวก")
        if not 1 <= self.question_count <= 60:
            raise ValueError("จำนวนข้อต้องอยู่ระหว่าง 1 ถึง 60 ข้อ")
        if not 2 <= self.choice_count <= 5:
            raise ValueError("จำนวนตัวเลือกต้องอยู่ระหว่าง 2 ถึง 5 ตัวเลือก")
        if len(self.choice_labels) != self.choice_count:
            raise ValueError("จำนวน choice_labels ไม่ตรงกับ choice_count")
        if len(self.display_choice_labels) != self.choice_count:
            raise ValueError("จำนวน display_choice_labels ไม่ตรงกับ choice_count")
        if not self.answer_blocks:
            raise ValueError("ต้องมีชุดคำตอบอย่างน้อย 1 ชุด")

        # Validate answer blocks coverage
        covered_questions: set[int] = set()
        for block in self.answer_blocks:
            for q in range(block.question_start, block.question_end + 1):
                if q in covered_questions:
                    raise ValueError(f"ข้อ {q} ซ้ำซ้อนในหลายชุดคำตอบ")
                covered_questions.add(q)
            if block.choice_count != self.choice_count:
                raise ValueError(
                    f"ชุดคำตอบที่ {block.block_index} มีจำนวนตัวเลือก ({block.choice_count}) ไม่ตรงกับแม่แบบ ({self.choice_count})"
                )

        expected_set = set(range(1, self.question_count + 1))
        if covered_questions != expected_set:
            missing = sorted(expected_set - covered_questions)
            raise ValueError(f"มีข้อที่ไม่ได้ระบุพิกัดในแม่แบบ: {missing[:5]}")

        # Validate bounding coordinates are within canonical dimensions
        w = self.canonical_width
        h = self.canonical_height
        for block in self.answer_blocks:
            if block.col_boundaries[0] < 0 or block.col_boundaries[-1] > w:
                raise ValueError(f"ชุดคำตอบที่ {block.block_index} อยู่นอกขอบเขตแนวนอนของภาพ")
            if block.row_boundaries[0] < 0 or block.row_boundaries[-1] > h:
                raise ValueError(f"ชุดคำตอบที่ {block.block_index} อยู่นอกขอบเขตแนวตั้งของภาพ")

        if self.student_number_roi is not None:
            x1, y1, x2, y2 = self.student_number_roi
            if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
                raise ValueError("พิกัด student_number_roi อยู่นอกภาพหรือไม่ถูกต้อง")

        if self.score_roi is not None:
            x1, y1, x2, y2 = self.score_roi
            if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
                raise ValueError("พิกัด score_roi อยู่นอกภาพหรือไม่ถูกต้อง")

    def canonical_choice(self, label: str) -> str:
        """Map any visual/display label to internal canonical choice (A, B, C, D, E)."""
        normalized = label.strip()
        if normalized in self.choice_map:
            return self.choice_map[normalized]
        upper = normalized.upper()
        if upper in self.choice_labels:
            return upper
        raise ValueError(f"ไม่พบตัวเลือกที่ตรงกับ: {label}")

    def display_choice(self, canonical: str) -> str:
        """Map canonical internal choice (A-E) to display label for teachers."""
        upper = canonical.strip().upper()
        if upper in self.choice_labels:
            idx = self.choice_labels.index(upper)
            return self.display_choice_labels[idx]
        return upper

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemplateDefinition:
        blocks = [
            AnswerBlock(**b) if isinstance(b, dict) else b for b in data.get("answer_blocks", [])
        ]
        student_roi = (
            tuple(data["student_number_roi"])
            if data.get("student_number_roi") is not None
            else None
        )
        score_roi = tuple(data["score_roi"]) if data.get("score_roi") is not None else None
        return cls(
            template_id=data["template_id"],
            name=data["name"],
            kind=data["kind"],
            version=int(data["version"]),
            canonical_width=int(data["canonical_width"]),
            canonical_height=int(data["canonical_height"]),
            choice_count=int(data["choice_count"]),
            choice_labels=list(data["choice_labels"]),
            display_choice_labels=list(data["display_choice_labels"]),
            choice_map=dict(data["choice_map"]),
            question_count=int(data["question_count"]),
            answer_blocks=blocks,
            student_number_roi=student_roi,  # type: ignore[arg-type]
            score_roi=score_roi,  # type: ignore[arg-type]
            reference_sha256=data.get("reference_sha256", ""),
            cell_inset=int(data.get("cell_inset", 4)),
            registration_config=dict(data.get("registration_config", {})),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


def cell_box_rect_for_template(
    template_def: TemplateDefinition, question: int, choice: int
) -> tuple[int, int, int, int]:
    """Return the outer cell boundary box (x, y, w, h) without inset."""
    if not 1 <= question <= template_def.question_count:
        raise ValueError(f"Invalid question: {question} (max {template_def.question_count})")
    if not 0 <= choice < template_def.choice_count:
        raise ValueError(f"Invalid choice: {choice} (max {template_def.choice_count - 1})")

    for block in template_def.answer_blocks:
        if block.question_start <= question <= block.question_end:
            row_idx = question - block.question_start
            x = block.col_boundaries[choice]
            y = block.row_boundaries[row_idx]
            w = block.col_boundaries[choice + 1] - x
            h = block.row_boundaries[row_idx + 1] - y
            return x, y, w, h

    raise ValueError(f"Question {question} not found in any answer block")


def cell_rect_for_template(
    template_def: TemplateDefinition, question: int, choice: int
) -> tuple[int, int, int, int]:
    """Return ink-analysis cell rect (x, y, w, h) excluding cell_inset border pixels."""
    x, y, w, h = cell_box_rect_for_template(template_def, question, choice)
    inset = template_def.cell_inset
    return x + inset, y + inset, w - 2 * inset, h - 2 * inset


def _get_resource_path(relative_path: str | Path) -> Path:
    """Get resource path that works in both dev and frozen (PyInstaller) mode."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller .exe
        base = Path(getattr(sys, "_MEIPASS", ""))
        candidate = base / relative_path
        if candidate.exists():
            return candidate
        candidate_pkg = base / "exam_grader" / relative_path
        if candidate_pkg.exists():
            return candidate_pkg
        return candidate
    else:
        # Running in development
        base = Path(__file__).parent
        return base / relative_path


def default_1_template_definition() -> TemplateDefinition:
    """Construct TemplateDefinition wrapping existing built-in Default #1."""
    data = json.loads(_get_resource_path("resources/template.json").read_text(encoding="utf-8"))
    groups = data["groups"]
    rows = data["rows"]
    blocks: list[AnswerBlock] = []
    for i, col_bounds in enumerate(groups):
        q_start = i * 15 + 1
        q_end = (i + 1) * 15
        blocks.append(
            AnswerBlock(
                block_index=i,
                question_start=q_start,
                question_end=q_end,
                rows=15,
                choice_count=5,
                col_boundaries=list(col_bounds),
                row_boundaries=list(rows),
            )
        )

    canonical = list(CANONICAL_CHOICES[:5])
    display = list(DEFAULT_THAI_LABELS[:5])
    choice_map = {
        "A": "A",
        "B": "B",
        "C": "C",
        "D": "D",
        "E": "E",
        "a": "A",
        "b": "B",
        "c": "C",
        "d": "D",
        "e": "E",
        "ก": "A",
        "ข": "B",
        "ค": "C",
        "ง": "D",
        "จ": "E",
        "1": "A",
        "2": "B",
        "3": "C",
        "4": "D",
        "5": "E",
    }

    student_roi = tuple(data["student_number_roi"])
    score_roi = tuple(data["score_roi"])

    return TemplateDefinition(
        template_id="default-1",
        name="Default #1 — กระดาษคำตอบมาตรฐาน (60 ข้อ · 5 ตัวเลือก)",
        kind="builtin",
        version=1,
        canonical_width=data["width"],
        canonical_height=data["height"],
        choice_count=5,
        choice_labels=canonical,
        display_choice_labels=display,
        choice_map=choice_map,
        question_count=60,
        answer_blocks=blocks,
        student_number_roi=student_roi,  # type: ignore[arg-type]
        score_roi=score_roi,  # type: ignore[arg-type]
        reference_sha256=data["reference_sha256"],
        registration_config={"color_theme": "green"},
        created_at="2026-09-08T00:00:00Z",
        updated_at="2026-09-08T00:00:00Z",
    )


BUILTIN_TEMPLATE_IDS = ("default-1", "default-2", "default-3")


def load_builtin_template(template_id: str) -> TemplateDefinition:
    """Load a built-in template definition by ID."""
    if template_id == "default-1":
        return default_1_template_definition()
    if template_id == "default-2":
        path = _get_resource_path("resources/template_default2.json")
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return TemplateDefinition.from_dict(data)
        except (FileNotFoundError, ModuleNotFoundError) as err:
            raise ValueError("แม่แบบ Default #2 ยังไม่ได้ถูกบรรจุหรือยังอยู่ระหว่างการปรับเทียบ") from err
    if template_id == "default-3":
        path = _get_resource_path("resources/template_default3.json")
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return TemplateDefinition.from_dict(data)
        except (FileNotFoundError, ModuleNotFoundError) as err:
            raise ValueError("แม่แบบ Default #3 ยังไม่ได้ถูกบรรจุหรือยังอยู่ระหว่างการปรับเทียบ") from err
    raise ValueError(f"ไม่พบแม่แบบในตัว: {template_id}")


def get_reference_image(
    template_def: TemplateDefinition,
    app_data_dir: Path | None = None,
    reference_override: np.ndarray | None = None,
) -> np.ndarray:
    """Load and verify reference image for the given template definition.

    If reference_override is provided, it is returned directly (used for in-memory previews).
    Built-ins are bundled inside the package resources.
    Custom templates are loaded from content-addressed storage in app_data_dir.
    """
    if reference_override is not None:
        if not isinstance(reference_override, np.ndarray) or reference_override.size == 0:
            raise ValueError("ภาพอ้างอิง in-memory ไม่ถูกต้อง")
        return reference_override.copy()

    if template_def.kind == "builtin":
        if template_def.template_id == "default-1":
            data = _get_resource_path("resources/reference.png").read_bytes()
        elif template_def.template_id == "default-2":
            data = _get_resource_path("resources/reference_default2.png").read_bytes()
        elif template_def.template_id == "default-3":
            data = _get_resource_path("resources/reference_default3.png").read_bytes()
        else:
            raise ValueError(f"ไม่รู้จัก built-in template: {template_def.template_id}")
    else:
        if app_data_dir is None:
            raise ValueError("จำเป็นต้องระบุ app_data_dir สำหรับแม่แบบกำหนดเอง")
        ref_path = (
            app_data_dir / "templates" / "references" / f"{template_def.reference_sha256}.png"
        )
        if not ref_path.exists():
            raise ValueError(f"ไม่พบไฟล์ภาพอ้างอิงแม่แบบ: {ref_path.name}")
        data = ref_path.read_bytes()

    computed_sha = hashlib.sha256(data).hexdigest()
    if computed_sha != template_def.reference_sha256:
        raise ValueError("ภาพอ้างอิงไม่ตรงกับค่าแฮชที่บันทึกไว้ในแม่แบบ")

    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("อ่านไฟล์ภาพอ้างอิงไม่ได้")
    return image


def save_custom_reference_image(app_data_dir: Path, image_bytes: bytes) -> str:
    """Save a custom reference image to content-addressed storage and return SHA-256."""
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    ref_dir = app_data_dir / "templates" / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)
    target = ref_dir / f"{sha256}.png"
    if not target.exists():
        target.write_bytes(image_bytes)
    return sha256


def load_exam_template_def(database: Any, exam_id: str) -> TemplateDefinition:
    """Resolve the TemplateDefinition bound to an exam from ExamStore, Path, or connection."""
    import sqlite3

    template_id = "default-1"
    template_version: int | None = None
    db_path: Path | None = None
    if hasattr(database, "path") and isinstance(database.path, (Path, str)):
        db_path = Path(database.path)
    elif isinstance(database, (Path, str)):
        db_path = Path(database)

    if db_path is not None and db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT template_id, template_version FROM exams WHERE id=?", (exam_id,)
                ).fetchone()
                if row:
                    if "template_id" in row.keys() and row["template_id"]:
                        template_id = str(row["template_id"])
                    if "template_version" in row.keys() and row["template_version"] is not None:
                        template_version = int(row["template_version"])
        except Exception:
            template_id = "default-1"

    if template_id in BUILTIN_TEMPLATE_IDS:
        return load_builtin_template(template_id)

    if db_path is not None and db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                if template_version is not None:
                    row = conn.execute(
                        "SELECT definition FROM templates WHERE id=? AND version=? AND deleted_at IS NULL",
                        (template_id, template_version),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT definition FROM templates WHERE id=? AND deleted_at IS NULL ORDER BY version DESC LIMIT 1",
                        (template_id,),
                    ).fetchone()
                if row and row["definition"]:
                    return TemplateDefinition.from_dict(json.loads(row["definition"]))
        except Exception:
            pass

    return load_builtin_template("default-1")
