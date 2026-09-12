"""Local, deterministic template discovery pipeline for custom answer sheets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
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
    """Detect paper contour and perspective-warp to canonical coordinates.

    Returns:
        (warped_image, homography_matrix, confidence, ordered_corners)
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    confidence = 0.50
    ordered_corners = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)

    if contours:
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        paper_contour = contours[0]
        area = cv2.contourArea(paper_contour)
        if area > (w * h * 0.35):
            peri = cv2.arcLength(paper_contour, True)
            approx = cv2.approxPolyDP(paper_contour, 0.02 * peri, True)
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                confidence = 0.95
            else:
                rect = cv2.minAreaRect(paper_contour)
                pts = cv2.boxPoints(rect).astype(np.float32)
                confidence = 0.80
            ordered_corners = order_quad_points(pts)
            dst = np.array(
                [[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]],
                dtype=np.float32,
            )
            matrix = cv2.getPerspectiveTransform(ordered_corners, dst)
            warped = cv2.warpPerspective(img, matrix, (target_w, target_h))
            return warped, matrix, confidence, ordered_corners

    # Fallback: simple resize
    matrix = np.diag([target_w / w, target_h / h, 1.0])
    warped = cv2.resize(img, (target_w, target_h))
    return warped, matrix, 0.40, ordered_corners


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

    # Filter row intervals: find consistent question row heights
    row_diffs = np.diff(abs_rows)
    if len(row_diffs) == 0:
        return []
    med_h = np.median(row_diffs)
    valid_row_indices = [i for i, d in enumerate(row_diffs) if 0.45 * med_h <= d <= 1.65 * med_h]

    if len(valid_row_indices) < 1:
        return []

    grid_rows = abs_rows[valid_row_indices[0] : valid_row_indices[-1] + 2]
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

    total_cols = len(abs_cols) - 1
    stride = choice_count + 1  # 1 question number column + choice_count choice columns
    blocks: list[AnswerBlock] = []
    curr_q = question_start

    if total_cols >= stride and total_cols % stride == 0:
        num_blocks = total_cols // stride
        for b_i in range(num_blocks):
            if curr_q > 60:
                break
            b_cols = abs_cols[b_i * stride : (b_i + 1) * stride + 1]
            choice_cols = b_cols[1:]  # skip question number column
            this_q_rows = min(q_count, 60 - curr_q + 1)
            b_rows = question_rows[: this_q_rows + 1]
            blocks.append(
                AnswerBlock(
                    block_index=b_i,
                    question_start=curr_q,
                    question_end=curr_q + this_q_rows - 1,
                    rows=this_q_rows,
                    choice_count=choice_count,
                    col_boundaries=choice_cols,
                    row_boundaries=b_rows,
                )
            )
            curr_q += this_q_rows
    elif total_cols >= choice_count and total_cols % choice_count == 0:
        num_blocks = total_cols // choice_count
        for b_i in range(num_blocks):
            if curr_q > 60:
                break
            choice_cols = abs_cols[b_i * choice_count : (b_i + 1) * choice_count + 1]
            this_q_rows = min(q_count, 60 - curr_q + 1)
            b_rows = question_rows[: this_q_rows + 1]
            blocks.append(
                AnswerBlock(
                    block_index=b_i,
                    question_start=curr_q,
                    question_end=curr_q + this_q_rows - 1,
                    rows=this_q_rows,
                    choice_count=choice_count,
                    col_boundaries=choice_cols,
                    row_boundaries=b_rows,
                )
            )
            curr_q += this_q_rows
    else:
        # Fallback: take the rightmost choice_count intervals
        if total_cols >= choice_count and curr_q <= 60:
            choice_cols = abs_cols[-choice_count - 1 :]
            this_q_rows = min(q_count, 60 - curr_q + 1)
            b_rows = question_rows[: this_q_rows + 1]
            blocks.append(
                AnswerBlock(
                    block_index=0,
                    question_start=curr_q,
                    question_end=curr_q + this_q_rows - 1,
                    rows=this_q_rows,
                    choice_count=choice_count,
                    col_boundaries=choice_cols,
                    row_boundaries=b_rows,
                )
            )

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
        if bw > 120 and bh > 180:
            raw_boxes.append((x, y, bw, bh))

    # Filter overlapping / merged shadows: prefer specific sub-blocks if they exist
    raw_boxes = sorted(raw_boxes, key=lambda b: b[2] * b[3])
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
                AnswerBlock(
                    block_index=len(answer_blocks),
                    question_start=inf_block.question_start,
                    question_end=inf_block.question_end,
                    rows=inf_block.rows,
                    choice_count=inf_block.choice_count,
                    col_boundaries=inf_block.col_boundaries,
                    row_boundaries=inf_block.row_boundaries,
                )
            )
            curr_q = inf_block.question_end + 1

    warnings: list[str] = []

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
        score_roi = (850, 120, 1080, 300)
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
        ny1 = iy + int(ih * 0.65)
        nx2 = ix + int(iw * 0.95)
        ny2 = iy + int(ih * 0.96)
        student_number_roi = (nx1, ny1, nx2, ny2)

    if student_number_roi is None:
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
        cell_inset=6,
        registration_config={"color_theme": "monochrome"},
        created_at="",
        updated_at="",
    )

    status_message = (
        f"ตรวจพบตารางคำตอบ {len(answer_blocks)} ชุด ({total_q} ข้อ · {detected_choice_count} ตัวเลือก)"
    )

    grid_confidence = 0.94 if len(answer_blocks) >= 2 else (0.88 if answer_blocks else 0.50)
    score_conf = 0.92 if score_roi is not None else 0.60
    student_conf = 0.88 if student_number_roi is not None else 0.60
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
