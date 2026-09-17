"""Explicit teacher confirmation with original evidence and editable answers."""

import sqlite3
from typing import cast

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from exam_grader.document_normalization_ui import ManualCropDialog
from exam_grader.geometry_resolution import GeometryResolutionError, geometry_from_detection
from exam_grader.imaging import decode
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.workflow import Workflow


def key_answer_text(answer) -> str:
    if isinstance(answer, str):
        return answer
    if isinstance(answer, (list, tuple)):
        return ",".join(choice for choice in "ABCDE" if choice in answer)
    return ""


THAI_TO_CANONICAL = {"ก": "A", "ข": "B", "ค": "C", "ง": "D", "จ": "E"}


def parse_key_answer(value: str, choice_count: int = 5) -> str | list[str]:
    choices = []
    valid_choices = "ABCDE"[:choice_count]
    for raw in value.replace("/", ",").replace(" ", "").split(","):
        if not raw:
            continue
        char = THAI_TO_CANONICAL.get(raw, raw.upper())
        if char and char not in choices:
            choices.append(char)
    if not choices or any(char not in valid_choices for char in choices):
        thai_part = f" (หรือ ก–{'กขคงจ'[choice_count - 1]})" if choice_count <= 5 else ""
        raise ValueError(f"เฉลยต้องเป็น A–{valid_choices[-1]}{thai_part} หรือหลายตัวเลือกคั่นด้วยจุลภาค")
    return choices[0] if len(choices) == 1 else choices


class FitImage(QWidget):
    """Aspect-preserving image view that never forces a horizontal scroll bar."""

    def __init__(self, pixels: np.ndarray, parent=None):
        super().__init__(parent)
        rgb = cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB)
        self.image = QImage(
            rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888
        ).copy()
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(1, 1)
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.label.setProperty("role", "preview-background")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self):
        if self.width() < 2 or self.height() < 2:
            return
        pixmap = QPixmap.fromImage(self.image).scaled(
            self.label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.label.setPixmap(pixmap)


def image_widget(pixels: np.ndarray) -> QWidget:
    # Keep the original image available in a bounded fit view. A scrollable
    # detail viewer is intentionally secondary to the aligned review surface.
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(FitImage(pixels))
    return scroll


def _normalization_corners(detection: dict | None, image_shape: tuple[int, ...]) -> np.ndarray:
    registration = (detection or {}).get("registration") or {}
    diagnostics = (detection or {}).get("alignment_diagnostics") or {}
    # A detected registration quad may belong to the printed answer grid, while
    # this editor is specifically for the physical page boundary. Prefer the
    # separately tracked boundary; a human-adjusted crop is authoritative.
    for key in ("physical_paper_corners", "paper_corners"):
        corners = registration.get(key)
        if corners is None:
            corners = diagnostics.get(key)
        if corners is not None:
            try:
                points = np.asarray(corners, dtype=np.float32).reshape(4, 2)
                if np.isfinite(points).all():
                    return points
            except (TypeError, ValueError):
                pass
    candidates = registration.get("paper_boundary_candidates") or diagnostics.get(
        "paper_boundary_candidates", []
    )
    if candidates:
        ranked = sorted(
            candidates,
            key=lambda item: (
                float(item.get("physical_boundary_confidence", item.get("geometry_confidence", 0.0))),
                float(item.get("physical_edge_support", 0.0)),
                float(item.get("proposal_score", 0.0)),
            ),
            reverse=True,
        )
        for candidate in ranked:
            corners = candidate.get("corners")
            if corners is not None:
                try:
                    points = np.asarray(corners, dtype=np.float32).reshape(4, 2)
                    if np.isfinite(points).all():
                        return points
                except (TypeError, ValueError):
                    pass
    for key in ("selected_corners",):
        corners = registration.get(key)
        if corners is None:
            corners = diagnostics.get(key)
        if corners is not None:
            try:
                points = np.asarray(corners, dtype=np.float32).reshape(4, 2)
                if np.isfinite(points).all():
                    return points
            except (TypeError, ValueError):
                pass
    height, width = image_shape[:2]
    return np.asarray(
        [[0.0, 0.0], [width - 1.0, 0.0], [width - 1.0, height - 1.0], [0.0, height - 1.0]],
        dtype=np.float32,
    )


def _paper_overlay(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    preview = image.copy()
    points = np.rint(corners).astype(np.int32).reshape(4, 1, 2)
    cv2.polylines(preview, [points], True, (0, 168, 137), max(2, round(min(image.shape[:2]) / 450)))
    radius = max(5, round(min(image.shape[:2]) / 95))
    for index, point in enumerate(points[:, 0, :], 1):
        cv2.circle(preview, tuple(map(int, point)), radius, (0, 168, 137), -1, cv2.LINE_AA)
        cv2.putText(
            preview,
            str(index),
            (int(point[0]) + radius, int(point[1]) - radius),
            cv2.FONT_HERSHEY_SIMPLEX,
            max(0.55, min(image.shape[:2]) / 900),
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return preview


class ReviewDialog(QDialog):
    def __init__(self, database, source: dict, parent=None):
        super().__init__(parent)
        self.database = database
        self.flow = Workflow(database)
        self.source = source
        self.observed_detection = ReviewService(database).state(source)["detection_id"]
        self.key_mode = source["purpose"] == "key"
        self.key = None if self.key_mode else self.flow.current_key(source["exam_id"])
        self.setWindowTitle("ตรวจเฉลย" if self.key_mode else "ตรวจทานคำตอบนักเรียน")
        app_icon = QApplication.windowIcon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        screen = None
        if parent is not None and hasattr(parent, "screen") and parent.screen() is not None:
            screen = parent.screen()
        if screen is None:
            screen = QApplication.primaryScreen()

        if screen is not None:
            avail = screen.availableGeometry()
            w = min(1180, max(680, avail.width() - 32))
            h = min(780, max(460, avail.height() - 48))
            self.setMinimumSize(min(640, avail.width() - 16), min(420, avail.height() - 32))
            self.resize(w, h)
            x = avail.x() + max(0, (avail.width() - w) // 2)
            y = avail.y() + max(0, (avail.height() - h) // 2)
            self.setGeometry(x, y, w, h)
        else:
            self.resize(1080, 720)
            self.setMinimumSize(640, 420)
        self.normalization_updated = False
        layout = QVBoxLayout(self)
        notice = QLabel("แก้ไขข้อมูลได้ทุกข้อ · ระบบส่งเฉพาะข้อมูลที่ยังมีปัญหาไปแท็บตรวจทาน")
        self.notice = notice
        notice.setWordWrap(True)
        notice.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout.addWidget(notice)
        body = QHBoxLayout()
        self.source_bytes = ImportService(database).verified_bytes(source)
        original = decode(self.source_bytes)
        self.original_image = original
        tabs = QTabWidget()
        from exam_grader.template_manager import load_exam_template_def

        self.template_def = load_exam_template_def(database, source["exam_id"])
        detection = self.flow.latest_detection(source["id"])
        self.detection = detection or {}
        try:
            self.geometry_resolution = geometry_from_detection(
                detection,
                self.template_def,
                source_sha256=source.get("sha256"),
            )
        except GeometryResolutionError:
            # A malformed/stale geometry result is review-required and must not
            # be guessed into an aligned preview.
            self.geometry_resolution = None
        resolved_corners = (self.geometry_resolution or {}).get("physical_paper_corners")
        if isinstance(resolved_corners, (list, tuple)) and len(resolved_corners) == 4:
            self.boundary_corners = np.asarray(resolved_corners, dtype=np.float32)
        else:
            self.boundary_corners = _normalization_corners(detection, original.shape)
        registration = (detection or {}).get("registration") or {}
        confidence = float(
            (detection or {}).get("document_normalization", {}).get(
                "normalization_confidence",
                registration.get("normalization_confidence", registration.get("alignment_confidence", 0.0)),
            )
            or 0.0
        )
        self.normalization_status = QLabel()
        if registration and confidence >= 0.82 and not registration.get("normalization_requires_review"):
            self.normalization_status.setText("✓ ตรวจพบกระดาษและจัดแนวแล้ว")
            self.normalization_status.setProperty("role", "success")
        elif registration:
            self.normalization_status.setText("ตรวจพบกรอบเบื้องต้น · โปรดดูภาพก่อนยืนยัน")
            self.normalization_status.setProperty("role", "warning")
        else:
            self.normalization_status.setText("ยังจัดแนวไม่ได้ · ปรับมุมกระดาษด้วยตนเองได้")
            self.normalization_status.setProperty("role", "warning")
        self.normalization_status.setWordWrap(True)
        self.normalization_status.setToolTip(
            "ถ่ายให้เห็นกระดาษครบ 4 มุม วางกล้องเหนือกระดาษ และหลีกเลี่ยงเงาหรือแสงสะท้อน"
        )
        normalization_actions = QHBoxLayout()
        normalization_actions.addWidget(self.normalization_status, stretch=1)
        self.adjust_corners_button = QPushButton("ปรับมุมกระดาษ…")
        self.adjust_corners_button.setToolTip(
            "ใช้เมื่อกรอบอัตโนมัติไม่ตรง: ให้เห็นกระดาษครบ 4 มุม ถ่ายเหนือกระดาษ และหลีกเลี่ยงเงา/แสงสะท้อน"
        )
        self.adjust_corners_button.clicked.connect(self._adjust_document_corners)
        normalization_actions.addWidget(self.adjust_corners_button)
        layout.addLayout(normalization_actions)
        matrix = (
            (self.geometry_resolution or {}).get("transform", {}).get("matrix")
            if self.geometry_resolution
            else None
        )
        if detection and matrix is not None:
            aligned = cv2.warpPerspective(
                original,
                np.asarray(matrix, dtype=np.float64),
                (self.template_def.canonical_width, self.template_def.canonical_height),
                borderValue=(255, 255, 255),
            )
            tabs.addTab(image_widget(aligned), "ภาพจัดแนว (หลัก)")
            tabs.addTab(image_widget(_paper_overlay(original, self.boundary_corners)), "ขอบกระดาษ")
            tabs.addTab(image_widget(original), "ดูต้นฉบับ")
        else:
            tabs.addTab(image_widget(_paper_overlay(original, self.boundary_corners)), "ขอบที่พบ")
            tabs.addTab(image_widget(original), "ต้นฉบับ · จัดแนวไม่ได้")
            reg_fail_msg = (detection or {}).get("failure") or "จัดแนวภาพไม่ได้"
            warning_box = QFrame()
            warning_box.setProperty("role", "warning")
            w_layout = QHBoxLayout(warning_box)
            w_layout.setContentsMargins(10, 6, 10, 6)
            warn_lbl = QLabel(
                f"⚠️ <b>{reg_fail_msg}</b>: ภาพนี้อาจไม่ตรงกับแม่แบบ <b>'{self.template_def.name}'</b> ({self.template_def.choice_count} ตัวเลือก) ของข้อสอบนี้"
            )
            warn_lbl.setWordWrap(True)
            w_layout.addWidget(warn_lbl, stretch=1)
            change_t_btn = QPushButton("เปลี่ยนแม่แบบของข้อสอบ…")
            change_t_btn.clicked.connect(self._change_exam_template_and_reanalyze)
            w_layout.addWidget(change_t_btn)
            layout.addWidget(warning_box)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(tabs)
        controls_widget = QFrame()
        controls = QVBoxLayout(controls_widget)
        controls.setContentsMargins(8, 0, 0, 0)
        self.number = QLineEdit()
        self.number.setPlaceholderText("เลขที่นักเรียน")
        suggested_candidate = None
        if not self.key_mode:
            controls.addWidget(QLabel("เลขที่ (ตรวจจากภาพต้นฉบับ)"))
            controls.addWidget(self.number)
            number_observation = (self.flow.latest_detection(source["id"]) or {}).get(
                "student_number_observation"
            ) or {}
            candidate = number_observation.get("candidate")
            candidates = number_observation.get("candidates") or []
            if candidate and candidates == [candidate]:
                suggested_candidate = candidate
                hint = QLabel(f"ผู้ช่วยอ่านได้: {candidate} · ยังไม่ยืนยัน")
                hint.setProperty("role", "warning")
                controls.addWidget(hint)
            elif candidates:
                hint = QLabel(f"ผู้ช่วยอ่านได้หลายแบบ: {' / '.join(candidates)} · ต้องตรวจทาน")
                hint.setProperty("role", "warning")
                controls.addWidget(hint)
            suggestions = number_observation.get("review_suggestions") or []
            suggested_numbers = [
                str(item["candidate"])
                for item in suggestions
                if isinstance(item, dict) and item.get("candidate")
            ]
            if suggested_numbers:
                hint = QLabel(
                    f"รูปร่างตัวเลขแนะนำให้ตรวจเพิ่ม: {' / '.join(suggested_numbers)} · ยังไม่ใช่ผล OCR ที่ยืนยัน"
                )
                hint.setProperty("role", "warning")
                controls.addWidget(hint)
        self.count = QSpinBox()
        self.count.setRange(1, 60)
        self.count.setValue(
            self.flow.question_count(source["exam_id"])
            if self.key_mode
            else len((self.key or {})["answers"])
        )
        self.count.setEnabled(False)
        controls.addWidget(QLabel("ใช้ข้อ 1 ถึงข้อ"))
        controls.addWidget(self.count)
        self.table = QTableWidget(60, 3)
        self.table.setHorizontalHeaderLabels(["ข้อ", "ระบบอ่านได้", "คำตอบที่ยืนยัน"])
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumWidth(360)
        tabs.setMinimumWidth(280)
        self.combos = []
        self.edited_questions: set[int] = set()
        self.skip_remaining_completed = False
        previous = None if self.key_mode else self.flow.latest_review(source["id"])
        partial = (
            []
            if self.key_mode
            else ReviewService(database).answers(
                ReviewService(database).state(source), self.key or {}
            )
        )
        approved_for_source = None
        if self.key_mode:
            try:
                candidate = self.flow.current_key(source["exam_id"])
                if candidate["source_id"] == source["id"]:
                    approved_for_source = candidate
            except ValueError:
                approved_for_source = None
        if previous:
            self.number.setText(previous["student_number"])
        elif not self.key_mode:
            identity = ReviewService(database).state(source)["number"]
            if identity:
                self.number.setText(identity)
            elif suggested_candidate:
                self.number.setText(suggested_candidate)
        self.initial_number = self.number.text()
        canonical_labels = self.template_def.choice_labels
        display_labels = self.template_def.display_choice_labels

        for index in range(60):
            item = QTableWidgetItem(str(index + 1))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(index, 0, item)
            observations = (detection or {}).get("answers", [])
            observation = observations[index] if index < len(observations) else None
            if observation is None:
                state_text = "ยังไม่มีผลอ่าน"
            else:
                state = observation["classification"]
                if state == "single_mark":
                    state_text = f"อ่านได้ {observation['selected'][0]}"
                elif state == "multiple" and observation.get("selected"):
                    selected = ",".join(observation["selected"])
                    state_text = f"อ่านได้หลายคำตอบ {selected} · ตรวจยืนยัน"
                else:
                    state_text = {
                        "blank": "ว่าง",
                        "multiple": "หลายคำตอบ",
                        "boundary_cross": "คาบเส้นสองช่อง · 0 คะแนน",
                        "uncertain": "ไม่แน่ใจ",
                    }.get(state, state)
            state_item = QTableWidgetItem(state_text)
            state_item.setFlags(state_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(index, 1, state_item)
            selected_value: object = None
            if index < len(partial):
                selected_value = partial[index]
            elif observation is not None:
                state = observation["classification"]
                if state == "single_mark":
                    selected_value = observation["selected"][0]
                elif state == "multiple" and observation.get("selected"):
                    # A clear multi-mark key observation is a candidate, not a
                    # teacher decision. Keep the confirmation checkbox and the
                    # key approval gate unchanged.
                    selected_value = list(observation["selected"]) if self.key_mode else state
                elif state in {"blank", "multiple", "boundary_cross"} and not self.key_mode:
                    selected_value = state
            if approved_for_source and index < len(approved_for_source["answers"]):
                selected_value = approved_for_source["answers"][index]
            editor: QLineEdit | QComboBox
            if self.key_mode:
                editor = QLineEdit(key_answer_text(selected_value))
                editor.setPlaceholderText(
                    f"{canonical_labels[0]} หรือ {canonical_labels[0]},{canonical_labels[1]}"
                )
                labels_str = f"A–{canonical_labels[-1]}"
                thai_str = f" (หรือ ก–{display_labels[-1]})" if display_labels else ""
                editor.setToolTip(f"พิมพ์ {labels_str}{thai_str} หนึ่งตัว หรือหลายตัวคั่นด้วยจุลภาค")
            else:
                editor = QComboBox()
                editor.addItem("— เลือกคำตอบ —", None)
                for d_lbl, c_lbl in zip(display_labels, canonical_labels):
                    combo_text = f"{d_lbl} / {c_lbl}" if d_lbl != c_lbl else c_lbl
                    editor.addItem(combo_text, c_lbl)
                editor.addItem("เว้นว่าง (0 คะแนน)", "blank")
                editor.addItem("หลายคำตอบ (0 คะแนน)", "multiple")
                editor.addItem("คาบเส้นสองช่อง (0 คะแนน)", "boundary_cross")
                editor.setCurrentIndex(max(0, editor.findData(selected_value)))
                editor.currentIndexChanged.connect(
                    lambda _index, question=index + 1: self.edited_questions.add(question)
                )
            self.combos.append(editor)
            self.table.setCellWidget(index, 2, editor)
        self.count.valueChanged.connect(self.update_rows)
        self.update_rows()
        unresolved = []
        for i, editor in enumerate(self.combos[: self.count.value()]):
            value = (
                editor.text()
                if isinstance(editor, QLineEdit)
                else cast(QComboBox, editor).currentData()
            )
            if value is None or (isinstance(value, str) and not value.strip()):
                unresolved.append(i)
        ambiguous_questions = [
            index
            for index, observation in enumerate(
                (detection or {}).get("answers", [])[: self.count.value()]
            )
            if observation.get("classification") in {"multiple", "boundary_cross"}
        ]
        if self.key_mode:
            multi_prefilled = sum(
                1
                for observation in (detection or {}).get("answers", [])[: self.count.value()]
                if observation.get("classification") == "multiple" and observation.get("selected")
            )
            notice.setText(
                f"ตรวจเฉลยก่อนเพิ่มนักเรียน · ต้องเลือกคำตอบข้อ {', '.join(str(i + 1) for i in unresolved)}"
                if unresolved
                else (
                    f"อ่านเฉลยครบ {self.count.value()} ข้อแล้ว"
                    + (f" · เติมหลายคำตอบให้อัตโนมัติ {multi_prefilled} ข้อ" if multi_prefilled else "")
                    + " · ตรวจภาพและยืนยันเพื่อไปนักเรียน"
                )
            )
        from exam_grader.preferences import is_dark_mode

        dark = is_dark_mode(QApplication.instance())
        pending_bg = QColor("#451A03") if dark else QColor("#FEF3C7")
        pending_fg = QColor("#FDE68A") if dark else QColor("#92400E")
        for index in unresolved:
            for column in (0, 1):
                pending_item = self.table.item(index, column)
                if pending_item is not None:
                    pending_item.setBackground(pending_bg)
                    pending_item.setForeground(pending_fg)
        if unresolved:
            first_pending = self.table.item(unresolved[0], 0)
            if first_pending is not None:
                QTimer.singleShot(0, lambda: self.table.scrollToItem(first_pending))
        controls.addWidget(self.table, 1)
        self.confirmed = QCheckBox("ยืนยันข้อมูลและการแก้ไขนี้")
        controls.addWidget(self.confirmed)
        answers_ready = not unresolved and not ambiguous_questions
        identity_ready = self.key_mode or bool(ReviewService(database).state(source)["number"])
        if answers_ready and identity_ready:
            self.confirmed.setChecked(True)
            if self.key_mode:
                notice.setText(
                    f"ระบบอ่านเฉลยครบ {self.count.value()} ข้อแล้ว · พร้อมบันทึกการยืนยัน"
                )
            else:
                notice.setText(
                    f"ระบบอ่านคำตอบครบ {self.count.value()} ข้อแล้ว · เลขที่ยืนยันแล้ว · พร้อมบันทึก"
                )
        elif answers_ready and not self.key_mode:
            notice.setText(
                f"ระบบอ่านคำตอบครบ {self.count.value()} ข้อแล้ว · กรุณายืนยันเลขที่ก่อนบันทึก"
            )
        splitter.addWidget(controls_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        controls_w = min(420, max(360, int(self.width() * 0.35)))
        image_w = max(280, self.width() - controls_w - 30)
        splitter.setSizes([image_w, controls_w])
        body.addWidget(splitter)
        layout.addLayout(body, 1)
        buttons = QDialogButtonBox()
        if not self.key_mode:
            delete_btn = QPushButton("ลบกระดาษนี้…")
            delete_btn.setProperty("destructive", True)
            delete_btn.clicked.connect(self._archive_this_sheet)
            buttons.addButton(delete_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(
            "ยืนยันเฉลย" if self.key_mode else "บันทึกการตรวจทาน",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        if not self.key_mode:
            self.skip_remaining_button = buttons.addButton(
                "ข้ามรายการที่เหลือ → ไปผลลัพธ์",
                QDialogButtonBox.ButtonRole.ActionRole,
            )
            self.skip_remaining_button.clicked.connect(self._skip_remaining)
        buttons.addButton("ยกเลิก", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _adjust_document_corners(self) -> None:
        crop_dialog = ManualCropDialog(
            self.original_image,
            self.boundary_corners,
            target_size=(
                self.template_def.canonical_width,
                self.template_def.canonical_height,
            ),
            parent=self,
        )
        if crop_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        corners = crop_dialog.accepted_corners()
        if corners is None:
            return

        from exam_grader.identity import observe as observe_student_number
        from exam_grader.imaging import RegistrationError, analyze

        self.adjust_corners_button.setEnabled(False)
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            observation = analyze(
                self.source_bytes,
                template_def=self.template_def,
                app_data_dir=getattr(self.database, "parent", None),
                decoded_image=self.original_image,
                manual_corners=corners,
            )
            if not self.key_mode:
                try:
                    observation["student_number_observation"] = observe_student_number(
                        self.source_bytes,
                        observation.get("registration", {}).get("matrix"),
                        template_def=self.template_def,
                        app_data_dir=getattr(self.database, "parent", None),
                        image=self.original_image,
                    )
                except (ValueError, OSError, cv2.error):
                    observation["student_number_observation"] = {
                        "candidate": None,
                        "confidence": None,
                        "review_reason": "เลขที่ยังต้องตรวจด้วยคน",
                    }
        except (RegistrationError, ValueError, OSError, cv2.error) as error:
            diagnostics = getattr(error, "diagnostics", {}) or {}
            stage = diagnostics.get("stage")
            stage_text = f"\\nขั้นที่ล้มเหลว: {stage}" if stage else ""
            QMessageBox.warning(
                self,
                "จัดแนวจากกรอบนี้ไม่ได้",
                f"{error}{stage_text}\\nลองปรับมุมใหม่ หรือยกเลิกแล้วถ่ายกระดาษให้เห็นครบทั้ง 4 มุม",
            )
            self.boundary_corners = corners
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.adjust_corners_button.setEnabled(True)

        self.flow.save_detection(self.source["id"], observation)
        self.normalization_updated = True
        self.reject()

    def _skip_remaining(self) -> None:
        if not self.confirmed.isChecked():
            QMessageBox.warning(self, "ยังไม่ยืนยัน", "โปรดยืนยันข้อมูลก่อนข้ามรายการที่เหลือ")
            return
        answer_edits: dict[str, dict[int, str]] = {}
        for question in self.edited_questions:
            value = cast(QComboBox, self.combos[question - 1]).currentData()
            if isinstance(value, str):
                answer_edits.setdefault(self.source["id"], {})[question] = value
        identity_edits = {}
        current_number = self.number.text().strip()
        if current_number and current_number != getattr(self, "initial_number", current_number):
            try:
                from exam_grader.review_service import normalize_number

                identity_edits[self.source["id"]] = normalize_number(current_number)
            except ValueError as error:
                QMessageBox.warning(self, "เลขที่ไม่ถูกต้อง", str(error))
                return

        service = ReviewService(self.flow.database)
        try:
            summary = service.skip_summary(
                self.source["exam_id"],
                answer_edits=answer_edits,
                identity_edits=identity_edits,
            )
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "ข้ามรายการไม่ได้", str(error))
            return
        message = (
            f"เลขที่ยังไม่ยืนยัน: {summary['unconfirmed_identities']}\n"
            f"คำตอบ/ข้อที่ยังไม่ชัด: {summary['unclear_answers']}\n"
            f"กระดาษที่ยังมีรายการค้าง: {summary['unresolved_sheets']}\n\n"
            "ระบบจะไม่เดาคำตอบที่ยังไม่ชัดและจะคิดเป็น 0 คะแนนในผลลัพธ์บางส่วน"
        )
        answer = QMessageBox.question(
            self,
            "ข้ามรายการตรวจทานที่เหลือ",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            service.skip_remaining(
                self.source["exam_id"],
                answer_edits=answer_edits,
                identity_edits=identity_edits,
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "ข้ามรายการไม่ได้", str(error))
            return
        self.skip_remaining_completed = True
        super().accept()

    def _archive_this_sheet(self):
        answer = QMessageBox.question(
            self,
            "ลบกระดาษนี้",
            f"ต้องการลบกระดาษ {self.source['original_name']} ออกจากชุดตรวจหรือไม่?\n"
            "ข้อมูลจะถูกนำออกจากรายการตรวจและผลลัพธ์ (สามารถกู้คืนได้ด้วยการนำเข้าไฟล์เดิมใหม่)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            ImportService(self.flow.database).archive_source(self.source["id"])
            self.reject()
        except Exception as error:
            QMessageBox.warning(self, "ลบกระดาษไม่ได้", str(error))

    def update_rows(self):
        for index in range(60):
            self.table.setRowHidden(index, index >= self.count.value())

    def accept(self):
        if not self.confirmed.isChecked():
            QMessageBox.warning(self, "ยังไม่ยืนยัน", "โปรดตรวจภาพและยืนยันว่าตรวจครบแล้ว")
            return
        try:
            if (
                ReviewService(self.flow.database).state(self.source)["detection_id"]
                != self.observed_detection
            ):
                raise ValueError("ผลอ่านเปลี่ยนแล้ว กรุณาเปิดตรวจใหม่")
            if self.key_mode:
                choice_count = self.template_def.choice_count if self.template_def else 5
                key_answers: list[object] = [
                    parse_key_answer(cast(QLineEdit, editor).text(), choice_count=choice_count)
                    for editor in self.combos[: self.count.value()]
                ]
            else:
                student_answers: list[str] = [
                    cast(str, cast(QComboBox, editor).currentData())
                    for editor in self.combos[: self.count.value()]
                ]
            answers_for_validation = key_answers if self.key_mode else student_answers
            missing = next(
                (
                    index + 1
                    for index, answer in enumerate(answers_for_validation)
                    if answer is None
                ),
                None,
            )
            if missing is not None:
                raise ValueError(f"กรุณาเลือกคำตอบข้อ {missing} ให้ครบก่อนบันทึก")
            if self.key_mode:
                self.flow.approve_key(
                    self.source["exam_id"],
                    key_answers,
                    self.source["id"],
                    detection_id=self.observed_detection,
                )
            else:
                self.flow.review(
                    self.source["id"],
                    self.number.text(),
                    student_answers,
                    (self.key or {})["id"],
                    detection_id=self.observed_detection,
                )
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "บันทึกไม่ได้", str(error))
            return
        super().accept()

    def _change_exam_template_and_reanalyze(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        from exam_grader.imaging import analyze, decode
        from exam_grader.imports import ImportService
        from exam_grader.storage import ExamStore
        from exam_grader.template_manager import BUILTIN_TEMPLATE_IDS, load_builtin_template

        store = ExamStore(self.database)
        available = []
        for b_id in BUILTIN_TEMPLATE_IDS:
            try:
                available.append(load_builtin_template(b_id))
            except Exception:
                pass
        try:
            for t in store.list_templates():
                if t.template_id not in BUILTIN_TEMPLATE_IDS:
                    available.append(t)
        except Exception:
            pass

        items = [
            f"{t.name} ({t.choice_count} ตัวเลือก · {len(t.answer_blocks)} ชุด) [ID: {t.template_id}]"
            for t in available
        ]
        current_idx = 0
        for i, t in enumerate(available):
            if t.template_id == self.template_def.template_id:
                current_idx = i
                break

        chosen_item, ok = QInputDialog.getItem(
            self,
            "เปลี่ยนแม่แบบของข้อสอบ",
            f"ข้อสอบนี้กำลังใช้: {self.template_def.name}\nเลือกแม่แบบใหม่ที่ต้องการให้ข้อสอบนี้ใช้:",
            items,
            current_idx,
            False,
        )
        if not ok or not chosen_item:
            return

        chosen_t = available[items.index(chosen_item)]
        if chosen_t.template_id == self.template_def.template_id:
            return

        store.update_exam_template(
            self.source["exam_id"], chosen_t.template_id, chosen_t.version, chosen_t.question_count
        )
        self.template_def = chosen_t

        importer = ImportService(self.database)
        data = importer.verified_bytes(self.source)
        try:
            decoded = decode(data)
            obs = analyze(
                data,
                template_def=self.template_def,
                app_data_dir=self.database.parent if hasattr(self.database, "parent") else None,
                decoded_image=decoded,
            )
            self.flow.save_detection(self.source["id"], obs)
            QMessageBox.information(
                self,
                "จัดแนวภาพสำเร็จ",
                f"เปลี่ยนแม่แบบเป็น '{chosen_t.name}' และตรวจคำตอบสำเร็จเรียบร้อยแล้ว\nระบบจะปิดหน้านี้เพื่อแสดงผลการตรวจใหม่",
            )
            self.accept()
        except Exception as e:
            QMessageBox.warning(
                self,
                "ผลการตรวจตามแม่แบบใหม่",
                f"เปลี่ยนแม่แบบเป็น '{chosen_t.name}' แล้ว แต่การจัดแนวภาพยังไม่สำเร็จ: {e}",
            )
            self.accept()
