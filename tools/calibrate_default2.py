"""Calibration tool for Default #2 answer sheet."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def order_points(pts: np.ndarray) -> np.ndarray:
    """Order points: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def warp_paper(
    img: np.ndarray, target_w: int = 1200, target_h: int = 1720
) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    paper_contour = contours[0]
    peri = cv2.arcLength(paper_contour, True)
    approx = cv2.approxPolyDP(paper_contour, 0.02 * peri, True)
    if len(approx) == 4:
        pts = approx.reshape(4, 2).astype(np.float32)
    else:
        rect = cv2.minAreaRect(paper_contour)
        pts = cv2.boxPoints(rect).astype(np.float32)

    ordered = order_points(pts)
    dst = np.array(
        [[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(img, matrix, (target_w, target_h))
    return warped, matrix


if __name__ == "__main__":
    img_path = Path("tests/fixtures/default2/sheet.jpg")
    img = cv2.imread(str(img_path))
    warped, m = warp_paper(img, 1200, 1720)
    out_dir = Path("docs/evidence")
    out_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_dir / "default2_warped.png"), warped)

    # Geometry definition
    # Block 0: Q1-20
    b0_cols = [103, 168, 234, 299, 364]
    b0_rows = [
        528,
        583,
        639,
        693,
        748,
        803,
        857,
        912,
        967,
        1022,
        1076,
        1131,
        1185,
        1240,
        1294,
        1350,
        1405,
        1460,
        1515,
        1569,
        1624,
    ]

    # Block 1: Q21-40
    b1_cols = [491, 557, 621, 687, 752]
    b1_rows = [
        527,
        583,
        639,
        693,
        748,
        803,
        857,
        912,
        966,
        1021,
        1076,
        1131,
        1185,
        1240,
        1294,
        1350,
        1405,
        1459,
        1514,
        1568,
        1623,
    ]

    # Block 2: Q41-60
    b2_cols = [878, 943, 1008, 1073, 1138]
    b2_rows = [
        527,
        582,
        638,
        692,
        747,
        802,
        857,
        911,
        966,
        1021,
        1076,
        1130,
        1185,
        1239,
        1294,
        1349,
        1404,
        1459,
        1513,
        1568,
        1623,
    ]

    student_number_roi = [856, 140, 935, 205]
    score_roi = [950, 111, 1114, 294]

    overlay = warped.copy()

    # Draw blocks
    blocks_meta = [
        (0, 1, 20, b0_cols, b0_rows),
        (1, 21, 40, b1_cols, b1_rows),
        (2, 41, 60, b2_cols, b2_rows),
    ]

    for b_idx, q_start, q_end, cols, rows in blocks_meta:
        # Draw block outer boundary
        cv2.rectangle(overlay, (cols[0], rows[0]), (cols[-1], rows[-1]), (255, 0, 0), 2)
        for r_idx in range(len(rows) - 1):
            q_num = q_start + r_idx
            y1, y2 = rows[r_idx], rows[r_idx + 1]
            for c_idx in range(len(cols) - 1):
                x1, x2 = cols[c_idx], cols[c_idx + 1]
                # Draw cell box in green
                cv2.rectangle(overlay, (x1 + 4, y1 + 4), (x2 - 4, y2 - 4), (0, 200, 0), 1)

    # Draw student number ROI in magenta
    cv2.rectangle(
        overlay,
        (student_number_roi[0], student_number_roi[1]),
        (student_number_roi[2], student_number_roi[3]),
        (255, 0, 255),
        2,
    )
    cv2.putText(
        overlay,
        "No.",
        (student_number_roi[0], student_number_roi[1] - 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 0, 255),
        1,
    )

    # Draw score ROI in orange
    cv2.rectangle(
        overlay, (score_roi[0], score_roi[1]), (score_roi[2], score_roi[3]), (0, 140, 255), 2
    )
    cv2.putText(
        overlay,
        "Score",
        (score_roi[0], score_roi[1] - 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 140, 255),
        1,
    )

    cv2.imwrite(str(out_dir / "default2_full_overlay.png"), overlay)
    print("Full overlay saved to docs/evidence/default2_full_overlay.png")
