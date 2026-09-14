"""Focused, headless contracts for editable calibration geometry."""

from dataclasses import replace
from pathlib import Path

import pytest

from exam_grader.calibration_model import (
    CalibrationDraft,
    cell_rect_for_block,
    remove_grid_line,
    resize_block_from_origin,
    set_boundary_position,
    split_cell,
)
from exam_grader.imaging import analyze
from exam_grader.storage import ExamStore
from exam_grader.template_discovery import discover_template
from exam_grader.template_manager import TemplateDefinition, load_builtin_template


def _block():
    return load_builtin_template("default-3").answer_blocks[0]


def test_individual_line_move_preserves_other_lines_and_marks_edit():
    block = _block()
    moved = set_boundary_position(
        block,
        axis="col",
        index=2,
        position=block.col_boundaries[2] + 7,
        canonical_width=1200,
        canonical_height=1720,
        cell_inset=6,
    )
    assert moved.geometry_state == "user_edited"
    assert moved.col_boundaries[2] == block.col_boundaries[2] + 7
    assert moved.col_boundaries[:2] == block.col_boundaries[:2]
    assert moved.col_boundaries[3:] == block.col_boundaries[3:]


def test_resize_uses_immutable_origin_without_accumulated_rounding():
    block = _block()
    first = resize_block_from_origin(
        block, rect=(200, 600, 700, 1400), canonical_width=1200, canonical_height=1720, cell_inset=6
    )
    second = resize_block_from_origin(
        block, rect=(200, 600, 700, 1400), canonical_width=1200, canonical_height=1720, cell_inset=6
    )
    assert first.col_boundaries == second.col_boundaries
    assert first.row_boundaries == second.row_boundaries


def test_add_delete_line_and_cell_mapping():
    block = _block()
    added = split_cell(block, axis="col", interval_index=1, cell_inset=6)
    assert added.choice_count == block.choice_count + 1
    assert len(added.col_boundaries) == added.choice_count + 1
    removed = remove_grid_line(added, axis="col", boundary_index=2)
    assert removed.choice_count == block.choice_count
    assert cell_rect_for_block(removed, 0, 0, 6)[2] > 0


def test_compile_and_reopen_preserves_corrected_geometry(tmp_path: Path):
    source = load_builtin_template("default-3")
    block = set_boundary_position(
        source.answer_blocks[0], axis="row", index=3,
        position=source.answer_blocks[0].row_boundaries[3] + 5,
        canonical_width=source.canonical_width, canonical_height=source.canonical_height,
        cell_inset=source.cell_inset,
    )
    blocks = [block, *source.answer_blocks[1:]]
    draft = CalibrationDraft.from_template(replace(source, answer_blocks=blocks))
    compiled = draft.compile()
    reopened = TemplateDefinition.from_dict(compiled.to_dict())
    assert reopened.answer_blocks[0].row_boundaries == compiled.answer_blocks[0].row_boundaries
    assert reopened.answer_blocks[0].geometry_state == "user_edited"
    store = ExamStore(tmp_path / "exams.sqlite3")
    store.initialize()
    persisted = replace(compiled, template_id="custom-geometry-test", kind="custom")
    store.save_template(persisted)
    loaded = store.get_template(persisted.template_id, persisted.version)
    assert loaded is not None
    assert loaded.answer_blocks[0].row_boundaries == persisted.answer_blocks[0].row_boundaries


def test_compile_rejects_overlapping_or_too_small_geometry():
    source = load_builtin_template("default-3")
    overlapping = replace(source.answer_blocks[1], col_boundaries=source.answer_blocks[0].col_boundaries)
    with pytest.raises(ValueError, match="ซ้อนทับ|ช่องแคบ|ช่องเตี้ย"):
        data = source.to_dict()
        data["answer_blocks"] = [source.answer_blocks[0].__dict__, overlapping.__dict__, source.answer_blocks[2].__dict__]
        TemplateDefinition.from_dict(data)


def test_vol7_discovery_infers_four_blocks_of_five_choices():
    reference = Path("tests/fixtures/real/vol.7/ถ่ายในที่แจ้ง/template.JPG")
    result = discover_template(reference.read_bytes())
    td = result.template_def
    assert [(b.rows, b.choice_count) for b in td.answer_blocks] == [(15, 5)] * 4
    assert td.question_count == 60
    assert all(b.source_geometry and b.confidence is not None for b in td.answer_blocks)
    assert td.registration_config["allow_paper_quad_fallback"] is True


def test_corrected_vol7_geometry_reaches_omr_cells():
    root = Path("tests/fixtures/real/vol.7")
    ref_result = discover_template((root / "ถ่ายในที่แจ้ง/template.JPG").read_bytes())
    sample = root / "ถ่ายในห้อง/IMG_0973.JPG"
    analysis = analyze(
        sample.read_bytes(),
        template_def=ref_result.template_def,
        reference_override=ref_result.warped_image,
    )
    assert len(analysis["answers"]) == 60
    assert analysis["registration"]["method"] == "paper-quad-fallback-v1"
    # Every answer observed by OMR is backed by the persisted five-choice cell
    # lattice; no synthetic fifth choice is introduced by the reader.
    assert all(len(answer["ink_density"]) == 5 for answer in analysis["answers"])


def test_keyyy_discovery_infers_four_blocks_of_five_choices():
    key_path = Path("tests/fixtures/real/vol.7/ถ่ายในที่แจ้ง/keyyy.jpg")
    result = discover_template(key_path.read_bytes())
    td = result.template_def
    assert [(b.rows, b.choice_count) for b in td.answer_blocks] == [(15, 5)] * 4
    assert td.question_count == 60
    assert td.choice_count == 5
    assert len(td.answer_blocks) == 4


def test_keyyy_omr_reads_actual_key():
    key_path = Path("tests/fixtures/real/vol.7/ถ่ายในที่แจ้ง/keyyy.jpg")
    key_bytes = key_path.read_bytes()
    result = discover_template(key_bytes)
    td = result.template_def
    analysis = analyze(
        key_bytes,
        template_def=td,
        reference_override=result.warped_image,
    )
    answers = analysis["answers"]
    assert len(answers) == 60
    assert all(len(a["ink_density"]) == 5 for a in answers)

    # Q1-Q30 have answers marked; Q4 is marked multiple (A and D)
    assert answers[0]["classification"] == "single_mark"
    assert answers[3]["classification"] == "multiple"  # Q4: A + D
    # Q1 is E (index 4)
    assert max(range(5), key=lambda i: answers[0]["ink_density"][i]) == 4
    # Q2 is D (index 3)
    assert max(range(5), key=lambda i: answers[1]["ink_density"][i]) == 3
    # Q3 is C (index 2)
    assert max(range(5), key=lambda i: answers[2]["ink_density"][i]) == 2
    # Q30 is E (index 4)
    assert max(range(5), key=lambda i: answers[29]["ink_density"][i]) == 4
    # Q31-Q60 are blank on the teacher answer key
    blanks = sum(1 for a in answers[30:] if a["classification"] == "blank")
    assert blanks >= 28

