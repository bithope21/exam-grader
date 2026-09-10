from pathlib import Path

import cv2
import numpy as np
import pytest

from exam_grader.imaging import analyze, cell_rect, reference_image


def encoded(image):
    return cv2.imencode(".png", image)[1].tobytes()


def test_reference_blank_and_synthetic_marks():
    blank = reference_image()
    result = analyze(encoded(blank))
    assert all(item["classification"] == "blank" for item in result["answers"])
    marked = blank.copy()
    for question, choices in ((1, [0]), (16, [1, 3]), (60, [4])):
        for choice in choices:
            x, y, w, h = cell_rect(question, choice)
            cv2.line(marked, (x + 5, y + 5), (x + w - 5, y + h - 5), (0, 0, 0), 3)
            cv2.line(marked, (x + w - 5, y + 5), (x + 5, y + h - 5), (0, 0, 0), 3)
    result = analyze(encoded(marked))
    assert result["answers"][0]["selected"] == ["A"]
    assert result["answers"][15]["classification"] == "multiple"
    assert result["answers"][59]["selected"] == ["E"]
    assert result["requires_review"] is True


def test_unrelated_image_and_corrupt_bytes_fail_closed():
    with pytest.raises(ValueError):
        analyze(b"corrupt")
    with pytest.raises(ValueError):
        analyze(encoded(np.full((500, 500, 3), 255, np.uint8)))


def test_real_fixture_local_feature_is_not_all_choices():
    fixture_dir = Path("tests/fixtures/real")
    for path in sorted(fixture_dir.rglob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        result = analyze(path.read_bytes())
        assert result["registration"]["table_coverage"] >= 0.995
        assert any(item["classification"] == "single_mark" for item in result["answers"])
        assert all(item["selected"] != list("ABCDE") for item in result["answers"])
