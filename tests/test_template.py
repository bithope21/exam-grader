"""Unit tests for template domain model, storage, and migration."""

import sqlite3
from pathlib import Path

import pytest

from exam_grader.domain import ExamDetails
from exam_grader.preferences import (
    annotation_colors,
    default_template_id,
    reset_annotation_colors,
    save_annotation_colors,
    save_default_template_id,
)
from exam_grader.storage import ExamStore
from exam_grader.template_manager import (
    AnswerBlock,
    TemplateDefinition,
    cell_rect_for_template,
    default_1_template_definition,
)


def test_default_1_builtin_definition():
    t1 = default_1_template_definition()
    assert t1.template_id == "default-1"
    assert t1.kind == "builtin"
    assert t1.version == 1
    assert t1.choice_count == 5
    assert t1.question_count == 60
    assert len(t1.answer_blocks) == 4
    assert t1.canonical_width == 836
    assert t1.canonical_height == 818
    # Test choice mapping
    assert t1.canonical_choice("ก") == "A"
    assert t1.canonical_choice("ข") == "B"
    assert t1.canonical_choice("ค") == "C"
    assert t1.canonical_choice("ง") == "D"
    assert t1.canonical_choice("จ") == "E"
    assert t1.canonical_choice("a") == "A"
    assert t1.canonical_choice("A") == "A"
    assert t1.display_choice("A") == "ก"
    assert t1.display_choice("B") == "ข"


def test_default_1_cell_rect_matches_original_geometry():
    from exam_grader.imaging import cell_rect as legacy_cell_rect

    t1 = default_1_template_definition()
    for q in (1, 15, 16, 30, 31, 45, 46, 60):
        for c in range(5):
            legacy = legacy_cell_rect(q, c)
            modern = cell_rect_for_template(t1, q, c)
            assert modern == legacy, f"Mismatch at Q{q} C{c}: {modern} vs {legacy}"


def test_template_validation_rejects_invalid_geometry():
    # Invalid question range in block
    with pytest.raises(ValueError, match="ช่วงข้อ"):
        AnswerBlock(
            block_index=0,
            question_start=1,
            question_end=10,
            rows=15,  # 10 != 15
            choice_count=5,
            col_boundaries=[0, 10, 20, 30, 40, 50],
            row_boundaries=list(range(16)),
        )

    # Choice count < 2 or > 5
    with pytest.raises(ValueError, match="จำนวนตัวเลือก"):
        AnswerBlock(
            block_index=0,
            question_start=1,
            question_end=5,
            rows=5,
            choice_count=1,
            col_boundaries=[0, 10],
            row_boundaries=list(range(6)),
        )

    # Out of page bounds
    bad_blocks = [
        AnswerBlock(
            block_index=0,
            question_start=1,
            question_end=60,
            rows=60,
            choice_count=4,
            col_boundaries=[0, 10, 20, 30, 900],  # 900 > width (836)
            row_boundaries=list(range(61)),
        )
    ]
    with pytest.raises(ValueError, match="อยู่นอกขอบเขต"):
        TemplateDefinition(
            template_id="bad",
            name="Bad",
            kind="custom",
            version=1,
            canonical_width=836,
            canonical_height=818,
            choice_count=4,
            choice_labels=["A", "B", "C", "D"],
            display_choice_labels=["ก", "ข", "ค", "ง"],
            choice_map={"ก": "A", "ข": "B", "ค": "C", "ง": "D"},
            question_count=60,
            answer_blocks=bad_blocks,
            student_number_roi=None,
            score_roi=None,
            reference_sha256="abc",
        )


def test_schema_migration_v12_to_v13(tmp_path: Path):
    db_path = tmp_path / "migration_test.sqlite3"
    # Create a realistic v12 database
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE exams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                academic_year TEXT NOT NULL,
                grade TEXT NOT NULL,
                room TEXT NOT NULL,
                subject TEXT NOT NULL,
                question_count INTEGER NOT NULL DEFAULT 60,
                expected_number_max INTEGER,
                archived_at TEXT,
                output_root TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE sources (
                id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id),
                sha256 TEXT NOT NULL, original_name TEXT NOT NULL,
                relative_path TEXT NOT NULL, width INTEGER NOT NULL,
                height INTEGER NOT NULL, purpose TEXT NOT NULL DEFAULT 'student',
                archived_at TEXT, created_at TEXT NOT NULL,
                UNIQUE(exam_id, sha256)
            )
        """)
        conn.execute(
            "INSERT INTO exams VALUES ('exam-1', 'Final', '2569', 'M.1', '1', 'Math', 40, 30, NULL, NULL, '2026-09-08')"
        )
        conn.execute("PRAGMA user_version = 12")

    store = ExamStore(db_path)
    store.initialize()

    # Verify backup was created before migration
    backup_file = tmp_path / "migration_test.sqlite3.v12.bak"
    assert backup_file.exists()

    with sqlite3.connect(db_path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 13

        # Check exams columns exist and backfilled
        row = conn.execute(
            "SELECT id, template_id, template_version FROM exams WHERE id='exam-1'"
        ).fetchone()
        assert row[0] == "exam-1"
        assert row[1] == "default-1"
        assert row[2] == 1

        # Check templates table exists and has default-1
        t_row = conn.execute("SELECT id, name, kind FROM templates WHERE id='default-1'").fetchone()
        assert t_row is not None
        assert t_row[0] == "default-1"
        assert t_row[2] == "builtin"

    # Verify list_exams reads the migrated exam
    exams = store.list_exams()
    assert len(exams) == 1
    assert exams[0].id == "exam-1"
    assert exams[0].details.template_id == "default-1"
    assert exams[0].details.template_version == 1


def test_template_store_crud_and_protections(tmp_path: Path):
    store = ExamStore(tmp_path / "test.sqlite3")
    store.initialize()

    # Built-in default-1 is present
    t1 = store.get_template("default-1")
    assert t1 is not None
    assert t1.template_id == "default-1"

    # Cannot delete built-in
    with pytest.raises(ValueError, match="ไม่สามารถลบรูปแบบกระดาษคำตอบมาตรฐาน"):
        store.delete_template("default-1")

    # Save a custom template
    custom_blocks = [
        AnswerBlock(
            block_index=0,
            question_start=1,
            question_end=30,
            rows=30,
            choice_count=4,
            col_boundaries=[50, 100, 150, 200, 250],
            row_boundaries=list(range(100, 410, 10)),
        )
    ]
    custom = TemplateDefinition(
        template_id="custom-sch-a",
        name="School A (30Q / 4C)",
        kind="custom",
        version=1,
        canonical_width=1000,
        canonical_height=1200,
        choice_count=4,
        choice_labels=["A", "B", "C", "D"],
        display_choice_labels=["ก", "ข", "ค", "ง"],
        choice_map={"ก": "A", "ข": "B", "ค": "C", "ง": "D"},
        question_count=30,
        answer_blocks=custom_blocks,
        student_number_roi=(500, 50, 700, 100),
        score_roi=(750, 50, 950, 150),
        reference_sha256="dummy-sha-256",
    )
    store.save_template(custom)

    fetched = store.get_template("custom-sch-a")
    assert fetched is not None
    assert fetched.name == "School A (30Q / 4C)"
    assert fetched.version == 1

    # Immutable version: saving a different definition under same version fails
    modified = TemplateDefinition(
        template_id="custom-sch-a",
        name="School A Modified",
        kind="custom",
        version=1,
        canonical_width=1000,
        canonical_height=1200,
        choice_count=4,
        choice_labels=["A", "B", "C", "D"],
        display_choice_labels=["ก", "ข", "ค", "ง"],
        choice_map={"ก": "A", "ข": "B", "ค": "C", "ง": "D"},
        question_count=30,
        answer_blocks=custom_blocks,
        student_number_roi=None,  # changed!
        score_roi=(750, 50, 950, 150),
        reference_sha256="dummy-sha-256",
    )
    with pytest.raises(ValueError, match="ห้ามแก้ไขแม่แบบเดิม"):
        store.save_template(modified)

    # Creating an exam with this template protects it from deletion
    _ = store.create(
        ExamDetails(
            "Custom Exam",
            "2569",
            "M.1",
            "1",
            "Art",
            30,
            template_id="custom-sch-a",
            template_version=1,
        )
    )
    assert store.is_template_referenced("custom-sch-a")

    with pytest.raises(ValueError, match="ไม่สามารถลบรูปแบบกระดาษคำตอบที่ถูกใช้งาน"):
        store.delete_template("custom-sch-a")


def test_annotation_color_preferences():
    reset_annotation_colors()
    colors = annotation_colors()
    assert colors["correct"] == (40, 180, 40, 255)
    assert colors["incorrect"] == (40, 40, 220, 255)

    # Customize correct to bright lime
    save_annotation_colors({"correct": (0, 255, 0, 255)})
    new_colors = annotation_colors()
    assert new_colors["correct"] == (0, 255, 0, 255)
    # Others remain default
    assert new_colors["incorrect"] == (40, 40, 220, 255)

    # Reset
    reset_annotation_colors()
    assert annotation_colors()["correct"] == (40, 180, 40, 255)


def test_default_template_preference():
    save_default_template_id("default-1")
    assert default_template_id() == "default-1"
    save_default_template_id("default-2")
    assert default_template_id() == "default-2"
    save_default_template_id("default-1")


def test_default_2_builtin_definition():
    from exam_grader.template_manager import load_builtin_template

    t2 = load_builtin_template("default-2")
    assert t2.template_id == "default-2"
    assert t2.kind == "builtin"
    assert t2.version == 1
    assert t2.choice_count == 4
    assert t2.question_count == 60
    assert len(t2.answer_blocks) == 3
    assert t2.canonical_width == 1200
    assert t2.canonical_height == 1720
    assert t2.cell_inset == 6

    # Test choice mapping
    assert t2.canonical_choice("ก") == "A"
    assert t2.canonical_choice("ข") == "B"
    assert t2.canonical_choice("ค") == "C"
    assert t2.canonical_choice("ง") == "D"
    with pytest.raises(ValueError, match="ไม่พบตัวเลือก"):
        t2.canonical_choice("จ")
    with pytest.raises(ValueError, match="ไม่พบตัวเลือก"):
        t2.canonical_choice("E")

    assert t2.display_choice("A") == "ก"
    assert t2.display_choice("D") == "ง"


def test_template_discovery_pipeline():
    from exam_grader.template_discovery import discover_template

    sheet_path = Path("tests/fixtures/default2/sheet.jpg")
    if not sheet_path.exists():
        pytest.skip("Default 2 fixture image not found")

    result = discover_template(sheet_path.read_bytes())
    assert result.overall_confidence > 0.85
    assert result.template_def.choice_count == 4
    assert len(result.template_def.answer_blocks) == 3
    assert result.warped_image.shape[:2] == (1720, 1200)


def test_load_exam_template_def(tmp_path: Path):
    from exam_grader.template_manager import load_exam_template_def

    store = ExamStore(tmp_path / "exams.sqlite3")
    store.initialize()

    e1 = store.create(ExamDetails("E1", "2569", "1", "1", "S", 60, template_id="default-1"))
    t1 = load_exam_template_def(store.path, e1.id)
    assert t1.template_id == "default-1"
    assert t1.choice_count == 5

    e2 = store.create(ExamDetails("E2", "2569", "1", "1", "S", 60, template_id="default-2"))
    t2 = load_exam_template_def(store.path, e2.id)
    assert t2.template_id == "default-2"
    assert t2.choice_count == 4
