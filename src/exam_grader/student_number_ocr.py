"""Small CPU ONNX recognizer adapter for handwritten Student Numbers."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

DEFAULT_DIGIT_CLASS_INDICES = {
    "0": 33,
    "1": 34,
    "2": 35,
    "3": 36,
    "4": 37,
    "5": 38,
    "6": 39,
    "7": 40,
    "8": 41,
    "9": 42,
}


def bundled_student_number_model_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / "student_number_ppocrv6_small_rec.onnx"


def bundled_student_number_metadata_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / "student_number_ppocrv6_small_rec.json"


@dataclass(frozen=True)
class DigitSequenceResult:
    candidate: str | None
    candidates: list[str]
    scores: dict[str, float]
    confidence: float | None
    confidence_margin: float | None
    raw_candidate: str | None


def _logaddexp(left: float, right: float) -> float:
    if left == -math.inf:
        return right
    if right == -math.inf:
        return left
    return float(np.logaddexp(left, right))


def _normalise_candidate(prefix: str) -> str | None:
    if not prefix or not prefix.isascii() or not prefix.isdigit():
        return None
    value = int(prefix)
    return str(value) if value > 0 else None


def decode_digit_logits(
    probabilities: np.ndarray,
    *,
    digit_class_indices: dict[str, int] | None = None,
    beam_width: int = 8,
) -> DigitSequenceResult:
    """Decode CTC probabilities while allowing only blank and ASCII digits.

    Non-digit classes are excluded during decoding rather than removed after
    a general OCR result has already won. Scores are normalized log scores and
    are useful for ranking only; they are not calibrated probabilities.
    """
    values = np.asarray(probabilities, dtype=np.float64)
    if values.ndim != 2 or values.shape[0] == 0:
        return DigitSequenceResult(None, [], {}, None, None, None)
    mapping = digit_class_indices or DEFAULT_DIGIT_CLASS_INDICES
    allowed = {0: ""}
    for digit, class_index in mapping.items():
        if len(digit) != 1 or not digit.isdigit() or not 0 <= class_index < values.shape[1]:
            continue
        allowed[class_index] = digit
    if len(allowed) < 2:
        return DigitSequenceResult(None, [], {}, None, None, None)

    selected = np.asarray(sorted(allowed), dtype=np.int64)
    restricted = np.clip(values[:, selected], 1e-12, 1.0)
    restricted /= restricted.sum(axis=1, keepdims=True)
    log_probs = np.log(restricted)
    class_to_column = {int(class_index): index for index, class_index in enumerate(selected)}

    # Each prefix tracks paths ending in blank and non-blank separately.
    beams: dict[str, tuple[float, float]] = {"": (0.0, -math.inf)}
    for row in log_probs:
        next_beams: dict[str, list[float]] = {}
        for prefix, (blank_score, nonblank_score) in beams.items():
            total_score = _logaddexp(blank_score, nonblank_score)

            def add(prefix_value: str, blank: bool, score: float) -> None:
                pair = next_beams.setdefault(prefix_value, [-math.inf, -math.inf])
                index = 0 if blank else 1
                pair[index] = _logaddexp(pair[index], score)

            add(prefix, True, total_score + row[class_to_column[0]])
            for class_index, digit in allowed.items():
                if class_index == 0:
                    continue
                if prefix.endswith(digit):
                    add(prefix, False, nonblank_score + row[class_to_column[class_index]])
                    add(
                        prefix + digit,
                        False,
                        blank_score + row[class_to_column[class_index]],
                    )
                else:
                    add(
                        prefix + digit,
                        False,
                        total_score + row[class_to_column[class_index]],
                    )

        ranked = sorted(
            next_beams.items(),
            key=lambda item: -_logaddexp(item[1][0], item[1][1]),
        )[:beam_width]
        beams = {prefix: (scores[0], scores[1]) for prefix, scores in ranked}

    ranked_prefixes = sorted(
        (
            prefix,
            _logaddexp(blank_score, nonblank_score),
        )
        for prefix, (blank_score, nonblank_score) in beams.items()
        if _normalise_candidate(prefix) is not None
    )
    ranked_prefixes.sort(key=lambda item: (-item[1], item[0]))
    candidate_scores: dict[str, float] = {}
    raw_by_candidate: dict[str, str] = {}
    for prefix, log_score in ranked_prefixes:
        candidate = _normalise_candidate(prefix)
        if candidate is None:
            continue
        # Length-normalized score is stable enough for diagnostics across 1/2
        # digit strings, while ranking still follows full CTC path score.
        score = math.exp(log_score / max(1, len(prefix)))
        if candidate not in candidate_scores or score > candidate_scores[candidate]:
            candidate_scores[candidate] = round(score, 8)
            raw_by_candidate[candidate] = prefix
    candidates = sorted(candidate_scores, key=lambda value: (-candidate_scores[value], value))
    top = candidates[0] if candidates else None
    confidence = candidate_scores.get(top) if top else None
    margin = None
    if top and len(candidates) > 1:
        margin = round(confidence - candidate_scores[candidates[1]], 8)
    return DigitSequenceResult(
        candidate=top,
        candidates=candidates,
        scores=candidate_scores,
        confidence=confidence,
        confidence_margin=margin,
        raw_candidate=raw_by_candidate.get(top) if top else None,
    )


def _prepare_input(image: np.ndarray, *, image_height: int = 48, image_width: int = 320) -> np.ndarray:
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim != 3 or image.shape[2] != 3 or image.size == 0:
        raise ValueError("Student Number OCR expects a non-empty BGR image")
    height, width = image.shape[:2]
    resized_width = min(image_width, max(1, int(math.ceil(image_height * width / height))))
    resized = cv2.resize(image, (resized_width, image_height), interpolation=cv2.INTER_LINEAR)
    normalized = resized.astype(np.float32).transpose((2, 0, 1)) / 255.0
    normalized = (normalized - 0.5) / 0.5
    padded = np.zeros((3, image_height, image_width), dtype=np.float32)
    padded[:, :, :resized_width] = normalized
    return padded[None, ...]


def cleaned_sequence_crop(processed: np.ndarray) -> np.ndarray:
    """Tighten the existing form-cleaned image without adding OCR heuristics."""
    ink_y, ink_x = np.where(processed == 0)
    if len(ink_x) == 0:
        return cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
    pad = max(8, round(processed.shape[0] * 0.05))
    x1 = max(0, int(ink_x.min()) - pad)
    y1 = max(0, int(ink_y.min()) - pad)
    x2 = min(processed.shape[1], int(ink_x.max()) + pad + 1)
    y2 = min(processed.shape[0], int(ink_y.max()) + pad + 1)
    return cv2.cvtColor(processed[y1:y2, x1:x2], cv2.COLOR_GRAY2BGR)


class OnnxStudentNumberRecognizer:
    """Lazy CPU ONNX recognizer with digits-only CTC decoding."""

    def __init__(self, model_path: Path, metadata_path: Path | None = None):
        self.model_path = Path(model_path)
        metadata = {}
        if metadata_path is not None and Path(metadata_path).is_file():
            metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        self.version = str(metadata.get("version", "student-number-ppocrv6-small-onnx-v1"))
        mapping = metadata.get("digit_class_indices", DEFAULT_DIGIT_CLASS_INDICES)
        self.digit_class_indices = {str(key): int(value) for key, value in mapping.items()}
        self.expected_sha256 = metadata.get("model_sha256")
        self._session = None

    @property
    def session(self):
        if self._session is None:
            try:
                import onnxruntime as ort
            except ImportError as error:  # pragma: no cover - packaging/runtime guard
                raise RuntimeError("ONNX Runtime is required for Student Number OCR") from error
            if not self.model_path.is_file():
                raise FileNotFoundError(self.model_path)
            if self.expected_sha256:
                digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
                if digest != self.expected_sha256:
                    raise RuntimeError("Student Number OCR model checksum mismatch")
            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
        return self._session

    def predict(self, image: np.ndarray) -> dict[str, Any]:
        session = self.session
        input_name = session.get_inputs()[0].name
        output = session.run(None, {input_name: _prepare_input(image)})[0]
        result = decode_digit_logits(
            np.asarray(output)[0], digit_class_indices=self.digit_class_indices
        )
        return {
            "candidate": result.candidate,
            "candidates": result.candidates,
            "candidate_scores": result.scores,
            "confidence": result.confidence,
            "confidence_margin": result.confidence_margin,
            "raw_candidate": result.raw_candidate,
            "pipeline_version": self.version,
            "confidence_semantics": "normalized restricted CTC score; not calibrated probability",
        }
