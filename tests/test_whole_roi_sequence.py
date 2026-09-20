from __future__ import annotations

import cv2
import numpy as np

from tools.benchmark.whole_roi_sequence import (
    FEATURE_SIZE,
    WholeRoiSequenceModel,
    _canvas_feature,
    _ink_feature,
)


def _pair(first: int, second: int) -> np.ndarray:
    image = np.full((65, 70, 3), 255, dtype=np.uint8)
    cv2.putText(image, str(first), (8, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 2)
    cv2.putText(image, str(second), (38, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 2)
    return image


def test_whole_roi_feature_has_fixed_shape_without_digit_boxes() -> None:
    feature, width_ratio, canvas = _ink_feature(_pair(1, 4))

    assert feature.shape == (FEATURE_SIZE,)
    assert canvas.shape == (32, 64)
    assert width_ratio > 0
    assert _canvas_feature(canvas).shape == (FEATURE_SIZE,)


def test_sequence_model_emits_top_candidates_from_the_complete_roi() -> None:
    images = [_pair(1, 4), _pair(1, 8), _pair(2, 4), _pair(2, 8)]
    model = WholeRoiSequenceModel.fit(images, ["14", "18", "24", "28"])

    prediction = model.predict(_pair(1, 4), top_k=3)

    assert prediction["candidate"] == "14"
    assert prediction["candidates"][0] == "14"
    assert prediction["sequence_length"] == 2
    assert model.model_size_bytes > 0
