from pathlib import Path

import cv2
import numpy as np

from exam_grader.digit_model import DigitModel, digit_feature, feature_matrix


def _digit(value: int) -> np.ndarray:
    image = np.full((32, 24, 3), 255, dtype=np.uint8)
    cv2.putText(image, str(value), (4, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    return image


def test_feature_normalization_and_model_round_trip(tmp_path: Path):
    images = [_digit(0), _digit(0), _digit(1), _digit(1)]
    features = feature_matrix(images)
    labels = np.array([0, 0, 1, 1], dtype=np.int64)
    model = DigitModel.from_training("knn", features, labels)
    path = tmp_path / "model.npz"
    model.save(path)
    loaded = DigitModel.load(path)

    assert digit_feature(images[0]).shape == (28 * 28,)
    assert loaded.predict(images[0])["candidate"] == "0"
    assert loaded.predict(features[2])["candidate"] == "1"


def test_review_calibration_caps_confidence_without_enabling_acceptance():
    model = DigitModel.from_training(
        "knn",
        feature_matrix([_digit(4), _digit(4)]),
        np.array([4, 4], dtype=np.int64),
        calibration={"max_confidence": 95.0, "auto_accept_enabled": False},
    )

    result = model.predict(_digit(4))

    assert result["confidence"] <= 95.0
    assert result["calibration"]["auto_accept_enabled"] is False


def test_centroid_model_returns_ranked_digit_candidates():
    images = [_digit(2), _digit(2), _digit(3), _digit(3)]
    model = DigitModel.from_training(
        "centroid", feature_matrix(images), np.array([2, 2, 3, 3], dtype=np.int64)
    )

    result = model.predict(images[2])

    assert result["candidate"] == "3"
    assert result["candidates"][:2] == ["3", "2"]
