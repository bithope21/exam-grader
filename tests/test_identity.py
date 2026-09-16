from pathlib import Path

import cv2
import numpy as np
import pytest

import exam_grader.identity as identity_module
from exam_grader.identity import (
    _digit_model_observation,
    _direct_segmented_alternatives,
    _rank_identity_candidates,
    _shape_segmented_suggestion,
    _supported_segmented_number,
    number_roi,
    observe,
)
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


def test_shape_inferred_digit_without_direct_ocr_support_cannot_be_stitched():
    observations = [
        {"candidate": "1", "runs": [{"candidate": "4", "raw_score": 74.0}]},
        {"candidate": "2", "runs": [{"candidate": "2", "raw_score": 81.0}]},
    ]

    assert _supported_segmented_number(observations) is None


def test_supported_segmented_candidate_uses_weakest_actual_digit_score():
    observations = [
        {"candidate": "1", "runs": [{"candidate": "1", "raw_score": 84.0}]},
        {
            "candidate": "2",
            "runs": [
                {"candidate": "2", "raw_score": 61.0},
                {"candidate": "3", "raw_score": 79.0},
            ],
        },
    ]

    assert _supported_segmented_number(observations) == ("12", 61.0)


def test_segmented_alternative_requires_direct_ocr_scores_for_each_digit():
    measured = [
        {
            "candidate": "0",
            "shape_suggestion": "6",
            "runs": [
                {"candidate": "0", "raw_score": 72.93},
                {"candidate": "6", "raw_score": 70.41},
            ],
        },
        {"candidate": "7", "runs": [{"candidate": "7", "raw_score": 65.65}]},
    ]

    assert _direct_segmented_alternatives(measured) == [("67", 65.65)]
    without_digit_six_support = [
        {**measured[0], "runs": [{"candidate": "0", "raw_score": 72.93}]},
        measured[1],
    ]
    assert _direct_segmented_alternatives(without_digit_six_support) == []


def test_weaker_supported_stitch_does_not_displace_stronger_whole_number_read():
    candidates, scores = _rank_identity_candidates(
        [{"candidate": "18", "raw_score": 60.46}],
        ("13", 50.0),
        [("19", 49.0)],
    )

    assert candidates == ["18", "13", "19"]
    assert scores == {"18": 60.46, "13": 50.0, "19": 49.0}


def test_shape_ambiguity_is_a_separate_unscored_review_suggestion():
    suggestion = _shape_segmented_suggestion(
        [
            {
                "candidate": "1",
                "shape_suggestion": None,
                "runs": [{"candidate": "1", "raw_score": 43.0}],
            },
            {
                "candidate": "4",
                "shape_suggestion": "3",
                "runs": [{"candidate": "4", "raw_score": 91.0}],
            },
        ]
    )

    assert suggestion == {
        "candidate": "13",
        "source": "shape-only-digit-ambiguity",
        "changed_positions": [2],
        "requires_review": True,
        "score": None,
    }
    assert _shape_segmented_suggestion(
        [
            {"candidate": "1", "runs": [{"candidate": "1", "raw_score": 43.0}]},
            {
                "candidate": "4",
                "shape_suggestion": "3",
                "runs": [{"candidate": "9", "raw_score": 91.0}],
            },
        ]
    ) is None


def test_incomplete_or_zero_segmented_identity_is_not_promoted():
    assert _supported_segmented_number(
        [{"candidate": "1", "runs": [{"candidate": "1", "raw_score": 90.0}]}]
    ) is None


def test_digit_model_observation_supports_a_single_digit_box():
    class FakeModel:
        def predict(self, image):
            assert image.shape == (24, 12)
            return {
                "candidate": "9",
                "candidates": ["9", "4"],
                "scores": {"9": 80.0, "4": 20.0},
            }

    result = _digit_model_observation(
        FakeModel(), np.full((40, 30), 255, dtype=np.uint8), [[2, 3, 12, 24]]
    )

    assert result is not None
    assert result["candidate"] == "9"
    assert result["candidates"] == ["9", "4"]


def test_model_path_fuses_legacy_candidates(monkeypatch):
    data = cv2.imencode(".png", reference_image())[1].tobytes()
    crop = np.full((40, 30, 3), 255, dtype=np.uint8)
    processed = np.full((40, 30), 255, dtype=np.uint8)
    processed[3:27, 2:14] = 0
    gray = np.full((40, 30), 220, dtype=np.uint8)

    class FakeModel:
        version = "student-number-digit-knn-v1"
        kind = "knn"

        def predict(self, image):
            return {
                "candidate": "9",
                "candidates": ["9", "4"],
                "scores": {"9": 80.0, "4": 20.0},
            }

    monkeypatch.setattr(identity_module, "_load_digit_model", lambda _path: FakeModel())
    monkeypatch.setattr(identity_module, "number_roi", lambda *args, **kwargs: crop)
    monkeypatch.setattr(
        identity_module,
        "preprocess",
        lambda *_args, **_kwargs: (processed, [[2, 3, 12, 24]], gray),
    )
    monkeypatch.setattr(identity_module, "find_tesseract", lambda: "/fake/tesseract")
    monkeypatch.setattr(identity_module, "backend_provenance", lambda _path: {})
    monkeypatch.setattr(
        identity_module,
        "_ocr",
        lambda *_args, **_kwargs: {"candidate": "4", "raw_score": 80.0},
    )

    result = observe(data, digit_model_path=Path("/tmp/fake-model.npz"))

    assert result["pipeline_version"] == "student-number-digit-knn-v1"
    assert "9" in result["candidates"]
    assert "4" in result["candidates"]
    assert result["requires_review"] is True
    assert _supported_segmented_number(
        [
            {"candidate": "0", "runs": [{"candidate": "0", "raw_score": 90.0}]},
            {"candidate": "0", "runs": [{"candidate": "0", "raw_score": 90.0}]},
        ]
    ) is None
