from pathlib import Path

import cv2
import numpy as np
import pytest

import exam_grader.identity as identity_module
from exam_grader.identity import (
    _bounded_single_stroke_correction,
    _digit_model_observation,
    _direct_segmented_alternatives,
    _group_digit_boxes,
    _rank_identity_candidates,
    _select_sequence_variant_observation,
    _selective_auto_accept_allowed,
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


def test_component_grouping_does_not_split_a_short_wide_single_glyph():
    ink = np.zeros((224, 563), dtype=np.uint8)
    ink[48:112, 145:174] = 255
    ink[48:112, 194:264] = 255
    ink[48:58, 174:194] = 255

    boxes = _group_digit_boxes(ink, scale=224 / 136)

    assert boxes == [[145, 48, 119, 64]]


def test_selective_auto_accept_requires_calibrated_confidence_and_complete_segmentation():
    class FakeModel:
        calibration = {
            "auto_accept_enabled": True,
            "auto_accept_min_confidence": 100.0,
            "auto_accept_min_margin": 15.0,
        }

    assert _selective_auto_accept_allowed(
        FakeModel(), "7", ["7"], 110.0, 100.0, segmentation_complete=True
    )
    assert not _selective_auto_accept_allowed(
        FakeModel(), "19", ["19", "09"], 90.0, 65.0, segmentation_complete=True
    )
    assert not _selective_auto_accept_allowed(
        FakeModel(), "18", ["18"], 110.0, 100.0, segmentation_complete=False
    )


def test_selective_auto_accept_requires_independent_agreement_and_clean_geometry():
    class FakeModel:
        calibration = {
            "auto_accept_enabled": True,
            "auto_accept_min_confidence": 100.0,
            "auto_accept_min_margin": 15.0,
        }

    kwargs = {
        "segmentation_complete": True,
        "candidate_disagreement": False,
        "independent_agreement": True,
        "merged_component_suspected": False,
    }
    assert _selective_auto_accept_allowed(
        FakeModel(), "7", ["7"], 110.0, 100.0, **kwargs
    )
    assert not _selective_auto_accept_allowed(
        FakeModel(), "7", ["7"], 110.0, 100.0, **{**kwargs, "candidate_disagreement": True}
    )
    assert not _selective_auto_accept_allowed(
        FakeModel(), "7", ["7"], 110.0, 100.0, **{**kwargs, "independent_agreement": False}
    )
    assert not _selective_auto_accept_allowed(
        FakeModel(), "7", ["7"], 110.0, 100.0, **{**kwargs, "merged_component_suspected": True}
    )


def test_sequence_variant_selector_prefers_cleaned_view_when_gray_evidence_is_weak():
    processed = {"candidate": "7", "confidence": 0.99}
    gray = {"candidate": "9", "confidence": 0.21}

    selected, diagnostics = _select_sequence_variant_observation(processed, gray)

    assert selected is processed
    assert diagnostics == {
        "selected_variant": "processed-tight",
        "variant_agreement": False,
        "selection_reason": "gray_disagreement_evidence_weak",
    }


def test_sequence_variant_selector_keeps_gray_view_when_disagreement_has_evidence():
    processed = {"candidate": "1", "confidence": 0.98}
    gray = {"candidate": "19", "confidence": 0.77}

    selected, diagnostics = _select_sequence_variant_observation(processed, gray)

    assert selected is gray
    assert diagnostics["selected_variant"] == "gray-tight"
    assert diagnostics["variant_agreement"] is False


def test_sequence_variant_selector_marks_matching_views_as_agreement():
    processed = {"candidate": "26", "confidence": 0.91}
    gray = {"candidate": "26", "confidence": 0.82}

    selected, diagnostics = _select_sequence_variant_observation(processed, gray)

    assert selected is gray
    assert diagnostics["variant_agreement"] is True


def test_bounded_single_stroke_correction_only_handles_narrow_open_nine_pair():
    ink = np.full((80, 20), 255, dtype=np.uint8)
    ink[8:72, 8:12] = 0
    assert _bounded_single_stroke_correction(ink, "9") == "1"

    closed = ink.copy()
    cv2.rectangle(closed, (4, 8), (16, 25), 0, thickness=2)
    assert _bounded_single_stroke_correction(closed, "9") is None


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
