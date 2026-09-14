"""Deterministic editable geometry operations for answer-sheet calibration.

The editor keeps a permissive in-memory draft while a teacher adjusts blocks one
at a time. Only :meth:`CalibrationDraft.compile` creates the strict canonical
``TemplateDefinition`` consumed by storage and OMR.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from exam_grader.template_manager import (
    MIN_EDITOR_CELL_CORE,
    AnswerBlock,
    TemplateDefinition,
)

Axis = Literal["row", "col"]


@dataclass(frozen=True)
class CalibrationDraft(TemplateDefinition):
    """Template-shaped UI state that permits temporarily inconsistent blocks."""

    def __post_init__(self) -> None:
        # Keep draft-level scalar bounds, but defer coverage/choice consistency to
        # compile(). Deleting the last block and partial choice-count edits are
        # valid editor states and must remain renderable.
        if not self.template_id.strip() or not self.name.strip():
            raise ValueError("รหัสและชื่อแม่แบบต้องไม่ว่าง")
        if self.canonical_width < 1 or self.canonical_height < 1:
            raise ValueError("ขนาดภาพแม่แบบไม่ถูกต้อง")
        if not 0 <= self.question_count <= 60:
            raise ValueError("จำนวนข้อร่างต้องอยู่ระหว่าง 0 ถึง 60 ข้อ")
        if not 2 <= self.choice_count <= 5:
            raise ValueError("จำนวนตัวเลือกต้องอยู่ระหว่าง 2 ถึง 5 ตัวเลือก")
        if self.cell_inset < 0:
            raise ValueError("ระยะขอบช่องต้องไม่ติดลบ")

    @classmethod
    def from_template(cls, template: TemplateDefinition) -> CalibrationDraft:
        return cls(
            template_id=template.template_id,
            name=template.name,
            kind=template.kind,
            version=template.version,
            canonical_width=template.canonical_width,
            canonical_height=template.canonical_height,
            choice_count=template.choice_count,
            choice_labels=list(template.choice_labels),
            display_choice_labels=list(template.display_choice_labels),
            choice_map=dict(template.choice_map),
            question_count=template.question_count,
            answer_blocks=list(template.answer_blocks),
            student_number_roi=template.student_number_roi,
            score_roi=template.score_roi,
            reference_sha256=template.reference_sha256,
            cell_inset=template.cell_inset,
            registration_config=dict(template.registration_config),
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    def compile(self) -> TemplateDefinition:
        """Validate the complete draft and return the strict persisted template."""
        if not self.answer_blocks:
            raise ValueError("ต้องมีชุดคำตอบอย่างน้อย 1 ชุด")
        if sum(block.rows for block in self.answer_blocks) != self.question_count:
            raise ValueError("จำนวนข้อรวมต้องตรงกับจำนวนแถวของทุกชุดคำตอบ")
        if any(block.choice_count != self.choice_count for block in self.answer_blocks):
            raise ValueError("จำนวนตัวเลือกของทุกชุดต้องตรงกับจำนวนตัวเลือกแม่แบบ")
        for block in self.answer_blocks:
            validate_block_geometry(
                block,
                canonical_width=self.canonical_width,
                canonical_height=self.canonical_height,
                cell_inset=self.cell_inset,
            )
        return TemplateDefinition(
            template_id=self.template_id,
            name=self.name,
            kind=self.kind,
            version=self.version,
            canonical_width=self.canonical_width,
            canonical_height=self.canonical_height,
            choice_count=self.choice_count,
            choice_labels=list(self.choice_labels),
            display_choice_labels=list(self.display_choice_labels),
            choice_map=dict(self.choice_map),
            question_count=self.question_count,
            answer_blocks=list(self.answer_blocks),
            student_number_roi=self.student_number_roi,
            score_roi=self.score_roi,
            reference_sha256=self.reference_sha256,
            cell_inset=self.cell_inset,
            registration_config=dict(self.registration_config),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


def _minimum_span(cell_inset: int) -> int:
    """Keep at least a four-pixel editing core after both cell insets."""
    return 2 * max(0, int(cell_inset)) + MIN_EDITOR_CELL_CORE


def validate_block_geometry(
    block: AnswerBlock,
    *,
    canonical_width: int,
    canonical_height: int,
    cell_inset: int,
) -> None:
    """Reject out-of-image or too-small cells before geometry reaches OMR."""
    if block.col_boundaries[0] < 0 or block.col_boundaries[-1] > canonical_width:
        raise ValueError("ตารางอยู่นอกขอบเขตแนวนอนของภาพ")
    if block.row_boundaries[0] < 0 or block.row_boundaries[-1] > canonical_height:
        raise ValueError("ตารางอยู่นอกขอบเขตแนวตั้งของภาพ")
    minimum = _minimum_span(cell_inset)
    if any(b - a < minimum for a, b in zip(block.col_boundaries, block.col_boundaries[1:])):
        raise ValueError("ความกว้างช่องน้อยเกินไปสำหรับระยะขอบ OMR")
    if any(b - a < minimum for a, b in zip(block.row_boundaries, block.row_boundaries[1:])):
        raise ValueError("ความสูงช่องน้อยเกินไปสำหรับระยะขอบ OMR")


def cell_box_for_block(
    block: AnswerBlock, row_index: int, choice_index: int
) -> tuple[int, int, int, int]:
    """Return one cell's canonical outer box from its row/column boundaries."""
    if not 0 <= row_index < block.rows:
        raise IndexError("row index is outside the answer block")
    if not 0 <= choice_index < block.choice_count:
        raise IndexError("choice index is outside the answer block")
    x1, x2 = block.col_boundaries[choice_index : choice_index + 2]
    y1, y2 = block.row_boundaries[row_index : row_index + 2]
    return x1, y1, x2 - x1, y2 - y1


def cell_rect_for_block(
    block: AnswerBlock, row_index: int, choice_index: int, cell_inset: int
) -> tuple[int, int, int, int]:
    """Return a derived OMR cell crop without storing duplicate cell geometry."""
    x, y, width, height = cell_box_for_block(block, row_index, choice_index)
    inset = max(0, int(cell_inset))
    return x + inset, y + inset, width - 2 * inset, height - 2 * inset


def mark_user_edited(block: AnswerBlock, **geometry: Any) -> AnswerBlock:
    """Apply changed fields while retaining original detector provenance."""
    return replace(block, **geometry, geometry_state="user_edited")


def set_boundary_position(
    block: AnswerBlock,
    *,
    axis: Axis,
    index: int,
    position: int,
    canonical_width: int,
    canonical_height: int,
    cell_inset: int,
) -> AnswerBlock:
    """Move one grid line, preserving all other non-uniform cell spacings."""
    boundaries = list(block.row_boundaries if axis == "row" else block.col_boundaries)
    if axis not in ("row", "col") or not 0 <= index < len(boundaries):
        raise ValueError("เลือกเส้นตารางไม่ถูกต้อง")
    minimum = _minimum_span(cell_inset)
    low = 0 if index == 0 else boundaries[index - 1] + minimum
    high = (
        canonical_height if axis == "row" else canonical_width
    ) if index == len(boundaries) - 1 else boundaries[index + 1] - minimum
    if not low <= int(position) <= high:
        raise ValueError("เส้นต้องอยู่ในภาพและเหลือพื้นที่ช่องเพียงพอ")
    boundaries[index] = int(position)
    edited = mark_user_edited(
        block,
        row_boundaries=boundaries if axis == "row" else block.row_boundaries,
        col_boundaries=boundaries if axis == "col" else block.col_boundaries,
    )
    validate_block_geometry(
        edited,
        canonical_width=canonical_width,
        canonical_height=canonical_height,
        cell_inset=cell_inset,
    )
    return edited


def translate_block(
    block: AnswerBlock,
    *,
    dx: int,
    dy: int,
    canonical_width: int,
    canonical_height: int,
    cell_inset: int,
) -> AnswerBlock:
    """Translate a full grid if every line stays inside the canonical image."""
    edited = mark_user_edited(
        block,
        col_boundaries=[x + int(dx) for x in block.col_boundaries],
        row_boundaries=[y + int(dy) for y in block.row_boundaries],
    )
    validate_block_geometry(
        edited,
        canonical_width=canonical_width,
        canonical_height=canonical_height,
        cell_inset=cell_inset,
    )
    return edited


def resize_block_from_origin(
    origin: AnswerBlock,
    *,
    rect: tuple[int, int, int, int],
    canonical_width: int,
    canonical_height: int,
    cell_inset: int,
) -> AnswerBlock:
    """Affine-resize a grid from immutable drag-origin lines, without drift."""
    x1, y1, x2, y2 = (int(value) for value in rect)
    if not (0 <= x1 < x2 <= canonical_width and 0 <= y1 < y2 <= canonical_height):
        raise ValueError("กรอบตารางต้องอยู่ภายในขอบเขตภาพ")
    old_x1, old_y1 = origin.col_boundaries[0], origin.row_boundaries[0]
    old_x2, old_y2 = origin.col_boundaries[-1], origin.row_boundaries[-1]
    minimum = _minimum_span(cell_inset)
    if x2 - x1 < origin.choice_count * minimum or y2 - y1 < origin.rows * minimum:
        raise ValueError("กรอบใหม่เล็กเกินไปสำหรับขนาดช่องและระยะขอบ OMR")
    width_ratio = (x2 - x1) / (old_x2 - old_x1)
    height_ratio = (y2 - y1) / (old_y2 - old_y1)
    columns = [round(x1 + (value - old_x1) * width_ratio) for value in origin.col_boundaries]
    rows = [round(y1 + (value - old_y1) * height_ratio) for value in origin.row_boundaries]
    edited = mark_user_edited(origin, col_boundaries=columns, row_boundaries=rows)
    validate_block_geometry(
        edited,
        canonical_width=canonical_width,
        canonical_height=canonical_height,
        cell_inset=cell_inset,
    )
    return edited


def split_cell(
    block: AnswerBlock,
    *,
    axis: Axis,
    interval_index: int | None = None,
    cell_inset: int,
) -> AnswerBlock:
    """Add a row/choice by bisecting one existing non-uniform interval."""
    if axis not in ("row", "col"):
        raise ValueError("เลือกแนวเส้นตารางไม่ถูกต้อง")
    boundaries = list(block.row_boundaries if axis == "row" else block.col_boundaries)
    max_cells = 60 if axis == "row" else 5
    count = block.rows if axis == "row" else block.choice_count
    if count >= max_cells:
        raise ValueError("จำนวนแถว/ตัวเลือกถึงขีดจำกัดแล้ว")
    if interval_index is None:
        interval_index = max(
            range(len(boundaries) - 1),
            key=lambda i: boundaries[i + 1] - boundaries[i],
        )
    if not 0 <= interval_index < len(boundaries) - 1:
        raise ValueError("เลือกช่วงช่องไม่ถูกต้อง")
    left, right = boundaries[interval_index : interval_index + 2]
    minimum = _minimum_span(cell_inset)
    if right - left < 2 * minimum:
        raise ValueError("ช่วงช่องแคบเกินไปที่จะแบ่งเพิ่ม")
    boundaries.insert(interval_index + 1, (left + right) // 2)
    if axis == "row":
        rows = block.rows + 1
        return mark_user_edited(
            block,
            rows=rows,
            question_end=block.question_start + rows - 1,
            row_boundaries=boundaries,
        )
    choices = block.choice_count + 1
    return mark_user_edited(block, choice_count=choices, col_boundaries=boundaries)


def remove_grid_line(block: AnswerBlock, *, axis: Axis, boundary_index: int) -> AnswerBlock:
    """Delete one interior line, merging the two neighboring row/choice cells."""
    if axis not in ("row", "col"):
        raise ValueError("เลือกแนวเส้นตารางไม่ถูกต้อง")
    boundaries = list(block.row_boundaries if axis == "row" else block.col_boundaries)
    count = block.rows if axis == "row" else block.choice_count
    minimum_count = 1 if axis == "row" else 2
    if count <= minimum_count:
        raise ValueError("ไม่สามารถลบแถว/ตัวเลือกสุดท้ายได้")
    if not 0 < boundary_index < len(boundaries) - 1:
        raise ValueError("ต้องเลือกเส้นภายในตารางเพื่อลบ")
    del boundaries[boundary_index]
    if axis == "row":
        rows = block.rows - 1
        return mark_user_edited(
            block,
            rows=rows,
            question_end=block.question_start + rows - 1,
            row_boundaries=boundaries,
        )
    choices = block.choice_count - 1
    return mark_user_edited(block, choice_count=choices, col_boundaries=boundaries)


def append_row(
    block: AnswerBlock,
    *,
    canonical_height: int,
    cell_inset: int,
    step: int | None = None,
) -> AnswerBlock:
    """Append a new question row at the bottom of the block, matching existing row height."""
    if block.rows >= 60:
        raise ValueError("จำนวนแถวถึงขีดจำกัดสูงสุด (60 ข้อ) แล้ว")
    if len(block.row_boundaries) < 2:
        raise ValueError("ข้อมูลขอบเขตแถวไม่สมบูรณ์")

    if step is None:
        diffs = [b - a for a, b in zip(block.row_boundaries, block.row_boundaries[1:])]
        step = diffs[-1] if diffs else 30

    minimum = _minimum_span(cell_inset)
    step = max(minimum, int(step))
    new_y = block.row_boundaries[-1] + step
    if new_y > canonical_height:
        raise ValueError("ไม่สามารถเพิ่มแถวได้เนื่องจากล้นขอบล่างของกระดาษ")

    new_boundaries = list(block.row_boundaries) + [new_y]
    new_rows = block.rows + 1
    edited = mark_user_edited(
        block,
        rows=new_rows,
        question_end=block.question_start + new_rows - 1,
        row_boundaries=new_boundaries,
    )
    validate_block_geometry(
        edited,
        canonical_width=100000,  # col boundaries unchanged
        canonical_height=canonical_height,
        cell_inset=cell_inset,
    )
    return edited


def remove_row_at_end(block: AnswerBlock) -> AnswerBlock:
    """Remove the bottom-most row from the block."""
    if block.rows <= 1:
        raise ValueError("ต้องมีแถวคำตอบอย่างน้อย 1 แถวในชุดคำตอบ")
    new_boundaries = list(block.row_boundaries[:-1])
    new_rows = block.rows - 1
    return mark_user_edited(
        block,
        rows=new_rows,
        question_end=block.question_start + new_rows - 1,
        row_boundaries=new_boundaries,
    )


def set_block_row_count(
    block: AnswerBlock,
    target_rows: int,
    *,
    canonical_height: int,
    cell_inset: int,
) -> AnswerBlock:
    """Set the exact row count of the block by extending or trimming at the bottom."""
    target = int(target_rows)
    if not 1 <= target <= 60:
        raise ValueError("จำนวนแถวต้องอยู่ระหว่าง 1 ถึง 60 แถว")
    if target == block.rows:
        return block

    current = block
    if target < block.rows:
        while current.rows > target:
            current = remove_row_at_end(current)
    else:
        while current.rows < target:
            current = append_row(current, canonical_height=canonical_height, cell_inset=cell_inset)

    return current


def append_choice(
    block: AnswerBlock,
    *,
    canonical_width: int,
    cell_inset: int,
    step: int | None = None,
) -> AnswerBlock:
    """Append a choice column at the right of the block."""
    if block.choice_count >= 5:
        raise ValueError("จำนวนตัวเลือกสูงสุดคือ 5 ตัวเลือก (ก-จ หรือ A-E)")
    if len(block.col_boundaries) < 2:
        raise ValueError("ข้อมูลขอบเขตคอลัมน์ไม่สมบูรณ์")

    if step is None:
        diffs = [b - a for a, b in zip(block.col_boundaries, block.col_boundaries[1:])]
        step = diffs[-1] if diffs else 30

    minimum = _minimum_span(cell_inset)
    step = max(minimum, int(step))
    new_x = block.col_boundaries[-1] + step
    if new_x > canonical_width:
        raise ValueError("ไม่สามารถเพิ่มตัวเลือกได้เนื่องจากล้นขอบขวาของกระดาษ")

    new_boundaries = list(block.col_boundaries) + [new_x]
    new_choices = block.choice_count + 1
    edited = mark_user_edited(
        block,
        choice_count=new_choices,
        col_boundaries=new_boundaries,
    )
    validate_block_geometry(
        edited,
        canonical_width=canonical_width,
        canonical_height=100000,
        cell_inset=cell_inset,
    )
    return edited


def remove_choice_at_end(block: AnswerBlock) -> AnswerBlock:
    """Remove the rightmost choice column from the block."""
    if block.choice_count <= 2:
        raise ValueError("ต้องมีตัวเลือกอย่างน้อย 2 ตัวเลือก")
    new_boundaries = list(block.col_boundaries[:-1])
    new_choices = block.choice_count - 1
    return mark_user_edited(
        block,
        choice_count=new_choices,
        col_boundaries=new_boundaries,
    )


def set_block_choice_count(
    block: AnswerBlock,
    target_choices: int,
    *,
    canonical_width: int,
    cell_inset: int,
) -> AnswerBlock:
    """Set the exact choice count of the block by extending or trimming at the right."""
    target = int(target_choices)
    if not 2 <= target <= 5:
        raise ValueError("จำนวนตัวเลือกต้องอยู่ระหว่าง 2 ถึง 5 ตัวเลือก")
    if target == block.choice_count:
        return block

    current = block
    if target < block.choice_count:
        while current.choice_count > target:
            current = remove_choice_at_end(current)
    else:
        while current.choice_count < target:
            current = append_choice(current, canonical_width=canonical_width, cell_inset=cell_inset)

    return current


def renumber_blocks(blocks: list[AnswerBlock]) -> list[AnswerBlock]:
    """Reindex blocks and map their ordered rows to contiguous question numbers."""
    result: list[AnswerBlock] = []
    question = 1
    for index, block in enumerate(blocks):
        result.append(
            replace(
                block,
                block_index=index,
                question_start=question,
                question_end=question + block.rows - 1,
            )
        )
        question += block.rows
    return result


def compile_draft(draft: CalibrationDraft, *, cell_inset: int | None = None) -> TemplateDefinition:
    """Validate OMR crops and return a strict immutable template definition."""
    inset = draft.cell_inset if cell_inset is None else int(cell_inset)
    return replace(draft, cell_inset=inset).compile()
