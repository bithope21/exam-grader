"""Calibration UI for creating, auto-discovering, inspecting, and saving answer-sheet templates."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, QThread, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from exam_grader.calibration_model import (
    CalibrationDraft,
    append_choice,
    append_row,
    cell_box_for_block,
    compile_draft,
    remove_choice_at_end,
    remove_grid_line,
    remove_row_at_end,
    renumber_blocks,
    resize_block_from_origin,
    set_block_choice_count,
    set_block_row_count,
    set_boundary_position,
    split_cell,
    translate_block,
)
from exam_grader.numeric_widgets import (
    NumericSpinBox,
    attach_digit_normalizer,
    normalize_digits,
)
from exam_grader.imaging import analyze
from exam_grader.local_upload import LanUnavailableError, UploadSession, UploadSessionError
from exam_grader.template_discovery import (
    DiscoveryResult,
    discover_template,
    extract_line_masks,
    infer_grid_in_area,
)
from exam_grader.template_manager import (
    CANONICAL_CHOICES,
    DEFAULT_THAI_LABELS,
    AnswerBlock,
    TemplateDefinition,
    cell_box_rect_for_template,
    get_reference_image,
    save_custom_reference_image,
)

if TYPE_CHECKING:
    from exam_grader.app import Application


def _blocks_overlap(first: AnswerBlock, second: AnswerBlock) -> bool:
    """Return whether two answer grids occupy overlapping positive-area boxes."""
    ax1, ay1, ax2, ay2 = (
        first.col_boundaries[0], first.row_boundaries[0],
        first.col_boundaries[-1], first.row_boundaries[-1],
    )
    bx1, by1, bx2, by2 = (
        second.col_boundaries[0], second.row_boundaries[0],
        second.col_boundaries[-1], second.row_boundaries[-1],
    )
    return max(ax1, bx1) < min(ax2, bx2) and max(ay1, by1) < min(ay2, by2)


class DiscoveryWorker(QThread):
    """Background worker to run template discovery without blocking GUI."""

    completed = Signal(object)  # DiscoveryResult
    failed = Signal(str)

    def __init__(self, image_bytes: bytes) -> None:
        super().__init__()
        self.image_bytes = image_bytes

    def run(self) -> None:
        try:
            result = discover_template(self.image_bytes)
            self.completed.emit(result)
        except Exception as err:
            self.failed.emit(str(err))


class GridDetectionWorker(QThread):
    """Detect one explicitly selected grid area without blocking the canvas."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        gray: np.ndarray,
        area_rect: tuple[int, int, int, int],
        choice_count: int,
        question_start: int,
    ) -> None:
        super().__init__()
        self.gray = gray
        self.area_rect = area_rect
        self.choice_count = choice_count
        self.question_start = question_start

    def run(self) -> None:
        try:
            _, horizontal, vertical = extract_line_masks(self.gray)
            self.completed.emit(
                infer_grid_in_area(
                    self.area_rect,
                    vertical,
                    horizontal,
                    choice_count=self.choice_count,
                    question_start=self.question_start,
                )
            )
        except Exception as err:
            self.failed.emit(str(err))


class CalibrationCanvas(QWidget):
    """Interactive, zoomable canvas supporting mouse selection, dragging, and box drawing."""

    MODE_SELECT_MOVE = "select_move"
    MODE_EDIT_GRID_LINE = "edit_grid_line"
    MODE_DRAW_GRID_AREA = "draw_grid_area"
    MODE_DRAW_STUDENT_ROI = "draw_student_roi"
    MODE_DRAW_SCORE_ROI = "draw_score_roi"

    target_selected = Signal(str)
    roi_updated = Signal(str, tuple)  # ("student"|"score", (x1, y1, x2, y2))
    block_updated = Signal(int, object)  # (block_index, AnswerBlock)
    line_selected = Signal(int, str, int, int)  # block_index, axis, boundary_index, position
    grid_area_completed = Signal(tuple)  # (bx, by, bw, bh) in canonical coords
    template_modified = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #181c24; border: 1px solid #334155;")

        self.base_pixmap: QPixmap | None = None
        self.reference_bgr: np.ndarray | None = None
        self.template_def: TemplateDefinition | None = None
        self.show_overlay: bool = True
        self.scale_factor: float = 0.5

        # Interactive state
        self.mode: str = self.MODE_SELECT_MOVE
        self.selected_target: str = (
            "all_blocks"  # "all_blocks" | "block_{i}" | "student_roi" | "score_roi"
        )

        self.is_dragging: bool = False
        self.drag_start_pt: QPoint | None = None
        self.drag_current_pt: QPoint | None = None
        self.active_handle: str | None = None
        self.drag_orig_rect: tuple[int, int, int, int] | None = None
        self.drag_origin_block: AnswerBlock | None = None
        self.active_line: tuple[int, str, int] | None = None
        self.line_origin_block: AnswerBlock | None = None
        self.selected_line: tuple[int, str, int] | None = None

    def set_reference(self, image_bgr: np.ndarray, template_def: TemplateDefinition | None) -> None:
        self.reference_bgr = image_bgr
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.base_pixmap = QPixmap.fromImage(qimg)
        self.template_def = template_def
        self._update_size()
        self.update()

    def set_template_def(self, template_def: TemplateDefinition | None) -> None:
        self.template_def = template_def
        self.update()

    def set_overlay_visible(self, visible: bool) -> None:
        self.show_overlay = visible
        self.update()

    def set_zoom(self, scale: float) -> None:
        self.scale_factor = max(0.2, min(2.0, scale))
        self._update_size()
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode == self.MODE_SELECT_MOVE:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif mode == self.MODE_EDIT_GRID_LINE:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def set_selected_target(self, target: str) -> None:
        self.selected_target = target
        self.update()

    def _update_size(self) -> None:
        if self.base_pixmap is not None:
            size = self.base_pixmap.size() * self.scale_factor
            self.setFixedSize(size)
        else:
            self.setFixedSize(600, 800)

    # Coordinate conversions
    def _canvas_to_img(self, pt: QPoint) -> tuple[int, int]:
        if self.scale_factor <= 0:
            return (0, 0)
        td = self.template_def
        max_w = td.canonical_width if td else 1200
        max_h = td.canonical_height if td else 1720
        ix = int(pt.x() / self.scale_factor)
        iy = int(pt.y() / self.scale_factor)
        return (max(0, min(ix, max_w)), max(0, min(iy, max_h)))

    def _img_to_canvas(self, ix: int, iy: int) -> QPoint:
        return QPoint(int(ix * self.scale_factor), int(iy * self.scale_factor))

    def _img_rect_to_canvas(self, rect: tuple[int, int, int, int]) -> QRect:
        x1, y1, x2, y2 = rect
        p1 = self._img_to_canvas(x1, y1)
        p2 = self._img_to_canvas(x2, y2)
        return QRect(p1.x(), p1.y(), p2.x() - p1.x(), p2.y() - p1.y())

    # Handle calculations for resize
    def _get_handles_for_rect(self, qrect: QRect) -> dict[str, QRect]:
        r = 5
        x1, y1, w, h = qrect.x(), qrect.y(), qrect.width(), qrect.height()
        x2, y2 = x1 + w, y1 + h
        mx, my = x1 + w // 2, y1 + h // 2
        return {
            "tl": QRect(x1 - r, y1 - r, 2 * r, 2 * r),
            "tr": QRect(x2 - r, y1 - r, 2 * r, 2 * r),
            "bl": QRect(x1 - r, y2 - r, 2 * r, 2 * r),
            "br": QRect(x2 - r, y2 - r, 2 * r, 2 * r),
            "t": QRect(mx - r, y1 - r, 2 * r, 2 * r),
            "b": QRect(mx - r, y2 - r, 2 * r, 2 * r),
            "l": QRect(x1 - r, my - r, 2 * r, 2 * r),
            "r": QRect(x2 - r, my - r, 2 * r, 2 * r),
        }

    def _get_target_rect(self) -> tuple[int, int, int, int] | None:
        td = self.template_def
        if td is None:
            return None
        if self.selected_target == "student_roi":
            return td.student_number_roi
        elif self.selected_target == "score_roi":
            return td.score_roi
        elif self.selected_target.startswith("block_"):
            try:
                b_idx = int(self.selected_target.split("_")[1])
                if 0 <= b_idx < len(td.answer_blocks):
                    b = td.answer_blocks[b_idx]
                    return (
                        b.col_boundaries[0],
                        b.row_boundaries[0],
                        b.col_boundaries[-1],
                        b.row_boundaries[-1],
                    )
            except (ValueError, IndexError):
                return None
        return None

    def mousePressEvent(self, event: Any) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self.template_def is None:
            return

        pt = event.position().toPoint()
        td = self.template_def
        if td is None:
            return
        self.drag_start_pt = pt
        self.drag_current_pt = pt
        self.is_dragging = True

        if self.mode == self.MODE_EDIT_GRID_LINE:
            selected = self._pick_grid_line(pt)
            if selected is None:
                self.is_dragging = False
                self.drag_start_pt = None
                self.drag_current_pt = None
                return
            self.active_line = selected
            self.selected_line = selected
            block_index, axis, boundary_index = selected
            self.line_origin_block = td.answer_blocks[block_index]
            boundaries = (
                self.line_origin_block.row_boundaries
                if axis == "row"
                else self.line_origin_block.col_boundaries
            )
            self.target_selected.emit(f"block_{block_index}")
            self.line_selected.emit(block_index, axis, boundary_index, boundaries[boundary_index])
            self.update()
            return

        if self.mode == self.MODE_SELECT_MOVE:
            # Check if clicked on a handle of the currently selected target
            target_rect = self._get_target_rect()
            if target_rect is not None:
                qrect = self._img_rect_to_canvas(target_rect)
                handles = self._get_handles_for_rect(qrect)
                for h_name, h_rect in handles.items():
                    if h_rect.contains(pt):
                        self.active_handle = h_name
                        self.drag_orig_rect = target_rect
                        if self.selected_target.startswith("block_"):
                            self.drag_origin_block = td.answer_blocks[
                                int(self.selected_target.split("_")[1])
                            ]
                        return
                if qrect.contains(pt):
                    self.active_handle = "move"
                    self.drag_orig_rect = target_rect
                    if self.selected_target.startswith("block_"):
                        self.drag_origin_block = td.answer_blocks[
                            int(self.selected_target.split("_")[1])
                        ]
                    return

            # Check if clicked on Student ROI
            if td.student_number_roi is not None:
                sq = self._img_rect_to_canvas(td.student_number_roi)
                if sq.contains(pt):
                    self.selected_target = "student_roi"
                    self.active_handle = "move"
                    self.drag_orig_rect = td.student_number_roi
                    self.target_selected.emit("student_roi")
                    self.update()
                    return

            # Check if clicked on Score ROI
            if td.score_roi is not None:
                scq = self._img_rect_to_canvas(td.score_roi)
                if scq.contains(pt):
                    self.selected_target = "score_roi"
                    self.active_handle = "move"
                    self.drag_orig_rect = td.score_roi
                    self.target_selected.emit("score_roi")
                    self.update()
                    return

            # Check if clicked on any block
            for idx, b in enumerate(td.answer_blocks):
                bq = self._img_rect_to_canvas(
                    (
                        b.col_boundaries[0],
                        b.row_boundaries[0],
                        b.col_boundaries[-1],
                        b.row_boundaries[-1],
                    )
                )
                if bq.contains(pt):
                    self.selected_target = f"block_{idx}"
                    self.active_handle = "move"
                    self.drag_orig_rect = (
                        b.col_boundaries[0],
                        b.row_boundaries[0],
                        b.col_boundaries[-1],
                        b.row_boundaries[-1],
                    )
                    self.drag_origin_block = b
                    self.target_selected.emit(f"block_{idx}")
                    self.update()
                    return

            self.active_handle = None
            self.drag_orig_rect = None

        self.update()

    def mouseMoveEvent(self, event: Any) -> None:
        pt = event.position().toPoint()
        self.drag_current_pt = pt

        if not self.is_dragging:
            # Update cursor based on hover in SELECT_MOVE mode
            if self.mode == self.MODE_SELECT_MOVE:
                target_rect = self._get_target_rect()
                if target_rect is not None:
                    qrect = self._img_rect_to_canvas(target_rect)
                    handles = self._get_handles_for_rect(qrect)
                    for h_name, h_rect in handles.items():
                        if h_rect.contains(pt):
                            if h_name in ("tl", "br"):
                                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                            elif h_name in ("tr", "bl"):
                                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                            elif h_name in ("l", "r"):
                                self.setCursor(Qt.CursorShape.SizeHorCursor)
                            elif h_name in ("t", "b"):
                                self.setCursor(Qt.CursorShape.SizeVerCursor)
                            return
                    if qrect.contains(pt):
                        self.setCursor(Qt.CursorShape.SizeAllCursor)
                        return
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self.mode == self.MODE_EDIT_GRID_LINE and self.active_line and self.line_origin_block:
            block_index, axis, boundary_index = self.active_line
            coordinate = round(
                (pt.x() if axis == "col" else pt.y()) / max(0.01, self.scale_factor)
            )
            td = self.template_def
            if td is not None:
                try:
                    updated = set_boundary_position(
                        self.line_origin_block,
                        axis=axis,  # type: ignore[arg-type]
                        index=boundary_index,
                        position=coordinate,
                        canonical_width=td.canonical_width,
                        canonical_height=td.canonical_height,
                        cell_inset=td.cell_inset,
                    )
                except ValueError:
                    pass
                else:
                    self.block_updated.emit(block_index, updated)
                    values = updated.row_boundaries if axis == "row" else updated.col_boundaries
                    self.line_selected.emit(block_index, axis, boundary_index, values[boundary_index])
            self.update()
            return

        # Dragging logic
        if self.mode == self.MODE_SELECT_MOVE and self.drag_orig_rect and self.drag_start_pt:
            dx = int((pt.x() - self.drag_start_pt.x()) / self.scale_factor)
            dy = int((pt.y() - self.drag_start_pt.y()) / self.scale_factor)
            ox1, oy1, ox2, oy2 = self.drag_orig_rect

            nx1, ny1, nx2, ny2 = ox1, oy1, ox2, oy2
            if self.active_handle == "move":
                nx1, ny1, nx2, ny2 = ox1 + dx, oy1 + dy, ox2 + dx, oy2 + dy
            elif self.active_handle == "tl":
                nx1, ny1 = ox1 + dx, oy1 + dy
            elif self.active_handle == "tr":
                nx2, ny1 = ox2 + dx, oy1 + dy
            elif self.active_handle == "bl":
                nx1, ny2 = ox1 + dx, oy2 + dy
            elif self.active_handle == "br":
                nx2, ny2 = ox2 + dx, oy2 + dy
            elif self.active_handle == "t":
                ny1 = oy1 + dy
            elif self.active_handle == "b":
                ny2 = oy2 + dy
            elif self.active_handle == "l":
                nx1 = ox1 + dx
            elif self.active_handle == "r":
                nx2 = ox2 + dx

            # Ensure valid bounds
            if nx2 > nx1 + 20 and ny2 > ny1 + 20:
                self._apply_interactive_rect((nx1, ny1, nx2, ny2))

        self.update()

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.is_dragging:
            return

        self.is_dragging = False
        pt = event.position().toPoint()
        if self.drag_start_pt is None:
            return

        ix1, iy1 = self._canvas_to_img(self.drag_start_pt)
        ix2, iy2 = self._canvas_to_img(pt)

        min_x, max_x = min(ix1, ix2), max(ix1, ix2)
        min_y, max_y = min(iy1, iy2), max(iy1, iy2)
        bw = max_x - min_x
        bh = max_y - min_y

        if self.mode == self.MODE_DRAW_GRID_AREA:
            if bw > 50 and bh > 50:
                self.grid_area_completed.emit((min_x, min_y, bw, bh))
        elif self.mode == self.MODE_DRAW_STUDENT_ROI:
            if bw > 30 and bh > 20:
                self.roi_updated.emit("student", (min_x, min_y, max_x, max_y))
        elif self.mode == self.MODE_DRAW_SCORE_ROI:
            if bw > 30 and bh > 20:
                self.roi_updated.emit("score", (min_x, min_y, max_x, max_y))

        self.drag_start_pt = None
        self.drag_current_pt = None
        self.active_handle = None
        self.drag_orig_rect = None
        self.drag_origin_block = None
        self.active_line = None
        self.line_origin_block = None
        self.update()

    def _pick_grid_line(self, point: QPoint) -> tuple[int, str, int] | None:
        td = self.template_def
        if td is None:
            return None
        candidates: list[tuple[int, int, str, int]] = []
        if self.selected_target.startswith("block_"):
            try:
                indices = [int(self.selected_target.split("_")[1])]
            except (ValueError, IndexError):
                indices = []
        else:
            indices = list(range(len(td.answer_blocks)))

        for block_index in indices:
            if not 0 <= block_index < len(td.answer_blocks):
                continue
            block = td.answer_blocks[block_index]
            rect = self._img_rect_to_canvas(
                (block.col_boundaries[0], block.row_boundaries[0],
                 block.col_boundaries[-1], block.row_boundaries[-1])
            )
            if not rect.adjusted(-8, -8, 8, 8).contains(point):
                continue
            for axis, boundaries in (("col", block.col_boundaries), ("row", block.row_boundaries)):
                point_value = point.x() if axis == "col" else point.y()
                for line_index, image_value in enumerate(boundaries):
                    canvas_value = round(image_value * self.scale_factor)
                    distance = abs(point_value - canvas_value)
                    if distance <= 8:
                        candidates.append((distance, block_index, axis, line_index))
        if not candidates:
            return None
        _, block_index, axis, line_index = min(candidates)
        return block_index, axis, line_index

    def _apply_interactive_rect(self, rect: tuple[int, int, int, int]) -> None:
        td = self.template_def
        if td is None:
            return
        x1, y1, x2, y2 = rect
        if self.selected_target == "student_roi":
            self.roi_updated.emit("student", rect)
        elif self.selected_target == "score_roi":
            self.roi_updated.emit("score", rect)
        elif self.selected_target.startswith("block_"):
            try:
                b_idx = int(self.selected_target.split("_")[1])
                if 0 <= b_idx < len(td.answer_blocks):
                    old_b = td.answer_blocks[b_idx]
                    origin = self.drag_origin_block or old_b
                    new_b = resize_block_from_origin(
                        origin,
                        rect=rect,
                        canonical_width=td.canonical_width,
                        canonical_height=td.canonical_height,
                        cell_inset=td.cell_inset,
                    )
                    self.block_updated.emit(b_idx, new_b)
            except (ValueError, IndexError):
                pass

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if self.base_pixmap is None:
            painter.setPen(QColor("#64748B"))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "ยังไม่มีภาพกระดาษคำตอบ\nกรุณากด 'เลือกภาพกระดาษคำตอบ' เพื่อเริ่มต้น",
            )
            return

        # 1. Draw scaled base image
        scaled = self.base_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(0, 0, scaled)

        if not self.show_overlay or self.template_def is None:
            painter.end()
            return

        td = self.template_def
        font = QFont("Arial", max(7, int(10 * self.scale_factor)))
        painter.setFont(font)

        # 2. Draw answer blocks
        for idx, block in enumerate(td.answer_blocks):
            is_selected = (
                self.selected_target == "all_blocks" or self.selected_target == f"block_{idx}"
            )

            # Block outer border
            b_rect = self._img_rect_to_canvas(
                (
                    block.col_boundaries[0],
                    block.row_boundaries[0],
                    block.col_boundaries[-1],
                    block.row_boundaries[-1],
                )
            )
            block_color = QColor(0, 200, 255) if is_selected else QColor(0, 160, 220, 180)
            painter.setPen(QPen(block_color, 2 if is_selected else 1))
            painter.setBrush(QBrush(QColor(0, 200, 255, 20 if is_selected else 8)))
            painter.drawRect(b_rect)

            # Cell boxes
            pen_box = QPen(QColor(0, 230, 118, 220 if is_selected else 150), 1)
            painter.setPen(pen_box)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            for q in range(block.question_start, block.question_end + 1):
                row_index = q - block.question_start
                for c in range(block.choice_count):
                    cx, cy, cw, ch = cell_box_for_block(block, row_index, c)
                    cq_rect = self._img_rect_to_canvas((cx, cy, cx + cw, cy + ch))
                    painter.drawRect(cq_rect)

            # Structured grid boundaries remain visible and individually editable.
            for axis, boundaries in (("col", block.col_boundaries), ("row", block.row_boundaries)):
                for line_index, image_value in enumerate(boundaries):
                    selected = self.selected_line == (idx, axis, line_index)
                    color = QColor(255, 196, 0) if selected else QColor(48, 120, 145, 170)
                    painter.setPen(QPen(color, 2 if selected else 1))
                    canvas_value = round(image_value * self.scale_factor)
                    if axis == "col":
                        painter.drawLine(canvas_value, b_rect.top(), canvas_value, b_rect.bottom())
                    else:
                        painter.drawLine(b_rect.left(), canvas_value, b_rect.right(), canvas_value)

            # Block label header
            painter.setPen(block_color)
            painter.drawText(
                b_rect.x() + 4,
                b_rect.y() - 4,
                f"ชุดที่ {idx + 1} (ข้อ {block.question_start}-{block.question_end}) · {block.choice_count} ตัวเลือก",
            )

            # Handles if this specific block is selected
            if self.selected_target == f"block_{idx}":
                self._draw_handles(painter, b_rect, block_color)

        # 3. Draw Student Number ROI
        if td.student_number_roi is not None:
            sn_color = QColor(168, 85, 247)
            sn_rect = self._img_rect_to_canvas(td.student_number_roi)
            is_selected = self.selected_target == "student_roi"
            painter.setPen(QPen(sn_color, 2 if is_selected else 1))
            painter.setBrush(QBrush(QColor(168, 85, 247, 30 if is_selected else 12)))
            painter.drawRect(sn_rect)
            painter.setPen(sn_color)
            painter.drawText(sn_rect.x() + 4, sn_rect.y() - 4, "🔢 ช่องเลขประจำตัว (Student ROI)")
            if is_selected:
                self._draw_handles(painter, sn_rect, sn_color)

        # 4. Draw Score ROI
        if td.score_roi is not None:
            sc_color = QColor(249, 115, 22)
            sc_rect = self._img_rect_to_canvas(td.score_roi)
            is_selected = self.selected_target == "score_roi"
            painter.setPen(QPen(sc_color, 2 if is_selected else 1))
            painter.setBrush(QBrush(QColor(249, 115, 22, 30 if is_selected else 12)))
            painter.drawRect(sc_rect)
            painter.setPen(sc_color)
            painter.drawText(sc_rect.x() + 4, sc_rect.y() - 4, "📝 ช่องคะแนนรวม (Score ROI)")
            if is_selected:
                self._draw_handles(painter, sc_rect, sc_color)

        # 5. Draw active drag box (rubber-band) when creating new box
        if (
            self.is_dragging
            and self.drag_start_pt
            and self.drag_current_pt
            and self.mode != self.MODE_SELECT_MOVE
        ):
            rx1 = min(self.drag_start_pt.x(), self.drag_current_pt.x())
            ry1 = min(self.drag_start_pt.y(), self.drag_current_pt.y())
            rw = abs(self.drag_current_pt.x() - self.drag_start_pt.x())
            rh = abs(self.drag_current_pt.y() - self.drag_start_pt.y())
            rubber_color = (
                QColor(0, 200, 255)
                if self.mode == self.MODE_DRAW_GRID_AREA
                else (
                    QColor(168, 85, 247)
                    if self.mode == self.MODE_DRAW_STUDENT_ROI
                    else QColor(249, 115, 22)
                )
            )
            pen_dash = QPen(rubber_color, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen_dash)
            painter.setBrush(
                QBrush(QColor(rubber_color.red(), rubber_color.green(), rubber_color.blue(), 40))
            )
            painter.drawRect(rx1, ry1, rw, rh)

        painter.end()

    def _draw_handles(self, painter: QPainter, rect: QRect, color: QColor) -> None:
        handles = self._get_handles_for_rect(rect)
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.setBrush(QBrush(color))
        for h_rect in handles.values():
            painter.drawRect(h_rect)


class CalibrationTestDialog(QDialog):
    """Visual test-before-save inspection dialog with aligned overlay, mark status, and ROI crops."""

    def __init__(
        self,
        template_def: TemplateDefinition,
        analysis_result: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.template_def = template_def
        self.analysis_result = analysis_result
        self.scale_factor: float = 0.55

        self.setWindowTitle("ผลการทดสอบการตรวจและอ่านค่า (Test Inspection Preview)")
        self.resize(1150, 780)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # Header
        header = QLabel("ตรวจสอบความถูกต้องก่อนบันทึกแม่แบบ (Visual Quality Inspection)")
        header.setProperty("role", "section-title")
        main_layout.addWidget(header)

        desc = QLabel(
            "ภาพด้านล่างแสดงการจัดตำแหน่ง (Registration), ผลการตรวจจับรอยกา (OMR) และภาพครอบตัดของช่องเลขประจำตัว/ช่องคะแนนจริง"
        )
        desc.setProperty("role", "muted")
        main_layout.addWidget(desc)

        # Splitter: Left aligned image, Right details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Aligned image with overlay
        left_box = QWidget()
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)

        img_toolbar = QHBoxLayout()
        img_toolbar.addWidget(QLabel("ภาพกระดาษที่จัดตำแหน่งแล้ว:"))
        img_toolbar.addStretch()
        btn_zoom_out = QPushButton("ย่อ")
        btn_zoom_out.clicked.connect(lambda: self._zoom(-0.1))
        img_toolbar.addWidget(btn_zoom_out)
        self.zoom_lbl = QLabel(f"{int(self.scale_factor * 100)}%")
        img_toolbar.addWidget(self.zoom_lbl)
        btn_zoom_in = QPushButton("ขยาย")
        btn_zoom_in.clicked.connect(lambda: self._zoom(0.1))
        img_toolbar.addWidget(btn_zoom_in)
        left_layout.addLayout(img_toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.img_label)
        left_layout.addWidget(self.scroll_area, 1)

        splitter.addWidget(left_box)

        # Right: Details, ROI crops, and answers table
        right_box = QWidget()
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        # Metrics card
        reg = analysis_result.get("registration", {})
        cov = reg.get("table_coverage", 0.0)
        answers = analysis_result.get("answers", [])

        singles = sum(1 for a in answers if a["classification"] == "single_mark")
        blanks = sum(1 for a in answers if a["classification"] == "blank")
        multis = sum(1 for a in answers if a["classification"] == "multiple")
        uncs = sum(1 for a in answers if a["classification"] == "uncertain")

        metrics_group = QGroupBox("สรุปผลการจัดตำแหน่งและการอ่านรอยกา")
        m_layout = QVBoxLayout(metrics_group)

        cov_text = (
            f"• Table Coverage: {cov:.1%}  ({'✅ แม่นยำสมบูรณ์' if cov >= 0.85 else '⚠️ ควรตรวจทาน'})"
        )
        lbl_cov = QLabel(cov_text)
        lbl_cov.setProperty("role", "metric")
        m_layout.addWidget(lbl_cov)

        stats_lbl = QLabel(
            f"• คำตอบเดี่ยว (Single): {singles} ข้อ  |  "
            f"• ไม่ได้กา (Blank): {blanks} ข้อ\n"
            f"• กาซ้ำ (Multiple): {multis} ข้อ  |  "
            f"• สงสัย (Uncertain): {uncs} ข้อ"
        )
        stats_lbl.setProperty("role", "body")
        m_layout.addWidget(stats_lbl)
        right_layout.addWidget(metrics_group)

        # ROI Visual crops
        roi_group = QGroupBox("ภาพตัดตรวจช่องระบุตัวตนและคะแนน (ROI Inspection)")
        roi_layout = QHBoxLayout(roi_group)

        aligned = analysis_result.get("aligned")

        # Student crop
        sn_box = QVBoxLayout()
        sn_box.addWidget(QLabel("ช่องเลขประจำตัว:"))
        self.sn_crop_lbl = QLabel("ไม่มีพิกัด")
        self.sn_crop_lbl.setProperty("role", "preview")
        self.sn_crop_lbl.setMinimumHeight(70)
        self.sn_crop_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if aligned is not None and template_def.student_number_roi is not None:
            x1, y1, x2, y2 = template_def.student_number_roi
            if 0 <= y1 < y2 <= aligned.shape[0] and 0 <= x1 < x2 <= aligned.shape[1]:
                scrop = aligned[y1:y2, x1:x2]
                if scrop.size > 0:
                    qimg = self._cv_to_qimage(scrop)
                    pix = QPixmap.fromImage(qimg).scaled(
                        200,
                        80,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.sn_crop_lbl.setPixmap(pix)
        sn_box.addWidget(self.sn_crop_lbl)
        roi_layout.addLayout(sn_box)

        # Score crop
        score_box = QVBoxLayout()
        score_box.addWidget(QLabel("ช่องคะแนนรวม:"))
        self.score_crop_lbl = QLabel("ไม่มีพิกัด")
        self.score_crop_lbl.setProperty("role", "preview")
        self.score_crop_lbl.setMinimumHeight(70)
        self.score_crop_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if aligned is not None and template_def.score_roi is not None:
            x1, y1, x2, y2 = template_def.score_roi
            if 0 <= y1 < y2 <= aligned.shape[0] and 0 <= x1 < x2 <= aligned.shape[1]:
                scrop = aligned[y1:y2, x1:x2]
                if scrop.size > 0:
                    qimg = self._cv_to_qimage(scrop)
                    pix = QPixmap.fromImage(qimg).scaled(
                        200,
                        80,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.score_crop_lbl.setPixmap(pix)
        score_box.addWidget(self.score_crop_lbl)
        roi_layout.addLayout(score_box)

        right_layout.addWidget(roi_group)

        # Table of answers
        table_group = QGroupBox("รายละเอียดการอ่านคำตอบรายข้อ")
        t_layout = QVBoxLayout(table_group)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ข้อที่", "คำตอบที่อ่านได้", "สถานะ", "ความต่างหมึก"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setRowCount(len(answers))

        for row_i, a in enumerate(answers):
            q_num = a["question"]
            selected_str = ", ".join(a.get("selected", [])) or "-"
            cls = a.get("classification", "-")
            cls_thai = {
                "single_mark": "✅ คำตอบเดี่ยว",
                "blank": "⚪ ไม่ได้กา",
                "multiple": "🟣 กาซ้ำ",
                "uncertain": "🔴 สงสัย",
                "boundary_cross": "🟡 กาล้ำช่อง",
            }.get(cls, cls)

            item_q = QTableWidgetItem(str(q_num))
            item_q.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_i, 0, item_q)

            item_ans = QTableWidgetItem(selected_str)
            item_ans.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_ans.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            self.table.setItem(row_i, 1, item_ans)

            item_cls = QTableWidgetItem(cls_thai)
            item_cls.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_i, 2, item_cls)

            margin = a.get("top_two_margin", 0.0)
            item_margin = QTableWidgetItem(f"{margin:.3f}")
            item_margin.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_i, 3, item_margin)

        t_layout.addWidget(self.table)
        right_layout.addWidget(table_group, 1)

        splitter.addWidget(right_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, 1)

        # Bottom buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_close = QPushButton("กลับไปปรับเทียบต่อ")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)

        btn_ok = QPushButton("ผลการทดสอบถูกต้อง")
        btn_ok.setProperty("accent", True)
        btn_ok.clicked.connect(self.accept)
        btn_box.addWidget(btn_ok)

        main_layout.addLayout(btn_box)

        # Render aligned image with overlay
        self._render_aligned_preview()

    def _cv_to_qimage(self, bgr: np.ndarray) -> QImage:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()

    def _render_aligned_preview(self) -> None:
        aligned = self.analysis_result.get("aligned")
        if aligned is None:
            self.img_label.setText("ไม่พบข้อมูลภาพที่จัดตำแหน่ง")
            return

        td = self.template_def
        overlay = aligned.copy()
        answers_dict = {a["question"]: a for a in self.analysis_result.get("answers", [])}

        # Draw answer cells colored by classification
        for block in td.answer_blocks:
            for q in range(block.question_start, block.question_end + 1):
                ans_info = answers_dict.get(q)
                cls = ans_info.get("classification") if ans_info else "blank"
                selected_labels = ans_info.get("selected", []) if ans_info else []

                for c in range(block.choice_count):
                    x, y, w, h = cell_box_rect_for_template(td, q, c)
                    choice_label = (
                        CANONICAL_CHOICES[c] if c < len(CANONICAL_CHOICES) else str(c + 1)
                    )
                    is_selected = choice_label in selected_labels

                    if is_selected:
                        if cls == "single_mark":
                            color = (0, 220, 100)  # Green
                        elif cls == "multiple":
                            color = (190, 70, 190)  # Purple
                        else:
                            color = (0, 165, 255)  # Orange
                        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
                    else:
                        cv2.rectangle(overlay, (x, y), (x + w, y + h), (180, 180, 180), 1)

        # Draw ROIs
        if td.student_number_roi:
            x1, y1, x2, y2 = td.student_number_roi
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (247, 85, 168), 2)
            cv2.putText(
                overlay,
                "Student ROI",
                (x1 + 4, y1 + 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (247, 85, 168),
                2,
            )

        if td.score_roi:
            x1, y1, x2, y2 = td.score_roi
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (22, 115, 249), 2)
            cv2.putText(
                overlay,
                "Score ROI",
                (x1 + 4, y1 + 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (22, 115, 249),
                2,
            )

        qimg = self._cv_to_qimage(overlay)
        self.preview_pixmap = QPixmap.fromImage(qimg)
        self._update_preview()

    def _zoom(self, delta: float) -> None:
        self.scale_factor = max(0.2, min(2.0, round(self.scale_factor + delta, 2)))
        self.zoom_lbl.setText(f"{int(self.scale_factor * 100)}%")
        self._update_preview()

    def _update_preview(self) -> None:
        if hasattr(self, "preview_pixmap"):
            size = self.preview_pixmap.size() * self.scale_factor
            scaled = self.preview_pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.img_label.setPixmap(scaled)
            self.img_label.resize(scaled.size())


class CalibrationDialog(QDialog):
    """Comprehensive dialog to discover, adjust, visually inspect, and save answer sheet templates."""

    def __init__(
        self,
        application: Application,
        duplicate_from: TemplateDefinition | None = None,
        edit_template: TemplateDefinition | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.application = application
        self.duplicate_from = duplicate_from
        self.edit_template = edit_template
        self.raw_image_bytes: bytes | None = None
        self.canonical_ref_bgr: np.ndarray | None = None
        self.current_template_def: TemplateDefinition | None = None
        self.discovery_worker: DiscoveryWorker | None = None
        self._active_workers: list[QThread] = []
        self._discovery_generation = 0
        self._grid_generation = 0
        self._draft_revision = 0
        self._geometry_dirty = False
        self._geometry_warnings: list[str] = []
        self._close_pending = False
        self.mobile_upload_session: UploadSession | None = None
        self.mobile_upload_dialog: QDialog | None = None
        self.canvas = CalibrationCanvas()
        self.canvas.roi_updated.connect(self._on_canvas_roi_updated)
        self.canvas.block_updated.connect(self._on_canvas_block_updated)
        self.canvas.grid_area_completed.connect(self._on_canvas_grid_area_completed)
        self.canvas.target_selected.connect(self._on_canvas_target_selected)
        self.canvas.line_selected.connect(self._on_canvas_line_selected)

        title = "ปรับเทียบและสร้างรูปแบบกระดาษคำตอบใหม่"
        if edit_template is not None:
            title = f"แก้ไข/ปรับเทียบแม่แบบ: {edit_template.name}"
        self.setWindowTitle(title)

        # Sensible initial size based on available screen geometry (up to 86% of usable screen)
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            w = min(1280, max(640, min(avail.width(), int(avail.width() * 0.86))))
            h = min(840, max(480, min(avail.height(), int(avail.height() * 0.86))))
            self.setMinimumSize(min(800, avail.width()), min(520, avail.height()))
            self.resize(w, h)
            self.setGeometry(
                avail.x() + max(0, (avail.width() - w) // 2),
                avail.y() + max(0, (avail.height() - h) // 2),
                w,
                h,
            )
        else:
            self.resize(1180, 720)
            self.setMinimumSize(920, 560)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # Header banner
        header = QLabel("ระบบปรับเทียบและสร้างแม่แบบกระดาษคำตอบ (Template Calibration System)")
        header.setProperty("role", "section-title")
        main_layout.addWidget(header)

        desc = QLabel(
            "ตรวจจับโครงสร้างตารางคำตอบอัตโนมัติ พร้อมเครื่องมือลาก/ปรับแก้ตำแหน่งบนภาพจริง "
            "เพื่อความแม่นยำสูงสุดก่อนนำไปใช้ตรวจข้อสอบ"
        )
        desc.setProperty("role", "muted")
        desc.setWordWrap(True)
        main_layout.addWidget(desc)

        # Splitter: Canvas on left, Controls on right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Interactive Canvas in scroll area
        left_box = QWidget()
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Toolbar Row 1: Actions & View controls
        toolbar_row1 = QHBoxLayout()
        toolbar_row1.setSpacing(6)

        self.load_img_btn = QPushButton("เลือกภาพ…")
        self.load_img_btn.setToolTip("เลือกไฟล์ภาพกระดาษคำตอบ (JPG, PNG) เพื่อใช้ในการปรับเทียบ")
        self.load_img_btn.clicked.connect(self._select_image)
        toolbar_row1.addWidget(self.load_img_btn)

        from exam_grader.exam_ui import QrGlyphButton

        self.mobile_load_btn = QrGlyphButton()
        self.mobile_load_btn.setFixedSize(42, 36)
        self.mobile_load_btn.setAccessibleName("เพิ่มภาพแม่แบบผ่านมือถือ")
        self.mobile_load_btn.setToolTip("รับภาพแม่แบบจากมือถือผ่าน QR")
        self.mobile_load_btn.clicked.connect(self._open_mobile_upload)
        toolbar_row1.addWidget(self.mobile_load_btn)

        self.redetect_btn = QPushButton("ตรวจหาใหม่")
        self.redetect_btn.setToolTip("ตรวจหาตำแหน่งและโครงสร้างตารางคำตอบจากภาพปัจจุบันใหม่อีกครั้ง")
        self.redetect_btn.setEnabled(False)
        self.redetect_btn.clicked.connect(self._redetect_current_image)
        toolbar_row1.addWidget(self.redetect_btn)

        self.help_photo_btn = QPushButton("คำแนะนำ")
        self.help_photo_btn.setToolTip("ดูคำแนะนำการถ่ายภาพกระดาษคำตอบให้ได้ผลตรวจจับที่แม่นยำ")
        self.help_photo_btn.clicked.connect(self._show_photo_tips)
        toolbar_row1.addWidget(self.help_photo_btn)

        toolbar_row1.addStretch()

        self.toggle_overlay_btn = QPushButton("เส้น")
        self.toggle_overlay_btn.setCheckable(True)
        self.toggle_overlay_btn.setChecked(True)
        self.toggle_overlay_btn.setToolTip("เปิด/ปิดการแสดงเส้นโครงร่างตารางคำตอบบนภาพ")
        self.toggle_overlay_btn.clicked.connect(self._toggle_overlay)
        toolbar_row1.addWidget(self.toggle_overlay_btn)

        zoom_out_btn = QPushButton("ย่อ")
        zoom_out_btn.setToolTip("ย่อภาพ")
        zoom_out_btn.clicked.connect(lambda: self._zoom(-0.1))
        toolbar_row1.addWidget(zoom_out_btn)

        self.zoom_lbl = QLabel("50%")
        toolbar_row1.addWidget(self.zoom_lbl)

        zoom_in_btn = QPushButton("ขยาย")
        zoom_in_btn.setToolTip("ขยายภาพ")
        zoom_in_btn.clicked.connect(lambda: self._zoom(0.1))
        toolbar_row1.addWidget(zoom_in_btn)

        left_layout.addLayout(toolbar_row1)

        # Toolbar Row 2: Interactive Tool Palette
        toolbar_row2 = QHBoxLayout()
        toolbar_row2.setSpacing(6)

        tool_label = QLabel("เครื่องมือ:")
        tool_label.setProperty("role", "section-label")
        toolbar_row2.addWidget(tool_label)

        self.tool_btn_group = QButtonGroup(self)
        self.tool_btn_group.setExclusive(True)

        self.btn_tool_select = QPushButton("เลือก")
        self.btn_tool_select.setCheckable(True)
        self.btn_tool_select.setChecked(True)
        self.btn_tool_select.setToolTip("คลิกลากเพื่อย้ายหรือปรับขนาดกรอบคำตอบ/ช่องคะแนน/ช่องเลขประจำตัว")
        self.btn_tool_select.clicked.connect(
            lambda: self.canvas.set_mode(CalibrationCanvas.MODE_SELECT_MOVE)
        )
        toolbar_row2.addWidget(self.btn_tool_select)
        self.tool_btn_group.addButton(self.btn_tool_select)

        self.btn_tool_lines = QPushButton("แก้เส้น")
        self.btn_tool_lines.setCheckable(True)
        self.btn_tool_lines.setToolTip("คลิกและลากเส้นแถวหรือคอลัมน์บนตารางที่เลือก")
        self.btn_tool_lines.clicked.connect(
            lambda: self.canvas.set_mode(CalibrationCanvas.MODE_EDIT_GRID_LINE)
        )
        toolbar_row2.addWidget(self.btn_tool_lines)
        self.tool_btn_group.addButton(self.btn_tool_lines)

        self.btn_tool_grid = QPushButton("วาด")
        self.btn_tool_grid.setCheckable(True)
        self.btn_tool_grid.setToolTip("ลากพื้นที่สี่เหลี่ยมบนภาพเพื่อตรวจจับตารางคำตอบในบริเวณนั้น")
        self.btn_tool_grid.clicked.connect(
            lambda: self.canvas.set_mode(CalibrationCanvas.MODE_DRAW_GRID_AREA)
        )
        toolbar_row2.addWidget(self.btn_tool_grid)
        self.tool_btn_group.addButton(self.btn_tool_grid)

        self.btn_tool_student = QPushButton("เลขที่")
        self.btn_tool_student.setCheckable(True)
        self.btn_tool_student.setToolTip(
            "💡 ลากกรอบเฉพาะช่องเขียนตัวเลข (เว้นคำว่า 'เลขที่' และเส้นไข่ปลาไว้ด้านนอกเพื่อความแม่นยำสูงสุด)"
        )
        self.btn_tool_student.clicked.connect(
            lambda: self.canvas.set_mode(CalibrationCanvas.MODE_DRAW_STUDENT_ROI)
        )
        toolbar_row2.addWidget(self.btn_tool_student)
        self.tool_btn_group.addButton(self.btn_tool_student)

        self.btn_tool_score = QPushButton("คะแนน")
        self.btn_tool_score.setCheckable(True)
        self.btn_tool_score.setToolTip("ลากกรอบสี่เหลี่ยมเพื่อกำหนดตำแหน่งช่องคะแนนรวม")
        self.btn_tool_score.clicked.connect(
            lambda: self.canvas.set_mode(CalibrationCanvas.MODE_DRAW_SCORE_ROI)
        )
        toolbar_row2.addWidget(self.btn_tool_score)
        self.tool_btn_group.addButton(self.btn_tool_score)

        toolbar_row2.addStretch()
        left_layout.addLayout(toolbar_row2)

        self.roi_helper_lbl = QLabel(
            "💡 ลากกรอบเฉพาะช่องเขียนตัวเลข (เว้นคำว่า 'เลขที่' และเส้นไข่ปลาไว้ด้านนอกเพื่อความแม่นยำสูงสุด)"
        )
        self.roi_helper_lbl.setProperty("role", "hint")
        self.roi_helper_lbl.setWordWrap(True)
        left_layout.addWidget(self.roi_helper_lbl)

        # Progress bar for background discovery
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setWidget(self.canvas)
        left_layout.addWidget(self.scroll_area, 1)

        splitter.addWidget(left_box)

        # Right: Parameters & Adjustments Form inside scrollable area
        right_box = QWidget()
        right_box.setMinimumWidth(330)
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(8, 0, 8, 0)
        right_layout.setSpacing(10)

        # Group 1: Template Info
        params_group = QGroupBox("ข้อมูลแม่แบบ")
        form = QFormLayout(params_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setSpacing(8)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("เช่น กระดาษคำตอบ 30 ข้อ (4 ตัวเลือก)")
        self.name_input.setMinimumWidth(180)
        form.addRow("ชื่อแม่แบบ:", self.name_input)

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("เช่น custom-final-30q")
        self.id_input.setMinimumWidth(180)
        attach_digit_normalizer(self.id_input)
        form.addRow("รหัส (ID):", self.id_input)

        self.q_count_spin = NumericSpinBox()
        self.q_count_spin.setRange(1, 60)
        self.q_count_spin.setValue(30)
        form.addRow("จำนวนข้อรวม:", self.q_count_spin)

        self.choice_count_spin = NumericSpinBox()
        self.choice_count_spin.setRange(2, 5)
        self.choice_count_spin.setValue(4)
        self.choice_count_spin.valueChanged.connect(self._on_choice_count_changed)
        form.addRow("จำนวนตัวเลือก:", self.choice_count_spin)

        self.header_style_combo = QComboBox()
        self.header_style_combo.addItems(["ภาษาไทย (ก, ข, ค, ง, จ)", "ภาษาอังกฤษ (A, B, C, D, E)"])
        form.addRow("รูปแบบหัวตัวเลือก:", self.header_style_combo)

        self.inset_spin = NumericSpinBox()
        self.inset_spin.setRange(1, 12)
        self.inset_spin.setValue(6)
        self.inset_spin.setToolTip("ระยะเว้นขอบกรอบดำของแต่ละช่อง (พิกเซล)")
        form.addRow("ระยะขอบช่อง (Inset px):", self.inset_spin)

        right_layout.addWidget(params_group)

        # Group 2: Fine-Tune / Nudge / Block Management
        nudge_group = QGroupBox("ปรับตำแหน่งตารางคำตอบ")
        nudge_layout = QVBoxLayout(nudge_group)
        nudge_layout.setSpacing(6)

        nudge_target_layout = QHBoxLayout()
        nudge_target_layout.addWidget(QLabel("เป้าหมาย:"))
        self.nudge_target_combo = QComboBox()
        self.nudge_target_combo.addItems(
            ["ทุกชุดคำตอบพร้อมกัน", "ช่องเลขประจำตัวนักเรียน", "ช่องคะแนนรวม"]
        )
        self.nudge_target_combo.currentIndexChanged.connect(self._on_target_combo_changed)
        nudge_target_layout.addWidget(self.nudge_target_combo, 1)
        nudge_layout.addLayout(nudge_target_layout)

        nudge_step_layout = QHBoxLayout()
        nudge_step_layout.addWidget(QLabel("ระยะขยับ:"))
        self.nudge_step_combo = QComboBox()
        self.nudge_step_combo.addItems(["1 px (ละเอียด)", "5 px (ปานกลาง)", "10 px (เร็ว)"])
        self.nudge_step_combo.setCurrentIndex(1)
        nudge_step_layout.addWidget(self.nudge_step_combo, 1)
        nudge_layout.addLayout(nudge_step_layout)

        # Arrow buttons
        arrows_layout = QVBoxLayout()
        up_box = QHBoxLayout()
        self.btn_nudge_up = QPushButton("ขึ้น")
        self.btn_nudge_up.clicked.connect(lambda: self._nudge(0, -1))
        up_box.addStretch()
        up_box.addWidget(self.btn_nudge_up)
        up_box.addStretch()
        arrows_layout.addLayout(up_box)

        mid_box = QHBoxLayout()
        self.btn_nudge_left = QPushButton("ซ้าย")
        self.btn_nudge_left.clicked.connect(lambda: self._nudge(-1, 0))
        self.btn_nudge_right = QPushButton("ขวา")
        self.btn_nudge_right.clicked.connect(lambda: self._nudge(1, 0))
        mid_box.addStretch()
        mid_box.addWidget(self.btn_nudge_left)
        mid_box.addWidget(self.btn_nudge_right)
        mid_box.addStretch()
        arrows_layout.addLayout(mid_box)

        down_box = QHBoxLayout()
        self.btn_nudge_down = QPushButton("ลง")
        self.btn_nudge_down.clicked.connect(lambda: self._nudge(0, 1))
        down_box.addStretch()
        down_box.addWidget(self.btn_nudge_down)
        down_box.addStretch()
        arrows_layout.addLayout(down_box)
        nudge_layout.addLayout(arrows_layout)

        # Block actions
        block_action_box = QHBoxLayout()
        self.btn_add_block = QPushButton("เพิ่มชุด")
        self.btn_add_block.setToolTip("เพิ่มชุดคำตอบใหม่ถัดจากชุดเดิม")
        self.btn_add_block.clicked.connect(self._add_block)
        block_action_box.addWidget(self.btn_add_block)

        self.btn_del_block = QPushButton("ลบชุดที่เลือก")
        self.btn_del_block.setToolTip("ลบชุดคำตอบที่เลือกออกจากแม่แบบ")
        self.btn_del_block.clicked.connect(self._delete_selected_block)
        block_action_box.addWidget(self.btn_del_block)

        nudge_layout.addLayout(block_action_box)

        line_group = QGroupBox("ปรับจำนวนแถวและเส้นตาราง")
        line_layout = QVBoxLayout(line_group)
        line_layout.setSpacing(6)

        row_count_row = QHBoxLayout()
        row_count_row.addWidget(QLabel("จำนวนแถว (ข้อ):"))
        self.block_row_spin = NumericSpinBox()
        self.block_row_spin.setRange(1, 60)
        self.block_row_spin.setValue(10)
        self.block_row_spin.setEnabled(False)
        self.block_row_spin.setToolTip("ตั้งจำนวนแถวของชุดคำตอบที่เลือกโดยตรง")
        self.block_row_spin.valueChanged.connect(self._on_block_row_spin_changed)
        row_count_row.addWidget(self.block_row_spin, 1)
        line_layout.addLayout(row_count_row)

        row_edit = QHBoxLayout()
        self.btn_add_row = QPushButton("เพิ่มแถวท้ายชุด")
        self.btn_add_row.setEnabled(False)
        self.btn_add_row.setToolTip("เพิ่มข้อคำตอบต่อท้ายชุดนี้ตามระยะห่างจริง")
        self.btn_add_row.clicked.connect(self._on_append_row_clicked)
        self.btn_delete_row = QPushButton("ลบแถวล่างสุด")
        self.btn_delete_row.setEnabled(False)
        self.btn_delete_row.setToolTip("ลดข้อคำตอบข้อสุดท้ายของชุดนี้ออก")
        self.btn_delete_row.clicked.connect(self._on_remove_row_clicked)
        row_edit.addWidget(self.btn_add_row)
        row_edit.addWidget(self.btn_delete_row)
        line_layout.addLayout(row_edit)

        choice_edit = QHBoxLayout()
        self.btn_add_choice = QPushButton("เพิ่มตัวเลือกขวา")
        self.btn_add_choice.setEnabled(False)
        self.btn_add_choice.setToolTip("เพิ่มคอลัมน์ตัวเลือกทางขวาสุดของชุดนี้")
        self.btn_add_choice.clicked.connect(self._on_append_choice_clicked)
        self.btn_delete_choice = QPushButton("ลบตัวเลือกขวาสุด")
        self.btn_delete_choice.setEnabled(False)
        self.btn_delete_choice.setToolTip("ลดคอลัมน์ตัวเลือกล่าสุดออก")
        self.btn_delete_choice.clicked.connect(self._on_remove_choice_clicked)
        choice_edit.addWidget(self.btn_add_choice)
        choice_edit.addWidget(self.btn_delete_choice)
        line_layout.addLayout(choice_edit)

        line_hint = QLabel("💡 ใช้เครื่องมือ ‘✏️ แก้เส้นตาราง’ บนแถบเครื่องมือ เพื่อคลิกลากเส้นตารางบนภาพได้โดยตรง")
        line_hint.setWordWrap(True)
        line_hint.setProperty("role", "hint")
        line_layout.addWidget(line_hint)

        line_position_row = QHBoxLayout()
        line_position_row.addWidget(QLabel("พิกัดเส้น (px):"))
        self.line_position_spin = NumericSpinBox()
        self.line_position_spin.setRange(0, 100000)
        self.line_position_spin.setEnabled(False)
        line_position_row.addWidget(self.line_position_spin, 1)
        self.btn_set_line_position = QPushButton("ตั้งพิกัด")
        self.btn_set_line_position.setEnabled(False)
        self.btn_set_line_position.clicked.connect(self._set_selected_line_position)
        line_position_row.addWidget(self.btn_set_line_position)
        line_layout.addLayout(line_position_row)
        nudge_layout.addWidget(line_group)
        right_layout.addWidget(nudge_group)

        # Group 3: Diagnostics Summary
        summary_group = QGroupBox("ผลการวิเคราะห์โครงสร้างกระดาษ")
        sum_layout = QVBoxLayout(summary_group)
        self.summary_lbl = QLabel("ยังไม่ได้เริ่มวิเคราะห์กระดาษ\nกรุณากด 'เลือกภาพกระดาษคำตอบ' ทางด้านซ้าย")
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setProperty("role", "body")
        sum_layout.addWidget(self.summary_lbl)
        right_layout.addWidget(summary_group)

        right_layout.addStretch()

        self.controls_scroll = QScrollArea()
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.controls_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.controls_scroll.setWidget(right_box)
        self.controls_scroll.setMinimumWidth(380)

        splitter.addWidget(self.controls_scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([720, 420])
        main_layout.addWidget(splitter, 1)

        # Persistent bottom bar (always visible, never scrolls or clips below screen)
        btn_box = QHBoxLayout()
        self.test_btn = QPushButton("ทดสอบกับภาพจริง…")
        self.test_btn.setEnabled(False)
        self.test_btn.clicked.connect(self._test_current_geometry)
        btn_box.addWidget(self.test_btn)

        btn_box.addStretch()

        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        self.save_btn = QPushButton("บันทึกแม่แบบ")
        self.save_btn.setProperty("accent", True)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_template)
        btn_box.addWidget(self.save_btn)

        main_layout.addLayout(btn_box)

        if edit_template is not None:
            self._init_from_edit(edit_template)
        elif duplicate_from is not None:
            self._init_from_duplicate(duplicate_from)

    def _init_from_edit(self, source: TemplateDefinition) -> None:
        """Initialize dialog to edit an existing custom template."""
        self.name_input.setText(source.name)
        self.id_input.setText(source.template_id)
        self.id_input.setEnabled(False)  # Keep template ID stable when editing
        self.q_count_spin.setValue(source.question_count)
        self.choice_count_spin.setValue(source.choice_count)
        self.inset_spin.setValue(source.cell_inset)

        if source.display_choice_labels and source.display_choice_labels[0] == "ก":
            self.header_style_combo.setCurrentIndex(0)
        else:
            self.header_style_combo.setCurrentIndex(1)

        try:
            ref_bgr = get_reference_image(source, self.application.data_dir)
            self.canonical_ref_bgr = ref_bgr
            success, enc = cv2.imencode(".png", ref_bgr)
            if success:
                self.raw_image_bytes = enc.tobytes()
            draft = CalibrationDraft.from_template(source)
            self.current_template_def = draft
            self.canvas.set_reference(ref_bgr, draft)
            self._update_target_combo()
            self.save_btn.setEnabled(True)
            self.test_btn.setEnabled(True)
            self.redetect_btn.setEnabled(True)
            self._update_summary_display(
                status_title=f"กำลังแก้ไขแม่แบบ '{source.name}'",
                warnings=[],
            )
        except Exception as err:
            QMessageBox.warning(self, "โหลดภาพอ้างอิงไม่สำเร็จ", str(err))

    def _init_from_duplicate(self, source: TemplateDefinition) -> None:
        """Initialize dialog from an existing template definition."""
        self.name_input.setText(f"สำเนาของ {source.name}")
        short_uuid = uuid.uuid4().hex[:6]
        self.id_input.setText(f"{source.template_id}-copy-{short_uuid}")
        self.q_count_spin.setValue(source.question_count)
        self.choice_count_spin.setValue(source.choice_count)
        self.inset_spin.setValue(source.cell_inset)

        if source.display_choice_labels and source.display_choice_labels[0] == "ก":
            self.header_style_combo.setCurrentIndex(0)
        else:
            self.header_style_combo.setCurrentIndex(1)

        try:
            ref_bgr = get_reference_image(source, self.application.data_dir)
            self.canonical_ref_bgr = ref_bgr
            success, enc = cv2.imencode(".png", ref_bgr)
            if success:
                self.raw_image_bytes = enc.tobytes()
            draft = CalibrationDraft.from_template(source)
            self.current_template_def = draft
            self.canvas.set_reference(ref_bgr, draft)
            self._update_target_combo()
            self.save_btn.setEnabled(True)
            self.test_btn.setEnabled(True)
            self.redetect_btn.setEnabled(True)
            self._update_summary_display(
                status_title=f"ทำสำเนาจาก '{source.name}'",
                warnings=[],
            )
        except Exception as err:
            QMessageBox.warning(self, "โหลดภาพอ้างอิงไม่สำเร็จ", str(err))

    def _select_image(self) -> None:
        if not self._confirm_image_replacement():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "เลือกภาพกระดาษคำตอบเปล่าเพื่อปรับเทียบ",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp)",
        )
        if not file_path:
            return

        try:
            data = open(file_path, "rb").read()
            self._start_discovery_from_bytes(data)
        except Exception as err:
            QMessageBox.critical(self, "อ่านไฟล์ไม่ได้", str(err))

    def _confirm_image_replacement(self) -> bool:
        if not self._geometry_dirty:
            return True
        answer = QMessageBox.question(
            self,
            "ยืนยันตรวจหาใหม่",
            "การโหลดภาพใหม่จะแทนที่การแก้ไขตารางปัจจุบัน ต้องการตรวจหาโครงสร้างจากภาพอื่นหรือไม่?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _start_discovery_from_bytes(self, data: bytes) -> None:
        self.raw_image_bytes = data
        self.progress_bar.setVisible(True)
        self.summary_lbl.setText("กำลังประมวลผลและตรวจหาโครงสร้างตารางคำตอบ...")
        self._discovery_generation += 1
        generation = self._discovery_generation
        revision = self._draft_revision
        worker = DiscoveryWorker(data)
        self.discovery_worker = worker
        self._track_worker(worker)
        worker.completed.connect(
            lambda result, gen=generation, rev=revision: self._handle_discovery_finished(
                result, gen, rev
            )
        )
        worker.failed.connect(
            lambda message, gen=generation: self._handle_discovery_failed(message, gen)
        )
        worker.start()

    def _open_mobile_upload(self) -> None:
        if not self._confirm_image_replacement():
            return
        if self.mobile_upload_session and self.mobile_upload_session.is_active():
            QMessageBox.information(self, "มี session อยู่แล้ว", "กรุณาปิด QR session เดิมก่อนเปิด session ใหม่")
            return
        self._cleanup_mobile_upload_session()

        session = UploadSession("template", "template-calibration")
        try:
            session.start()
        except (LanUnavailableError, UploadSessionError) as error:
            session.cleanup()
            QMessageBox.warning(self, "เปิด QR upload ไม่ได้", str(error))
            return

        from exam_grader.exam_ui import MobileUploadDialog

        self.mobile_upload_session = session
        dialog = MobileUploadDialog(session, self)
        self.mobile_upload_dialog = dialog
        session.files_received.connect(self._on_mobile_upload_files)
        dialog.exec()
        self.mobile_upload_dialog = None
        self._cleanup_mobile_upload_session()

    def _on_mobile_upload_files(self, paths: list[str]) -> None:
        if self.mobile_upload_session is None:
            for value in paths:
                Path(value).unlink(missing_ok=True)
            return
        path = Path(paths[0]) if paths else None
        if path is None:
            return
        try:
            self._start_discovery_from_bytes(path.read_bytes())
            if self.mobile_upload_dialog is not None:
                self.mobile_upload_dialog.close()
        except OSError as error:
            QMessageBox.critical(self, "อ่านไฟล์จากมือถือไม่ได้", str(error))
        finally:
            self._cleanup_mobile_upload_session()

    def _cleanup_mobile_upload_session(self) -> None:
        session = self.mobile_upload_session
        if session is None:
            return
        session.cleanup()
        self.mobile_upload_session = None

    def _track_worker(self, worker: QThread) -> None:
        self._active_workers.append(worker)
        worker.finished.connect(lambda w=worker: self._release_worker(w))

    def _release_worker(self, worker: QThread) -> None:
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        if worker is self.discovery_worker:
            self.discovery_worker = None

    def _handle_discovery_finished(
        self, result: DiscoveryResult, generation: int, revision: int
    ) -> None:
        if generation != self._discovery_generation:
            return
        self.progress_bar.setVisible(False)
        if revision != self._draft_revision:
            self._update_summary_display(
                "เก็บการแก้ไขล่าสุดไว้; ละเว้นผลตรวจภาพเก่าที่เพิ่งเสร็จ",
                self._geometry_warnings,
            )
            return
        self._on_discovery_finished(result)

    def _handle_discovery_failed(self, err_msg: str, generation: int) -> None:
        if generation != self._discovery_generation:
            return
        self.progress_bar.setVisible(False)
        self._on_discovery_failed(err_msg)

    def _on_discovery_finished(self, result: DiscoveryResult) -> None:
        self.progress_bar.setVisible(False)

        td = result.template_def
        draft = CalibrationDraft.from_template(td)
        self.current_template_def = draft
        self.canonical_ref_bgr = result.warped_image
        self._geometry_warnings = list(result.warnings)
        self._geometry_dirty = False
        self._draft_revision += 1

        if not self.name_input.text():
            self.name_input.setText(
                f"กระดาษคำตอบ {td.question_count} ข้อ ({td.choice_count} ตัวเลือก)"
            )
        if not self.id_input.text():
            self.id_input.setText(f"template-{uuid.uuid4().hex[:8]}")

        self.q_count_spin.setValue(td.question_count)
        self.choice_count_spin.setValue(td.choice_count)
        self.inset_spin.setValue(td.cell_inset)

        if self.canonical_ref_bgr is not None:
            self.canvas.set_reference(self.canonical_ref_bgr, draft)

        self._update_target_combo()
        self._update_summary_display(result.status_message, self._geometry_warnings)

        self.save_btn.setEnabled(True)
        self.test_btn.setEnabled(True)
        self.redetect_btn.setEnabled(True)

    def _handle_grid_detection_finished(
        self, inferred: list[AnswerBlock], generation: int, revision: int, area_rect: tuple[int, int, int, int]
    ) -> None:
        if generation != self._grid_generation:
            return
        self.progress_bar.setVisible(False)
        if revision != self._draft_revision:
            self._update_summary_display("เก็บการแก้ไขล่าสุดไว้; ละเว้นผลตรวจพื้นที่เก่าที่เพิ่งเสร็จ", self._geometry_warnings)
            return
        td = self.current_template_def
        if td is None:
            return
        if not inferred:
            QMessageBox.information(
                self,
                "ไม่พบตารางในพื้นที่ที่เลือก",
                "ไม่พบเส้นตารางที่ชัดเจนในกรอบที่ลาก กรุณาลองลากให้ครอบคลุมขอบตารางทั้งหมด",
            )
            return
        if sum(block.rows for block in td.answer_blocks) + sum(block.rows for block in inferred) > 60:
            QMessageBox.warning(self, "ข้อจำกัด", "จำนวนข้อคำตอบรวมไม่สามารถเกิน 60 ข้อได้")
            return

        blocks = list(td.answer_blocks)
        for detected in inferred:
            candidate = replace(
                detected,
                block_index=len(blocks),
                geometry_state="draft",
                confidence=None,
                source_geometry={
                    "kind": "roi_grid_inference",
                    "coordinate_space": "canonical_px",
                    "candidate_box": list(area_rect),
                    "detected_column_boundaries": list(detected.col_boundaries),
                    "detected_row_boundaries": list(detected.row_boundaries),
                },
            )
            if any(_blocks_overlap(candidate, existing) for existing in blocks):
                QMessageBox.warning(self, "ตารางซ้อนกัน", "พื้นที่ตารางใหม่ทับซ้อนกับชุดคำตอบเดิม จึงไม่ได้เพิ่ม")
                return
            blocks.append(candidate)
        blocks = renumber_blocks(blocks)
        total_q = sum(block.rows for block in blocks)
        self.q_count_spin.setValue(total_q)
        self.current_template_def = replace(td, answer_blocks=blocks, question_count=total_q)
        self._mark_geometry_changed()
        self.canvas.set_template_def(self.current_template_def)
        self._update_target_combo()
        self.btn_tool_select.setChecked(True)
        self.canvas.set_mode(CalibrationCanvas.MODE_SELECT_MOVE)
        self._update_summary_display(f"เพิ่มชุดคำตอบใหม่ {len(inferred)} ชุดสำเร็จ", self._geometry_warnings)

    def _handle_grid_detection_failed(self, err_msg: str, generation: int) -> None:
        if generation != self._grid_generation:
            return
        self.progress_bar.setVisible(False)
        QMessageBox.warning(self, "ตรวจหาพื้นที่ไม่สำเร็จ", err_msg)

    def _mark_geometry_changed(self) -> None:
        self._draft_revision += 1
        self._geometry_dirty = True

    def _apply_block_list(self, blocks: list[AnswerBlock], message: str) -> None:
        td = self.current_template_def
        if td is None:
            return
        normalized = renumber_blocks(blocks)
        total_questions = sum(block.rows for block in normalized)
        self.q_count_spin.setValue(max(1, total_questions))
        self.current_template_def = replace(
            td,
            answer_blocks=normalized,
            question_count=total_questions,
        )
        self._mark_geometry_changed()
        self.canvas.set_template_def(self.current_template_def)
        self._update_target_combo()
        self._update_summary_display(message, self._geometry_warnings)

    def _on_discovery_failed(self, err_msg: str) -> None:
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "การปรับเทียบล้มเหลว", f"เกิดข้อผิดพลาด: {err_msg}")
        self.summary_lbl.setText(
            f"❌ วิเคราะห์โครงสร้างไม่สำเร็จ: {err_msg}\n\n"
            "คำแนะนำในการแก้ปัญหา:\n"
            "• วางกระดาษคำตอบบนพื้นผิวเรียบสีเข้ม (ตัดกับขอบกระดาษขาว)\n"
            "• ถ่ายให้เห็นขอบกระดาษครบทั้ง 4 ด้าน หลีกเลี่ยงแสงสะท้อน\n"
            "• สามารถใช้เครื่องมือ 'ลากตารางคำตอบ' บนภาพ เพื่อกำหนดขอบเขตด้วยตนเองได้"
        )

    def closeEvent(self, event: Any) -> None:
        self._discovery_generation += 1
        self._grid_generation += 1
        self._cleanup_mobile_upload_session()
        running = [worker for worker in self._active_workers if worker.isRunning()]
        if running:
            # Never block the GUI thread waiting for OpenCV.  QThread completion
            # will release the worker and retry the pending close safely.
            self._close_pending = True
            event.ignore()
            for worker in running:
                if not getattr(worker, "_close_hooked", False):
                    worker._close_hooked = True  # type: ignore[attr-defined]
                    worker.finished.connect(self._finish_pending_close)
            return
        super().closeEvent(event)

    def _finish_pending_close(self) -> None:
        if self._close_pending and not any(worker.isRunning() for worker in self._active_workers):
            self._close_pending = False
            self.close()

    def _update_target_combo(self) -> None:
        td = self.current_template_def
        if td is None:
            return
        curr_idx = self.nudge_target_combo.currentIndex()
        self.nudge_target_combo.blockSignals(True)
        self.nudge_target_combo.clear()
        self.nudge_target_combo.addItem("ทุกชุดคำตอบพร้อมกัน")
        for i, b in enumerate(td.answer_blocks):
            self.nudge_target_combo.addItem(f"ชุดที่ {i + 1} (ข้อ {b.question_start}–{b.question_end})")
        self.nudge_target_combo.addItem("ช่องเลขประจำตัวนักเรียน")
        self.nudge_target_combo.addItem("ช่องคะแนนรวม")
        if 0 <= curr_idx < self.nudge_target_combo.count():
            self.nudge_target_combo.setCurrentIndex(curr_idx)
        else:
            self.nudge_target_combo.setCurrentIndex(0)
        self.nudge_target_combo.blockSignals(False)
        self._sync_selected_block_controls()

    def _on_target_combo_changed(self, idx: int) -> None:
        td = self.current_template_def
        if td is None:
            return
        if idx == 0:
            self.canvas.set_selected_target("all_blocks")
        elif idx == self.nudge_target_combo.count() - 2:
            self.canvas.set_selected_target("student_roi")
        elif idx == self.nudge_target_combo.count() - 1:
            self.canvas.set_selected_target("score_roi")
        else:
            block_idx = idx - 1
            self.canvas.set_selected_target(f"block_{block_idx}")
        self._sync_selected_block_controls()

    def _on_canvas_target_selected(self, target: str) -> None:
        self.nudge_target_combo.blockSignals(True)
        if target == "all_blocks":
            self.nudge_target_combo.setCurrentIndex(0)
        elif target == "student_roi":
            self.nudge_target_combo.setCurrentIndex(self.nudge_target_combo.count() - 2)
        elif target == "score_roi":
            self.nudge_target_combo.setCurrentIndex(self.nudge_target_combo.count() - 1)
        elif target.startswith("block_"):
            try:
                b_idx = int(target.split("_")[1])
                self.nudge_target_combo.setCurrentIndex(b_idx + 1)
            except (ValueError, IndexError):
                pass
        self.nudge_target_combo.blockSignals(False)
        self._sync_selected_block_controls()

    def _on_canvas_roi_updated(self, roi_type: str, rect: tuple[int, int, int, int]) -> None:
        td = self.current_template_def
        if td is None:
            return
        from dataclasses import replace

        if roi_type == "student":
            self.current_template_def = replace(td, student_number_roi=rect)
        elif roi_type == "score":
            self.current_template_def = replace(td, score_roi=rect)
        self._mark_geometry_changed()
        self.canvas.set_template_def(self.current_template_def)
        self._update_summary_display("ปรับตำแหน่ง ROI สำเร็จ", self._geometry_warnings)

    def _on_canvas_block_updated(self, block_index: int, new_block: AnswerBlock) -> None:
        td = self.current_template_def
        if td is None:
            return
        new_blocks = list(td.answer_blocks)
        if 0 <= block_index < len(new_blocks):
            new_blocks[block_index] = new_block
            self._apply_block_list(new_blocks, f"ปรับพิกัดชุดคำตอบที่ {block_index + 1} สำเร็จ")

    def _on_canvas_line_selected(
        self, block_index: int, axis: str, boundary_index: int, position: int
    ) -> None:
        td = self.current_template_def
        if td is None or not 0 <= block_index < len(td.answer_blocks):
            return
        self._on_canvas_target_selected(f"block_{block_index}")
        maximum = td.canonical_height if axis == "row" else td.canonical_width
        self.line_position_spin.blockSignals(True)
        self.line_position_spin.setRange(0, maximum)
        self.line_position_spin.setValue(position)
        self.line_position_spin.blockSignals(False)
        self.line_position_spin.setEnabled(True)
        self.btn_set_line_position.setEnabled(True)

    def _selected_block_index_silent(self) -> int | None:
        td = self.current_template_def
        if td is None or not td.answer_blocks:
            return None
        if self.canvas.selected_target.startswith("block_"):
            try:
                idx = int(self.canvas.selected_target.split("_")[1])
                if 0 <= idx < len(td.answer_blocks):
                    return idx
            except (ValueError, IndexError):
                pass
        idx = self.nudge_target_combo.currentIndex() - 1
        if 0 <= idx < len(td.answer_blocks):
            return idx
        if len(td.answer_blocks) == 1:
            return 0
        return None

    def _selected_block_index(self) -> int | None:
        idx = self._selected_block_index_silent()
        if idx is not None:
            return idx
        td = self.current_template_def
        if td is not None and len(td.answer_blocks) > 1:
            QMessageBox.information(self, "เลือกชุดคำตอบ", "กรุณาเลือกชุดคำตอบที่ต้องการปรับจากเมนูเป้าหมายก่อน")
        return None

    def _sync_selected_block_controls(self) -> None:
        td = self.current_template_def
        if td is None:
            return
        b_idx = self._selected_block_index_silent()
        if b_idx is not None and 0 <= b_idx < len(td.answer_blocks):
            block = td.answer_blocks[b_idx]
            self.block_row_spin.blockSignals(True)
            self.block_row_spin.setValue(block.rows)
            self.block_row_spin.blockSignals(False)
            self.block_row_spin.setEnabled(True)
            self.btn_add_row.setEnabled(True)
            self.btn_delete_row.setEnabled(True)
            self.btn_add_choice.setEnabled(True)
            self.btn_delete_choice.setEnabled(True)
        else:
            self.block_row_spin.setEnabled(False)
            self.btn_add_row.setEnabled(False)
            self.btn_delete_row.setEnabled(False)
            self.btn_add_choice.setEnabled(False)
            self.btn_delete_choice.setEnabled(False)

    def _on_block_row_spin_changed(self, new_rows: int) -> None:
        td = self.current_template_def
        if td is None:
            return
        b_idx = self._selected_block_index_silent()
        if b_idx is None:
            return
        block = td.answer_blocks[b_idx]
        if block.rows == new_rows:
            return
        try:
            updated = set_block_row_count(
                block,
                new_rows,
                canonical_height=td.canonical_height,
                cell_inset=self.inset_spin.value(),
            )
            blocks = list(td.answer_blocks)
            blocks[b_idx] = updated
            self._apply_block_list(blocks, f"ปรับจำนวนแถวชุดที่ {b_idx + 1} เป็น {new_rows} แถวสำเร็จ")
        except ValueError as err:
            QMessageBox.warning(self, "ปรับจำนวนแถวไม่ได้", str(err))
            self._sync_selected_block_controls()

    def _on_append_row_clicked(self) -> None:
        td = self.current_template_def
        if td is None:
            return
        b_idx = self._selected_block_index()
        if b_idx is None:
            return
        block = td.answer_blocks[b_idx]
        try:
            updated = append_row(
                block,
                canonical_height=td.canonical_height,
                cell_inset=self.inset_spin.value(),
            )
            blocks = list(td.answer_blocks)
            blocks[b_idx] = updated
            self._apply_block_list(blocks, f"เพิ่มแถวท้ายชุดที่ {b_idx + 1} สำเร็จ (รวม {updated.rows} แถว)")
        except ValueError as err:
            QMessageBox.warning(self, "เพิ่มแถวไม่ได้", str(err))

    def _on_remove_row_clicked(self) -> None:
        td = self.current_template_def
        if td is None:
            return
        b_idx = self._selected_block_index()
        if b_idx is None:
            return
        block = td.answer_blocks[b_idx]
        try:
            updated = remove_row_at_end(block)
            blocks = list(td.answer_blocks)
            blocks[b_idx] = updated
            self._apply_block_list(blocks, f"ลบแถวล่างสุดของชุดที่ {b_idx + 1} สำเร็จ (เหลือ {updated.rows} แถว)")
        except ValueError as err:
            QMessageBox.warning(self, "ลบแถวไม่ได้", str(err))

    def _on_append_choice_clicked(self) -> None:
        td = self.current_template_def
        if td is None:
            return
        b_idx = self._selected_block_index()
        if b_idx is None:
            return
        block = td.answer_blocks[b_idx]
        try:
            updated = append_choice(
                block,
                canonical_width=td.canonical_width,
                cell_inset=self.inset_spin.value(),
            )
            blocks = list(td.answer_blocks)
            blocks[b_idx] = updated
            self._apply_block_list(blocks, f"เพิ่มตัวเลือกชุดที่ {b_idx + 1} สำเร็จ ({updated.choice_count} ตัวเลือก)")
        except ValueError as err:
            QMessageBox.warning(self, "เพิ่มตัวเลือกไม่ได้", str(err))

    def _on_remove_choice_clicked(self) -> None:
        td = self.current_template_def
        if td is None:
            return
        b_idx = self._selected_block_index()
        if b_idx is None:
            return
        block = td.answer_blocks[b_idx]
        try:
            updated = remove_choice_at_end(block)
            blocks = list(td.answer_blocks)
            blocks[b_idx] = updated
            self._apply_block_list(blocks, f"ลบตัวเลือกขวาสุดของชุดที่ {b_idx + 1} สำเร็จ (เหลือ {updated.choice_count} ตัวเลือก)")
        except ValueError as err:
            QMessageBox.warning(self, "ลบตัวเลือกไม่ได้", str(err))

    def _show_photo_tips(self) -> None:
        QMessageBox.information(
            self,
            "คำแนะนำการถ่ายภาพกระดาษคำตอบ",
            "เพื่อให้ระบบตรวจจับขอบกระดาษและเส้นตารางได้อย่างแม่นยำ:\n\n"
            "1. แสงสว่างสม่ำเสมอ: ถ่ายในที่สว่างเพียงพอ หลีกเลี่ยงเงามือหรือเงาโทรศัพท์พาดผ่านตารางคำตอบ\n"
            "2. เห็นขอบกระดาษครบ 4 มุม: วางกระดาษให้เห็นมุมทั้งสี่อย่างชัดเจน เพื่อให้ระบบดึงระนาบภาพ (Perspective Warp) ได้ตรง\n"
            "3. ถ่ายมุมตรง: ถือกล้องขนานกับกระดาษ หลีกเลี่ยงการถ่ายเอียงเกินไป\n"
            "4. พื้นหลังสีตัดกับกระดาษ: วางกระดาษบนโต๊ะสีเข้มหรือพื้นผิวที่ตัดกับสีขาวของกระดาษ",
        )

    def _redetect_current_image(self) -> None:
        if self.raw_image_bytes is None:
            QMessageBox.information(self, "ยังไม่มีภาพ", "กรุณาเลือกภาพกระดาษคำตอบก่อน")
            return
        if self._geometry_dirty:
            answer = QMessageBox.question(
                self,
                "ยืนยันตรวจหาใหม่",
                "คุณได้ทำการปรับแก้เส้นตารางหรือโครงสร้างด้วยตนเอง การตรวจหาใหม่จะคำนวณตำแหน่งจากภาพใหม่ทั้งหมดและแทนที่การปรับแต่ง ต้องการทำต่อหรือไม่?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self.progress_bar.setVisible(True)
        self.summary_lbl.setText("กำลังตรวจหาโครงสร้างตารางคำตอบใหม่อัตโนมัติ...")
        self._discovery_generation += 1
        generation = self._discovery_generation
        revision = self._draft_revision
        worker = DiscoveryWorker(self.raw_image_bytes)
        self.discovery_worker = worker
        self._track_worker(worker)
        worker.completed.connect(
            lambda result, gen=generation, rev=revision: self._handle_discovery_finished(
                result, gen, rev
            )
        )
        worker.failed.connect(
            lambda message, gen=generation: self._handle_discovery_failed(message, gen)
        )
        worker.start()

    def _set_selected_line_position(self) -> None:
        td = self.current_template_def
        selected = self.canvas.selected_line
        if td is None or selected is None:
            return
        block_index, axis, boundary_index = selected
        if not 0 <= block_index < len(td.answer_blocks):
            return
        try:
            updated = set_boundary_position(
                td.answer_blocks[block_index],
                axis=axis,  # type: ignore[arg-type]
                index=boundary_index,
                position=self.line_position_spin.value(),
                canonical_width=td.canonical_width,
                canonical_height=td.canonical_height,
                cell_inset=self.inset_spin.value(),
            )
        except ValueError as err:
            QMessageBox.warning(self, "พิกัดไม่ถูกต้อง", str(err))
            return
        blocks = list(td.answer_blocks)
        blocks[block_index] = updated
        self._apply_block_list(blocks, "ปรับตำแหน่งเส้นตารางสำเร็จ")
        boundaries = updated.row_boundaries if axis == "row" else updated.col_boundaries
        self.canvas.line_selected.emit(block_index, axis, boundary_index, boundaries[boundary_index])

    def _edit_grid_line(self, axis: str, add: bool) -> None:
        if add:
            if axis == "row":
                self._on_append_row_clicked()
            else:
                self._on_append_choice_clicked()
        else:
            if axis == "row":
                self._on_remove_row_clicked()
            else:
                self._on_remove_choice_clicked()

    def _on_canvas_grid_area_completed(self, area_rect: tuple[int, int, int, int]) -> None:
        if self.canonical_ref_bgr is None or self.current_template_def is None:
            return
        td = self.current_template_def
        question_start = sum(block.rows for block in td.answer_blocks) + 1
        if question_start > 60:
            QMessageBox.warning(self, "ข้อจำกัด", "จำนวนข้อคำตอบรวมถึง 60 ข้อแล้ว")
            return
        gray = cv2.cvtColor(self.canonical_ref_bgr, cv2.COLOR_BGR2GRAY)
        self._grid_generation += 1
        generation = self._grid_generation
        revision = self._draft_revision
        worker = GridDetectionWorker(
            gray,
            area_rect,
            self.choice_count_spin.value(),
            question_start,
        )
        self._track_worker(worker)
        worker.completed.connect(
            lambda inferred, gen=generation, rev=revision, rect=area_rect: self._handle_grid_detection_finished(
                inferred, gen, rev, rect
            )
        )
        worker.failed.connect(
            lambda message, gen=generation: self._handle_grid_detection_failed(message, gen)
        )
        self.progress_bar.setVisible(True)
        self.summary_lbl.setText("กำลังตรวจหาเส้นตารางในพื้นที่ที่เลือก...")
        worker.start()

    def _nudge(self, dir_x: int, dir_y: int) -> None:
        if self.current_template_def is None:
            return
        step = [1, 5, 10][self.nudge_step_combo.currentIndex()]
        dx = dir_x * step
        dy = dir_y * step
        td = self.current_template_def
        target = self.nudge_target_combo.currentIndex()
        try:
            if target == 0:  # All blocks
                new_blocks = [
                    translate_block(
                        block,
                        dx=dx,
                        dy=dy,
                        canonical_width=td.canonical_width,
                        canonical_height=td.canonical_height,
                        cell_inset=self.inset_spin.value(),
                    )
                    for block in td.answer_blocks
                ]
                self.current_template_def = replace(td, answer_blocks=new_blocks)
            elif target == self.nudge_target_combo.count() - 2:  # Student ROI
                if td.student_number_roi is None:
                    return
                x1, y1, x2, y2 = td.student_number_roi
                roi = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
                if not (0 <= roi[0] < roi[2] <= td.canonical_width and 0 <= roi[1] < roi[3] <= td.canonical_height):
                    raise ValueError("ROI ต้องอยู่ภายในขอบเขตภาพ")
                self.current_template_def = replace(td, student_number_roi=roi)
            elif target == self.nudge_target_combo.count() - 1:  # Score ROI
                if td.score_roi is None:
                    return
                x1, y1, x2, y2 = td.score_roi
                roi = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
                if not (0 <= roi[0] < roi[2] <= td.canonical_width and 0 <= roi[1] < roi[3] <= td.canonical_height):
                    raise ValueError("ROI ต้องอยู่ภายในขอบเขตภาพ")
                self.current_template_def = replace(td, score_roi=roi)
            else:  # Specific block
                b_idx = target - 1
                if not 0 <= b_idx < len(td.answer_blocks):
                    return
                new_blocks = list(td.answer_blocks)
                new_blocks[b_idx] = translate_block(
                    new_blocks[b_idx],
                    dx=dx,
                    dy=dy,
                    canonical_width=td.canonical_width,
                    canonical_height=td.canonical_height,
                    cell_inset=self.inset_spin.value(),
                )
                self.current_template_def = replace(td, answer_blocks=new_blocks)
        except ValueError as err:
            QMessageBox.warning(self, "ย้ายพิกัดไม่ได้", str(err))
            return

        self._mark_geometry_changed()
        self.canvas.set_template_def(self.current_template_def)
        self._update_summary_display("ปรับพิกัดเรียบร้อย", self._geometry_warnings)

    def _add_block(self) -> None:
        td = self.current_template_def
        if td is None:
            return
        choice_count = self.choice_count_spin.value()
        used_questions = sum(block.rows for block in td.answer_blocks)
        remaining = 60 - used_questions
        if remaining <= 0:
            QMessageBox.warning(self, "ข้อจำกัด", "จำนวนข้อคำตอบรวมไม่สามารถเกิน 60 ข้อได้")
            return
        rows = min(10, remaining)
        curr_q = used_questions + 1
        last_b = td.answer_blocks[-1] if td.answer_blocks else None
        step_w = min(60, td.canonical_width // max(1, choice_count))
        step_h = 55
        total_block_w = step_w * choice_count
        minimum = 2 * self.inset_spin.value() + 4
        step_w = max(minimum, step_w)
        total_block_w = step_w * choice_count
        total_block_h = step_h * rows
        candidate_x = [20, td.canonical_width - total_block_w - 20]
        candidate_y = [
            (last_b.row_boundaries[0] if last_b else 600),
            (last_b.row_boundaries[-1] + 20 if last_b else 100),
            td.canonical_height - total_block_h - 20,
        ]
        rect: tuple[int, int] | None = None
        for y0 in candidate_y:
            for x0 in candidate_x:
                if not (0 <= x0 and x0 + total_block_w <= td.canonical_width and 0 <= y0 and y0 + total_block_h <= td.canonical_height):
                    continue
                candidate = AnswerBlock(
                    block_index=len(td.answer_blocks),
                    question_start=curr_q,
                    question_end=curr_q + rows - 1,
                    rows=rows,
                    choice_count=choice_count,
                    col_boundaries=[x0 + i * step_w for i in range(choice_count + 1)],
                    row_boundaries=[y0 + i * step_h for i in range(rows + 1)],
                    geometry_state="draft",
                )
                if not any(_blocks_overlap(candidate, existing) for existing in td.answer_blocks):
                    rect = (x0, y0)
                    break
            if rect is not None:
                break
        if rect is None:
            # A crowded page may not have room for the default ten-row draft.
            # Add the smallest useful one-row draft instead of opening a modal
            # dialog from a programmatic/editor action; the teacher can resize
            # or add rows explicitly.
            rows = 1
            total_block_h = step_h
            for y0 in candidate_y + [20]:
                for x0 in candidate_x:
                    if not (0 <= x0 and x0 + total_block_w <= td.canonical_width and 0 <= y0 and y0 + total_block_h <= td.canonical_height):
                        continue
                    candidate = AnswerBlock(
                        block_index=len(td.answer_blocks),
                        question_start=curr_q,
                        question_end=curr_q,
                        rows=1,
                        choice_count=choice_count,
                        col_boundaries=[x0 + i * step_w for i in range(choice_count + 1)],
                        row_boundaries=[y0, y0 + step_h],
                        geometry_state="draft",
                    )
                    if not any(_blocks_overlap(candidate, existing) for existing in td.answer_blocks):
                        rect = (x0, y0)
                        break
                if rect is not None:
                    break
            if rect is None:
                QMessageBox.warning(self, "เพิ่มชุดไม่ได้", "ไม่พบพื้นที่ว่างเพียงพอสำหรับชุดคำตอบใหม่")
                return
        x0, y0 = rect
        new_b = AnswerBlock(
            block_index=len(td.answer_blocks),
            question_start=curr_q,
            question_end=curr_q + rows - 1,
            rows=rows,
            choice_count=choice_count,
            col_boundaries=[x0 + i * step_w for i in range(choice_count + 1)],
            row_boundaries=[y0 + i * step_h for i in range(rows + 1)],
            geometry_state="draft",
        )
        self._apply_block_list(list(td.answer_blocks) + [new_b], f"เพิ่มชุดคำตอบที่ {len(td.answer_blocks) + 1} เรียบร้อย")

    def _delete_selected_block(self) -> None:
        td = self.current_template_def
        if td is None or not td.answer_blocks:
            return
        idx = self.nudge_target_combo.currentIndex()
        if idx == 0 or idx >= len(td.answer_blocks) + 1:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือกชุดคำตอบที่ต้องการลบจากเมนู 'เป้าหมาย'")
            return

        b_idx = idx - 1
        new_blocks = [b for i, b in enumerate(td.answer_blocks) if i != b_idx]
        self._apply_block_list(new_blocks, f"ลบชุดคำตอบที่ {b_idx + 1} เรียบร้อย")

    def _update_summary_display(self, status_title: str, warnings: list[str]) -> None:
        td = self.current_template_def
        if td is None:
            return

        lines = [f"📋 <b>{status_title}</b>", ""]
        lines.append(f"• จำนวนชุดคำตอบ: {len(td.answer_blocks)} ชุด")
        for i, b in enumerate(td.answer_blocks):
            confidence = "ไม่ระบุ" if b.confidence is None else f"{b.confidence:.2f}"
            lines.append(
                f"   - ชุดที่ {i + 1}: ข้อ {b.question_start}–{b.question_end} "
                f"({b.choice_count} ตัวเลือก · {b.geometry_state} · confidence {confidence})"
            )
        lines.append(f"• จำนวนข้อรวม: {td.question_count} ข้อ")
        lines.append(f"• ตัวเลือกแม่แบบที่เลือก: {self.choice_count_spin.value()} ตัวเลือก")
        if any(block.choice_count != self.choice_count_spin.value() for block in td.answer_blocks):
            lines.append("⚠️ จำนวนตัวเลือกบางชุดยังไม่ตรงกับค่าของแม่แบบ")
        sn_status = "✅ กำหนดแล้ว" if td.student_number_roi else "⚪ ยังไม่กำหนด"
        lines.append(f"• ช่องเลขประจำตัว: {sn_status}")
        sc_status = "✅ กำหนดแล้ว" if td.score_roi else "⚪ ยังไม่กำหนด"
        lines.append(f"• ช่องคะแนนรวม: {sc_status}")

        all_warnings = list(dict.fromkeys([*self._geometry_warnings, *warnings]))
        for i, block in enumerate(td.answer_blocks, start=1):
            if block.geometry_state == "draft":
                all_warnings.append(f"ชุดที่ {i} เป็นตารางร่าง ต้องตรวจเส้นทั้งหมดก่อนบันทึก")
            if block.confidence is not None and block.confidence < 0.85:
                all_warnings.append(f"ชุดที่ {i} มีความเชื่อมั่นต่ำ ({block.confidence:.2f})")
        all_warnings = list(dict.fromkeys(all_warnings))
        if not td.answer_blocks:
            all_warnings.append("ยังไม่มีชุดคำตอบ ตารางยังบันทึกใช้งานไม่ได้")

        if all_warnings:
            lines.append("")
            lines.append("⚠️ <b>ข้อควรตรวจสอบ:</b>")
            for w in all_warnings:
                lines.append(f"• {w}")

        self.summary_lbl.setText("<br>".join(lines))

    def _toggle_overlay(self) -> None:
        self.canvas.set_overlay_visible(self.toggle_overlay_btn.isChecked())

    def _zoom(self, delta: float) -> None:
        new_scale = round(self.canvas.scale_factor + delta, 2)
        self.canvas.set_zoom(new_scale)
        self.zoom_lbl.setText(f"{int(self.canvas.scale_factor * 100)}%")

    def _on_choice_count_changed(self, count: int) -> None:
        td = self.current_template_def
        if td is None or td.choice_count == count:
            return
        canonical_labels = list(CANONICAL_CHOICES[:count])
        display_labels = (
            list(DEFAULT_THAI_LABELS[:count])
            if self.header_style_combo.currentIndex() == 0
            else list(CANONICAL_CHOICES[:count])
        )
        choice_map: dict[str, str] = {}
        for index, label in enumerate(canonical_labels):
            choice_map[label] = label
            choice_map[label.lower()] = label
            choice_map[str(index + 1)] = label
            choice_map[DEFAULT_THAI_LABELS[index]] = label
        self.current_template_def = replace(
            td,
            choice_count=count,
            choice_labels=canonical_labels,
            display_choice_labels=display_labels,
            choice_map=choice_map,
        )
        self._mark_geometry_changed()
        self.canvas.set_template_def(self.current_template_def)
        self._update_summary_display("อัปเดตจำนวนตัวเลือกแม่แบบแล้ว", self._geometry_warnings)

    def _build_current_template_def(self) -> TemplateDefinition:
        """Construct validated TemplateDefinition from current inputs."""
        if self.current_template_def is None:
            raise ValueError("ยังไม่มีข้อมูลโครงสร้างแม่แบบ")

        name = self.name_input.text().strip()
        if not name:
            raise ValueError("กรุณาระบุชื่อแม่แบบ")
        tid = self.id_input.text().strip()
        if not tid:
            raise ValueError("กรุณาระบุรหัสแม่แบบ")

        choice_count = self.choice_count_spin.value()
        canonical_labels = list(CANONICAL_CHOICES[:choice_count])

        if self.header_style_combo.currentIndex() == 0:
            display_labels = list(DEFAULT_THAI_LABELS[:choice_count])
        else:
            display_labels = list(CANONICAL_CHOICES[:choice_count])

        choice_map: dict[str, str] = {}
        for i, c in enumerate(canonical_labels):
            choice_map[c] = c
            choice_map[c.lower()] = c
            choice_map[str(i + 1)] = c
            if i < len(DEFAULT_THAI_LABELS):
                choice_map[DEFAULT_THAI_LABELS[i]] = c

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        inset = self.inset_spin.value()
        orig = self.current_template_def
        if any(block.geometry_state == "draft" for block in orig.answer_blocks):
            raise ValueError("ยังมีชุดตารางร่างอยู่ กรุณาตรวจหรือแก้เส้นทั้งหมดก่อนบันทึก")

        version = (
            self.edit_template.version + 1
            if (self.edit_template is not None and self.edit_template.template_id == tid)
            else 1
        )

        draft = CalibrationDraft.from_template(orig)
        draft = replace(
            draft,
            template_id=tid,
            name=name,
            kind="custom",
            version=version,
            canonical_width=orig.canonical_width,
            canonical_height=orig.canonical_height,
            choice_count=choice_count,
            choice_labels=canonical_labels,
            display_choice_labels=display_labels,
            choice_map=choice_map,
            question_count=self.q_count_spin.value(),
            answer_blocks=orig.answer_blocks,
            student_number_roi=orig.student_number_roi,
            score_roi=orig.score_roi,
            reference_sha256=orig.reference_sha256,
            cell_inset=inset,
            registration_config=orig.registration_config,
            created_at=orig.created_at or now_iso,
            updated_at=now_iso,
        )
        return compile_draft(draft, cell_inset=inset)

    def _test_current_geometry(self) -> None:
        try:
            td = self._build_current_template_def()
        except ValueError as err:
            QMessageBox.warning(self, "ข้อมูลไม่ถูกต้อง", str(err))
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "เลือกภาพกระดาษคำตอบเพื่อทดสอบ",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp)",
        )
        if not file_path:
            return

        try:
            img_bytes = open(file_path, "rb").read()
            res = analyze(
                img_bytes,
                template_def=td,
                reference_override=self.canonical_ref_bgr,
                app_data_dir=self.application.data_dir,
            )
            # Open comprehensive inspection preview
            dlg = CalibrationTestDialog(td, res, parent=self)
            dlg.exec()
        except Exception as err:
            QMessageBox.critical(self, "ทดสอบไม่สำเร็จ", f"เกิดข้อผิดพลาดในการวิเคราะห์ภาพ:\n{err}")

    def _save_template(self) -> None:
        try:
            td = self._build_current_template_def()
        except ValueError as err:
            QMessageBox.warning(self, "ข้อมูลไม่ถูกต้อง", str(err))
            return

        needs_review = bool(self._geometry_warnings) or any(
            block.geometry_state in ("draft", "user_edited")
            or (block.confidence is not None and block.confidence < 0.85)
            for block in td.answer_blocks
        )
        if needs_review:
            review_details = "\n".join(self._geometry_warnings[:5])
            message = "มีข้อมูลตารางที่ต้องตรวจทานก่อนบันทึก\n\nตรวจเส้นและจำนวนช่องบนภาพแล้ว ยืนยันบันทึกแม่แบบนี้หรือไม่?"
            if review_details:
                message += f"\n\n{review_details}"
            answer = QMessageBox.question(
                self,
                "ยืนยันการตรวจทานตาราง",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        if self.canonical_ref_bgr is not None:
            success, enc = cv2.imencode(".png", self.canonical_ref_bgr)
            if not success:
                QMessageBox.critical(self, "บันทึกไม่สำเร็จ", "ไม่สามารถแปลงภาพอ้างอิงเป็น PNG ได้")
                return
            ref_bytes = enc.tobytes()
            sha256 = save_custom_reference_image(self.application.data_dir, ref_bytes)
            from dataclasses import replace

            td = replace(td, reference_sha256=sha256)

        try:
            self.application.exams.save_template(td)
            self.saved_template_id = td.template_id
            from exam_grader.preferences import save_default_template_id

            save_default_template_id(td.template_id)
            QMessageBox.information(
                self,
                "บันทึกสำเร็จ",
                f"บันทึกแม่แบบ '{td.name}' เรียบร้อยแล้ว พร้อมใช้งานในการสร้างข้อสอบ",
            )
            self.accept()
        except Exception as err:
            QMessageBox.critical(self, "บันทึกแม่แบบล้มเหลว", str(err))
