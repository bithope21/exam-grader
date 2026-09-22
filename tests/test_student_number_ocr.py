import numpy as np

from exam_grader.identity import _constrain_sequence_observation, _selective_auto_accept_allowed
from exam_grader.student_number_constraints import StudentNumberConstraint
from exam_grader.student_number_ocr import decode_digit_logits


def _probabilities(sequence: str) -> np.ndarray:
    rows = []
    mapping = {str(index): 33 + index for index in range(10)}
    for digit in sequence:
        row = np.full(43, 0.001, dtype=np.float64)
        row[mapping[digit]] = 0.99
        rows.extend([row, np.eye(1, 43, 0, dtype=np.float64)[0]])
    return np.asarray(rows)


def test_digits_only_ctc_decode_collapses_blank_and_returns_ranked_candidates():
    result = decode_digit_logits(_probabilities("26"))

    assert result.candidate == "26"
    assert result.candidates[0] == "26"
    assert result.confidence is not None


def test_digits_only_ctc_decode_does_not_return_zero_or_non_digit_classes():
    values = np.full((3, 43), 0.001, dtype=np.float64)
    values[:, 10] = 0.99  # Non-digit model class.

    result = decode_digit_logits(values)

    assert result.candidate is not None
    assert all(candidate.isdigit() for candidate in result.candidates)
    assert result.raw_candidate is not None
    assert result.raw_candidate.isdigit()


def test_known_room_max_filters_impossible_sequence_candidate_before_selection():
    result = _constrain_sequence_observation(
        {
            "candidate": "111",
            "candidates": ["111", "14", "11"],
            "candidate_scores": {"111": 0.99, "14": 0.80, "11": 0.20},
        },
        StudentNumberConstraint("room-1", 30, "room"),
    )

    assert result["raw_candidate"] == "111"
    assert result["candidate"] == "14"
    assert result["candidates"] == ["14", "11"]


def test_sequence_gate_accepts_only_the_calibrated_high_confidence_band():
    class CalibratedModel:
        calibration = {
            "auto_accept_enabled": True,
            "auto_accept_min_confidence": 0.90,
            "auto_accept_min_margin": 0.45,
        }

    assert _selective_auto_accept_allowed(
        CalibratedModel(), "26", ["26", "21"], 0.95, 0.63,
        segmentation_complete=True,
        independent_agreement=True,
    )
    assert not _selective_auto_accept_allowed(
        CalibratedModel(), "12", ["12", "2"], 0.20, 0.11,
        segmentation_complete=True,
        independent_agreement=True,
    )
