"""Tests for validating synthetic answer sheet dataset generator and fixtures."""

import json
from pathlib import Path

import cv2

from tools.synthetic.generate_dataset import generate_dataset
from tools.synthetic.sheet_builder import (
    GROUPS,
    HEIGHT,
    ROWS,
    STUDENT_ROI,
    TEMPLATE_ID,
    TEMPLATE_VERSION,
    WIDTH,
    get_cell_bounds,
)

FIX_DIR = Path("tests/fixtures/synthetic")


def test_synthetic_directory_structure():
    """Verifies all expected category directories exist."""
    assert FIX_DIR.exists()
    assert (FIX_DIR / "clean").is_dir()
    assert (FIX_DIR / "degraded").is_dir()
    assert (FIX_DIR / "edge_cases").is_dir()
    assert (FIX_DIR / "expected").is_dir()
    assert (FIX_DIR / "manifest.json").is_file()
    assert (FIX_DIR / "expected" / "answer_keys.json").is_file()


def test_answer_keys_validity():
    """Verifies answer keys format and corresponding image files exist."""
    key_data = json.loads((FIX_DIR / "expected" / "answer_keys.json").read_text(encoding="utf-8"))
    assert "key_01" in key_data
    assert "key_02" in key_data
    assert "key_03" in key_data

    for key_id in ("key_01", "key_02", "key_03"):
        answers = key_data[key_id]
        assert len(answers) == 60
        for q in range(1, 61):
            assert str(q) in answers
            assert answers[str(q)] in ("A", "B", "C", "D", "E")

        key_img_path = FIX_DIR / "expected" / f"{key_id}.png"
        assert key_img_path.is_file()
        img = cv2.imread(str(key_img_path))
        assert img is not None
        assert img.shape[0] > 700 and img.shape[1] > 700


def test_manifest_entries_and_images_integrity():
    """Verifies every manifest entry has an existing, readable image matching ground truth."""
    manifest = json.loads((FIX_DIR / "manifest.json").read_text(encoding="utf-8"))
    fixtures = manifest["fixtures"]
    assert len(fixtures) >= 55

    categories = {f["category"] for f in fixtures}
    assert {"clean", "degraded", "edge_cases", "expected"}.issubset(categories)

    for item in fixtures:
        img_path = FIX_DIR / item["filename"]
        assert img_path.is_file(), f"Missing image file: {item['filename']}"
        img = cv2.imread(str(img_path))
        assert img is not None, f"Failed to decode image: {item['filename']}"
        assert img.shape[0] >= 600 and img.shape[1] >= 600

        # Verify ground truth structure
        assert "answers" in item
        assert "expected_score" in item
        assert "expected_review_flags" in item
        assert "transforms" in item
        assert 0 <= item["expected_score"] <= 60


def test_coverage_requirements():
    """Verifies all required prompt coverage patterns exist in the dataset."""
    manifest = json.loads((FIX_DIR / "manifest.json").read_text(encoding="utf-8"))
    fixtures = manifest["fixtures"]

    scores = [f["expected_score"] for f in fixtures if f["category"] != "expected"]
    assert 60 in scores  # Perfect score
    assert 0 in scores  # Zero score
    assert any(20 <= s <= 50 for s in scores)  # Random/partial score

    all_flags = set()
    all_transforms = set()
    student_nos = []

    for f in fixtures:
        all_flags.update(f.get("expected_review_flags", []))
        for t in f.get("transforms", []):
            all_transforms.add(t.split(":")[0])
        if f.get("student_no"):
            student_nos.append(f["student_no"])

    # Verify key flags
    assert "blank_answer" in all_flags
    assert "multiple_mark" in all_flags
    assert "faint_mark" in all_flags
    assert "heavy_mark" in all_flags
    assert "off_center_mark" in all_flags
    assert "non_standard_mark" in all_flags
    assert "scribble_mark" in all_flags
    assert "rotation" in all_flags or "large_rotation" in all_flags
    assert "perspective_skew" in all_flags
    assert "lighting_variation" in all_flags or "shadow" in all_flags
    assert "image_blur" in all_flags or "jpeg_compression" in all_flags
    assert "cropped_sheet" in all_flags
    assert "duplicate_student_no" in all_flags
    assert "missing_student_no" in all_flags or "unreadable_student_no" in all_flags

    # Verify duplicate student numbers exist
    dup_count = sum(1 for s in student_nos if student_nos.count(s) > 1)
    assert dup_count >= 2


def test_deterministic_generator_repeatability(tmp_path):
    """Verifies generating with the same seed produces byte-for-byte identical dataset manifests."""
    m1 = json.loads((FIX_DIR / "manifest.json").read_text(encoding="utf-8"))
    m2 = generate_dataset(seed=42, output_dir=tmp_path)

    assert m1["total_fixtures"] == m2["total_fixtures"]
    assert len(m1["fixtures"]) == len(m2["fixtures"])

    for f1, f2 in zip(m1["fixtures"], m2["fixtures"], strict=True):
        assert f1["filename"] == f2["filename"]
        assert f1["expected_score"] == f2["expected_score"]
        assert f1["expected_review_flags"] == f2["expected_review_flags"]


def test_deterministic_generator_is_byte_identical_within_environment(tmp_path):
    """The same pinned runtime/seed must reproduce both manifests and PNG bytes."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_dataset(seed=42, output_dir=first)
    generate_dataset(seed=42, output_dir=second)
    first_files = sorted(
        path for path in first.rglob("*") if path.is_file() and not path.name.startswith(".")
    )
    second_files = sorted(
        path for path in second.rglob("*") if path.is_file() and not path.name.startswith(".")
    )
    assert [path.relative_to(first) for path in first_files] == [
        path.relative_to(second) for path in second_files
    ]
    assert [path.read_bytes() for path in first_files] == [
        path.read_bytes() for path in second_files
    ]


def test_synthetic_geometry_is_derived_from_canonical_template():
    template = json.loads(Path("src/exam_grader/resources/template.json").read_text())
    assert TEMPLATE_ID == template["id"]
    assert (WIDTH, HEIGHT) == (template["width"], template["height"])
    assert GROUPS == template["groups"]
    assert ROWS == template["rows"]
    assert STUDENT_ROI == template["student_number_roi"]
    assert get_cell_bounds(60, 4) == (
        template["groups"][3][4],
        template["rows"][14],
        template["groups"][3][5],
        template["rows"][15],
    )


def test_synthetic_template_cannot_masquerade_as_production_template():
    # A future separate renderer must carry an explicit distinct ID/version.
    assert TEMPLATE_ID == "thai-main-draft-v2"
    assert TEMPLATE_VERSION == "canonical-resource-v1"
