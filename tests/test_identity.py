from pathlib import Path

import cv2
import numpy as np
import pytest

from exam_grader.identity import number_roi, observe
from exam_grader.imaging import reference_image


def test_number_roi_is_bounded_and_high_resolution():
    data = cv2.imencode(".png", reference_image())[1].tobytes()
    crop = number_roi(data)
    assert crop.shape[0] > 0 and crop.shape[1] > 0
    result = observe(data)
    assert result["confidence"] is None
    assert result["review_reason"]
    assert result["diagnostics"]["model"].startswith("student-number-")


def test_real_number_observation_never_becomes_authoritative():
    path = Path("tests/fixtures/real/vol.1/IMG_0791.JPG")
    result = observe(path.read_bytes())
    assert "candidate" in result
    assert result["confidence"] is None
    assert "teacher" in result["review_reason"] or "unavailable" in result["review_reason"]


def test_missing_and_invalid_registration_cannot_generate_an_identity():
    path = Path("tests/fixtures/real/vol.1/IMG_0791.JPG")
    assert observe(path.read_bytes())["candidate"] is None
    for matrix in (np.zeros((3, 3)), np.full((3, 3), np.nan), np.eye(2)):
        with pytest.raises(ValueError):
            number_roi(path.read_bytes(), matrix.tolist())


def test_blank_number_roi_never_becomes_zero():
    data = cv2.imencode(".png", np.full_like(reference_image(), 255))[1].tobytes()
    result = observe(data)
    assert result["candidate"] is None
    assert result["requires_review"] is True
    assert result["diagnostics"]["segmented_boxes"] == []
