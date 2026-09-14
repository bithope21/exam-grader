"""Local, deterministic template discovery pipeline for custom answer sheets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Any

import cv2
import numpy as np

from exam_grader.imaging import decode
from exam_grader.template_manager import (
    CANONICAL_CHOICES,
    DEFAULT_THAI_LABELS,
    AnswerBlock,
    TemplateDefinition,
)


@dataclass
class DiscoveryResult:
    """Outcome of template auto-discovery with per-component confidence."""

    confidence: dict[str, float]
    overall_confidence: float
    template_def: TemplateDefinition
    warped_image: np.ndarray
    paper_corners: np.ndarray | None = None
    status_message: str = ""
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def requires_confirmation(self) -> bool:
        return (
            bool(self.warnings)
            or self.overall_confidence < 0.85
            or len(self.template_def.answer_blocks) == 0
        )


def order_quad_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def detect_paper(
    img: np.ndarray, target_w: int = 1200, target_h: int = 1720
) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Detect a sheet against neutral or colored backgrounds and warp it.

    Returns:
        (warped_image, homography_matrix, confidence, ordered_corners)
    """
    h, w = img.shape[:2]
    ordered_corners = np.array(
        [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32
    )

    # Fast check: If outer borders are uniform white flat-scanned margins,
    # the entire image is already an aligned, cropped paper scan.
    b_scan = max(4, min(h, w) // 50)
    border_scan = np.concatenate([
        img[:b_scan, :].reshape(-1, 3),
        img[-b_scan:, :].reshape(-1, 3),
        img[:, :b_scan].reshape(-1, 3),
        img[:, -b_scan:].reshape(-1, 3),
    ])
    if (
        float(np.mean(border_scan)) > 235.0
        and float(np.std(border_scan)) < 18.0
        and float(np.min(border_scan)) > 190.0
    ):
        dst = np.array(
            [[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(ordered_corners, dst)
        warped = cv2.warpPerspective(img, matrix, (target_w, target_h))
        return warped, matrix, 0.95, ordered_corners

    # Work at a bounded resolution. A union of neutral paper and green ink/paper
    # regions keeps the mask connected across forms with a colored background.
    scale = min(1.0, 1400.0 / max(h, w))
    small = cv2.resize(img, None, fx=scale, fy=scale) if scale < 1 else img
    sh, sw = small.shape[:2]
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = max(2, min(sh, sw) // 18)
    
    # Compute per-border background references to remain robust against lighting gradients / shadows
    top_lab = np.median(lab[:border].reshape(-1, 3), axis=0)
    bot_lab = np.median(lab[-border:].reshape(-1, 3), axis=0)
    left_lab = np.median(lab[:, :border].reshape(-1, 3), axis=0)
    right_lab = np.median(lab[:, -border:].reshape(-1, 3), axis=0)
    
    d_top = np.linalg.norm(lab - top_lab[None, None, :], axis=2)
    d_bot = np.linalg.norm(lab - bot_lab[None, None, :], axis=2)
    d_left = np.linalg.norm(lab - left_lab[None, None, :], axis=2)
    d_right = np.linalg.norm(lab - right_lab[None, None, :], axis=2)
    min_border_dist = np.minimum(np.minimum(d_top, d_bot), np.minimum(d_left, d_right))
    
    border_pixels = np.concatenate(
        [
            lab[:border].reshape(-1, 3),
            lab[-border:].reshape(-1, 3),
            lab[:, :border].reshape(-1, 3),
            lab[:, -border:].reshape(-1, 3),
        ],
        axis=0,
    )
    background_lab = np.median(border_pixels, axis=0)
    border_delta = np.linalg.norm(border_pixels - background_lab, axis=1)
    separation = max(13.0, float(np.percentile(border_delta, 75)) + 7.0)
    
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    hue = hsv[:, :, 0]
    neutral_paper = (saturation < 92) & (value > 112) & (min_border_dist > 15.0)
    green_paper = (hue >= 28) & (hue <= 100) & (saturation >= 18) & (value >= 48)
    mask = (neutral_paper | green_paper).astype(np.uint8) * 255
    close_size = max(7, min(41, int(round(min(sh, sw) * 0.025))))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_size, close_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    color_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Edge-based contour extraction for physical sheets under non-uniform illumination/shadows
    gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray_small, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 80)
    dilated_edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
    edge_contours, _ = cv2.findContours(dilated_edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    tagged_contours = [(c, True) for c in color_contours] + [(c, False) for c in edge_contours]
    candidates: list[tuple[float, np.ndarray, bool]] = []
    for contour, is_color in tagged_contours:
        area_ratio = cv2.contourArea(contour) / float(sw * sh)
        if not 0.12 <= area_ratio <= 0.985:
            continue
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.018 * perimeter, True)
        is_quad = len(approx) == 4
        points = approx.reshape(4, 2).astype(np.float32) if is_quad else cv2.boxPoints(cv2.minAreaRect(hull))
        points = order_quad_points(points)
        edge_lengths = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
        short_edge = max(1.0, float(min(edge_lengths)))
        aspect = float(max(edge_lengths) / short_edge)
        if not 0.48 <= aspect <= 2.2:
            continue
        frame_distance = min(
            float(points[:, 0].min()), float(points[:, 1].min()),
            float(sw - 1 - points[:, 0].max()), float(sh - 1 - points[:, 1].max()),
        ) / max(1.0, min(sh, sw))
        # Prefer a large, four-sided foreground object; touching the photo edge
        # and using a min-area rectangle each lower confidence instead of making
        # an unsupported page claim. Color-segmented paper is much more reliable
        # than interior edge features.
        source_weight = 1.0 if is_color else 0.65
        score = area_ratio * (1.0 if is_quad else 0.72) * min(1.0, 0.5 + frame_distance * 12.0) * source_weight
        candidates.append((score, points / scale, is_quad))

    if candidates:
        _, points, is_quad = max(candidates, key=lambda item: item[0])
        ordered_corners = order_quad_points(points.astype(np.float32))
        edge_lengths = np.linalg.norm(np.roll(ordered_corners, -1, axis=0) - ordered_corners, axis=1)
        frame_margin = min(
            float(ordered_corners[:, 0].min()), float(ordered_corners[:, 1].min()),
            float(w - 1 - ordered_corners[:, 0].max()), float(h - 1 - ordered_corners[:, 1].max()),
        ) / max(1.0, min(h, w))
        confidence = 0.92 if is_quad else 0.58
        if frame_margin < 0.012:
            confidence = min(confidence, 0.58)
        if (max(edge_lengths) / max(1.0, min(edge_lengths))) > 1.85:
            confidence = min(confidence, 0.72)
        dst = np.array(
            [[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(ordered_corners, dst)
        warped = cv2.warpPerspective(img, matrix, (target_w, target_h))
        return warped, matrix, confidence, ordered_corners

    # A full-frame scan may be a legitimate sheet, but its paper edge cannot be
    # independently verified. Keep it usable for correction while requiring review.
    matrix = np.diag([target_w / w, target_h / h, 1.0])
    warped = cv2.resize(img, (target_w, target_h))
    return warped, matrix, 0.45, ordered_corners


def normalize_illumination(gray: np.ndarray) -> np.ndarray:
    """Normalize lighting gradients across the sheet using large-kernel Gaussian background."""
    bg = cv2.GaussianBlur(gray, (51, 51), 0)
    norm = np.clip(
        (gray.astype(np.float32) / np.maximum(bg.astype(np.float32), 10.0)) * 255.0,
        0,
        255,
    ).astype(np.uint8)
    return norm


def extract_line_masks(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract horizontal and vertical line masks after illumination normalization and morphology.

    Returns:
        (thresh, h_lines, v_lines)
    """
    norm = normalize_illumination(gray)
    thresh = cv2.adaptiveThreshold(
        norm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 10
    )
    h_len = max(25, gray.shape[1] // 35)
    v_len = max(25, gray.shape[0] // 45)

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
    h_lines = cv2.dilate(h_lines, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 1)))

    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
    v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)
    v_lines = cv2.dilate(v_lines, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 7)))

    return thresh, h_lines, v_lines


def cluster_coordinates(indices: list[int] | np.ndarray, min_gap: int = 8) -> list[int]:
    """Cluster raw peak pixel indices into line divider coordinates."""
    if len(indices) == 0:
        return []
    sorted_idx = sorted(int(i) for i in indices)
    clusters: list[int] = []
    current = [sorted_idx[0]]
    for idx in sorted_idx[1:]:
        if idx - current[-1] <= min_gap:
            current.append(idx)
        else:
            clusters.append(int(round(float(np.mean(current)))))
            current = [idx]
    if current:
        clusters.append(int(round(float(np.mean(current)))))
    return clusters


def infer_grid_in_area(
    area_rect: tuple[int, int, int, int],
    v_lines: np.ndarray,
    h_lines: np.ndarray,
    choice_count: int = 4,
    question_start: int = 1,
) -> list[AnswerBlock]:
    """Infer one or more answer blocks inside a specified rectangular area.

    Handles single-block or multi-block layouts by detecting column grouping strides
    and row intervals.
    """
    bx, by, bw, bh = area_rect
    h_img, w_img = v_lines.shape[:2]
    # Bound area inside image
    bx = max(0, min(bx, w_img - 10))
    by = max(0, min(by, h_img - 10))
    bw = max(10, min(bw, w_img - bx))
    bh = max(10, min(bh, h_img - by))

    sub_v = v_lines[by : by + bh, bx : bx + bw]
    sub_h = h_lines[by : by + bh, bx : bx + bw]

    v_proj = sub_v.sum(axis=0)
    h_proj = sub_h.sum(axis=1)

    v_thresh = max(1000, int(v_proj.max() * 0.20)) if v_proj.max() > 0 else 1000
    h_thresh = max(1000, int(h_proj.max() * 0.20)) if h_proj.max() > 0 else 1000

    col_peaks = np.where(v_proj > v_thresh)[0]
    row_peaks = np.where(h_proj > h_thresh)[0]

    cols = cluster_coordinates(col_peaks, min_gap=8)
    rows = cluster_coordinates(row_peaks, min_gap=8)

    if len(cols) < 2 or len(rows) < 2:
        return []

    abs_cols = [bx + c for c in cols]
    abs_rows = [by + r for r in rows]

    # Keep the longest contiguous run of repeated row spacing. Header rules and
    # footer boxes otherwise get mistaken for question rows, especially after a
    # perspective warp has made one or two lines faint.
    row_diffs = np.diff(abs_rows)
    if len(row_diffs) == 0:
        return []
    spacing_samples = row_diffs[(row_diffs >= 25) & (row_diffs <= 220)]
    med_h = float(np.median(spacing_samples)) if len(spacing_samples) else float(np.median(row_diffs))
    valid = (row_diffs >= 0.50 * med_h) & (row_diffs <= 1.70 * med_h)
    runs: list[tuple[int, int]] = []
    start = None
    for i, ok in enumerate(valid):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(valid)))
    if not runs:
        return []
    run_start, run_end = max(runs, key=lambda item: item[1] - item[0])
    grid_rows = abs_rows[run_start : run_end + 1]
    # Bridge one or two faint/missing horizontal rules when the gap is an
    # integer multiple of the learned lattice spacing.  This recovers the last
    # rows of dim Vol.7 photographs without inventing a long footer lattice.
    next_index = run_end + 1
    while next_index < len(abs_rows):
        gap = abs_rows[next_index] - grid_rows[-1]
        if gap <= 1.70 * med_h:
            break
        if gap > 2.45 * med_h:
            break
        steps = max(2, int(round(gap / med_h)))
        for step in range(1, steps):
            grid_rows.append(int(round(grid_rows[-1] + gap * step / steps)))
        if abs_rows[next_index] > grid_rows[-1]:
            grid_rows.append(abs_rows[next_index])
        next_index += 1
    num_intervals = len(grid_rows) - 1

    # Standard exam blocks commonly have 20, 15, or 10 question rows
    if num_intervals >= 20:
        question_rows = grid_rows[-21:]
        q_count = 20
    elif num_intervals >= 15:
        question_rows = grid_rows[-16:]
        q_count = 15
    elif num_intervals >= 10:
        question_rows = grid_rows[-11:]
        q_count = 10
    else:
        question_rows = grid_rows
        q_count = len(question_rows) - 1

    if q_count < 1:
        return []

    # A tiny border artifact at the edge is not a cell divider.
    col_diffs = np.diff(abs_cols)
    if len(col_diffs):
        med_w = float(np.median(col_diffs))
        filtered = [abs_cols[0]]
        for left, right in zip(abs_cols, abs_cols[1:]):
            if right - left >= max(8.0, 0.45 * med_w):
                filtered.append(right)
        abs_cols = filtered
        col_diffs = np.diff(abs_cols)
    total_cols = len(abs_cols) - 1
    blocks: list[AnswerBlock] = []
    curr_q = question_start

    # Evaluate column subsets to tolerate spurious outer border lines.
    col_subsets: list[tuple[list[int], float]] = [(abs_cols, 0.0)]
    if len(abs_cols) >= 3:
        can_trim_left = (abs_cols[0] - bx <= 20)
        can_trim_right = ((bx + bw) - abs_cols[-1] <= 20)
        if can_trim_left:
            col_subsets.append((abs_cols[1:], 0.05))
        if can_trim_right:
            col_subsets.append((abs_cols[:-1], 0.05))
        if can_trim_left and can_trim_right:
            col_subsets.append((abs_cols[1:-1], 0.10))

    # Evaluate layout hypotheses across all valid strides and subsets.
    # Prefer a repeated wide first interval (the printed question-number column)
    # when the evidence supports it; otherwise retain caller preference.
    candidates: list[tuple[float, int, int, bool, list[int]]] = []
    for c_cols, penalty in col_subsets:
        c_diffs = np.diff(c_cols)
        c_total = len(c_cols) - 1
        for candidate_choices in range(2, 6):
            for with_number in (True, False):
                stride_candidate = candidate_choices + 1 if with_number else candidate_choices
                if c_total < stride_candidate or c_total % stride_candidate:
                    continue
                intervals = np.asarray(c_diffs[:c_total], dtype=float)
                groups = intervals.reshape((-1, stride_candidate))
                remainder = groups[:, 1:] if with_number else groups
                spread = float(np.std(remainder) / max(1.0, np.mean(remainder)))
                wide_ratio = float(np.mean(groups[:, 0]) / max(1.0, np.mean(remainder))) if with_number else 1.0
                if with_number and wide_ratio < 0.85:
                    continue
                evidence = (wide_ratio - 1.0) * 2.0 if with_number else 0.0
                score = evidence - spread * 2.0 - penalty
                if candidate_choices == choice_count:
                    score += 0.25
                candidates.append((score, candidate_choices, stride_candidate, with_number, c_cols))

    if candidates:
        _, inferred_choices, inferred_stride, with_number, best_cols = max(candidates, key=lambda item: item[0])
        num_blocks = (len(best_cols) - 1) // inferred_stride
        for b_i in range(num_blocks):
            if curr_q > 60:
                break
            b_cols = best_cols[b_i * inferred_stride : (b_i + 1) * inferred_stride + 1]
            choice_cols = b_cols[1:] if with_number else b_cols
            this_q_rows = min(q_count, 60 - curr_q + 1)
            b_rows = question_rows[: this_q_rows + 1]
            blocks.append(AnswerBlock(
                block_index=b_i,
                question_start=curr_q,
                question_end=curr_q + this_q_rows - 1,
                rows=this_q_rows,
                choice_count=inferred_choices,
                col_boundaries=choice_cols,
                row_boundaries=b_rows,
            ))
            curr_q += this_q_rows
    elif total_cols >= choice_count:
        # An incomplete lattice is explicitly review-required. Keep the largest
        # coherent choice run so a teacher can correct it instead of silently
        # manufacturing a right-aligned grid.
        choice_cols = abs_cols[: choice_count + 1]
        this_q_rows = min(q_count, 60 - curr_q + 1)
        blocks.append(AnswerBlock(
            block_index=0,
            question_start=curr_q,
            question_end=curr_q + this_q_rows - 1,
            rows=this_q_rows,
            choice_count=choice_count,
            col_boundaries=choice_cols,
            row_boundaries=question_rows[: this_q_rows + 1],
        ))

    return blocks


def discover_template(
    data: bytes,
    *,
    template_name: str = "แบบกระดาษคำตอบกำหนดเอง",
    template_id: str = "custom-discovered",
    preferred_choice_count: int = 4,
) -> DiscoveryResult:
    """Run robust deterministic auto-discovery on a photographed blank/representative sheet."""
    started = perf_counter()
    img = decode(data)
    target_w, target_h = 1200, 1720
    warped, matrix, paper_conf, paper_corners = detect_paper(img, target_w, target_h)

    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    thresh, h_lines, v_lines = extract_line_masks(gray)

    table_mask = cv2.bitwise_or(v_lines, h_lines)
    closed_table = cv2.morphologyEx(
        table_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    )
    contours, _ = cv2.findContours(closed_table, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    raw_boxes: list[tuple[int, int, int, int]] = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw > 120 and bh > 180 and not (y <= 5 and bh >= target_h - 10):
            raw_boxes.append((x, y, bw, bh))

    # Filter overlapping / merged shadows.  Prefer several comparable narrow
    # answer columns (Default #2), but keep the broad contour when it is the only
    # complete lattice (Vol.7); a lone right-hand header contour must not mask it.
    narrow_boxes = [b for b in raw_boxes if b[2] < 0.75 * target_w]
    if len(narrow_boxes) >= 2:
        raw_boxes = sorted(narrow_boxes, key=lambda b: b[2] * b[3], reverse=True)
    else:
        # Prefer specific table contours over canvas-spanning bounding boxes.
        # When a contour spans >=95% of both dimensions, it encompasses the outer paper margins.
        def box_priority(b: tuple[int, int, int, int]) -> tuple[int, int]:
            is_canvas = (b[0] <= 10 and b[1] <= 10 and b[2] >= target_w - 20 and b[3] >= target_h - 20)
            return (0 if is_canvas else 1, b[2] * b[3])

        raw_boxes = sorted(raw_boxes, key=box_priority, reverse=True)
    candidate_boxes: list[tuple[int, int, int, int]] = []
    for b in raw_boxes:
        bx, by, bw, bh = b
        if bw > 0.85 * target_w and len(candidate_boxes) >= 1:
            continue
        overlap = False
        for kx, ky, kw, kh in candidate_boxes:
            ix1 = max(bx, kx)
            iy1 = max(by, ky)
            ix2 = min(bx + bw, kx + kw)
            iy2 = min(by + bh, ky + kh)
            if ix2 > ix1 and iy2 > iy1:
                intersection_area = (ix2 - ix1) * (iy2 - iy1)
                min_area = min(bw * bh, kw * kh)
                if intersection_area / min_area > 0.35:
                    overlap = True
                    break
        if not overlap:
            candidate_boxes.append(b)

    # Sort candidate boxes left-to-right
    candidate_boxes = sorted(candidate_boxes, key=lambda b: (b[0], b[1]))

    answer_blocks: list[AnswerBlock] = []
    detected_choice_count = preferred_choice_count
    curr_q = 1
    warnings: list[str] = []
    if paper_conf < 0.70:
        warnings.append("ขอบกระดาษ/มุมมองภาพมีความเชื่อมั่นต่ำ โปรดตรวจ quad ก่อนใช้ตรวจข้อสอบ")

    for bx, by, bw, bh in candidate_boxes:
        if curr_q > 60:
            break
        inferred = infer_grid_in_area(
            (bx, by, bw, bh),
            v_lines,
            h_lines,
            choice_count=detected_choice_count,
            question_start=curr_q,
        )
        for inf_block in inferred:
            if curr_q > 60:
                break
            answer_blocks.append(
                replace(
                    inf_block,
                    block_index=len(answer_blocks),
                    confidence=round(float(paper_conf), 3),
                    source_geometry={
                        "kind": "grid_inference",
                        "coordinate_space": "canonical_px",
                        "candidate_box": [bx, by, bw, bh],
                        "detected_column_boundaries": list(inf_block.col_boundaries),
                        "detected_row_boundaries": list(inf_block.row_boundaries),
                        "paper_corners": paper_corners.tolist() if paper_corners is not None else None,
                    },
                )
            )
            curr_q = inf_block.question_end + 1

    # The inferred lattice is the source of truth for choice count.  Mixed
    # candidate blocks are not safe to merge into one strict template; retain
    # the first consistent family and surface a review warning.
    if answer_blocks:
        inferred_counts = {block.choice_count for block in answer_blocks}
        if len(inferred_counts) == 1:
            detected_choice_count = answer_blocks[0].choice_count
        else:
            # Do not construct an invalid mixed-choice TemplateDefinition. Keep
            # the largest consistent family as an editable draft and renumber
            # it contiguously; the warning makes the dropped candidates visible
            # and forces teacher review before persistence.
            detected_choice_count = max(
                inferred_counts,
                key=lambda count: sum(block.choice_count == count for block in answer_blocks),
            )
            consistent = [b for b in answer_blocks if b.choice_count == detected_choice_count]
            rebuilt: list[AnswerBlock] = []
            question = 1
            for index, block in enumerate(consistent):
                rows = block.rows
                rebuilt.append(AnswerBlock(
                    block_index=index,
                    question_start=question,
                    question_end=question + rows - 1,
                    rows=rows,
                    choice_count=detected_choice_count,
                    col_boundaries=block.col_boundaries,
                    row_boundaries=block.row_boundaries,
                    geometry_state="draft",
                    confidence=block.confidence,
                    source_geometry=block.source_geometry,
                ))
                question += rows
            answer_blocks = rebuilt
            warnings.append("ตรวจพบชุดตารางที่มีจำนวนตัวเลือกไม่สอดคล้องกัน โปรดตรวจแก้ก่อนบันทึก")
        if detected_choice_count < preferred_choice_count:
            warnings.append(
                f"ตรวจพบจำนวนตัวเลือกน้อยกว่าค่าที่แนะนำ ({detected_choice_count} เทียบกับ {preferred_choice_count}) โปรดตรวจเส้นแนวตั้ง"
            )
        if len(answer_blocks) > 4:
            warnings.append("ตรวจพบชุดคำตอบจำนวนมากผิดปกติ โปรดตรวจว่าเส้นเลขข้อถูกแยกออกจากตัวเลือกแล้ว")

    # If no blocks detected from contours, create an initial draft layout
    if not answer_blocks:
        warnings.append("ไม่สามารถตรวจจับตารางคำตอบอัตโนมัติได้ชัดเจน โปรดลากกรอบตารางคำตอบบนภาพ")
        step_w = 60
        step_h = 55
        answer_blocks = [
            AnswerBlock(
                block_index=0,
                question_start=1,
                question_end=20,
                rows=20,
                choice_count=detected_choice_count,
                col_boundaries=[100 + i * step_w for i in range(detected_choice_count + 1)],
                row_boundaries=[520 + i * step_h for i in range(21)],
            )
        ]

    total_q = answer_blocks[-1].question_end

    # Detect score ROI and student number ROI in header area (above the answer blocks)
    answer_top = min((b.row_boundaries[0] for b in answer_blocks), default=600)
    top_mask = cv2.bitwise_or(v_lines[:answer_top, :], h_lines[:answer_top, :])
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed_top = cv2.morphologyEx(top_mask, cv2.MORPH_CLOSE, kernel)
    h_contours, _ = cv2.findContours(closed_top, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    score_roi: tuple[int, int, int, int] | None = None
    info_box: tuple[int, int, int, int] | None = None

    for c in sorted(h_contours, key=cv2.contourArea, reverse=True):
        x, y, bw, bh = cv2.boundingRect(c)
        # Skip the outermost container box if it spans almost full width
        if bw > 0.75 * target_w:
            continue
        # Score box candidate: upper-right quadrant, moderate width and height
        if score_roi is None and 80 < bw < 450 and 60 < bh < 400 and x > (0.45 * target_w):
            score_roi = (x, y, x + bw, y + bh)
        # Info box candidate: left side, wide enough for student info
        elif info_box is None and bw > 300 and bh > 120 and x < (0.45 * target_w):
            info_box = (x, y, bw, bh)

    if score_roi is None:
        # Keep the historical safe draft location inside the header band.  This
        # is deliberately a review-required hint, never a confident detection.
        score_roi = (850, 180, 1080, 300)
        warnings.append("ตรวจไม่พบช่องคะแนนโดยตรง (ใช้ตำแหน่งแนะนำ โปรดลาก/ตรวจสอบก่อนบันทึก)")

    # Student number ROI
    student_number_roi: tuple[int, int, int, int] | None = None
    # Check if there is an explicit digit grid or sub-box
    for c in sorted(h_contours, key=cv2.contourArea, reverse=True):
        x, y, bw, bh = cv2.boundingRect(c)
        if (
            80 < bw < 350
            and 30 < bh < 150
            and x < (score_roi[0] if score_roi else 800)
            and (x, y, x + bw, y + bh) != score_roi
        ):
            student_number_roi = (x, y, x + bw, y + bh)
            break

    # If no separate box was found, infer from the student info box
    if student_number_roi is None and info_box is not None:
        ix, iy, iw, ih = info_box
        nx1 = ix + int(iw * 0.50)
        # The upper part of the information panel contains labels and ruled
        # lines; the number field is in its lower band.  Keep this as a
        # review-required inference when no dedicated box was found.
        ny1 = iy + int(ih * 0.80)
        nx2 = ix + int(iw * 0.95)
        ny2 = iy + int(ih * 0.99)
        student_number_roi = (nx1, ny1, nx2, ny2)

    if student_number_roi is None:
        if score_roi is not None and score_roi[0] >= 700 and score_roi[1] < 350:
            student_number_roi = (740, 150, 960, 240)
        else:
            student_number_roi = (450, 320, 650, 420)
        warnings.append("ตรวจไม่พบช่องเลขประจำตัวโดยตรง (ใช้ตำแหน่งแนะนำ โปรดลาก/ตรวจสอบก่อนบันทึก)")

    canonical_choices = list(CANONICAL_CHOICES[:detected_choice_count])
    display_choices = list(DEFAULT_THAI_LABELS[:detected_choice_count])
    choice_map = {}
    for i in range(detected_choice_count):
        choice_map[canonical_choices[i]] = canonical_choices[i]
        choice_map[canonical_choices[i].lower()] = canonical_choices[i]
        choice_map[display_choices[i]] = canonical_choices[i]
        choice_map[str(i + 1)] = canonical_choices[i]

    ref_sha256 = hashlib.sha256(cv2.imencode(".png", warped)[1].tobytes()).hexdigest()

    t_def = TemplateDefinition(
        template_id=template_id,
        name=template_name,
        kind="custom",
        version=1,
        canonical_width=target_w,
        canonical_height=target_h,
        choice_count=detected_choice_count,
        choice_labels=canonical_choices,
        display_choice_labels=display_choices,
        choice_map=choice_map,
        question_count=total_q,
        answer_blocks=answer_blocks,
        student_number_roi=student_number_roi,
        score_roi=score_roi,
        reference_sha256=ref_sha256,
        # Discovered line masks include the anti-aliased printed border after
        # perspective warping.  An 8 px crop keeps that border out of OMR while
        # remaining well inside the photographed cells; bundled templates retain
        # their explicit historical inset values.
        cell_inset=8,
        registration_config={
            "color_theme": "monochrome",
            "allow_paper_quad_fallback": True,
            "paper_corners": paper_corners.tolist() if paper_corners is not None else None,
            "paper_to_canonical_matrix": matrix.tolist(),
            "source_coordinate_space": "decoded_exif_oriented_px",
        },
        created_at="",
        updated_at="",
    )

    status_message = (
        f"ตรวจพบตารางคำตอบ {len(answer_blocks)} ชุด ({total_q} ข้อ · {detected_choice_count} ตัวเลือก)"
    )

    grid_confidence = 0.94 if len(answer_blocks) >= 2 else (0.88 if answer_blocks else 0.50)
    if warnings:
        grid_confidence = min(grid_confidence, 0.65)
    score_conf = 0.92 if score_roi is not None and not any("คะแนน" in w for w in warnings) else 0.60
    student_conf = 0.88 if student_number_roi is not None and not any("เลขประจำตัว" in w for w in warnings) else 0.60
    conf_dict = {
        "paper_boundary": round(paper_conf, 2),
        "answer_grids": grid_confidence,
        "choice_headers": 0.88,
        "student_number": student_conf,
        "score_region": score_conf,
    }
    overall = round(float(np.mean(list(conf_dict.values()))), 2)

    diagnostics = {
        "candidate_boxes": len(candidate_boxes),
        "detected_blocks": len(answer_blocks),
        "total_questions": total_q,
        "choice_count": detected_choice_count,
        "seconds": round(perf_counter() - started, 4),
    }

    return DiscoveryResult(
        confidence=conf_dict,
        overall_confidence=overall,
        template_def=t_def,
        warped_image=warped,
        paper_corners=paper_corners,
        status_message=status_message,
        warnings=warnings,
        diagnostics=diagnostics,
    )
