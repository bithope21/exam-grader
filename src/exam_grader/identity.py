"""Review-required student-number observation adapter.

The bundled seed digit model and Tesseract are candidates only. Teacher
confirmation remains mandatory unless the explicitly calibrated, independent
agreement gate proves the observation safe enough for selective auto-accept.
"""

from __future__ import annotations

import csv
import hashlib
import io
import itertools
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from exam_grader.imaging import decode, template
from exam_grader.template_manager import TemplateDefinition

IDENTITY_PIPELINE_VERSION = "student-number-adaptive-roi-v6"
NUMBER_SEARCH_X_FRACTION = 0.25
NUMBER_SEARCH_Y_FRACTION = 0.40


def _supported_segmented_number(
    observations: list[dict[str, Any]],
) -> tuple[str, float] | None:
    """Return a stitched number only when each digit has direct OCR support."""
    if not 2 <= len(observations) <= 6:
        return None
    digits: list[str] = []
    scores: list[float] = []
    for observation in observations:
        candidate = observation.get("candidate")
        if not isinstance(candidate, str) or len(candidate) != 1 or not candidate.isdigit():
            return None
        matching_scores = [
            float(run["raw_score"])
            for run in observation.get("runs", [])
            if isinstance(run, dict)
            and run.get("candidate") == candidate
            and isinstance(run.get("raw_score"), (int, float))
            and math.isfinite(float(run["raw_score"]))
        ]
        if not matching_scores:
            return None
        digits.append(candidate)
        scores.append(max(matching_scores))
    number = "".join(digits)
    if int(number) <= 0:
        return None
    return number, min(scores)


def _direct_segmented_alternatives(
    observations: list[dict[str, Any]],
) -> list[tuple[str, float]]:
    """Return at most one measured alternative per digit position.

    Every emitted number is one digit away from the best segmented read, and
    every position is backed by an OCR run's finite score. Shape suggestions
    and inferred digits are deliberately ignored.
    """
    if not 2 <= len(observations) <= 6:
        return []

    primary_digits: list[str] = []
    score_by_position: list[dict[str, float]] = []
    for observation in observations:
        primary = observation.get("candidate")
        if not isinstance(primary, str) or len(primary) != 1 or not primary.isdigit():
            return []
        scores: dict[str, float] = {}
        for run in observation.get("runs", []):
            candidate = run.get("candidate") if isinstance(run, dict) else None
            raw_score = run.get("raw_score") if isinstance(run, dict) else None
            if (
                isinstance(candidate, str)
                and len(candidate) == 1
                and candidate.isdigit()
                and isinstance(raw_score, (int, float))
                and math.isfinite(float(raw_score))
            ):
                scores[candidate] = max(scores.get(candidate, -math.inf), float(raw_score))
        if primary not in scores:
            return []
        primary_digits.append(primary)
        score_by_position.append(scores)

    primary_scores = [scores[digit] for scores, digit in zip(score_by_position, primary_digits)]
    alternatives: dict[str, float] = {}
    for index, scores in enumerate(score_by_position):
        measured_alternatives = sorted(
            ((digit, score) for digit, score in scores.items() if digit != primary_digits[index]),
            key=lambda item: (-item[1], item[0]),
        )
        if not measured_alternatives:
            continue
        alternative_digit, alternative_score = measured_alternatives[0]
        digits = list(primary_digits)
        digits[index] = alternative_digit
        candidate = "".join(digits)
        if int(candidate) <= 0:
            continue
        evidence_scores = list(primary_scores)
        evidence_scores[index] = alternative_score
        alternatives[candidate] = max(
            alternatives.get(candidate, -math.inf), min(evidence_scores)
        )

    return sorted(alternatives.items(), key=lambda item: (-item[1], item[0]))


def _rank_identity_candidates(
    runs: list[dict[str, Any]],
    segmented_candidate: tuple[str, float] | None = None,
    segmented_alternatives: list[tuple[str, float]] | None = None,
) -> tuple[list[str], dict[str, float]]:
    """Rank whole-read and segmented candidates only by observed OCR scores."""
    values = [str(run["candidate"]) for run in runs if run.get("candidate")]
    scores: dict[str, float] = {}
    for run in runs:
        candidate = run.get("candidate")
        if candidate:
            raw_score = run.get("raw_score")
            score = (
                float(raw_score)
                if isinstance(raw_score, (int, float)) and math.isfinite(float(raw_score))
                else 0.0
            )
            scores[candidate] = max(scores.get(candidate, 0.0), score)
    segmented = list(segmented_alternatives or [])
    if segmented_candidate is not None:
        segmented.insert(0, segmented_candidate)
    for candidate, score in segmented:
        scores[candidate] = max(scores.get(candidate, -math.inf), float(score))
        values.append(candidate)
    candidates = sorted(
        set(values),
        key=lambda value: (
            -scores.get(value, 0.0),
            -values.count(value),
            value,
        ),
    )
    return candidates, scores


def _rank_identity_candidates_with_voting(
    runs: list[dict[str, Any]],
    segmented_candidate: tuple[str, float] | None = None,
    segmented_alternatives: list[tuple[str, float]] | None = None,
) -> tuple[list[str], dict[str, float], dict[str, int]]:
    """Aggregate independent preprocessing reads without inventing digits."""
    candidates, scores = _rank_identity_candidates(
        runs, segmented_candidate, segmented_alternatives
    )
    votes: dict[str, set[str]] = {}
    for run in runs:
        candidate = run.get("candidate")
        variant = run.get("variant")
        if isinstance(candidate, str) and candidate and isinstance(variant, str):
            votes.setdefault(candidate, set()).add(variant)
    if segmented_candidate is not None:
        votes.setdefault(segmented_candidate[0], set()).add("segmented")
    for candidate, _score in segmented_alternatives or []:
        votes.setdefault(candidate, set()).add("segmented-alternative")

    def aggregate(candidate: str) -> float:
        score = scores.get(candidate, 0.0)
        vote_bonus = min(2, max(0, len(votes.get(candidate, set())) - 1)) * 5.0
        return score + vote_bonus

    ranked = sorted(
        candidates,
        key=lambda value: (-aggregate(value), -len(votes.get(value, set())), value),
    )
    aggregate_scores = {candidate: round(aggregate(candidate), 2) for candidate in ranked}
    return ranked, aggregate_scores, {
        candidate: len(votes.get(candidate, set())) for candidate in ranked
    }


def _shape_segmented_suggestion(
    observations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Keep OCR-supported digit strings with shape alternatives review-only."""
    if not 2 <= len(observations) <= 6:
        return None
    digits: list[str] = []
    changed_positions: list[int] = []
    for index, observation in enumerate(observations):
        recognized = observation.get("candidate")
        alternative = observation.get("shape_suggestion")
        if (
            not isinstance(recognized, str)
            and not isinstance(alternative, str)
        ) or (
            isinstance(recognized, str)
            and (len(recognized) != 1 or not recognized.isdigit())
        ):
            return None
        has_direct_support = isinstance(recognized, str) and any(
            isinstance(run, dict)
            and run.get("candidate") == recognized
            and isinstance(run.get("raw_score"), (int, float))
            and math.isfinite(float(run["raw_score"]))
            for run in observation.get("runs", [])
        )
        if isinstance(recognized, str) and not has_direct_support:
            return None
        if not has_direct_support and not (
            isinstance(alternative, str) and len(alternative) == 1 and alternative.isdigit()
        ):
            return None
        if (
            isinstance(alternative, str)
            and len(alternative) == 1
            and alternative.isdigit()
            and alternative != recognized
        ) or not has_direct_support:
            digits.append(alternative)
            changed_positions.append(index + 1)
        else:
            digits.append(str(recognized))
    value = "".join(digits)
    if not changed_positions or int(value) <= 0:
        return None
    return {
        "candidate": value,
        "source": "shape-only-digit-ambiguity",
        "changed_positions": changed_positions,
        "requires_review": True,
        "score": None,
    }


def find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    # Finder-launched macOS apps do not inherit the interactive shell PATH.
    if sys.platform == "darwin":
        for location in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"):
            if Path(location).is_file():
                return location
    elif sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        for location in (
            os.path.join(local_app, "Programs", "Tesseract-OCR", "tesseract.exe"),
            os.path.join(prog_files, "Tesseract-OCR", "tesseract.exe"),
            os.path.join(prog_files_x86, "Tesseract-OCR", "tesseract.exe"),
        ):
            if Path(location).is_file():
                return location
    return None


@lru_cache(maxsize=4)
def _load_digit_model(path: str):
    from exam_grader.digit_model import DigitModel

    return DigitModel.load(Path(path))


def _digit_model_observation(model: Any, gray: np.ndarray, boxes: list[list[int]]) -> dict[str, Any] | None:
    if not 1 <= len(boxes) <= 6:
        return None
    positions: list[dict[str, Any]] = []
    for x, y, width, height in boxes:
        prediction = model.predict(gray[y : y + height, x : x + width])
        if not prediction.get("candidate"):
            return None
        positions.append({"box": [x, y, width, height], **prediction})
    combinations: list[tuple[str, float]] = []
    choices = [position.get("candidates", [])[:3] for position in positions]
    for candidate_digits in itertools.product(*choices):
        scores = []
        for position, digit in zip(positions, candidate_digits):
            score = position.get("scores", {}).get(digit)
            if not isinstance(score, (int, float)):
                scores = []
                break
            scores.append(float(score))
        if scores:
            combinations.append(("".join(candidate_digits), min(scores)))
    ranked = sorted(combinations, key=lambda item: (-item[1], item[0]))
    if not ranked:
        return None
    candidate, confidence = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    return {
        "candidate": candidate,
        "candidates": [item[0] for item in ranked[:12]],
        "candidate_scores": {
            item[0]: round(item[1], 4) for item in ranked[:12]
        },
        "confidence": round(confidence, 4),
        "confidence_margin": round(confidence - runner_up, 4),
        "digit_observations": positions,
    }


def _selective_auto_accept_allowed(
    model: Any | None,
    candidate: str | None,
    candidates: list[str],
    confidence: float | None,
    confidence_margin: float | None,
    *,
    segmentation_complete: bool,
    candidate_disagreement: bool = False,
    independent_agreement: bool = True,
    merged_component_suspected: bool = False,
) -> bool:
    """Apply an explicitly calibrated, fail-closed identity acceptance gate."""
    calibration = getattr(model, "calibration", {}) if model is not None else {}
    if (
        not calibration.get("auto_accept_enabled")
        or not segmentation_complete
        or merged_component_suspected
        or candidate_disagreement
        or not independent_agreement
    ):
        return False
    if not candidate or not candidates or candidates[0] != candidate:
        return False
    minimum_confidence = calibration.get("auto_accept_min_confidence")
    minimum_margin = calibration.get("auto_accept_min_margin")
    if not isinstance(minimum_confidence, (int, float)) or not isinstance(
        minimum_margin, (int, float)
    ):
        return False
    if not isinstance(confidence, (int, float)) or not isinstance(
        confidence_margin, (int, float)
    ):
        return False
    return (
        math.isfinite(float(confidence))
        and math.isfinite(float(confidence_margin))
        and float(confidence) >= float(minimum_confidence)
        and float(confidence_margin) >= float(minimum_margin)
    )


def _subprocess_windows_flags() -> dict[str, Any]:
    if sys.platform == "win32":
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags |= subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        return {"creationflags": creationflags, "startupinfo": startupinfo}
    return {}


@lru_cache(maxsize=4)
def backend_provenance(executable: str) -> dict:
    result = {"executable": executable, "language": "eng"}
    try:
        version = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            **_subprocess_windows_flags(),
        )
        result["version"] = version.stdout.splitlines()[0]
        languages = subprocess.run(
            [executable, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=8,
            **_subprocess_windows_flags(),
        )
        match = re.search(r'"([^"]+)"', languages.stdout)
        if match:
            model = Path(match.group(1)) / "eng.traineddata"
            if model.is_file():
                result["traineddata_sha256"] = hashlib.sha256(model.read_bytes()).hexdigest()
    except (OSError, subprocess.TimeoutExpired, IndexError):
        result["provenance_status"] = "backend metadata unavailable"
    return result


def _roi_crop(aligned: np.ndarray, roi: tuple[int, int, int, int] | None = None) -> np.ndarray:
    if roi is not None:
        x1, y1, x2, y2 = roi
    else:
        x1, y1, x2, y2 = template()["student_number_roi"]
    if x2 <= x1 or y2 <= y1 or x1 < 0 or y1 < 0:
        raise ValueError("student-number ROI ไม่ถูกต้อง")
    crop = aligned[y1:y2, x1:x2]
    if crop.size == 0:
        raise ValueError("student-number ROI ว่าง")
    return crop


def _expanded_number_roi(
    roi: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int]:
    """Expand the configured digit box into a bounded registration-tolerant search window."""
    x1, y1, x2, y2 = roi
    pad_x = max(12, round((x2 - x1) * NUMBER_SEARCH_X_FRACTION))
    pad_y = max(10, round((y2 - y1) * NUMBER_SEARCH_Y_FRACTION))
    return (
        max(0, x1 - pad_x),
        max(0, y1 - pad_y),
        min(width, x2 + pad_x),
        min(height, y2 + pad_y),
    )


def number_roi(
    data: bytes,
    matrix: list[list[float]] | None = None,
    *,
    top_padding: int = 0,
    template_def: TemplateDefinition | None = None,
    image: np.ndarray | None = None,
) -> np.ndarray:
    """Return a high-resolution ROI crop in canonical coordinates when possible."""
    if image is None:
        image = decode(data)
    if template_def is not None:
        if template_def.student_number_roi is None:
            raise ValueError("แม่แบบนี้ไม่ได้ระบุ student_number_roi")
        roi = template_def.student_number_roi
        geom_w, geom_h = template_def.canonical_width, template_def.canonical_height
    else:
        geometry = template()
        roi = tuple(geometry["student_number_roi"])
        geom_w, geom_h = geometry["width"], geometry["height"]
    roi = _expanded_number_roi(tuple(roi), geom_w, geom_h)

    transform = (
        np.eye(3, dtype=np.float64) if matrix is None else np.asarray(matrix, dtype=np.float64)
    )
    if (
        transform.shape != (3, 3)
        or not np.isfinite(transform).all()
        or abs(np.linalg.det(transform)) < 1e-12
    ):
        raise ValueError("registration transform ไม่ถูกต้อง")
    scale = max(1.0, min(4.0, max(image.shape[:2]) / max(geom_w, geom_h)))
    x1, y1, x2, y2 = (int(value * scale) for value in roi)
    y1 = max(0, y1 - int(top_padding * scale))
    scaled = (
        np.array([[1, 0, -x1], [0, 1, -y1], [0, 0, 1]]) @ np.diag([scale, scale, 1.0]) @ transform
    )
    corners = np.array(
        [[[0.0, 0.0], [x2 - x1 - 1.0, 0.0], [x2 - x1 - 1.0, y2 - y1 - 1.0], [0.0, y2 - y1 - 1.0]]]
    )
    source_corners = cv2.perspectiveTransform(corners, np.linalg.inv(scaled))[0]
    if (
        not np.isfinite(source_corners).all()
        or (source_corners < 0).any()
        or (source_corners[:, 0] >= image.shape[1]).any()
        or (source_corners[:, 1] >= image.shape[0]).any()
    ):
        raise ValueError("student-number ROI อยู่นอกภาพ")
    crop = cv2.warpPerspective(
        image,
        scaled,
        (x2 - x1, y2 - y1),
        borderValue=(255, 255, 255),
    )
    if crop.size == 0:
        raise ValueError("student-number ROI ว่าง")
    return crop


def _normalize_candidate(value: str) -> str | None:
    value = value.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
    digits = re.sub(r"[^0-9]", "", value)
    return digits or None


HOMOGLYPH_MAP = {
    "l": "1", "I": "1", "|": "1",
    "O": "0", "o": "0",
    "S": "5", "s": "5",
    "B": "8",
    "Z": "2", "z": "2",
    "/": "7",
}


def _clean_component_mask(
    mask: np.ndarray,
    *,
    crop_shape: tuple[int, ...],
    scale: float,
) -> np.ndarray:
    """Keep handwriting-like components while removing form rules and labels."""
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    ink = np.zeros_like(mask)
    for index, (x, y, w, h, area) in enumerate(stats[1:], 1):
        if (
            h >= 22 * scale
            and area >= 25 * scale * scale
            and w >= 3 * scale
            and w < crop_shape[1] * 0.85
        ):
            # Safety Net 1: Suppress bottom dotted guide lines
            if y + h >= crop_shape[0] - 4 * scale and h < 18 * scale:
                continue
            # Safety Net 2: Suppress left-margin Thai label components (e.g. 'เลขที่')
            is_thai_left = (
                x < crop_shape[1] * 0.45
                and (
                    (y > crop_shape[0] * 0.40 and h < 55 * scale)
                    or (x <= 4 * scale and w < 0.15 * crop_shape[1])
                )
            )
            if is_thai_left:
                continue
            ink[labels == index] = 255

    # Printed horizontal/vertical rules are not digit strokes. Remove only
    # components whose geometry is overwhelmingly line-like; handwriting stays
    # available for the following grouping stage.
    line_clean = np.zeros_like(ink)
    _, line_labels, line_stats, _ = cv2.connectedComponentsWithStats(ink)
    for index, (x, y, w, h, area) in enumerate(line_stats[1:], 1):
        if (w >= crop_shape[1] * 0.65 and h <= max(6, round(8 * scale))) or (
            h >= crop_shape[0] * 0.70 and w <= max(6, round(8 * scale))
        ):
            continue
        line_clean[line_labels == index] = 255
    return line_clean


def _group_digit_boxes(ink: np.ndarray, *, scale: float) -> list[list[int]]:
    """Group x-overlapping ink and conservatively split genuinely touching digits."""
    occupied = np.flatnonzero(ink.any(axis=0))
    boxes: list[list[int]] = []
    if occupied.size:
        groups = np.split(
            occupied,
            np.where(np.diff(occupied) > max(2, round(3 * scale)))[0] + 1,
        )
        for group in groups:
            x1, x2 = int(group[0]), int(group[-1]) + 1
            ys = np.flatnonzero(ink[:, x1:x2].any(axis=1))
            boxes.append([x1, int(ys[0]), x2 - x1, int(ys[-1] - ys[0] + 1)])

    # A short, wide glyph is more likely a broken single digit (notably an 8)
    # than a pair of touching digits. Require the component to span most of the
    # search height before attempting a vertical split.
    final_boxes: list[list[int]] = []
    # Keep the existing short-wide single-glyph guard. Merged components are
    # handled as review-required below when the valley is not strong enough;
    # splitting a short/wide clean glyph here can erase a real single digit.
    minimum_split_height = max(25 * scale, ink.shape[0] * 0.45)
    for box in boxes:
        bx, by, bw, bh = box
        if bw >= 0.45 * bh and bh >= minimum_split_height:
            box_ink = ink[by : by + bh, bx : bx + bw]
            proj = (box_ink == 255).sum(axis=0)
            start_x = int(bw * 0.25)
            end_x = int(bw * 0.75)
            if end_x > start_x:
                mid = proj[start_x:end_x]
                v_idx = start_x + int(np.argmin(mid))
                left_peak = proj[:v_idx].max() if v_idx > 0 else 0
                right_peak = proj[v_idx:].max() if v_idx < bw else 0
                min_peak = min(left_peak, right_peak)
                if min_peak > 0 and proj[v_idx] <= 0.20 * min_peak and proj[v_idx] <= 8 * scale:
                    final_boxes.append([bx, by, v_idx, bh])
                    final_boxes.append([bx + v_idx, by, bw - v_idx, bh])
                    continue
        final_boxes.append(box)
    return final_boxes


def preprocess(
    crop: np.ndarray,
    reference_crop: np.ndarray | None = None,
) -> tuple[np.ndarray, list[list[int]], np.ndarray]:
    """Suppress form texture, locate ink, retain gray strokes for OCR.

    Component boxes are diagnostics, not independently recognized characters:
    disconnected strokes are joined by their overlapping x projection.
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    scale = crop.shape[0] / 136.0
    darkness = cv2.GaussianBlur(gray, (0, 0), max(2, round(9 * scale))) - gray
    mask = (darkness > 30).astype(np.uint8) * 255
    green_print = np.zeros_like(mask)
    ref_mask_dilated = np.zeros_like(mask)

    # Remove the colored printed form before connected-component grouping. The
    # test is intentionally conservative: dark neutral handwriting has low
    # chroma, while the green form has a positive G-minus-(R+B)/2 signal.
    if crop.ndim == 3 and crop.shape[2] >= 3:
        blue, green, red = cv2.split(crop)
        chroma = green.astype(np.int16) - (
            blue.astype(np.int16) + red.astype(np.int16)
        ) // 2
        green_print = ((chroma >= 10) & (green >= 55)).astype(np.uint8) * 255
        green_print = cv2.dilate(
            green_print,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        )
        mask = cv2.bitwise_and(mask, cv2.bitwise_not(green_print))

    if reference_crop is not None and reference_crop.size > 0:
        scaled_ref = cv2.resize(
            reference_crop, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_LINEAR
        )
        ref_gray = cv2.cvtColor(scaled_ref, cv2.COLOR_BGR2GRAY).astype(np.float32)
        ref_dark = cv2.GaussianBlur(ref_gray, (0, 0), 2) - ref_gray
        ref_mask = (ref_dark > 25).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        ref_mask_dilated = cv2.dilate(ref_mask, kernel)
        mask = cv2.bitwise_and(mask, cv2.bitwise_not(ref_mask_dilated)).astype(np.uint8)

    ink = _clean_component_mask(mask, crop_shape=crop.shape, scale=scale)
    boxes = _group_digit_boxes(ink, scale=scale)

    # Recover faint lower strokes only when the baseline geometry itself signals
    # an incomplete digit. This keeps the proven threshold-30 path unchanged for
    # complete handwriting while avoiding a global low-threshold regression.
    heights = [box[3] for box in boxes]
    needs_recovery = bool(
        len(heights) >= 2 and min(heights) < 0.55 * max(heights)
    )
    if needs_recovery:
        recovery_mask = (darkness > 20).astype(np.uint8) * 255
        recovery_mask = cv2.bitwise_and(
            recovery_mask, cv2.bitwise_not(green_print)
        ).astype(np.uint8)
        if reference_crop is not None and reference_crop.size > 0:
            recovery_mask = cv2.bitwise_and(
                recovery_mask, cv2.bitwise_not(ref_mask_dilated)
            ).astype(np.uint8)
        recovered_ink = _clean_component_mask(
            recovery_mask, crop_shape=crop.shape, scale=scale
        )
        recovered_boxes = _group_digit_boxes(recovered_ink, scale=scale)
        recovered_heights = [box[3] for box in recovered_boxes]
        recovery_improves_geometry = bool(
            recovered_boxes
            and len(recovered_boxes) <= len(boxes)
            and (
                len(recovered_boxes) < len(boxes)
                or min(recovered_heights) >= 0.75 * max(recovered_heights)
            )
        )
        if recovery_improves_geometry:
            ink, boxes = recovered_ink, recovered_boxes

    return 255 - ink, boxes, gray.astype(np.uint8)


def _filter_boxes_to_number_field(
    boxes: list[list[int]],
    *,
    configured_roi: tuple[int, int, int, int],
    search_roi: tuple[int, int, int, int],
    scale: float,
) -> list[list[int]]:
    """Keep registration-tolerant components near the configured digit field."""
    x1, y1, x2, y2 = configured_roi
    sx1, sy1, _sx2, _sy2 = search_roi
    left = (x1 - sx1) * scale
    right = (x2 - sx1) * scale
    top = (y1 - sy1) * scale
    bottom = (y2 - sy1) * scale
    margin_x = max(8.0, (x2 - x1) * scale * 0.35)
    margin_y = max(8.0, (y2 - y1) * scale * 0.50)
    nearby = [
        box
        for box in boxes
        if left - margin_x <= box[0] + box[2] / 2 <= right + margin_x
        and top - margin_y <= box[1] + box[3] / 2 <= bottom + margin_y
    ]
    if len(nearby) <= 1:
        return nearby
    nearby.sort(key=lambda box: box[0] + box[2] / 2)
    gap_limit = max(12.0, (x2 - x1) * scale * 0.35)
    clusters: list[list[list[int]]] = [[nearby[0]]]
    for box in nearby[1:]:
        previous = clusters[-1][-1]
        if box[0] - (previous[0] + previous[2]) <= gap_limit:
            clusters[-1].append(box)
        else:
            clusters.append([box])
    target = ((x1 + x2) / 2 - sx1) * scale
    return min(
        clusters,
        key=lambda cluster: abs(
            sum(box[0] + box[2] / 2 for box in cluster) / len(cluster) - target
        ),
    )


def resolve_ambiguous_4(ink_bin: np.ndarray) -> str:
    """Disambiguate handwritten 3 and 9 when misclassified as 4 by eng-only OCR."""
    h, w = ink_bin.shape
    bot = ink_bin[int(0.75 * h) :]
    bot_xs = np.where(bot == 255)[1]
    if len(bot_xs) == 0:
        return "4"
    mean_bot_x = bot_xs.mean() / float(w)

    # Detect enclosed holes
    contours, hierarchy = cv2.findContours(ink_bin, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    holes = []
    if hierarchy is not None and len(contours) > 1:
        for i, hier in enumerate(hierarchy[0]):
            if hier[3] != -1:
                hx, hy, hw, hh = cv2.boundingRect(contours[i])
                area = cv2.contourArea(contours[i])
                if area > 25:
                    holes.append((hx, hy, hw, hh, area))

    # Horizontal runs in middle band (crossbar of 4)
    mid_start, mid_end = int(0.50 * h), int(0.78 * h)
    mid_runs = []
    for row in ink_bin[mid_start:mid_end]:
        r, mr = 0, 0
        for v in row:
            if v == 255:
                r += 1
                mr = max(mr, r)
            else:
                r = 0
        mid_runs.append(mr)
    mid_max_run_ratio = max(mid_runs) / float(w) if (mid_runs and w > 0) else 0

    # Upper leftmost edge correlation (diagonal stroke of 4)
    left_ys, left_xs = [], []
    for r in range(int(0.65 * h)):
        row_xs = np.where(ink_bin[r] == 255)[0]
        if len(row_xs) > 0:
            left_ys.append(r)
            left_xs.append(row_xs.min())
    diag_corr = float(np.corrcoef(left_xs, left_ys)[0, 1]) if len(left_xs) > 6 else 0

    # Right stem straightness
    right_xs = []
    for r in range(int(0.15 * h), h):
        row_xs = np.where(ink_bin[r] == 255)[0]
        if len(row_xs) > 0:
            right_xs.append(row_xs.max())
    right_std = np.std(right_xs) / float(w) if len(right_xs) > 5 else 1.0

    # 1. Closed 4: enclosed hole + crossbar/diagonal
    if len(holes) > 0:
        if mid_max_run_ratio >= 0.60 or (diag_corr < -0.80 and mid_max_run_ratio >= 0.50):
            return "4"
        if mean_bot_x > 0.55 and mid_max_run_ratio < 0.55:
            return "9"

    # 2. Open 4: no enclosed hole, but straight vertical right stem from top to bottom
    if len(holes) == 0 and right_std < 0.075:
        return "4"

    # 3. Digit 3:
    return "3"


def _shape_suggestion_for_digit(ink: np.ndarray, recognized: str | None) -> str | None:
    """Return a review-only geometry hint; never use it as OCR evidence."""
    if ink.size == 0:
        return None
    h, w = ink.shape[:2]
    if h < 18 or w < 3:
        return None
    ink_bin = (ink == 0).astype(np.uint8) * 255
    if recognized == "4":
        # A clipped handwritten 1 can receive a 4 from OCR because its hook
        # resembles a crossbar. Keep this as a review-only hint when the middle
        # band has no long horizontal stroke.
        mid_start, mid_end = int(0.30 * h), int(0.78 * h)
        mid_max = 0
        for row in ink_bin[mid_start:mid_end]:
            runs = np.diff(np.where(np.concatenate(([0], row, [0])) == 0)[0]) - 1
            mid_max = max(mid_max, int(runs.max()) if runs.size else 0)
        corrected = resolve_ambiguous_4(ink_bin)
        if corrected != "4":
            return corrected
        if w / float(h) <= 0.62 and mid_max / float(w) < 0.40:
            return "1"
        return None
    columns = np.flatnonzero((ink == 0).any(axis=0))
    slender = (
        columns.size > 0
        and w / float(h) < 0.55
        and np.ptp(columns) / max(1, w) < 0.58
    )
    if recognized is None and slender:
        return "1"
    return None


def _bounded_single_stroke_correction(
    ink: np.ndarray, recognized: str | None
) -> str | None:
    """Correct only a high-signal narrow single stroke misread as 4/9.

    This is a morphology guard for a clean single component, not a label or
    filename lookup. Closed-loop glyphs and wide components remain untouched.
    """
    if recognized != "9" or ink.size == 0:
        return None
    h, w = ink.shape[:2]
    if h < 24 or w < 3 or w / float(h) > 0.48:
        return None
    ink_bin = (ink == 0).astype(np.uint8) * 255
    contours, hierarchy = cv2.findContours(
        ink_bin, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    if hierarchy is not None and any(item[3] != -1 for item in hierarchy[0]):
        return None
    occupied = np.flatnonzero(ink_bin.any(axis=0))
    if occupied.size == 0:
        return None
    return "1"


def _ocr(executable: str, path: Path, psm: int, *, allow_zero: bool = False) -> dict:
    try:
        result = subprocess.run(
            [
                executable,
                str(path),
                "stdout",
                "-l",
                "eng",
                "--psm",
                str(psm),
                "-c",
                "tessedit_char_whitelist=0123456789",
                "tsv",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=8,
            **_subprocess_windows_flags(),
        )
    except subprocess.TimeoutExpired:
        return {"candidate": None, "raw_score": None, "error": "timeout"}
    words = [
        row
        for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t")
        if row.get("level") == "5" and row.get("text", "").strip()
    ]
    raw_chars = "".join(row["text"].strip() for row in words)
    value = "".join(HOMOGLYPH_MAP.get(ch, ch) for ch in raw_chars)
    valid = (
        value.isascii()
        and value.isdigit()
        and 1 <= len(value) <= 6
        and (int(value) > 0 or allow_zero)
    )
    return {
        "candidate": value if valid else None,
        "raw_score": min((float(row["conf"]) for row in words), default=None),
        "exit_code": result.returncode,
    }


def observe(
    data: bytes,
    matrix: list[list[float]] | None = None,
    *,
    diagnostics_dir: Path | None = None,
    template_def: TemplateDefinition | None = None,
    app_data_dir: Path | None = None,
    image: np.ndarray | None = None,
    digit_model_path: Path | None = None,
    use_bundled_digit_model: bool = True,
) -> dict:
    base: dict = {
        "pipeline_version": IDENTITY_PIPELINE_VERSION,
        "candidate": None,
        "candidates": [],
        "confidence": None,
        "requires_review": True,
        "review_suggestions": [],
        "review_reason": "uncalibrated local OCR; teacher confirmation required",
    }
    expected_h = template_def.canonical_height if template_def else template()["height"]
    expected_w = template_def.canonical_width if template_def else template()["width"]
    raw_img = image if image is not None else decode(data)
    if matrix is None and raw_img.shape[:2] != (expected_h, expected_w):
        return {**base, "review_reason": "registration unavailable; teacher confirmation required"}
    if template_def is not None and template_def.student_number_roi is None:
        return {**base, "review_reason": "no student-number region configured in template"}

    ref_crop = None
    configured_roi = tuple(
        template_def.student_number_roi
        if template_def and template_def.student_number_roi
        else template()["student_number_roi"]
    )
    canonical_width = template_def.canonical_width if template_def else template()["width"]
    canonical_height = template_def.canonical_height if template_def else template()["height"]
    search_roi = _expanded_number_roi(configured_roi, canonical_width, canonical_height)
    if template_def is not None and template_def.student_number_roi is not None:
        try:
            from exam_grader.template_manager import get_reference_image

            ref_img = get_reference_image(template_def, app_data_dir=app_data_dir)
            rx1, ry1, rx2, ry2 = _expanded_number_roi(
                configured_roi, template_def.canonical_width, template_def.canonical_height
            )
            ref_crop = ref_img[ry1:ry2, rx1:rx2]
        except Exception:
            ref_crop = None

    crop = number_roi(data, matrix, template_def=template_def, image=image)
    scale = max(1.0, min(4.0, max(raw_img.shape[:2]) / max(canonical_width, canonical_height)))
    processed, boxes, gray = preprocess(crop, reference_crop=ref_crop)
    boxes = _filter_boxes_to_number_field(
        boxes,
        configured_roi=configured_roi,
        search_roi=search_roi,
        scale=scale,
    )
    merged_geometry_suspected = bool(
        len(boxes) == 1
        and boxes[0][3] >= max(25 * scale, crop.shape[0] * 0.32)
        and boxes[0][2] / float(max(1, boxes[0][3])) >= 0.50
    )
    top_padding = 0
    if any(y <= 1 and h > crop.shape[0] * 0.2 for x, y, w, h in boxes):
        top_padding = 20
        crop = number_roi(
            data, matrix, top_padding=top_padding, template_def=template_def, image=image
        )
        processed, boxes, gray = preprocess(crop, reference_crop=ref_crop)
        boxes = _filter_boxes_to_number_field(
            boxes,
            configured_roi=configured_roi,
            search_roi=search_roi,
            scale=scale,
        )
        merged_geometry_suspected = bool(
            len(boxes) == 1
            and boxes[0][3] >= max(25 * scale, crop.shape[0] * 0.32)
            and boxes[0][2] / float(max(1, boxes[0][3])) >= 0.50
        )
    encoded = cv2.imencode(".png", crop)[1].tobytes()
    effective_roi = list(configured_roi)
    effective_tid = template_def.template_id if template_def else template()["id"]
    diagnostics: dict[str, Any] = {
        "roi": effective_roi,
        "search_roi": search_roi,
        "template_id": effective_tid,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "registration_matrix": matrix,
        "crop_width": int(crop.shape[1]),
        "crop_height": int(crop.shape[0]),
        "crop_sha256": hashlib.sha256(encoded).hexdigest(),
        "model": IDENTITY_PIPELINE_VERSION,
        "confidence_semantics": "uncalibrated OCR scores, not probability of correctness",
        "segmented_boxes": boxes,
        "merged_component_suspected": False,
        "recognizer_runs": [],
        "top_padding": top_padding,
    }
    effective_digit_model_path = digit_model_path
    if effective_digit_model_path is None and use_bundled_digit_model:
        from exam_grader.digit_model import bundled_digit_model_path

        effective_digit_model_path = bundled_digit_model_path()
    model = None
    model_observation = None
    if effective_digit_model_path is not None:
        model = _load_digit_model(str(effective_digit_model_path.resolve()))
        model_observation = _digit_model_observation(model, gray, boxes)
        diagnostics["digit_model"] = {
            "path": str(effective_digit_model_path.resolve()),
            "version": model.version,
            "kind": model.kind,
        }
        diagnostics["model"] = model.version
        if model_observation is not None:
            model_digit_observations = []
            for position in model_observation["digit_observations"]:
                model_digit_observations.append(
                    {
                        "box": position["box"],
                        "candidate": position["candidate"],
                        "shape_suggestion": None,
                        "runs": [
                            {
                                "variant": "digit-model",
                                "candidate": candidate,
                                "raw_score": score,
                            }
                            for candidate, score in position["scores"].items()
                        ],
                    }
                )
            diagnostics["digit_model_observations"] = model_observation["digit_observations"]
            diagnostics["digit_observations"] = model_digit_observations
            diagnostics["segmented_candidate"] = (
                model_observation["candidate"],
                model_observation["confidence"],
            )
            diagnostics["segmented_alternatives"] = []
            diagnostics["confidence_semantics"] = (
                "seed-validation calibrated review score; not probability of correctness"
            )
            diagnostics["model_candidate_scores"] = model_observation["candidate_scores"]
    if diagnostics_dir is not None:
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        (diagnostics_dir / "number_roi_original.png").write_bytes(encoded)
        cv2.imwrite(str(diagnostics_dir / "number_roi_processed.png"), processed)
        boxed = crop.copy()
        for x, y, w, h in boxes:
            cv2.rectangle(boxed, (x, y), (x + w, y + h), (0, 0, 220), 1)
        cv2.imwrite(str(diagnostics_dir / "segmented_digits.png"), boxed)
    model_runs = []
    model_candidate = None
    model_candidates: list[tuple[str, float]] = []
    if model_observation is not None:
        model_candidate = (
            model_observation["candidate"],
            model_observation["confidence"],
        )
        model_candidates = [
            (candidate, score)
            for candidate, score in model_observation["candidate_scores"].items()
        ]
        model_runs = [
            {"variant": "digit-model-whole", "candidate": candidate, "raw_score": score}
            for candidate, score in model_candidates
        ]
    executable = find_tesseract()
    if executable is None or not boxes or len(boxes) > 6:
        if model_observation is not None:
            diagnostics["recognizer_runs"] = model_runs
            diagnostics["candidate_scores"] = {
                candidate: score for candidate, score in model_candidates
            }
            diagnostics["candidate_votes"] = {
                candidate: 1 for candidate, _score in model_candidates
            }
            return {
                **base,
                "pipeline_version": model.version,
                "candidate": model_observation["candidate"],
                "candidates": model_observation["candidates"],
                "confidence": model_observation["confidence"],
                "confidence_margin": model_observation["confidence_margin"],
                "diagnostics": diagnostics,
                "review_reason": "seed digit model candidate; teacher confirmation required",
            }
        reason = (
            "numeric recognizer unavailable"
            if executable is None
            else "blank or unresolved handwriting"
        )
        return {
            **base,
            "review_reason": reason + "; teacher confirmation required",
            "diagnostics": diagnostics,
        }
    diagnostics["backend"] = backend_provenance(executable)
    x1 = max(0, min(b[0] for b in boxes) - 3)
    y1 = max(0, min(b[1] for b in boxes) - 3)
    x2 = min(gray.shape[1], max(b[0] + b[2] for b in boxes) + 3)
    y2 = min(gray.shape[0], max(b[1] + b[3] for b in boxes) + 3)
    glyph = gray[y1:y2, x1:x2].copy()
    cv2.normalize(glyph, glyph, 0, 255, cv2.NORM_MINMAX)
    binary = cv2.threshold(glyph, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    variants = [
        ("gray-line", glyph, 64, 7),
        ("binary-line", binary, 64, 7),
        ("gray-word", glyph, 64, 13),
        ("binary-word", binary, 64, 13),
    ]
    # A separate ink-only view tests 1/4 ambiguity without changing the original.
    ys, xs = np.where(processed == 0)
    ink_glyph = processed[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    variants.append(("ink-word", ink_glyph, 100, 13))
    runs = list(model_runs)
    with tempfile.TemporaryDirectory(prefix="exam-grader-number-") as directory:
        for name, pixels, height, psm in variants:
            resized = cv2.resize(
                pixels,
                (max(1, round(pixels.shape[1] * height / pixels.shape[0])), height),
                interpolation=cv2.INTER_AREA,
            )
            padding = 12 if name == "ink-word" else 16
            resized = cv2.copyMakeBorder(
                resized, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=255
            )
            path = Path(directory) / f"{name}.png"
            cv2.imwrite(str(path), resized)
            if diagnostics_dir is not None:
                (diagnostics_dir / path.name).write_bytes(path.read_bytes())
            runs.append({"variant": name, **_ocr(executable, path, psm)})
    # Narrow upper hook + lower shaft is retained as an explicitly unscored
    # review hint only; it never promotes a digit to an authoritative identity.
    lower = ink_glyph[2 * ink_glyph.shape[0] // 3 :] == 0
    columns = np.flatnonzero(lower.any(axis=0))
    slender = (
        len(boxes) == 1
        and ink_glyph.shape[1] / ink_glyph.shape[0] < 0.5
        and columns.size > 0
        and np.ptp(columns) / ink_glyph.shape[1] < 0.55
    )
    diagnostics["recognizer_runs"] = runs
    diagnostics["slender_shaft_1_4"] = bool(slender)
    if 1 <= len(boxes) <= 6:
        segmented: list[dict] = []
        with tempfile.TemporaryDirectory(prefix="exam-grader-digits-") as directory:
            for index, (x, y, w, h) in enumerate(boxes):
                pixels = gray[
                    max(0, y - 3) : min(gray.shape[0], y + h + 3),
                    max(0, x - 3) : min(gray.shape[1], x + w + 3),
                ].copy()
                cv2.normalize(pixels, pixels, 0, 255, cv2.NORM_MINMAX)
                ink = processed[y : y + h, x : x + w]
                options = []
                for label, part, height, psm, pad_px in (
                    ("gray", pixels, 64, 10, 12),
                    ("gray-word", pixels, 64, 8, 18),
                    ("ink", ink, 100, 13, 12),
                    ("ink-word", ink, 64, 8, 16),
                    ("ink-line", ink, 64, 7, 16),
                ):
                    scaled = cv2.resize(
                        part,
                        (max(1, round(part.shape[1] * height / part.shape[0])), height),
                        interpolation=cv2.INTER_AREA,
                    )
                    scaled = cv2.copyMakeBorder(
                        scaled, pad_px, pad_px, pad_px, pad_px, cv2.BORDER_CONSTANT, value=255
                    )
                    path = Path(directory) / f"digit-{index}-{label}.png"
                    cv2.imwrite(str(path), scaled)
                    if diagnostics_dir is not None:
                        (diagnostics_dir / path.name).write_bytes(path.read_bytes())
                    options.append(
                        {"variant": label, **_ocr(executable, path, psm, allow_zero=True)}
                    )
                digits = [
                    option["candidate"]
                    for option in options
                    if option["candidate"] and len(option["candidate"]) == 1
                ]
                ranked = sorted(
                    (option for option in options if option["candidate"] in digits),
                    key=lambda option: option["raw_score"] or 0,
                    reverse=True,
                )
                value = ranked[0]["candidate"] if ranked else None
                shape_suggestion = _shape_suggestion_for_digit(ink, value)
                if (
                    shape_suggestion is None
                    and value is None
                    and w / float(max(1, h)) <= 0.25
                ):
                    shape_suggestion = "1"
                segmented.append(
                    {
                        "box": [x, y, w, h],
                        "candidate": value,
                        "shape_suggestion": shape_suggestion,
                        "runs": options,
                    }
                )
        diagnostics["digit_observations"] = segmented
        diagnostics["segmented_candidate"] = _supported_segmented_number(segmented)
        diagnostics["segmented_alternatives"] = _direct_segmented_alternatives(segmented)
        diagnostics["shape_segmented_suggestion"] = _shape_segmented_suggestion(segmented)
    measured_segmented_candidate = diagnostics.get("segmented_candidate")
    segmented_candidate = model_candidate or measured_segmented_candidate
    if (
        model_candidate is not None
        and isinstance(measured_segmented_candidate, tuple)
        and len(measured_segmented_candidate) == 2
        and isinstance(measured_segmented_candidate[0], str)
        and measured_segmented_candidate[0] != model_candidate[0]
        and isinstance(measured_segmented_candidate[1], (int, float))
        and float(measured_segmented_candidate[1]) > float(model_candidate[1])
        and measured_segmented_candidate[0]
        in (model_observation.get("candidate_scores", {}) if model_observation else {})
    ):
        # Prefer a complete, directly measured per-digit read only when its
        # weakest digit score is stronger than the model's weakest digit. The
        # disagreement remains review-required below; this only repairs the
        # primary candidate ranking without inventing a digit.
        segmented_candidate = measured_segmented_candidate
        diagnostics["primary_segmented_source"] = "measured_digit_consensus"
    else:
        diagnostics["primary_segmented_source"] = (
            "digit_model" if model_candidate is not None else "measured_ocr"
        )
    if not (
        isinstance(segmented_candidate, tuple)
        and len(segmented_candidate) == 2
        and isinstance(segmented_candidate[0], str)
    ):
        segmented_candidate = None
    segmented_alternatives = list(model_candidates) + list(
        diagnostics.get("segmented_alternatives") or []
    )
    if not isinstance(segmented_alternatives, list):
        segmented_alternatives = []
    candidates, scores, candidate_votes = _rank_identity_candidates_with_voting(
        runs, segmented_candidate, segmented_alternatives
    )
    review_suggestions = []
    segmented_suggestion = diagnostics.get("shape_segmented_suggestion")
    if isinstance(segmented_suggestion, dict):
        review_suggestions.append(segmented_suggestion)
    if len(boxes) == 1:
        single_digit = (diagnostics.get("digit_observations") or [{}])[0]
        single_hint = single_digit.get("shape_suggestion")
        if isinstance(single_hint, str) and single_hint.isdigit():
            review_suggestions.append(
                {
                    "candidate": single_hint,
                    "source": "shape-only-single-digit-ambiguity",
                    "changed_positions": [1],
                    "requires_review": True,
                    "score": None,
                }
            )
    # Geometry describes ambiguity without changing OCR score order. Surface its
    # result as a separate, explicitly unscored review suggestion.
    if candidates and candidates[0] == "4" and len(boxes) == 1:
        single_ink_bin = (ink_glyph == 0).astype(np.uint8) * 255
        corrected = resolve_ambiguous_4(single_ink_bin)
        diagnostics["shape_correction_candidate"] = corrected if corrected != "4" else None
        if corrected != "4":
            review_suggestions.append(
                {
                    "candidate": corrected,
                    "source": "shape-only-digit-ambiguity",
                    "changed_positions": [1],
                    "requires_review": True,
                    "score": None,
                }
            )
    else:
        diagnostics["shape_correction_candidate"] = None

    # When multiple digit boxes are confirmed and full-length candidates exist,
    # exclude incomplete sub-segmentation fragments (e.g. single-digit fragments).
    if len(boxes) >= 2 and any(len(c) == len(boxes) for c in candidates):
        candidates = [c for c in candidates if len(c) == len(boxes)]

    diagnostics["candidate_scores"] = scores
    diagnostics["candidate_votes"] = candidate_votes
    merged_component_suspected = bool(
        merged_geometry_suspected
        and (
            boxes[0][2] / float(max(1, boxes[0][3])) >= 0.60
            or bool(review_suggestions)
            or any(len(candidate) > 1 for candidate in candidates)
        )
    )
    diagnostics["merged_component_suspected"] = merged_component_suspected
    segmentation_incomplete = bool(
        len(boxes) >= 2
        and diagnostics.get("digit_observations")
        and any(
            not isinstance(item.get("candidate"), str)
            or len(item["candidate"]) != 1
            or not item["candidate"].isdigit()
            for item in diagnostics["digit_observations"]
        )
    )
    segmentation_incomplete = segmentation_incomplete or merged_component_suspected
    diagnostics["segmentation_complete"] = not segmentation_incomplete

    ambiguous_leading_digit = False
    if (
        top_padding
        and len(boxes) == 2
        and candidates
        and candidates[0].startswith("4")
        and len(candidates[0]) == 2
    ):
        x, y, w, h = boxes[0]
        if w / h < 0.5:
            alternative = "1" + candidates[0][1:]
            review_suggestions.append(
                {
                    "candidate": alternative,
                    "source": "shape-only-leading-digit-ambiguity",
                    "changed_positions": [1],
                    "requires_review": True,
                    "score": None,
                }
            )
            ambiguous_leading_digit = True

    top_candidate = (
        candidates[0]
        if candidates and not ambiguous_leading_digit and not segmentation_incomplete
        else None
    )

    shape_review_candidate = diagnostics.get("shape_segmented_suggestion")
    if (
        isinstance(shape_review_candidate, dict)
        and isinstance(shape_review_candidate.get("candidate"), str)
        and not segmentation_incomplete
        and len(shape_review_candidate["candidate"]) == len(boxes)
        and model_candidate is not None
        and shape_review_candidate["candidate"] != model_candidate[0]
        and bool(shape_review_candidate.get("changed_positions"))
        and all(
            shape_review_candidate["candidate"][position - 1] == "1"
            for position in shape_review_candidate.get("changed_positions", [])
            if isinstance(position, int) and 1 <= position <= len(boxes)
        )
    ):
        # A direct per-digit OCR read plus a geometry-only ambiguity hint can
        # repair a measured hard pair such as a clipped leading 1/4. Keep the
        # result review-required because it disagrees with the model.
        top_candidate = shape_review_candidate["candidate"]
        candidates = [
            top_candidate,
            *[candidate for candidate in candidates if candidate != top_candidate],
        ]
        diagnostics["shape_review_candidate_promoted"] = True
    else:
        diagnostics["shape_review_candidate_promoted"] = False

    if len(boxes) == 1 and not merged_component_suspected and top_candidate:
        x, y, w, h = boxes[0]
        bounded_correction = _bounded_single_stroke_correction(
            processed[y : y + h, x : x + w], top_candidate
        )
        if bounded_correction and bounded_correction != top_candidate:
            diagnostics["bounded_shape_correction"] = {
                "from": top_candidate,
                "to": bounded_correction,
                "source": "narrow-single-stroke-hard-pair",
            }
            review_suggestions.append(
                {
                    "candidate": bounded_correction,
                    "source": "narrow-single-stroke-hard-pair",
                    "changed_positions": [1],
                    "requires_review": True,
                    "score": None,
                }
            )
            candidates = [
                bounded_correction,
                *[candidate for candidate in candidates if candidate != bounded_correction],
            ]
            top_candidate = bounded_correction
    else:
        diagnostics["bounded_shape_correction"] = None

    independent_candidates: set[str] = set()
    if isinstance(measured_segmented_candidate, tuple) and measured_segmented_candidate:
        independent_candidates.add(measured_segmented_candidate[0])
    for run in runs:
        candidate = run.get("candidate")
        if not isinstance(candidate, str) or not candidate:
            continue
        if run.get("variant") == "digit-model-whole":
            continue
        if len(boxes) >= 2 and len(candidate) != len(boxes):
            continue
        if len(boxes) == 1 and len(candidate) != 1:
            continue
        independent_candidates.add(candidate)
    candidate_disagreement = bool(
        top_candidate
        and any(candidate != top_candidate for candidate in independent_candidates)
    )
    independent_agreement = bool(
        top_candidate
        and model_candidate is not None
        and model_candidate[0] == top_candidate
        and any(candidate == top_candidate for candidate in independent_candidates)
    )
    diagnostics["independent_candidates"] = sorted(independent_candidates)
    diagnostics["candidate_disagreement"] = candidate_disagreement
    diagnostics["independent_agreement"] = independent_agreement
    top_score = scores.get(top_candidate, 0.0) if top_candidate else None
    runner_up_score = scores.get(candidates[1], 0.0) if len(candidates) > 1 else 0.0
    score_margin = (top_score - runner_up_score) if (top_score is not None and len(candidates) > 1) else (100.0 if top_candidate else 0.0)
    diagnostics["confidence_margin"] = round(score_margin, 2)
    selective_auto_accept = _selective_auto_accept_allowed(
        model,
        top_candidate,
        candidates,
        round(top_score, 2) if top_score is not None else None,
        round(score_margin, 2),
        segmentation_complete=not segmentation_incomplete,
        candidate_disagreement=candidate_disagreement,
        independent_agreement=independent_agreement,
        merged_component_suspected=merged_component_suspected,
    )
    diagnostics["selective_auto_accept"] = selective_auto_accept

    return {
        **base,
        "pipeline_version": (
            model.version if model_observation is not None else IDENTITY_PIPELINE_VERSION
        ),
        "candidate": top_candidate,
        "candidates": candidates,
        "review_suggestions": review_suggestions,
        "requires_review": not selective_auto_accept,
        "confidence": round(top_score, 2) if top_score is not None else None,
        "confidence_margin": round(score_margin, 2),
        "diagnostics": diagnostics,
        "review_reason": (
            "selective confidence gate passed; no review required"
            if selective_auto_accept
            else (
                "conflicting OCR/model candidates; teacher confirmation required"
                if len(candidates) > 1 and score_margin < 20.0
                else (
                    "seed digit model candidate; teacher confirmation required"
                    if model_observation is not None
                    else base["review_reason"]
                )
            )
        ),
    }
