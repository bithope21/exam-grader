"""Base answer sheet renderer and mark drawing engine for synthetic dataset generation."""

import json
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QApplication

# Ensure QApplication is initialized for font/widget rendering headlessly
_app = QApplication.instance() or QApplication([])

CHOICES = ["A", "B", "C", "D", "E"]
THAI_CHOICES = ["ก", "ข", "ค", "ง", "จ"]


def _canonical_geometry() -> dict:
    path = Path(__file__).parents[2] / "src" / "exam_grader" / "resources" / "template.json"
    return json.loads(path.read_text(encoding="utf-8"))


_TEMPLATE = _canonical_geometry()
TEMPLATE_ID = _TEMPLATE["id"]
TEMPLATE_VERSION = "canonical-resource-v1"
WIDTH = _TEMPLATE["width"]
HEIGHT = _TEMPLATE["height"]
GROUPS = _TEMPLATE["groups"]
ROWS = _TEMPLATE["rows"]
STUDENT_ROI = _TEMPLATE["student_number_roi"]


def get_cell_bounds(question_1_based: int, choice_index_0_based: int) -> tuple[int, int, int, int]:
    """Returns (x_min, y_min, x_max, y_max) for question 1..60 and choice 0..4."""
    group_idx = (question_1_based - 1) // 15
    row_idx = (question_1_based - 1) % 15
    x_min = GROUPS[group_idx][choice_index_0_based]
    x_max = GROUPS[group_idx][choice_index_0_based + 1]
    y_min = ROWS[row_idx]
    y_max = ROWS[row_idx + 1]
    return x_min, y_min, x_max, y_max


def render_blank_sheet(header_title: str = "กระดาษคำตอบ") -> np.ndarray:
    """Renders a clean, blank answer sheet image matching the PO layout reference."""
    img = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB888)
    img.fill(QColor(255, 255, 255))

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Green header banner
    banner_color = QColor(45, 139, 85)
    p.fillRect(0, 0, WIDTH, 60, banner_color)

    font_title = QFont("Thonburi", 18, QFont.Weight.Bold)
    p.setFont(font_title)
    p.setPen(QColor(255, 255, 255))
    p.drawText(60, 40, header_title)

    # Barcode placeholder & total score box
    p.setPen(QPen(QColor(255, 255, 255), 2))
    p.drawRect(WIDTH - 120, 10, 100, 40)
    font_score = QFont("Thonburi", 10)
    p.setFont(font_score)
    p.drawText(WIDTH - 110, 32, "คะแนนรวม")

    # Outer border
    p.setPen(QPen(banner_color, 2))
    p.drawRect(5, 5, WIDTH - 10, HEIGHT - 10)

    # Info lines section
    p.setPen(QPen(QColor(80, 80, 80), 1))
    font_info = QFont("Thonburi", 9)
    p.setFont(font_info)

    p.drawText(
        15,
        85,
        "โรงเรียน ................................................................ ปีการศึกษา ..........",
    )
    p.drawText(
        15,
        115,
        "ชื่อ ..................................................................................... ชั้น .......... เลขที่ ..........",
    )
    p.drawText(
        15,
        145,
        "วิชา .................................................................................... วันที่ ..... เดือน .......... พ.ศ. .....",
    )

    # Draw answer grid (4 columns)
    grid_pen = QPen(QColor(45, 139, 85), 1.5)
    p.setPen(grid_pen)

    for g_idx, g_xs in enumerate(GROUPS):
        x_q_start = g_xs[0] - 25
        x_end = g_xs[-1]
        y_start = ROWS[0]
        y_end = ROWS[-1]

        # Draw outer box for question group
        p.drawRect(x_q_start, y_start, x_end - x_q_start, y_end - y_start)

        # Draw vertical choice dividers
        for x in g_xs:
            p.drawLine(x, y_start, x, y_end)

        # Draw horizontal row dividers
        for y in ROWS[1:]:
            p.drawLine(x_q_start, y, x_end, y)

        # Header background inside group (Row 0)
        p.fillRect(x_q_start, y_start, x_end - x_q_start, ROWS[1] - y_start, QColor(220, 240, 225))
        p.drawLine(x_q_start, ROWS[1], x_end, ROWS[1])

        # Header texts
        font_hdr = QFont("Thonburi", 8, QFont.Weight.Bold)
        p.setFont(font_hdr)
        p.setPen(QColor(30, 90, 50))
        p.drawText(
            QRect(x_q_start, y_start, 25, ROWS[1] - y_start), Qt.AlignmentFlag.AlignCenter, "ข้อ"
        )

        for c_idx in range(5):
            box = QRect(g_xs[c_idx], y_start, g_xs[c_idx + 1] - g_xs[c_idx], ROWS[1] - y_start)
            txt = f"{THAI_CHOICES[c_idx]}\n{CHOICES[c_idx]}"
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, txt)

        # Question numbers in green column (1..15, 16..30, etc.)
        for r_idx in range(15):
            q_num = g_idx * 15 + r_idx + 1
            y_r1 = ROWS[r_idx + 1]
            y_r2 = ROWS[r_idx + 2] if r_idx + 2 < len(ROWS) else 714
            q_box = QRect(x_q_start, y_r1, 25, y_r2 - y_r1)
            p.fillRect(q_box, QColor(210, 235, 215))
            p.drawRect(q_box)
            font_q = QFont("Thonburi", 9, QFont.Weight.Bold)
            p.setFont(font_q)
            p.setPen(QColor(20, 80, 40))
            p.drawText(q_box, Qt.AlignmentFlag.AlignCenter, str(q_num))

    # Bottom score section
    y_bot = 730
    p.setPen(grid_pen)
    for b_idx in range(8):
        x_b1 = 57 + b_idx * 94
        x_b2 = x_b1 + 90
        p.drawRect(x_b1, y_bot, 90, 60)
        p.fillRect(x_b1, y_bot, 90, 20, QColor(230, 245, 235))
        p.drawLine(x_b1, y_bot + 20, x_b2, y_bot + 20)
        font_bot = QFont("Thonburi", 8)
        p.setFont(font_bot)
        p.setPen(QColor(30, 90, 50))
        p.drawText(QRect(x_b1, y_bot, 90, 20), Qt.AlignmentFlag.AlignCenter, f"ตอนที่ {b_idx + 1}")

    p.end()

    # Convert QImage to OpenCV BGR ndarray
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    ptr = img.bits()
    arr = np.frombuffer(ptr, np.uint8).reshape(HEIGHT, img.bytesPerLine())
    rgb = arr[:, : WIDTH * 3].reshape(HEIGHT, WIDTH, 3).copy()
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def draw_mark(
    image: np.ndarray,
    question: int,
    choice_index: int,
    mark_type: str = "x_mark",
    rng: np.random.Generator | None = None,
) -> None:
    """Draws a mark (X, check, slash, scribble, bubble) in specified cell."""
    if rng is None:
        rng = np.random.default_rng(42)

    x1, y1, x2, y2 = get_cell_bounds(question, choice_index)
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    # Default ink color: Dark blue/black
    ink_color = (int(rng.integers(10, 40)), int(rng.integers(10, 40)), int(rng.integers(15, 60)))

    if mark_type == "x_mark":
        dx = int(rng.integers(-2, 3))
        dy = int(rng.integers(-2, 3))
        thickness = int(rng.integers(2, 4))
        w = (x2 - x1) // 2 - 4
        h = (y2 - y1) // 2 - 4
        cv2.line(
            image,
            (cx - w + dx, cy - h + dy),
            (cx + w + dx, cy + h + dy),
            ink_color,
            thickness,
            cv2.LINE_AA,
        )
        cv2.line(
            image,
            (cx + w + dx, cy - h + dy),
            (cx - w + dx, cy + h + dy),
            ink_color,
            thickness,
            cv2.LINE_AA,
        )

    elif mark_type == "faint_mark":
        faint_color = (160, 160, 165)
        thickness = 1
        w = (x2 - x1) // 2 - 5
        h = (y2 - y1) // 2 - 5
        cv2.line(image, (cx - w, cy - h), (cx + w, cy + h), faint_color, thickness, cv2.LINE_AA)
        cv2.line(image, (cx + w, cy - h), (cx - w, cy + h), faint_color, thickness, cv2.LINE_AA)

    elif mark_type == "heavy_mark":
        heavy_color = (5, 5, 10)
        thickness = 5
        w = (x2 - x1) // 2 - 2
        h = (y2 - y1) // 2 - 2
        cv2.line(image, (cx - w, cy - h), (cx + w, cy + h), heavy_color, thickness, cv2.LINE_AA)
        cv2.line(image, (cx + w, cy - h), (cx - w, cy + h), heavy_color, thickness, cv2.LINE_AA)

    elif mark_type == "off_center_mark":
        dx = int(rng.choice([-7, -6, 6, 7]))
        dy = int(rng.choice([-7, -6, 6, 7]))
        thickness = 2
        w = (x2 - x1) // 2 - 4
        h = (y2 - y1) // 2 - 4
        cv2.line(
            image,
            (cx - w + dx, cy - h + dy),
            (cx + w + dx, cy + h + dy),
            ink_color,
            thickness,
            cv2.LINE_AA,
        )
        cv2.line(
            image,
            (cx + w + dx, cy - h + dy),
            (cx - w + dx, cy + h + dy),
            ink_color,
            thickness,
            cv2.LINE_AA,
        )

    elif mark_type == "check_mark":
        thickness = 2
        p1 = (cx - 7, cy)
        p2 = (cx - 2, cy + 6)
        p3 = (cx + 7, cy - 7)
        cv2.line(image, p1, p2, ink_color, thickness, cv2.LINE_AA)
        cv2.line(image, p2, p3, ink_color, thickness, cv2.LINE_AA)

    elif mark_type == "slash_mark":
        thickness = 2
        w = (x2 - x1) // 2 - 4
        h = (y2 - y1) // 2 - 4
        cv2.line(image, (cx - w, cy + h), (cx + w, cy - h), ink_color, thickness, cv2.LINE_AA)

    elif mark_type == "scribble":
        for _ in range(4):
            x_a = int(rng.integers(x1 + 2, x2 - 2))
            y_a = int(rng.integers(y1 + 2, y2 - 2))
            x_b = int(rng.integers(x1 + 2, x2 - 2))
            y_b = int(rng.integers(y1 + 2, y2 - 2))
            cv2.line(image, (x_a, y_a), (x_b, y_b), ink_color, 2, cv2.LINE_AA)

    elif mark_type == "solid_bubble":
        r = min((x2 - x1) // 2, (y2 - y1) // 2) - 4
        cv2.circle(image, (cx, cy), r, ink_color, -1, cv2.LINE_AA)


def draw_student_number(
    image: np.ndarray,
    student_no: str | None,
    mode: str = "clean",
    rng: np.random.Generator | None = None,
) -> None:
    """Draws handwritten-style student number digits into the student number ROI."""
    if rng is None:
        rng = np.random.default_rng(42)

    x1, y1, x2, y2 = STUDENT_ROI

    if student_no is None or mode == "missing":
        return  # Leave blank

    if mode == "unreadable":
        for _ in range(8):
            xa = int(rng.integers(x1, x2))
            ya = int(rng.integers(y1, y2))
            xb = int(rng.integers(x1, x2))
            yb = int(rng.integers(y1, y2))
            cv2.line(image, (xa, ya), (xb, yb), (30, 30, 30), 2, cv2.LINE_AA)
        return

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.65
    thickness = 2
    color = (20, 20, 40)
    cv2.putText(image, student_no, (x1 + 4, y2 - 6), font, scale, color, thickness, cv2.LINE_AA)


def render_blank_sheet_default2() -> np.ndarray:
    """Returns a clean base image for Default #2 (60Q/4C/3x20)."""
    from exam_grader.template_manager import get_reference_image, load_builtin_template

    t2 = load_builtin_template("default-2")
    return get_reference_image(t2).copy()


def get_cell_bounds_default2(
    question_1_based: int, choice_index_0_based: int
) -> tuple[int, int, int, int]:
    """Returns (x_min, y_min, x_max, y_max) for Default #2."""
    from exam_grader.template_manager import cell_box_rect_for_template, load_builtin_template

    t2 = load_builtin_template("default-2")
    x, y, w, h = cell_box_rect_for_template(t2, question_1_based, choice_index_0_based)
    return x, y, x + w, y + h


def draw_mark_default2(
    image: np.ndarray,
    question: int,
    choice_index: int,
    mark_type: str = "x_mark",
    ink_color: tuple[int, int, int] = (20, 20, 25),
    rng: np.random.Generator | None = None,
) -> None:
    """Draws an answer mark on a Default #2 sheet."""
    if rng is None:
        rng = np.random.default_rng(42)
    x1, y1, x2, y2 = get_cell_bounds_default2(question, choice_index)
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    if mark_type == "x_mark":
        thickness = 3
        pad_x = (x2 - x1) // 4
        pad_y = (y2 - y1) // 4
        cv2.line(
            image,
            (x1 + pad_x, y1 + pad_y),
            (x2 - pad_x, y2 - pad_y),
            ink_color,
            thickness,
            cv2.LINE_AA,
        )
        cv2.line(
            image,
            (x1 + pad_x, y2 - pad_y),
            (x2 - pad_x, y1 + pad_y),
            ink_color,
            thickness,
            cv2.LINE_AA,
        )
    elif mark_type == "solid_bubble":
        r = min((x2 - x1) // 2, (y2 - y1) // 2) - 4
        cv2.circle(image, (cx, cy), r, ink_color, -1, cv2.LINE_AA)
    elif mark_type == "check_mark":
        thickness = 2
        p1 = (cx - 7, cy)
        p2 = (cx - 2, cy + 6)
        p3 = (cx + 7, cy - 7)
        cv2.line(image, p1, p2, ink_color, thickness, cv2.LINE_AA)
        cv2.line(image, p2, p3, ink_color, thickness, cv2.LINE_AA)
    elif mark_type == "slash_mark":
        w = (x2 - x1) // 2 - 4
        h = (y2 - y1) // 2 - 4
        cv2.line(image, (cx - w, cy + h), (cx + w, cy - h), ink_color, 2, cv2.LINE_AA)
