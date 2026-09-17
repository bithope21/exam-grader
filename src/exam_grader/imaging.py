"""Reference registration/OMR with per-question automatic decision evidence."""

import hashlib
import json
from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from time import perf_counter
from typing import cast

import cv2
import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QImageReader

from exam_grader.document_normalization import (
    DOCUMENT_NORMALIZATION_VERSION,
    perspective_normalize,
    source_sha256,
    validate_manual_corners,
)
from exam_grader.geometry_resolution import GeometryResolutionError, resolve_geometry
from exam_grader.template_manager import (
    AnswerBlock,
    TemplateDefinition,
    cell_rect_for_template,
    default_1_template_definition,
    get_reference_image,
)

CHOICES = "ABCDE"
OMR_PIPELINE_VERSION = "omr-illumination-v10-document-normalization-v2"
INK_DARKNESS_THRESHOLD = 30.0
SELECTED_DENSITY_THRESHOLD = 0.10
UNCERTAIN_DENSITY_THRESHOLD = 0.025
GREEN_GRID_CHROMA_THRESHOLD = 6.0
GREEN_CORE_DOMINANCE_THRESHOLD = 0.06
GREEN_CORE_ISOLATION_THRESHOLD = 0.02


def _image_color_theme(image: np.ndarray) -> tuple[str, dict[str, float | str]]:
    """Measure whether a photographed form has substantial green print."""
    stride = max(1, int(np.ceil(max(image.shape[:2]) / 512)))
    pixels = image[::stride, ::stride, :3].astype(np.float32).reshape(-1, 3)
    blue, green, red = pixels.T
    chroma = pixels.max(axis=1) - pixels.min(axis=1)
    brightest = pixels.max(axis=1)
    colored = (chroma >= 12.0) & (brightest >= 32.0) & (brightest <= 245.0)
    green_pixels = colored & (
        (green - np.maximum(blue, red)) >= np.maximum(6.0, 0.35 * chroma)
    )
    chromatic_count = int(np.count_nonzero(colored))
    green_count = int(np.count_nonzero(green_pixels))
    coverage = green_count / max(1, len(pixels))
    green_share = green_count / max(1, chromatic_count)
    theme = "green" if coverage >= 0.03 and green_share >= 0.60 else "monochrome"
    return theme, {
        "classifier": "photographed-form-chroma-v1",
        "sample_scope": "whole_source_image",
        "green_coverage": round(float(coverage), 4),
        "green_share_of_chromatic": round(float(green_share), 4),
    }


def _template_for_image(image: np.ndarray, template_def: TemplateDefinition) -> TemplateDefinition:
    """Correct stale monochrome metadata when the photographed form is green."""
    config = dict(template_def.registration_config)
    configured_theme = str(config.get("color_theme", "green"))
    detected_theme, evidence = _image_color_theme(image)
    effective_theme = "green" if detected_theme == "green" else configured_theme
    config["color_theme"] = effective_theme
    config["configured_color_theme"] = configured_theme
    config["color_theme_detection"] = evidence
    return replace(template_def, registration_config=config)


def _green_form_ink_mask(cell: np.ndarray, darkness_mask: np.ndarray) -> np.ndarray:
    """Remove chromatically green print while retaining neutral student ink."""
    pixels = cell.astype(np.float32)
    green_chroma = pixels[:, :, 1] - (pixels[:, :, 0] + pixels[:, :, 2]) / 2
    return darkness_mask & (green_chroma <= GREEN_GRID_CHROMA_THRESHOLD)


def _green_core_decision(
    selected: list[str], classification: str, cores: list[float]
) -> tuple[list[str], str, str | None]:
    """Resolve only strong centered marks and reject density-only multiples."""
    ranked = sorted(range(len(cores)), key=cores.__getitem__, reverse=True)
    winner = ranked[0]
    best = cores[winner]
    runner_up = cores[ranked[1]] if len(ranked) > 1 else 0.0
    if best >= SELECTED_DENSITY_THRESHOLD and runner_up < GREEN_CORE_ISOLATION_THRESHOLD:
        return [CHOICES[winner]], "single_mark", "green-center-ink-dominance"
    if classification == "multiple" and sum(core >= 0.08 for core in cores) < 2:
        return selected, "uncertain", "multiple-without-two-centered-marks"
    return selected, classification, None


def _green_cross_features(mask: np.ndarray) -> tuple[bool, bool]:
    """Detect a centered pair of diagonal strokes in one canonical answer cell."""
    height, width = mask.shape[:2]
    min_dimension = min(height, width)
    line_length = max(5, round(min_dimension * 0.24))
    margin_x = max(2, round(width * 0.12))
    margin_y = max(2, round(height * 0.12))
    segments = cv2.HoughLinesP(
        (mask > 0).astype(np.uint8) * 255,
        1,
        np.pi / 180,
        threshold=max(3, round(min_dimension * 0.12)),
        minLineLength=line_length,
        maxLineGap=max(2, round(min_dimension * 0.12)),
    )
    signs: set[int] = set()
    if segments is not None:
        for segment in segments[:, 0, :]:
            x1, y1, x2, y2 = map(int, segment)
            dx = x2 - x1
            if dx == 0:
                continue
            slope = (y2 - y1) / dx
            center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
            if (
                0.45 <= abs(slope) <= 2.5
                and margin_x <= center_x <= width - margin_x
                and margin_y <= center_y <= height - margin_y
            ):
                signs.add(1 if slope > 0 else -1)
    return len(signs) == 2, bool(signs)


def classify_ink(densities: list[float], cores: list[float]) -> tuple[list[str], str, str]:
    """Distinguish a dominant mark from weak texture/border spill.

    A coherent faint second mark still requires review. Two strong marks are a
    resolved multiple answer, not an unreadable image. Scores are not calibrated
    probabilities and thresholds are independent of the student's answer/key.
    """
    selected = [
        CHOICES[i] for i, value in enumerate(densities) if value >= SELECTED_DENSITY_THRESHOLD
    ]
    peak = max(densities)
    weak = [
        i
        for i, value in enumerate(densities)
        if UNCERTAIN_DENSITY_THRESHOLD <= value < SELECTED_DENSITY_THRESHOLD
    ]
    unresolved = [
        i
        for i in weak
        if not (selected and densities[i] < 0.06 and densities[i] < peak * 0.35 and cores[i] < 0.08)
    ]
    if unresolved or (not selected and peak >= 0.012):
        return selected, "uncertain", "faint-or-competing-ink"
    if not selected:
        return [], "blank", "no-answer-ink"
    return (
        selected,
        "multiple" if len(selected) > 1 else "single_mark",
        "core-dominance" if weak else "clear-ink",
    )


class RegistrationError(ValueError):
    """Fail-closed registration error with safe, non-image diagnostics."""

    def __init__(self, message: str, *, diagnostics: dict | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def template() -> dict:
    return json.loads(files("exam_grader").joinpath("resources/template.json").read_text())


_DEFAULT1_REF_IMAGE: np.ndarray | None = None


def reference_image() -> np.ndarray:
    global _DEFAULT1_REF_IMAGE
    if _DEFAULT1_REF_IMAGE is not None:
        return _DEFAULT1_REF_IMAGE.copy()
    data = files("exam_grader").joinpath("resources/reference.png").read_bytes()
    if hashlib.sha256(data).hexdigest() != template()["reference_sha256"]:
        raise ValueError("ภาพอ้างอิงเสียหาย กรุณาติดตั้งแอปใหม่")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("อ่านภาพอ้างอิงไม่ได้")
    _DEFAULT1_REF_IMAGE = image
    return image.copy()


def decode(data: bytes) -> np.ndarray:
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError("อ่านภาพไม่ได้")
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    pixels = np.frombuffer(image.bits(), np.uint8).reshape(image.height(), image.bytesPerLine())
    rgb = pixels[:, : image.width() * 3].reshape(image.height(), image.width(), 3).copy()
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def cell_rect(
    question: int, choice: int, *, template_def: TemplateDefinition | None = None
) -> tuple[int, int, int, int]:
    if template_def is not None:
        return cell_rect_for_template(template_def, question, choice)
    if not 1 <= question <= 60 or not 0 <= choice < 5:
        raise ValueError("Invalid cell")
    geometry = template()
    xs = geometry["groups"][(question - 1) // 15]
    ys = geometry["rows"]
    row = (question - 1) % 15
    # Exclude printed borders from ink analysis.
    return xs[choice] + 4, ys[row] + 4, xs[choice + 1] - xs[choice] - 8, ys[row + 1] - ys[row] - 8


_REF_FEATURES_CACHE: dict[tuple[str, str, bool], tuple[tuple[cv2.KeyPoint, ...], np.ndarray]] = {}


def clear_imaging_cache() -> None:
    """Clear cached reference features and images."""
    global _DEFAULT1_REF_IMAGE
    _DEFAULT1_REF_IMAGE = None
    _REF_FEATURES_CACHE.clear()


def _green_form_signal(pixels: np.ndarray) -> np.ndarray:
    values = pixels.astype(np.float32)
    return cv2.GaussianBlur(values[:, :, 1] - (values[:, :, 0] + values[:, :, 2]) / 2, (5, 5), 0)


def _grid_line_observations(
    aligned: np.ndarray, template_def: TemplateDefinition, radius: int = 10
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], int]:
    """Measure printed grid-line positions without using student marks as anchors."""
    if template_def.registration_config.get("color_theme", "green") == "green":
        signal = _green_form_signal(aligned)
    else:
        gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY).astype(np.float32)
        signal = cv2.GaussianBlur(255.0 - gray, (5, 5), 0)
    height, width = signal.shape
    x_observations: list[tuple[float, float, float]] = []
    y_observations: list[tuple[float, float, float]] = []
    expected_count = 0

    for block in template_def.answer_blocks:
        y1 = max(0, block.row_boundaries[0] + 5)
        y2 = min(height, block.row_boundaries[-1] - 5)
        x1 = max(0, block.col_boundaries[0] + 5)
        x2 = min(width, block.col_boundaries[-1] - 5)
        if y2 <= y1 or x2 <= x1:
            continue
        vertical_profile = signal[y1:y2, :].mean(axis=0)
        horizontal_profile = signal[:, x1:x2].mean(axis=1)

        for expected in block.col_boundaries:
            expected_count += 1
            lo, hi = max(0, expected - radius), min(width, expected + radius + 1)
            if hi - lo < 3:
                continue
            position = lo + int(np.argmax(vertical_profile[lo:hi]))
            local = vertical_profile[lo:hi]
            center_lo, center_hi = max(0, position - lo - 2), min(len(local), position - lo + 3)
            baseline = np.concatenate((local[:center_lo], local[center_hi:]))
            contrast = (
                float(vertical_profile[position] - np.median(baseline)) if baseline.size else 0.0
            )
            if contrast >= 2.0:
                x_observations.append((float(position), float(expected), contrast))

        for expected in block.row_boundaries:
            expected_count += 1
            lo, hi = max(0, expected - radius), min(height, expected + radius + 1)
            if hi - lo < 3:
                continue
            position = lo + int(np.argmax(horizontal_profile[lo:hi]))
            local = horizontal_profile[lo:hi]
            center_lo, center_hi = max(0, position - lo - 2), min(len(local), position - lo + 3)
            baseline = np.concatenate((local[:center_lo], local[center_hi:]))
            contrast = (
                float(horizontal_profile[position] - np.median(baseline)) if baseline.size else 0.0
            )
            if contrast >= 2.0:
                y_observations.append((float(position), float(expected), contrast))

    return x_observations, y_observations, expected_count


def _grid_alignment_metrics(aligned: np.ndarray, template_def: TemplateDefinition) -> dict:
    x_obs, y_obs, expected_count = _grid_line_observations(aligned, template_def)
    residuals = [abs(actual - expected) for actual, expected, _ in (*x_obs, *y_obs)]
    coverage = len(residuals) / max(1, expected_count)
    mean_error = float(np.mean(residuals)) if residuals else float("inf")
    median_error = float(np.median(residuals)) if residuals else float("inf")
    median_contrast = float(np.median([item[2] for item in (*x_obs, *y_obs)])) if residuals else 0.0
    confidence = (
        0.45 * coverage
        + 0.40 * float(np.exp(-mean_error / 5.0))
        + 0.15 * min(1.0, median_contrast / 10.0)
    )
    return {
        "grid_residual_px": round(mean_error, 3),
        "grid_median_residual_px": round(median_error, 3),
        "grid_line_coverage": round(coverage, 4),
        "grid_line_contrast": round(median_contrast, 3),
        "alignment_confidence": round(confidence, 4),
    }


def _canonical_identity_metrics(
    image: np.ndarray, reference: np.ndarray, template_def: TemplateDefinition
) -> dict | None:
    """Recognize an already-canonical green sheet without warping its marks."""
    if (
        image.shape != reference.shape
        or template_def.registration_config.get("color_theme", "green") != "green"
    ):
        return None
    actual_hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    reference_hsv = cv2.cvtColor(reference, cv2.COLOR_BGR2HSV)
    actual_mask = (
        (actual_hsv[:, :, 0] >= 28)
        & (actual_hsv[:, :, 0] <= 100)
        & (actual_hsv[:, :, 1] >= 18)
        & (actual_hsv[:, :, 2] >= 48)
    )
    reference_mask = (
        (reference_hsv[:, :, 0] >= 28)
        & (reference_hsv[:, :, 0] <= 100)
        & (reference_hsv[:, :, 1] >= 18)
        & (reference_hsv[:, :, 2] >= 48)
    )
    union = int(np.count_nonzero(actual_mask | reference_mask))
    overlap = float(np.count_nonzero(actual_mask & reference_mask) / max(1, union))
    grid = _grid_alignment_metrics(image, template_def)
    if not (
        overlap >= 0.95
        and grid["grid_residual_px"] <= 3.5
        and grid["grid_median_residual_px"] <= 2.5
        and grid["grid_line_coverage"] >= 0.65
        and grid["grid_line_contrast"] >= 2.5
    ):
        return None
    return {
        **grid,
        "identity_grid_overlap": round(overlap, 4),
        "alignment_confidence": round(max(grid["alignment_confidence"], 0.70 + 0.25 * overlap), 4),
    }


def _fit_line_correction(
    observations: list[tuple[float, float, float]],
) -> tuple[float, float] | None:
    if len(observations) < 4:
        return None
    actual = np.asarray([item[0] for item in observations], dtype=np.float64)
    expected = np.asarray([item[1] for item in observations], dtype=np.float64)
    weights = np.asarray([min(1.0, item[2] / 10.0) for item in observations], dtype=np.float64)
    keep = np.ones(len(actual), dtype=bool)
    for _ in range(3):
        if int(keep.sum()) < 4:
            return None
        slope, offset = np.polyfit(actual[keep], expected[keep], 1, w=weights[keep])
        residual = expected - (slope * actual + offset)
        center = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - center)))
        keep = np.abs(residual - center) <= max(1.5, 2.5 * mad)
    if not 0.97 <= slope <= 1.03 or abs(offset) > 12:
        return None
    return float(slope), float(offset)


def _refine_grid_alignment(
    aligned: np.ndarray, matrix: np.ndarray, template_def: TemplateDefinition
) -> tuple[np.ndarray, np.ndarray, dict, dict]:
    """Stage 2: gently snap the coarse warp to printed horizontal/vertical lines."""
    before = _grid_alignment_metrics(aligned, template_def)
    x_obs, y_obs, _ = _grid_line_observations(aligned, template_def)
    x_fit, y_fit = _fit_line_correction(x_obs), _fit_line_correction(y_obs)
    if x_fit is None and y_fit is None:
        return aligned, matrix, before, {"applied": False, "reason": "insufficient-grid-lines"}
    sx, tx = x_fit or (1.0, 0.0)
    sy, ty = y_fit or (1.0, 0.0)
    correction = np.asarray([[sx, 0.0, tx], [0.0, sy, ty], [0.0, 0.0, 1.0]], dtype=np.float64)
    height, width = aligned.shape[:2]
    refined = cv2.warpPerspective(aligned, correction, (width, height), borderValue=(255, 255, 255))
    after = _grid_alignment_metrics(refined, template_def)
    if (
        after["grid_residual_px"] + 0.20 >= before["grid_residual_px"]
        or after["alignment_confidence"] < before["alignment_confidence"]
    ):
        return aligned, matrix, before, {"applied": False, "reason": "quality-not-improved"}
    return (
        refined,
        correction @ matrix,
        after,
        {
            "applied": True,
            "scale": [round(sx, 6), round(sy, 6)],
            "translation_px": [round(tx, 3), round(ty, 3)],
            "before_residual_px": before["grid_residual_px"],
            "after_residual_px": after["grid_residual_px"],
        },
    )


def _grid_quad_registration(
    image: np.ndarray, reference: np.ndarray, template_def: TemplateDefinition
) -> tuple[np.ndarray, dict] | None:
    """Try page and printed-frame quads, then rank them against the known answer grid."""
    if template_def.registration_config.get("color_theme", "green") != "green":
        return None
    from exam_grader.template_discovery import detect_paper, order_quad_points

    height, width = reference.shape[:2]
    full_target = np.asarray(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32
    )

    def green_mask(pixels: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(pixels, cv2.COLOR_BGR2HSV)
        return (
            (hsv[:, :, 0] >= 28)
            & (hsv[:, :, 0] <= 100)
            & (hsv[:, :, 1] >= 18)
            & (hsv[:, :, 2] >= 48)
        ).astype(np.uint8) * 255

    ref_mask = green_mask(reference)
    ys, xs = np.where(ref_mask > 0)
    if len(xs) < 4:
        return None
    reference_frame_bounds = np.asarray(
        [
            xs.min() / max(1, width - 1),
            ys.min() / max(1, height - 1),
            xs.max() / max(1, width - 1),
            ys.max() / max(1, height - 1),
        ],
        dtype=np.float64,
    )

    def normalized_green_bounds(pixels: np.ndarray) -> np.ndarray | None:
        mask = green_mask(pixels)
        green_y, green_x = np.where(mask > 0)
        if len(green_x) < 4:
            return None
        return np.asarray(
            [
                green_x.min() / max(1, pixels.shape[1] - 1),
                green_y.min() / max(1, pixels.shape[0] - 1),
                green_x.max() / max(1, pixels.shape[1] - 1),
                green_y.max() / max(1, pixels.shape[0] - 1),
            ],
            dtype=np.float64,
        )

    print_target = np.asarray(
        [[xs.min(), ys.min()], [xs.max(), ys.min()], [xs.max(), ys.max()], [xs.min(), ys.max()]],
        dtype=np.float32,
    )
    candidates: list[dict] = []

    def add_candidate(
        corners: np.ndarray,
        target: np.ndarray,
        kind: str,
        prior: float,
        *,
        boundary_evidence: dict | None = None,
    ) -> None:
        points = order_quad_points(np.asarray(corners, dtype=np.float32).reshape(4, 2))
        edge_vectors = np.roll(points, -1, axis=0) - points
        edge_lengths = np.linalg.norm(edge_vectors, axis=1)
        if np.any(edge_lengths < max(image.shape[:2]) * 0.08):
            return
        next_vectors = np.roll(edge_vectors, -1, axis=0)
        cross = edge_vectors[:, 0] * next_vectors[:, 1] - edge_vectors[:, 1] * next_vectors[:, 0]
        if not (np.all(cross > 0) or np.all(cross < 0)):
            return
        area_ratio = abs(float(cv2.contourArea(points))) / float(image.shape[0] * image.shape[1])
        if not 0.08 <= area_ratio <= 0.97:
            return
        avg_w = float((edge_lengths[0] + edge_lengths[2]) / 2)
        avg_h = float((edge_lengths[1] + edge_lengths[3]) / 2)
        aspect = avg_w / max(avg_h, 1.0)
        target_aspect = float((target[1, 0] - target[0, 0]) / max(1.0, target[3, 1] - target[0, 1]))
        if not 0.62 <= aspect <= 1.55:
            return
        aspect_error = abs(float(np.log(max(aspect, 1e-4) / max(target_aspect, 1e-4))))
        if aspect_error > 0.45:
            return
        margin = min(
            float(points[:, 0].min()),
            float(points[:, 1].min()),
            float(image.shape[1] - 1 - points[:, 0].max()),
            float(image.shape[0] - 1 - points[:, 1].max()),
        ) / max(1.0, min(image.shape[:2]))
        touches_edge = margin < 0.008
        geometry_penalty = min(0.25, aspect_error * 0.20) + (0.20 if touches_edge else 0.0)
        transform = cv2.getPerspectiveTransform(points, target)
        warped = cv2.warpPerspective(image, transform, (width, height), borderValue=(255, 255, 255))
        refined, final_matrix, metrics, fine = _refine_grid_alignment(
            warped, transform.astype(np.float64), template_def
        )
        candidate_boundary_evidence = dict(boundary_evidence or {})
        if candidate_boundary_evidence:
            # Score the physical edge before fine grid refinement so the
            # boundary decision cannot inherit corrections from the next stage.
            observed_frame_bounds = normalized_green_bounds(warped)
            if observed_frame_bounds is not None:
                frame_alignment_error = float(
                    np.linalg.norm(observed_frame_bounds - reference_frame_bounds)
                )
                frame_alignment_score = float(np.exp(-frame_alignment_error / 0.04))
                candidate_boundary_evidence.update(
                    {
                        "template_frame_bounds": reference_frame_bounds.round(5).tolist(),
                        "observed_frame_bounds": observed_frame_bounds.round(5).tolist(),
                        "template_frame_alignment_error": round(frame_alignment_error, 5),
                        "template_frame_alignment_score": round(frame_alignment_score, 4),
                    }
                )
                metrics["template_frame_alignment_error"] = round(frame_alignment_error, 5)
                metrics["template_frame_alignment_score"] = round(frame_alignment_score, 4)
        # Keep the ranking evidence-based: a small source-type prior used to
        # let a weak page contour beat a materially better answer-grid fit.
        # Blend independent fit, coverage, residual, and geometry signals so
        # competing inner/outer edges remain visible in diagnostics.
        grid_coverage = max(0.0, min(1.0, float(metrics["grid_line_coverage"])))
        residual_score = float(np.exp(-max(0.0, float(metrics["grid_residual_px"])) / 3.0))
        contrast_score = max(0.0, min(1.0, float(metrics["grid_line_contrast"]) / 8.0))
        geometry_confidence = max(0.0, min(1.0, 1.0 - geometry_penalty / 0.45))
        grid_fit_score = (
            0.50 * float(metrics["alignment_confidence"])
            + 0.20 * grid_coverage
            + 0.20 * residual_score
            + 0.10 * contrast_score
        )
        metrics["grid_fit_score"] = round(grid_fit_score, 4)
        metrics["candidate_score"] = round(
            0.82 * grid_fit_score + 0.18 * geometry_confidence + prior * 0.05, 4
        )
        metrics["geometry_penalty"] = round(geometry_penalty, 4)
        metrics["geometry_confidence"] = round(geometry_confidence, 4)
        metrics["normalization_confidence"] = round(
            0.70 * metrics["alignment_confidence"]
            + 0.30 * metrics["geometry_confidence"],
            4,
        )
        metrics["area_ratio"] = round(area_ratio, 4)
        metrics["aspect_ratio"] = round(aspect, 4)
        metrics["touches_image_edge"] = touches_edge
        candidates.append(
            {
                "kind": kind,
                "corners": points,
                "matrix": final_matrix,
                "image": refined,
                "metrics": metrics,
                "fine": fine,
                "prior": prior,
                "target": target.copy(),
                "boundary_evidence": candidate_boundary_evidence,
            }
        )

    page_diagnostics: dict = {}
    _, _, paper_confidence, paper_corners = detect_paper(
        image, width, height, diagnostics=page_diagnostics
    )
    # The legacy detector's four full-frame defaults are weak fallbacks, not page evidence.
    for page_candidate in page_diagnostics.get("candidates", []):
        boundary_confidence = float(page_candidate.get("geometry_confidence", 0.0))
        if boundary_confidence < 0.58:
            continue
        candidate_corners = np.asarray(page_candidate["corners"], dtype=np.float32)
        add_candidate(
            candidate_corners,
            full_target,
            f"paper-{page_candidate.get('source', page_candidate.get('kind', 'quad'))}",
            0.06 if boundary_confidence >= 0.85 else -0.08,
            boundary_evidence={
                **{key: value for key, value in page_candidate.items() if key != "corners"},
                "source": str(page_candidate.get("source", page_candidate.get("kind", "quad"))),
            },
        )
    if paper_confidence >= 0.94:
        # Flatbed scans can already include a verified white page border.
        add_candidate(
            np.asarray(
                [
                    [0, 0],
                    [image.shape[1] - 1, 0],
                    [image.shape[1] - 1, image.shape[0] - 1],
                    [0, image.shape[0] - 1],
                ],
                dtype=np.float32,
            ),
            full_target,
            "verified-full-frame-scan",
            0.0,
        )

    scale = min(1.0, 1400.0 / max(image.shape[:2]))
    small = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
    source_mask = green_mask(small)
    for kernel_size in (9, 17, 31, 51):
        closed = cv2.morphologyEx(
            source_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size)),
        )
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            area_ratio = cv2.contourArea(contour) / float(small.shape[0] * small.shape[1])
            if not 0.08 <= area_ratio <= 0.97:
                continue
            hull = cv2.convexHull(contour)
            perimeter = cv2.arcLength(hull, True)
            approx = cv2.approxPolyDP(hull, 0.02 * perimeter, True)
            if len(approx) == 4:
                points = approx.reshape(4, 2).astype(np.float32) / scale
                add_candidate(points, print_target, "green-print-quad", 0.0)

    if not candidates:
        return None
    candidates.sort(key=lambda item: item["metrics"]["candidate_score"], reverse=True)
    physical_boundary_candidates = [
        candidate
        for candidate in candidates
        if candidate["boundary_evidence"].get("template_frame_alignment_score") is not None
    ]
    if physical_boundary_candidates:
        # Prefer physical edges supported by more distinct contour proposals.
        # For equally supported boundaries, use the known answer-grid fit and
        # template-frame margins to rank the crop hypotheses. This chooses the
        # physical boundary independently of the final registration winner.
        physical_boundary_candidates.sort(
            key=lambda item: (
                len(item["boundary_evidence"].get("supporting_proposal_methods", [])),
                float(item["metrics"].get("grid_fit_score", 0.0)),
                -float(item["boundary_evidence"].get("template_frame_alignment_error", float("inf"))),
                float(item["boundary_evidence"].get("proposal_score", 0.0)),
            ),
            reverse=True,
        )
        physical_boundary = physical_boundary_candidates[0]
    else:
        physical_boundary = None
    distinct_candidates: list[dict] = []
    for candidate in candidates:
        duplicate = next(
            (
                prior_candidate
                for prior_candidate in distinct_candidates
                if np.allclose(candidate["target"], prior_candidate["target"], atol=0.5)
                and float(
                    np.mean(
                        np.linalg.norm(
                            candidate["corners"] - prior_candidate["corners"], axis=1
                        )
                    )
                )
                <= max(image.shape[:2]) * 0.01
            ),
            None,
        )
        if duplicate is None:
            distinct_candidates.append(candidate)
    candidates = distinct_candidates
    diagnostics = [
        {
            "kind": candidate["kind"],
            "corners": np.round(candidate["corners"], 2).tolist(),
            "target_corners": np.round(candidate["target"], 2).tolist(),
            "boundary_evidence": candidate["boundary_evidence"],
            **candidate["metrics"],
        }
        for candidate in candidates[:12]
    ]
    best = candidates[0]
    metrics = best["metrics"]
    if (
        metrics["alignment_confidence"] < 0.62
        or metrics["grid_line_coverage"] < 0.70
        or metrics["grid_residual_px"] > 5.0
        or metrics["grid_line_contrast"] < 2.5
    ):
        return None
    return best["image"], {
        "matrix": best["matrix"].tolist(),
        "inverse_matrix": np.linalg.inv(best["matrix"]).tolist(),
        "method": "grid-quad-two-stage-v1",
        "selected_candidate": best["kind"],
        "selected_corners": np.asarray(best["corners"]).tolist(),
        "selected_target_corners": np.asarray(best["target"]).tolist(),
        "paper_confidence": round(
            float(
                physical_boundary["boundary_evidence"].get("geometry_confidence", paper_confidence)
                if physical_boundary is not None
                else paper_confidence
            ),
            4,
        ),
        "paper_corners": np.asarray(
            physical_boundary["corners"] if physical_boundary is not None else paper_corners
        ).tolist(),
        "physical_paper_corners": np.asarray(
            physical_boundary["corners"] if physical_boundary is not None else paper_corners
        ).tolist(),
        "physical_boundary_confidence": round(
            float(
                physical_boundary["boundary_evidence"].get("geometry_confidence", paper_confidence)
                if physical_boundary is not None
                else paper_confidence
            ),
            4,
        ),
        "physical_boundary_method": (
            "/".join(
                str(value)
                for value in (
                    physical_boundary["boundary_evidence"].get("source"),
                    physical_boundary["boundary_evidence"].get("proposal_method"),
                )
                if value
            )
            if physical_boundary is not None
            else page_diagnostics.get("selected_candidate")
        ),
        "physical_boundary_proposal_score": (
            round(float(physical_boundary["boundary_evidence"].get("proposal_score", 0.0)), 4)
            if physical_boundary is not None
            else None
        ),
        "physical_boundary_supporting_method_count": (
            len(physical_boundary["boundary_evidence"].get("supporting_proposal_methods", []))
            if physical_boundary is not None
            else None
        ),
        "physical_boundary_grid_fit_score": (
            round(float(physical_boundary["metrics"].get("grid_fit_score", 0.0)), 4)
            if physical_boundary is not None
            else None
        ),
        "physical_boundary_selection_basis": (
            "proposal-method-consensus-then-grid-fit" if physical_boundary is not None else None
        ),
        "physical_boundary_template_frame_alignment_error": (
            physical_boundary["boundary_evidence"].get("template_frame_alignment_error")
            if physical_boundary is not None
            else None
        ),
        "paper_boundary_candidates": [
            {
                **candidate["boundary_evidence"],
                "corners": np.round(candidate["corners"], 2).tolist(),
                "registration_grid_fit_score": round(
                    float(candidate["metrics"].get("grid_fit_score", 0.0)), 4
                ),
            }
            for candidate in physical_boundary_candidates[:12]
        ] if physical_boundary_candidates else page_diagnostics.get("candidates", [])[:12],
        "candidate_count": len(candidates),
        "candidate_diagnostics": diagnostics,
        "fine_registration": best["fine"],
        "canonical_size": [width, height],
        "roi_coordinate_space": "canonical_px",
        **metrics,
    }


def register(
    image: np.ndarray,
    *,
    template_def: TemplateDefinition | None = None,
    refined: bool = False,
    app_data_dir: Path | None = None,
    reference_override: np.ndarray | None = None,
    manual_corners: np.ndarray | list[list[float]] | None = None,
) -> tuple[np.ndarray, dict]:
    started = perf_counter()
    if template_def is not None:
        reference = get_reference_image(
            template_def, app_data_dir=app_data_dir, reference_override=reference_override
        )
    elif reference_override is not None:
        reference = reference_override
    else:
        reference = reference_image()
    effective_template = template_def or default_1_template_definition()
    if manual_corners is not None:
        points = validate_manual_corners(
            manual_corners,
            image.shape,
            target_size=(reference.shape[1], reference.shape[0]),
        )
        target = np.asarray(
            [
                [0.0, 0.0],
                [reference.shape[1] - 1.0, 0.0],
                [reference.shape[1] - 1.0, reference.shape[0] - 1.0],
                [0.0, reference.shape[0] - 1.0],
            ],
            dtype=np.float32,
        )
        initial_manual_matrix = cv2.getPerspectiveTransform(points, target).astype(np.float64)
        final_matrix = initial_manual_matrix
        final_image = perspective_normalize(
            image, initial_manual_matrix, (reference.shape[1], reference.shape[0])
        )
        # Teacher-chosen corners define the physical crop. Fine-grid evidence
        # may describe quality, but it must not reject or replace that crop.
        # The old gate made valid manual selections unusable precisely when
        # the grid was weak or slightly clipped.
        manual_grid_metrics = _grid_alignment_metrics(final_image, effective_template)
        manual_fine_registration = {
            "applied": False,
            "reason": "manual-corners-authoritative",
        }
        grid_needs_review = (
            manual_grid_metrics["alignment_confidence"] < 0.55
            or manual_grid_metrics["grid_line_coverage"] < 0.60
            or manual_grid_metrics["grid_residual_px"] > 5.0
            or manual_grid_metrics["grid_line_contrast"] < 2.5
        )
        coverage = cv2.warpPerspective(
            np.ones(image.shape[:2], np.uint8),
            final_matrix,
            (reference.shape[1], reference.shape[0]),
        )
        if effective_template.answer_blocks:
            ymin = min(block.row_boundaries[0] for block in effective_template.answer_blocks)
            ymax = max(block.row_boundaries[-1] for block in effective_template.answer_blocks)
            xmin = min(block.col_boundaries[0] for block in effective_template.answer_blocks)
            xmax = max(block.col_boundaries[-1] for block in effective_template.answer_blocks)
            table_coverage = float(coverage[ymin:ymax, xmin:xmax].mean())
        else:
            table_coverage = 0.0
        coverage_needs_review = table_coverage < 0.985
        manual_warnings = []
        if grid_needs_review:
            manual_warnings.append("manual-grid-fit-weak")
        if coverage_needs_review:
            manual_warnings.append("manual-crop-clips-template-table")
        manual_metrics = {
            **manual_grid_metrics,
            "matrix": final_matrix.tolist(),
            "inverse_matrix": np.linalg.inv(final_matrix).tolist(),
            "method": "manual-paper-quad-authoritative-v2",
            "selected_candidate": "manual-4-corner",
            "selected_corners": points.tolist(),
            "paper_corners": points.tolist(),
            "physical_paper_corners": points.tolist(),
            "physical_boundary_confidence": 1.0,
            "candidate_count": 1,
            "candidate_diagnostics": [
                {"kind": "manual-4-corner", "corners": points.tolist(), **manual_grid_metrics}
            ],
            "fine_registration": manual_fine_registration,
            "normalization_boundary_status": "human-adjusted",
            "normalization_confidence": manual_grid_metrics["alignment_confidence"],
            "normalization_requires_review": bool(manual_warnings),
            "manual_grid_status": "review-required" if manual_warnings else "fit-acceptable",
            "manual_grid_warnings": manual_warnings,
            "canonical_size": [reference.shape[1], reference.shape[0]],
            "roi_coordinate_space": "canonical_px",
            "table_coverage": round(table_coverage, 6),
            "seconds": round(perf_counter() - started, 6),
        }
        return final_image, manual_metrics

    if image.shape == reference.shape and np.array_equal(image, reference):
        return image.copy(), {
            "matrix": np.eye(3).tolist(),
            "inliers": 0,
            "method": "exact-reference",
            "alignment_confidence": 1.0,
            "normalization_confidence": 1.0,
            "selected_candidate": "canonical-reference",
            "selected_corners": [
                [0.0, 0.0],
                [reference.shape[1] - 1.0, 0.0],
                [reference.shape[1] - 1.0, reference.shape[0] - 1.0],
                [0.0, reference.shape[0] - 1.0],
            ],
        }
    identity_metrics = _canonical_identity_metrics(image, reference, effective_template)
    if identity_metrics is not None:
        height, width = reference.shape[:2]
        corners = [[0.0, 0.0], [width - 1.0, 0.0], [width - 1.0, height - 1.0], [0.0, height - 1.0]]
        return image.copy(), {
            "matrix": np.eye(3).tolist(),
            "inverse_matrix": np.eye(3).tolist(),
            "method": "canonical-grid-identity-v1",
            "selected_candidate": "canonical-identity",
            "candidate_count": 1,
            "candidate_diagnostics": [
                {"kind": "canonical-identity", "corners": corners, **identity_metrics}
            ],
            "paper_confidence": identity_metrics["identity_grid_overlap"],
            "paper_corners": corners,
            "fine_registration": {"applied": False, "reason": "already-canonical"},
            "canonical_size": [width, height],
            "roi_coordinate_space": "canonical_px",
            **identity_metrics,
        }
    grid_candidate = _grid_quad_registration(image, reference, effective_template)
    # Bound feature extraction size while retaining transform into decoded original pixels.
    scale = min(1.0, 1800 / max(image.shape[:2]))
    working = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
    extractor = cv2.SIFT.create(nfeatures=5000) if refined else cv2.ORB.create(nfeatures=5000)
    kp1, desc1 = extractor.detectAndCompute(cv2.cvtColor(working, cv2.COLOR_BGR2GRAY), None)

    # Reference feature caching avoids redundant 150-200ms SIFT / 20ms ORB extraction per sheet
    if template_def is not None:
        ref_key = (template_def.template_id, template_def.reference_sha256, refined)
    elif reference_override is not None:
        ref_key = ("override", str(id(reference_override)), refined)
    else:
        ref_key = ("default-1", template()["reference_sha256"], refined)

    cached_ref = _REF_FEATURES_CACHE.get(ref_key)
    if cached_ref is not None:
        kp2_tuple, desc2 = cached_ref
        kp2 = list(kp2_tuple)
    else:
        kp2_seq, desc2 = extractor.detectAndCompute(
            cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY), None
        )
        kp2 = list(kp2_seq)
        if desc2 is not None:
            _REF_FEATURES_CACHE[ref_key] = (tuple(kp2_seq), desc2)

    if desc1 is None or desc2 is None:
        if grid_candidate is not None:
            return grid_candidate
        raise RegistrationError(
            "หาตารางไม่พบ กรุณาตรวจภาพต้นฉบับ",
            diagnostics={"stage": "features", "seconds": round(perf_counter() - started, 6)},
        )
    matches = cv2.BFMatcher(cv2.NORM_L2 if refined else cv2.NORM_HAMMING).knnMatch(
        desc1, desc2, k=2
    )
    good = [
        pair[0] for pair in matches if len(pair) == 2 and pair[0].distance < 0.7 * pair[1].distance
    ]

    def _paper_quad_fallback() -> tuple[np.ndarray, dict] | None:
        """Warp page candidates, then rank them against template grid evidence."""
        if template_def is None or not template_def.registration_config.get(
            "allow_paper_quad_fallback", False
        ):
            return None
        from exam_grader.template_discovery import detect_paper

        page_diagnostics: dict = {}
        _, _, detector_confidence, detector_corners = detect_paper(
            image,
            reference.shape[1],
            reference.shape[0],
            diagnostics=page_diagnostics,
        )
        height, width = reference.shape[:2]
        target = np.asarray(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
            dtype=np.float32,
        )
        if template_def.answer_blocks:
            ymin = min(b.row_boundaries[0] for b in template_def.answer_blocks)
            ymax = max(b.row_boundaries[-1] for b in template_def.answer_blocks)
            xmin = min(b.col_boundaries[0] for b in template_def.answer_blocks)
            xmax = max(b.col_boundaries[-1] for b in template_def.answer_blocks)
        else:
            return None

        registrations: list[dict] = []
        for candidate in page_diagnostics.get("candidates", [])[:12]:
            try:
                from exam_grader.template_discovery import order_quad_points

                corners = order_quad_points(
                    np.asarray(candidate.get("corners", detector_corners), dtype=np.float32)
                )
                if corners.shape != (4, 2) or not np.isfinite(corners).all():
                    continue
                candidate_matrix = cv2.getPerspectiveTransform(corners, target).astype(np.float64)
                coarse = cv2.warpPerspective(
                    image, candidate_matrix, (width, height), borderValue=(255, 255, 255)
                )
                aligned, fine_matrix, grid_metrics, fine = _refine_grid_alignment(
                    coarse, candidate_matrix, template_def
                )
                coverage = cv2.warpPerspective(
                    np.ones(image.shape[:2], np.uint8),
                    fine_matrix,
                    (width, height),
                )
                table_coverage = float(coverage[ymin:ymax, xmin:xmax].mean())
                grid_fit_score = (
                    0.50 * float(grid_metrics["alignment_confidence"])
                    + 0.20 * min(1.0, float(grid_metrics["grid_line_coverage"]))
                    + 0.20
                    * float(np.exp(-max(0.0, float(grid_metrics["grid_residual_px"])) / 3.0))
                    + 0.10 * min(1.0, float(grid_metrics["grid_line_contrast"]) / 8.0)
                )
                physical_confidence = float(
                    candidate.get("physical_boundary_confidence", candidate.get("geometry_confidence", 0.0))
                )
                score = (
                    0.62 * grid_fit_score
                    + 0.28 * physical_confidence
                    + 0.10 * table_coverage
                )
                normalization_confidence = (
                    0.70 * float(grid_metrics["alignment_confidence"])
                    + 0.30 * physical_confidence
                )
                needs_review = bool(
                    normalization_confidence < 0.82
                    or physical_confidence < 0.82
                    or grid_metrics["alignment_confidence"] < 0.78
                    or grid_metrics["grid_line_coverage"] < 0.90
                    or grid_metrics["grid_residual_px"] > 3.0
                    or grid_metrics["grid_line_contrast"] < 2.5
                    or table_coverage < 0.985
                )
                registrations.append(
                    {
                        "image": aligned,
                        "matrix": fine_matrix,
                        "corners": corners,
                        "candidate": candidate,
                        "grid": grid_metrics,
                        "fine": fine,
                        "table_coverage": table_coverage,
                        "score": score,
                        "physical_confidence": physical_confidence,
                        "normalization_confidence": normalization_confidence,
                        "needs_review": needs_review,
                        "grid_fit_score": grid_fit_score,
                    }
                )
            except (cv2.error, TypeError, ValueError, np.linalg.LinAlgError):
                continue
        if not registrations:
            return None
        registrations.sort(key=lambda item: float(item["score"]), reverse=True)
        best = registrations[0]
        candidate_diagnostics = [
            {
                **{
                    key: value
                    for key, value in item["candidate"].items()
                    if key != "corners"
                },
                "corners": np.round(item["corners"], 2).tolist(),
                "grid_fit_score": round(float(item["grid_fit_score"]), 4),
                "candidate_score": round(float(item["score"]), 4),
                "table_coverage": round(float(item["table_coverage"]), 6),
                **item["grid"],
            }
            for item in registrations
        ]
        return best["image"], {
            "matrix": best["matrix"].tolist(),
            "inverse_matrix": np.linalg.inv(best["matrix"]).tolist(),
            "inliers": 0,
            "good_matches": len(good),
            "method": "paper-quad-grid-refined-v2",
            "selected_candidate": best["candidate"].get("source", "paper-quad"),
            "selected_corners": best["corners"].tolist(),
            "paper_confidence": round(float(detector_confidence), 4),
            "paper_corners": detector_corners.tolist(),
            "physical_paper_corners": best["corners"].tolist(),
            "physical_boundary_confidence": round(best["physical_confidence"], 4),
            "physical_boundary_method": best["candidate"].get("source"),
            "paper_boundary_candidates": page_diagnostics.get("candidates", [])[:12],
            "candidate_count": len(registrations),
            "candidate_diagnostics": candidate_diagnostics,
            "fine_registration": best["fine"],
            "canonical_size": [width, height],
            "roi_coordinate_space": "canonical_px",
            "table_coverage": round(float(best["table_coverage"]), 6),
            "review_required": best["needs_review"],
            "normalization_boundary_status": "detected",
            "normalization_confidence": round(best["normalization_confidence"], 4),
            "normalization_requires_review": best["needs_review"],
            "grid_fit_score": round(float(best["grid_fit_score"]), 4),
            **best["grid"],
            "seconds": round(perf_counter() - started, 6),
        }

    def _registration_fallback() -> tuple[np.ndarray, dict] | None:
        return grid_candidate or _paper_quad_fallback()

    if len(good) < 24:
        fallback_result = _registration_fallback()
        if fallback_result is not None:
            return fallback_result
        raise RegistrationError(
            "จัดแนวภาพไม่ได้ กรุณาตรวจหรือถ่ายภาพใหม่",
            diagnostics={
                "stage": "matches",
                "good_matches": len(good),
                "seconds": round(perf_counter() - started, 6),
            },
        )
    src = np.asarray([kp1[m.queryIdx].pt for m in good], dtype=np.float32)
    dst = np.asarray([kp2[m.trainIdx].pt for m in good], dtype=np.float32)
    matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 2.5)

    def _is_valid_homography(m: np.ndarray | None, k: np.ndarray | None) -> bool:
        if m is None or k is None:
            return False
        inliers = int(k.sum())
        ratio = float(k.mean())
        if inliers < 20:
            return False
        if ratio >= 0.45:
            return True
        # For dense keypoint matching where paper background textures generate matches,
        # high inlier counts (>50 or >100) are mathematically impossible by chance with RANSAC
        if inliers >= 80 and ratio >= 0.35:
            return True
        if inliers >= 150 and ratio >= 0.30:
            return True
        return False

    if not _is_valid_homography(matrix, mask):
        if refined:
            matrix_alt, mask_alt = cv2.findHomography(src, dst, cv2.RANSAC, 3.5)
            if _is_valid_homography(matrix_alt, mask_alt):
                matrix, mask = matrix_alt, mask_alt
            else:
                fallback_result = _registration_fallback()
                if fallback_result is not None:
                    return fallback_result
                raise RegistrationError(
                    "ภาพไม่ตรงแบบหลัก หรือจัดแนวไม่ชัดเจน",
                    diagnostics={
                        "stage": "homography",
                        "good_matches": len(good),
                        "seconds": round(perf_counter() - started, 6),
                    },
                )
        else:
            fallback_result = _registration_fallback()
            if fallback_result is not None:
                return fallback_result
            raise RegistrationError(
                "ภาพไม่ตรงแบบหลัก หรือจัดแนวไม่ชัดเจน",
                diagnostics={
                    "stage": "homography",
                    "good_matches": len(good),
                    "seconds": round(perf_counter() - started, 6),
                },
            )
    inlier_points = dst[mask.ravel().astype(bool)]
    span = np.ptp(inlier_points, axis=0)
    min_span_x = 500 if template_def is None else int(reference.shape[1] * 0.45)
    min_span_y = (
        (300 if refined else 400)
        if template_def is None
        else int(reference.shape[0] * (0.25 if refined else 0.35))
    )
    if span[0] < min_span_x or span[1] < min_span_y:
        fallback_result = _registration_fallback()
        if fallback_result is not None:
            return fallback_result
        raise RegistrationError(
            "พบตารางไม่ครบทั้งหน้า",
            diagnostics={
                "stage": "coverage",
                "anchor_span": [float(span[0]), float(span[1])],
                "seconds": round(perf_counter() - started, 6),
            },
        )
    matrix = matrix @ np.diag([scale, scale, 1.0])
    aligned = cv2.warpPerspective(
        image, matrix, (reference.shape[1], reference.shape[0]), borderValue=(255, 255, 255)
    )

    theme = (
        template_def.registration_config.get("color_theme", "green") if template_def else "green"
    )
    if theme == "green":

        def form_signal(pixels):
            values = pixels.astype(np.float32)
            green = values[:, :, 1] - (values[:, :, 0] + values[:, :, 2]) / 2
            return cv2.GaussianBlur(green, (5, 5), 0)
    else:

        def form_signal(pixels):
            gray_sig = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY).astype(np.float32)
            return cv2.GaussianBlur(gray_sig, (5, 5), 0)

    try:
        if not refined:
            raise cv2.error("refinement not requested")
        ref_sig = form_signal(reference)
        ali_sig = form_signal(aligned)
        max_dim = max(ref_sig.shape[:2])
        if max_dim > 860:
            ecc_scale = 860.0 / max_dim
            s_ref = cv2.resize(ref_sig, None, fx=ecc_scale, fy=ecc_scale)
            s_ali = cv2.resize(ali_sig, None, fx=ecc_scale, fy=ecc_scale)
        else:
            ecc_scale = 1.0
            s_ref, s_ali = ref_sig, ali_sig

        _, corr_small = cv2.findTransformECC(
            s_ref,
            s_ali,
            np.eye(3, dtype=np.float32),
            cv2.MOTION_HOMOGRAPHY,
            (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 25, 1e-5),
        )
        if ecc_scale < 1.0:
            S = np.diag([ecc_scale, ecc_scale, 1.0])
            correction = np.linalg.inv(S) @ corr_small @ S
        else:
            correction = corr_small

        anchor_corners = np.array(
            [
                [
                    [30.0, 180.0],
                    [float(reference.shape[1] - 30), 180.0],
                    [float(reference.shape[1] - 30), float(reference.shape[0] - 100)],
                    [30.0, float(reference.shape[0] - 100)],
                ]
            ],
            np.float32,
        )
        if (
            np.max(
                np.linalg.norm(
                    cv2.perspectiveTransform(anchor_corners, correction) - anchor_corners,
                    axis=2,
                )
            )
            < 25
        ):
            matrix = np.linalg.inv(correction) @ matrix
            aligned = cv2.warpPerspective(
                image, matrix, (reference.shape[1], reference.shape[0]), borderValue=(255, 255, 255)
            )
    except cv2.error:
        pass

    theme = (
        template_def.registration_config.get("color_theme", "green") if template_def else "green"
    )
    fine_registration = {"applied": False, "reason": "non-green-template"}
    grid_metrics: dict[str, float] = {}
    if theme == "green":
        aligned, matrix, grid_metrics, fine_registration = _refine_grid_alignment(
            aligned, matrix, effective_template
        )

    coverage = cv2.warpPerspective(
        np.ones(image.shape[:2], np.uint8), matrix, (reference.shape[1], reference.shape[0])
    )
    if template_def is None:
        table_cov = float(coverage[227:714, 56:814].mean())
    else:
        ymin = min(b.row_boundaries[0] for b in template_def.answer_blocks)
        ymax = max(b.row_boundaries[-1] for b in template_def.answer_blocks)
        xmin = min(b.col_boundaries[0] for b in template_def.answer_blocks)
        xmax = max(b.col_boundaries[-1] for b in template_def.answer_blocks)
        table_cov = float(coverage[ymin:ymax, xmin:xmax].mean())

    if table_cov < 0.995:
        fallback_result = _registration_fallback()
        if fallback_result is not None:
            return fallback_result
        raise RegistrationError(
            "ภาพตัดตารางคำตอบไม่ครบ",
            diagnostics={
                "stage": "coverage",
                "coverage": table_cov,
                "seconds": round(perf_counter() - started, 6),
            },
        )
    feature_registration = {
        "matrix": matrix.tolist(),
        "inverse_matrix": np.linalg.inv(matrix).tolist(),
        "inliers": int(mask.sum()),
        "method": "sift-ransac-ecc-v2" if refined else "orb-ransac-draft-v1",
        "good_matches": len(good),
        "inlier_ratio": round(float(mask.mean()), 6),
        "table_coverage": table_cov,
        "fine_registration": fine_registration,
        "roi_coordinate_space": "canonical_px",
        "seconds": round(perf_counter() - started, 6),
    }
    if theme == "green":
        feature_registration.update(grid_metrics)
        grid_quality_ok = (
            grid_metrics["alignment_confidence"] >= 0.62
            and grid_metrics["grid_line_coverage"] >= 0.70
            and grid_metrics["grid_residual_px"] <= 5.0
            and grid_metrics["grid_line_contrast"] >= 2.5
        )
        feature_alignment_confidence = (
            min(1.0, float(mask.mean()) * 1.5)
            * min(1.0, float(span[0]) / max(1.0, min_span_x))
            * min(1.0, float(span[1]) / max(1.0, min_span_y))
            * min(1.0, table_cov)
        )
        feature_quality_ok = grid_quality_ok
        feature_registration["feature_alignment_confidence"] = round(
            feature_alignment_confidence, 4
        )
        feature_registration["alignment_evidence"] = (
            "template-grid" if grid_quality_ok else "weak-grid-review-required"
        )
        if grid_candidate is not None:
            candidate_metrics = grid_candidate[1]
            candidate_is_better = (
                not feature_quality_ok
                or candidate_metrics["alignment_confidence"]
                > grid_metrics["alignment_confidence"] + 0.015
                or (
                    abs(
                        candidate_metrics["alignment_confidence"]
                        - grid_metrics["alignment_confidence"]
                    )
                    <= 0.015
                    and candidate_metrics["grid_residual_px"] + 0.35
                    < grid_metrics["grid_residual_px"]
                )
            )
            if candidate_is_better:
                return grid_candidate
        if not feature_quality_ok:
            # A geometrically usable transform with a weak template/grid fit is
            # still useful for teacher review. Keep the warped image available,
            # but make every answer non-automatic through the normalization
            # review gate. True decode/coverage/degenerate-geometry failures
            # still raise above and cannot reach OMR.
            feature_registration.update(
                {
                    "alignment_needs_review": True,
                    "normalization_requires_review": True,
                    "alignment_review_reason": "จัดแนวไม่มั่นใจ กรุณาตรวจภาพต้นฉบับ",
                    "alignment_quality_thresholds": {
                        "minimum_confidence": 0.62,
                        "minimum_grid_line_coverage": 0.70,
                        "maximum_grid_residual_px": 5.0,
                        "minimum_grid_line_contrast": 2.5,
                    },
                }
            )
    else:
        feature_registration["alignment_confidence"] = round(
            min(1.0, float(mask.mean()) * 1.5)
            * min(1.0, float(span[0]) / max(1.0, min_span_x))
            * min(1.0, float(span[1]) / max(1.0, min_span_y))
            * min(1.0, table_cov),
            4,
        )
    return aligned, feature_registration


def align_block_lattice(
    gray: np.ndarray, block: AnswerBlock, search_range: int = 18
) -> tuple[int, int]:
    """Find exact (dx, dy) translation offset for an answer block by Sobel line resonance.

    Photocopied and photographed sheets often carry a 5-32px translation residual
    relative to the canonical blank reference. Correlating horizontal and vertical
    Sobel gradients along the block's expected row and column boundaries snaps the
    cell coordinates snugly to the physical table grid.
    """
    bx0, by0 = block.col_boundaries[0], block.row_boundaries[0]
    bx1, by1 = block.col_boundaries[-1], block.row_boundaries[-1]
    pad = search_range + 5
    h_img, w_img = gray.shape[:2]
    y_min, y_max = max(0, by0 - pad), min(h_img, by1 + pad)
    x_min, x_max = max(0, bx0 - pad), min(w_img, bx1 + pad)
    region = gray[y_min:y_max, x_min:x_max]
    if region.size == 0 or region.shape[0] < 10 or region.shape[1] < 10:
        return 0, 0

    sob_y = np.abs(cv2.Sobel(region, cv2.CV_64F, 0, 1, ksize=3))
    sob_x = np.abs(cv2.Sobel(region, cv2.CV_64F, 1, 0, ksize=3))
    expected_rows = [r - y_min for r in block.row_boundaries]
    expected_cols = [c - x_min for c in block.col_boundaries]

    best_dy, max_score_y = 0, -1.0
    for dy in range(-search_range, search_range + 1):
        valid_rows = [r + dy for r in expected_rows if 0 <= r + dy < region.shape[0]]
        if not valid_rows:
            continue
        score = sum(float(sob_y[r, :].mean()) for r in valid_rows)
        if score > max_score_y:
            max_score_y = score
            best_dy = dy

    best_dx, max_score_x = 0, -1.0
    for dx in range(-search_range, search_range + 1):
        valid_cols = [c + dx for c in expected_cols if 0 <= c + dx < region.shape[1]]
        if not valid_cols:
            continue
        score = sum(float(sob_x[:, c].mean()) for c in valid_cols)
        if score > max_score_x:
            max_score_x = score
            best_dx = dx

    return best_dx, best_dy


def analyze(
    data: bytes,
    *,
    refined: bool = False,
    template_def: TemplateDefinition | None = None,
    app_data_dir: Path | None = None,
    reference_override: np.ndarray | None = None,
    decoded_image: np.ndarray | None = None,
    manual_corners: np.ndarray | list[list[float]] | None = None,
) -> dict:
    decode_started = perf_counter()
    decoded = decoded_image if decoded_image is not None else decode(data)
    decode_seconds = perf_counter() - decode_started
    effective_template = _template_for_image(
        decoded, template_def or default_1_template_definition()
    )
    registration_started = perf_counter()
    try:
        aligned, registration = register(
            decoded,
            template_def=effective_template,
            refined=refined,
            app_data_dir=app_data_dir,
            reference_override=reference_override,
            manual_corners=manual_corners,
        )
    except RegistrationError as error:
        if refined:
            diagnostics = dict(getattr(error, "diagnostics", {}) or {})
            if "paper_boundary_candidates" not in diagnostics:
                try:
                    from exam_grader.template_discovery import detect_paper

                    page_diagnostics: dict = {}
                    detect_paper(
                        decoded,
                        effective_template.canonical_width,
                        effective_template.canonical_height,
                        diagnostics=page_diagnostics,
                    )
                    diagnostics["paper_boundary_candidates"] = page_diagnostics.get(
                        "candidates", []
                    )[:12]
                    diagnostics["paper_candidate_count"] = page_diagnostics.get(
                        "candidate_count", 0
                    )
                    diagnostics["boundary_detector_selection"] = page_diagnostics.get(
                        "selected_candidate"
                    )
                except (cv2.error, ValueError):
                    pass
            error.diagnostics = diagnostics
            raise
        return analyze(
            data,
            template_def=effective_template,
            refined=True,
            app_data_dir=app_data_dir,
            reference_override=reference_override,
            decoded_image=decoded,
            manual_corners=manual_corners,
        )
    registration_seconds = perf_counter() - registration_started
    registration["color_theme"] = effective_template.registration_config.get(
        "color_theme", "green"
    )
    registration["configured_color_theme"] = effective_template.registration_config.get(
        "configured_color_theme", registration["color_theme"]
    )
    registration["color_theme_detection"] = effective_template.registration_config.get(
        "color_theme_detection", {}
    )

    # Keep provenance and transform metadata; the derived raster is regenerated
    # from the immutable source instead of being persisted alongside it.
    normalization_confidence = float(
        registration.get(
            "normalization_confidence",
            registration.get("alignment_confidence", registration.get("paper_confidence", 0.0)),
        )
    )
    registration["normalization_confidence"] = round(
        max(0.0, min(1.0, normalization_confidence)), 4
    )
    registration["normalization_requires_review"] = bool(
        registration.get("normalization_requires_review", False)
        or normalization_confidence < 0.82
        or float(registration.get("physical_boundary_confidence", 1.0)) < 0.82
    )
    registration.setdefault("normalization_boundary_status", "detected")

    if template_def is not None:
        ref_img = get_reference_image(
            effective_template, app_data_dir=app_data_dir, reference_override=reference_override
        )
    elif reference_override is not None:
        ref_img = reference_override
    else:
        ref_img = reference_image()
    reference = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY).astype(np.float32)
    # Raw pixel subtraction is invalid for photographs with exposure/illumination
    # differences. Local darkness is a conservative mark feature that suppresses
    # broad lighting changes while retaining dark strokes inside a cell.
    local_background = cv2.GaussianBlur(gray, (0, 0), 9)
    darkness = local_background - gray
    if refined:
        darkness = darkness * 180 / np.maximum(local_background, 30)
    omr_started = perf_counter()
    answers = []

    # Phase-2 Local Grid Snapping: for discovered/custom templates with fallback registration,
    # compute local (dx, dy) per block to absorb physical paper margin skew.
    block_offsets: dict[int, tuple[int, int]] = {}
    use_lattice_snapping = registration.get(
        "method"
    ) == "paper-quad-fallback-v1" or effective_template.registration_config.get(
        "allow_paper_quad_fallback", False
    )
    if use_lattice_snapping:
        gray_u8 = gray.astype(np.uint8)
        for block in effective_template.answer_blocks:
            block_offsets[block.block_index] = align_block_lattice(gray_u8, block)
    else:
        for block in effective_template.answer_blocks:
            block_offsets[block.block_index] = (0, 0)
    registration["omr_block_offsets"] = {
        str(block): [int(offset[0]), int(offset[1])] for block, offset in block_offsets.items()
    }
    try:
        geometry_resolution = resolve_geometry(
            effective_template,
            registration,
            block_offsets=block_offsets,
            source_sha256=source_sha256(data),
        )
    except GeometryResolutionError as error:
        raise RegistrationError(
            str(error),
            diagnostics={"stage": "geometry-resolver", "geometry_error": str(error)},
        ) from error

    q_to_block: dict[int, AnswerBlock] = {}
    for block in effective_template.answer_blocks:
        for q in range(block.question_start, block.question_end + 1):
            q_to_block[q] = block

    theme = effective_template.registration_config.get("color_theme", "green")
    total_q = effective_template.question_count
    for question in range(1, total_q + 1):
        block = q_to_block[question]
        dx, dy = block_offsets.get(block.block_index, (0, 0))
        choice_count = block.choice_count
        densities = []
        cores = []
        cross_features = []
        for choice in range(choice_count):
            roi = geometry_resolution["answer_rois"][str(question)][CHOICES[choice]]
            x, y, w, h = roi
            cell_raw = darkness[y : y + h, x : x + w] > (16 if refined else INK_DARKNESS_THRESHOLD)
            cell_ink = cell_raw.astype(np.uint8) * 255
            # Morphological grid line removal: eliminates table borders that encroach on the cell
            # while leaving diagonal pencil strokes ("X") intact.
            if refined and theme != "green":
                h_k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(7, min(13, w // 2)), 1))
                v_k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(7, min(13, h // 3))))
                h_lines = cv2.morphologyEx(cell_ink, cv2.MORPH_OPEN, h_k)
                v_lines = cv2.morphologyEx(cell_ink, cv2.MORPH_OPEN, v_k)
                clean_ink = cv2.bitwise_and(
                    cell_ink, cv2.bitwise_not(cv2.bitwise_or(h_lines, v_lines))
                )
            else:
                clean_ink = cell_ink
                if theme == "green":
                    clean_ink = (
                        _green_form_ink_mask(
                            aligned[y : y + h, x : x + w],
                            cell_raw,
                        ).astype(np.uint8)
                        * 255
                    )
            cores.append(float((clean_ink[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] > 0).mean()))
            densities.append(float((clean_ink > 0).mean()))
            if theme == "green":
                cross_features.append(_green_cross_features(clean_ink))
        selected, classification, reason = classify_ink(densities, cores)
        winner = int(np.argmax(densities))
        rivals = [i for i in range(choice_count) if i != winner]

        # Differential Row SNR: median baseline subtraction across choices in this row
        row_med = float(np.median(cores))
        delta_cores = [c - row_med for c in cores]
        c_winner = int(np.argmax(delta_cores))
        c_ranked = sorted(delta_cores, reverse=True)
        c_top1 = c_ranked[0]
        c_top2 = c_ranked[1] if len(c_ranked) > 1 else 0.0

        is_custom = template_def is not None and getattr(template_def, "kind", None) == "custom"
        if is_custom and classification in {"uncertain", "multiple"}:
            if (
                not selected
                and max(densities) < 0.06
                and (
                    (c_top1 < 0.035 and max(cores) < 0.05)
                    or (max(densities) < 0.035 and max(cores) < 0.03)
                )
            ):
                selected = []
                classification = "blank"
                reason = "no-answer-ink"
            elif c_top1 >= 0.05 and c_top2 < c_top1 * 0.45 and cores[c_winner] >= 0.06:
                selected = [CHOICES[c_winner]]
                classification = "single_mark"
                reason = "differential-core-dominance"
            elif c_top1 >= 0.06 and c_top2 >= c_top1 * 0.70:
                selected = [CHOICES[i] for i, dc in enumerate(delta_cores) if dc >= c_top1 * 0.70]
                classification = "multiple"
                reason = "competing-marks"

        if (
            refined
            and classification == "uncertain"
            and densities[winner] >= 0.045
            and cores[winner] >= 0.08
        ):
            if all(densities[i] < densities[winner] * 0.38 and cores[i] < 0.08 for i in rivals):
                selected, classification, reason = (
                    [CHOICES[winner]],
                    "single_mark",
                    "relative-contrast-dominance",
                )
        if refined and not selected and max(densities) >= 0.025:
            x, y, w, h = cell_rect(question, winner, template_def=effective_template)
            x += dx
            y += dy
            faint = darkness[y : y + h, x : x + w] > 12
            if (
                faint.mean() >= 0.05
                and faint[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4].mean() >= 0.07
                and all(densities[i] < 0.01 for i in rivals)
            ):
                selected, classification, reason = (
                    [CHOICES[winner]],
                    "single_mark",
                    "coherent-faint-ink",
                )
        if refined and classification in {"uncertain", "multiple"} and max(cores) < 0.08:
            xs = [c + dx for c in block.col_boundaries]
            row_idx = question - block.question_start
            y1 = block.row_boundaries[row_idx] + dy
            y2 = block.row_boundaries[row_idx + 1] + dy
            strip = aligned[y1 + 3 : y2 - 3, xs[0] : xs[-1]].astype(np.float32)
            if theme == "green":
                green = strip[:, :, 1] - (strip[:, :, 0] + strip[:, :, 2]) / 2
                mask = ((darkness[y1 + 3 : y2 - 3, xs[0] : xs[-1]] > 16) & (green < 10)).astype(
                    np.uint8
                )
            else:
                raw_mask = (darkness[y1 + 3 : y2 - 3, xs[0] : xs[-1]] > 16).astype(np.uint8)
                h_k = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
                v_k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
                h_l = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, h_k)
                v_l = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, v_k)
                mask = np.asarray(
                    cv2.bitwise_and(raw_mask, cv2.bitwise_not(cv2.bitwise_or(h_l, v_l))),
                    dtype=np.uint8,
                )
            _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
            if len(stats) > 1:
                component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                area = int(stats[component, cv2.CC_STAT_AREA])
                mass = [
                    int((labels[:, xs[c] - xs[0] : xs[c + 1] - xs[0]] == component).sum())
                    for c in range(choice_count)
                ]
                other_area = max(
                    (
                        int(s[cv2.CC_STAT_AREA])
                        for i, s in enumerate(stats[1:], 1)
                        if i != component
                    ),
                    default=0,
                )
                if area > 100 and other_area < area * 0.3 and np.count_nonzero(mass) > 1:
                    if max(mass) / area >= 0.6:
                        selected, classification, reason = (
                            [CHOICES[int(np.argmax(mass))]],
                            "single_mark",
                            "connected-mark-majority",
                        )
                    else:
                        # A single connected stroke that genuinely spans two
                        # cells is a resolved invalid answer. It earns zero,
                        # while faint spill and disconnected marks remain
                        # reviewable/multiple through the paths above.
                        classification, reason = "boundary_cross", "mark-straddles-two-cells"
        if theme == "green":
            selected, classification, green_reason = _green_core_decision(
                selected, classification, cores
            )
            if green_reason is not None:
                reason = green_reason
            cross_choices = [i for i, (is_cross, _) in enumerate(cross_features) if is_cross]
            diagonal_choices = [
                i for i, (_, has_diagonal) in enumerate(cross_features) if has_diagonal
            ]
            if (
                classification == "uncertain"
                and len(cross_choices) == 1
                and len(diagonal_choices) == 1
                and cross_choices == diagonal_choices
                and cores[cross_choices[0]] >= GREEN_CORE_DOMINANCE_THRESHOLD
            ):
                selected = [CHOICES[cross_choices[0]]]
                classification = "single_mark"
                reason = "centered-cross-geometry"
        ranked = sorted(densities, reverse=True)
        margin = ranked[0] - ranked[1] if len(ranked) > 1 else ranked[0]
        confidence_band = (
            "explicit-zero-boundary"
            if classification == "boundary_cross"
            else "review-required"
            if classification in {"uncertain", "multiple", "blank"}
            else "uncalibrated-single"
        )
        block_review_required = bool(geometry_resolution["review_gates"]["block"])
        answer_review_required = (
            classification not in {"single_mark", "blank"} or block_review_required
        )
        answers.append(
            {
                "question": question,
                "selected": selected,
                "classification": classification,
                "ink_density": densities,
                "core_density": cores,
                "decision_reason": reason,
                # Page confidence is a separate gate. A clear answer remains
                # machine-resolved for prefill even when the page still needs
                # teacher inspection; ambiguous/multiple/bad geometry does not.
                "auto_resolved": not answer_review_required,
                "answer_review_required": answer_review_required,
                "review_gates": {
                    "page": bool(registration["normalization_requires_review"]),
                    "block": block_review_required,
                    "answer": answer_review_required,
                    "identity": True,
                },
                "top_two_margin": round(float(margin), 6),
                "confidence_band": (
                    "normalization-review-required"
                    if registration["normalization_requires_review"]
                    and classification != "uncertain"
                    else confidence_band
                ),
                "feature": "relative-contrast-v2" if refined else "local-darkness-v1",
                "roi_rects": geometry_resolution["answer_rois"][str(question)],
            }
        )
    omr_seconds = perf_counter() - omr_started
    if not refined and any(a["classification"] == "uncertain" for a in answers):
        try:
            rescued = analyze(
                data,
                template_def=effective_template,
                refined=True,
                app_data_dir=app_data_dir,
                reference_override=reference_override,
                decoded_image=decoded,
                manual_corners=manual_corners,
            )
            if sum(a["classification"] == "uncertain" for a in rescued["answers"]) < sum(
                a["classification"] == "uncertain" for a in answers
            ):
                return rescued
        except RegistrationError:
            pass  # Retain the valid conservative observation if rescue fails.
    out_template_id = template()["id"] if template_def is None else template_def.template_id
    boundary_candidates = registration.get("paper_boundary_candidates", [])
    document_normalization = {
        "version": DOCUMENT_NORMALIZATION_VERSION,
        "source_sha256": source_sha256(data),
        "source_dimensions_px": [int(decoded.shape[1]), int(decoded.shape[0])],
        "exif_orientation": "QImageReader.setAutoTransform",
        "original_immutable": True,
        "preview_storage": "regenerated-on-demand-from-source-and-homography",
        "boundary_status": registration.get("normalization_boundary_status", "detected"),
        "boundary_method": registration.get("selected_candidate", registration.get("method")),
        "boundary_confidence": registration.get(
            "physical_boundary_confidence",
            registration.get("paper_confidence", registration.get("normalization_confidence")),
        ),
        "normalization_confidence": registration.get("normalization_confidence"),
        "normalization_requires_review": registration.get("normalization_requires_review", False),
        "physical_boundary_method": registration.get("physical_boundary_method"),
        "physical_boundary_confidence": registration.get("physical_boundary_confidence"),
        "physical_paper_corners": registration.get("physical_paper_corners"),
        "manual_grid_status": registration.get("manual_grid_status"),
        "manual_grid_warnings": registration.get("manual_grid_warnings", []),
        "candidate_count": registration.get("candidate_count", len(boundary_candidates)),
        "selected_corners": registration.get("selected_corners", registration.get("paper_corners")),
        "canonical_size_px": registration.get("canonical_size"),
        "photometric_feature": {
            "method": "local-background-subtraction",
            "gaussian_sigma_px": 9,
            "raw_canonical_raster_preserved": True,
        },
    }
    uncertain_questions = [
        cast(int, answer["question"])
        for answer in answers
        if answer["classification"] == "uncertain"
    ]
    return {
        "template_id": out_template_id,
        "pipeline_version": OMR_PIPELINE_VERSION,
        "registration": registration,
        "document_normalization": document_normalization,
        "diagnostic_stages": {
            "boundary": {
                "status": document_normalization["boundary_status"],
                "candidate_count": document_normalization["candidate_count"],
                "confidence": document_normalization["boundary_confidence"],
            },
            "registration": {
                "method": registration.get("method"),
                "confidence": registration.get("alignment_confidence"),
            },
            "grid": {
                "line_coverage": registration.get("grid_line_coverage"),
                "residual_px": registration.get("grid_residual_px"),
                "line_contrast": registration.get("grid_line_contrast"),
            },
            "omr": {
                "uncertain_questions": uncertain_questions,
                "uncertain_count": len(uncertain_questions),
            },
        },
        "answers": answers,
        "geometry_resolution": geometry_resolution,
        "review_gates": {
            "page": bool(registration["normalization_requires_review"]),
            "block": bool(geometry_resolution["review_gates"]["block"]),
            "answer": any(answer["answer_review_required"] for answer in answers),
            "identity": True,
        },
        "aligned": aligned,
        "student_number": None,
        "alignment_needs_review": bool(registration.get("alignment_needs_review", False)),
        "requires_review": True,
        "review_reason": "Experimental geometry/OMR; no calibrated real-sheet benchmark or digit model",
        "stage_timings": {
            "decode_seconds": round(decode_seconds, 6),
            "registration_seconds": round(registration_seconds, 6),
            "omr_seconds": round(omr_seconds, 6),
        },
        "photometric_diagnostics": {
            "reference_gray_mean": round(float(reference.mean()), 3),
            "aligned_gray_mean": round(float(gray.mean()), 3),
            "local_darkness_median": round(float(np.median(darkness)), 3),
            "feature_config": "local-background-gaussian-sigma-9",
        },
    }
