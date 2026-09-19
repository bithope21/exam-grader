"""Teacher workflow, background processing, review queue, and result export."""

from datetime import datetime
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from exam_grader.exporting import export_results
from exam_grader.geometry_resolution import geometry_from_detection
from exam_grader.identity import observe as observe_student_number
from exam_grader.imaging import OMR_PIPELINE_VERSION, RegistrationError, analyze, decode
from exam_grader.imports import ImportService
from exam_grader.preferences import default_output_root
from exam_grader.review_service import ReviewService
from exam_grader.review_ui import ReviewDialog
from exam_grader.template_manager import load_exam_template_def
from exam_grader.workflow import Workflow, validate_assessment_indicators

PHOTO_GUIDANCE_TEXT = (
    "ถ่ายให้ตรวจได้แม่นขึ้น\n"
    "• ให้เห็นกระดาษครบ 4 มุม\n"
    "• ถ่ายเหนือกระดาษให้ตรงที่สุด\n"
    "• อย่าตัดขอบ/ตารางคำตอบ\n"
    "• หลีกเลี่ยงเงาและแสงสะท้อนแรง\n"
    "• ให้ตัวหนังสือและรอยกากบาทเห็นชัด"
)


class CheckBoxDelegate(QStyledItemDelegate):
    """Delegate for multi-select checkbox column with centered rendering and wide hit area."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()

        # 1. Draw standard background (respects hover, alternate row color, and selection)
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget)

        # 2. Draw centered check indicator
        if opt.features & QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator:
            chk_opt = QStyleOptionViewItem(opt)
            base_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, widget)
            w = base_rect.width() if base_rect.isValid() and base_rect.width() > 0 else 18
            h = base_rect.height() if base_rect.isValid() and base_rect.height() > 0 else 18
            x = opt.rect.x() + (opt.rect.width() - w) // 2
            y = opt.rect.y() + (opt.rect.height() - h) // 2
            chk_opt.rect = QRect(x, y, w, h)
            chk_opt.state = opt.state
            if opt.checkState == Qt.CheckState.Checked:
                chk_opt.state |= QStyle.StateFlag.State_On
                chk_opt.state &= ~QStyle.StateFlag.State_Off
            else:
                chk_opt.state |= QStyle.StateFlag.State_Off
                chk_opt.state &= ~QStyle.StateFlag.State_On
            style.drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck, chk_opt, painter, widget)

    def editorEvent(self, event: QEvent, model, option: QStyleOptionViewItem, index) -> bool:
        flags = index.flags()
        if not (flags & Qt.ItemFlag.ItemIsUserCheckable) or not (flags & Qt.ItemFlag.ItemIsEnabled):
            return super().editorEvent(event, model, option, index)

        # Left-click press: consume to prevent rubber-band / drag selection artifacts
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                return True
            return False

        # Left-click release: toggle check-state if within cell bounds
        if event.type() == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint()
                if option.rect.contains(pos):
                    curr = index.data(Qt.ItemDataRole.CheckStateRole)
                    is_checked = (
                        curr == Qt.CheckState.Checked
                        or curr == Qt.CheckState.Checked.value
                        or curr == 2
                    )
                    new_state = (
                        Qt.CheckState.Unchecked
                        if is_checked
                        else Qt.CheckState.Checked
                    )
                    model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                    return True
            return False

        # Space key: toggle check-state while preserving standard Qt keyboard navigation
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Space:
                curr = index.data(Qt.ItemDataRole.CheckStateRole)
                is_checked = (
                    curr == Qt.CheckState.Checked
                    or curr == Qt.CheckState.Checked.value
                    or curr == 2
                )
                new_state = (
                    Qt.CheckState.Unchecked
                    if is_checked
                    else Qt.CheckState.Checked
                )
                model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                return True

        return super().editorEvent(event, model, option, index)


class BatchWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(list)

    def __init__(self, database, exam_id, paths, purpose, room_id=None, parent=None):
        super().__init__(parent)
        self.database, self.exam_id, self.paths, self.purpose, self.room_id = (
            database,
            exam_id,
            paths,
            purpose,
            room_id,
        )

    def run(self):
        failures = []
        importer = ImportService(self.database)
        flow = Workflow(self.database)
        if self.purpose == "student":
            try:
                flow.confirmed_key(self.exam_id)
            except ValueError as error:
                self.completed.emit([str(error)])
                return
        from exam_grader.template_manager import load_exam_template_def

        template_def = load_exam_template_def(self.database, self.exam_id)

        for index, path in enumerate(self.paths):
            if self.isInterruptionRequested():
                break
            try:
                source = importer.import_file(
                    self.exam_id, path, self.purpose, room_id=self.room_id
                )
                existing = flow.latest_detection(source["id"])
                if (
                    existing is None
                    or existing.get("pipeline_version") != OMR_PIPELINE_VERSION
                    or existing.get("alignment_needs_review")
                ):
                    source_bytes = importer.verified_bytes(source)
                    decoded = decode(source_bytes)
                    try:
                        observation = analyze(
                            source_bytes,
                            template_def=template_def,
                            app_data_dir=getattr(self.database, "parent", None),
                            decoded_image=decoded,
                        )
                    except RegistrationError as error:
                        observation = {
                            "requires_review": True,
                            "failure": str(error),
                            "pipeline_version": OMR_PIPELINE_VERSION,
                            "alignment_needs_review": True,
                            "alignment_diagnostics": getattr(error, "diagnostics", {}),
                        }
                    except ValueError as error:
                        observation = {
                            "requires_review": True,
                            "failure": str(error),
                            "pipeline_version": "draft-omr-v2",
                        }
                    if self.purpose == "student" and "failure" not in observation:
                        try:
                            observation["student_number_observation"] = observe_student_number(
                                source_bytes,
                                observation.get("registration", {}).get("matrix"),
                                template_def=template_def,
                                app_data_dir=getattr(self.database, "parent", None),
                                image=decoded,
                            )
                        except (ValueError, OSError):
                            observation["student_number_observation"] = {
                                "candidate": None,
                                "confidence": None,
                                "review_reason": "student-number observation unavailable",
                            }
                    flow.save_detection(source["id"], observation)
                importer.clear_failure(self.exam_id, path, self.purpose, room_id=self.room_id)
            except Exception as error:
                importer.record_failure(
                    self.exam_id, path, self.purpose, str(error), room_id=self.room_id
                )
                failures.append(f"{path.name}: {error}")
            self.progress.emit(index + 1, len(self.paths), path.name)
        try:
            service = ReviewService(self.database, room_id=self.room_id)
            service.finalize(self.exam_id)
        except Exception as error:
            failures.append(f"ประมวลผลอัตโนมัติไม่สำเร็จ: {error}")
        self.completed.emit(failures)


class ExportWorker(QThread):
    completed = Signal(str, str)

    def __init__(self, database, exam_id, output_root, room_id=None, parent=None):
        super().__init__(parent)
        self.database, self.exam_id, self.output_root, self.room_id = (
            database,
            exam_id,
            output_root,
            room_id,
        )

    def run(self):
        try:
            path = export_results(
                Workflow(self.database),
                self.exam_id,
                output_root=self.output_root,
                room_id=self.room_id,
            )
            self.completed.emit(str(path), "")
        except Exception as error:
            self.completed.emit("", str(error))


class AssessmentIndicatorsDialog(QDialog):
    def __init__(self, database, exam_id: str, question_count: int, parent=None):
        super().__init__(parent)
        self.database = database
        self.exam_id = exam_id
        self.question_count = question_count
        self.setWindowTitle("ระบุตัวชี้วัด")
        self.setMinimumWidth(720)

        layout = QVBoxLayout(self)
        self.notice = QLabel(
            f"กำหนดคะแนนรายตัวชี้วัดจากช่วงข้อสอบ {question_count} ข้อ · ช่วงข้อเป็นแบบรวมต้นและปลาย"
        )
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(8)
        layout.addLayout(self.rows_layout)
        self.add_button = QPushButton("+ เพิ่มตัวชี้วัด")
        self.add_button.clicked.connect(self._add_row)
        layout.addWidget(self.add_button)
        buttons = QDialogButtonBox()
        buttons.addButton("บันทึก", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("ยกเลิก", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.rows: list[tuple[QWidget, QLineEdit, QSpinBox, QSpinBox]] = []
        existing = Workflow(database).list_assessment_indicators(exam_id)
        try:
            validate_assessment_indicators(existing, question_count)
        except ValueError as error:
            self.notice.setText(f"ต้องแก้ไขตัวชี้วัดก่อนออกผล: {error}")
            self.notice.setProperty("role", "warning")
        for item in existing:
            self._add_row(item)

    def _add_row(self, item: dict | None = None) -> None:
        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        identifier = QLineEdit(str((item or {}).get("identifier", "")))
        identifier.setPlaceholderText("เช่น 2.1, การอ่าน, ว 2.1")
        identifier.setMaxLength(120)
        from_question = QSpinBox()
        to_question = QSpinBox()
        for control, key in ((from_question, "from_question"), (to_question, "to_question")):
            control.setRange(1, 9999)
            control.setValue(int((item or {}).get(key, 1)))
            control.setToolTip(f"ต้องอยู่ในช่วง 1 ถึง {self.question_count}")
        remove = QPushButton("ลบ")
        remove.setProperty("destructive", True)
        row.addWidget(QLabel("ตัวชี้วัด"))
        row.addWidget(identifier, 2)
        row.addWidget(QLabel("ข้อ"))
        row.addWidget(from_question)
        row.addWidget(QLabel("ถึง"))
        row.addWidget(to_question)
        row.addWidget(remove)
        self.rows_layout.addWidget(container)
        record = (container, identifier, from_question, to_question)
        self.rows.append(record)
        remove.clicked.connect(lambda: self._remove_row(record))

    def _remove_row(self, record) -> None:
        if record not in self.rows:
            return
        self.rows.remove(record)
        record[0].setParent(None)
        record[0].deleteLater()

    def accept(self) -> None:
        values = [
            {
                "identifier": identifier.text(),
                "from_question": from_question.value(),
                "to_question": to_question.value(),
            }
            for _container, identifier, from_question, to_question in self.rows
        ]
        try:
            Workflow(self.database).save_assessment_indicators(self.exam_id, values)
        except ValueError as error:
            QMessageBox.warning(self, "บันทึกตัวชี้วัดไม่ได้", str(error))
            return
        super().accept()


class ExamDialog(QDialog):
    def __init__(self, application, exam, parent=None):
        super().__init__(parent)
        self.application, self.exam = application, exam
        self.flow = Workflow(application.exams.path)
        self.importer = ImportService(application.exams.path)
        self.rooms = application.exams.list_rooms(exam.id)
        if not self.rooms:
            raise ValueError("ข้อสอบยังไม่มีห้องเรียน")
        self.room_id = self.rooms[0].id
        self.room_label = self.rooms[0].label
        self.review_service = ReviewService(application.exams.path, room_id=self.room_id)
        self.worker = None
        self.output_root = application.exams.output_root(exam.id) or default_output_root()
        self.template_def = load_exam_template_def(application.exams.path, exam.id)
        self.student_sort_desc = False
        self.setWindowTitle(f"{exam.details.name} · Exam Grader")
        self.resize(1100, 760)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        room_actions = QHBoxLayout()
        room_actions.addWidget(QLabel("ห้อง"))
        self.room_combo = QComboBox()
        for room in self.rooms:
            self.room_combo.addItem(room.label, room.id)
        self.room_combo.currentIndexChanged.connect(self._on_room_changed)
        room_actions.addWidget(self.room_combo, 1)
        self.add_room_button = QPushButton("เพิ่มห้อง…")
        self.add_room_button.clicked.connect(self._add_room)
        room_actions.addWidget(self.add_room_button)
        layout.addLayout(room_actions)

        self.tabs = QTabWidget()
        self.key_list = QListWidget()
        self.key_list.itemDoubleClicked.connect(lambda _: self.review_key())
        self.student_list = QListWidget()
        self.student_list.itemDoubleClicked.connect(lambda _: self.review_student())
        self.review_list = QListWidget()
        self.review_list.itemDoubleClicked.connect(lambda _: self.review_selected())
        self.sources = self.student_list

        key_page = QVBoxLayout()
        key_actions = QHBoxLayout()
        self.key_button = QPushButton("เพิ่ม/เปลี่ยนเฉลย")
        self.key_button.clicked.connect(self.pick_key)
        key_actions.addWidget(self.key_button)
        self.confirm_key_button = QPushButton("ตรวจและยืนยันเฉลย → นักเรียน")
        self.confirm_key_button.clicked.connect(self.review_key)
        key_actions.addWidget(self.confirm_key_button)

        key_actions.addSpacing(12)
        self.template_badge = QLabel()
        self._update_template_badge()
        key_actions.addWidget(self.template_badge)

        self.change_template_btn = QPushButton("เปลี่ยนแม่แบบข้อสอบ…")
        self.change_template_btn.clicked.connect(self._change_exam_template)
        key_actions.addWidget(self.change_template_btn)

        self.indicator_button = QPushButton("ระบุตัวชี้วัด")
        self.indicator_button.clicked.connect(self._open_indicators)
        key_actions.addWidget(self.indicator_button)

        key_actions.addStretch()
        key_page.addLayout(key_actions)
        key_page.addWidget(self.key_list)

        student_page = QVBoxLayout()
        student_actions = QHBoxLayout()
        self.student_button = QPushButton("เพิ่มกระดาษคำตอบ")
        student_menu = QMenu(self.student_button)
        student_menu.addAction("เลือกไฟล์…", self.pick_student_files)
        student_menu.addAction("เลือกโฟลเดอร์…", self.pick_folder)
        self.student_button.setMenu(student_menu)
        student_actions.addWidget(self.student_button)
        self.photo_guidance_button = QToolButton()
        self.photo_guidance_button.setText("ⓘ")
        self.photo_guidance_button.setProperty("kind", "icon")
        self.photo_guidance_button.setFixedSize(36, 36)
        self.photo_guidance_button.setAccessibleName("คำแนะนำการถ่ายภาพ")
        self.photo_guidance_button.setToolTip(PHOTO_GUIDANCE_TEXT)
        self.photo_guidance_button.setAutoRaise(True)
        self.photo_guidance_button.clicked.connect(self._show_photo_guidance)
        student_actions.addWidget(self.photo_guidance_button)
        self.delete_student_button = QPushButton("ลบกระดาษที่เลือก…")
        self.delete_student_button.clicked.connect(self.archive_selected_student)
        student_actions.addWidget(self.delete_student_button)
        self.delete_all_students_button = QPushButton("ลบกระดาษนักเรียนทั้งหมด…")
        self.delete_all_students_button.clicked.connect(self.archive_all_students)
        student_actions.addWidget(self.delete_all_students_button)
        self.student_sort = QComboBox()
        self.student_sort.addItems(["เลขที่น้อย → มาก", "เลขที่มาก → น้อย"])
        self.student_sort.currentIndexChanged.connect(self.change_student_sort)
        student_actions.addWidget(self.student_sort)
        self.adopt_button = QPushButton("ใช้เลขที่ที่แนะนำทั้งหมด")
        self.adopt_button.clicked.connect(self.adopt_numbers)
        student_actions.addWidget(self.adopt_button)
        student_actions.addStretch()
        student_page.addLayout(student_actions)
        student_page.addWidget(self.student_list)
        self.attendance_restore = QComboBox()
        self.attendance_restore.addItem("แก้สถานะขาดสอบที่บันทึกแล้ว…", None)
        self.attendance_restore.activated.connect(self.restore_attendance)
        student_page.addWidget(self.attendance_restore)

        review_page = QVBoxLayout()
        review_actions = QHBoxLayout()
        self.review_button = QPushButton("ตรวจทานที่เลือก")
        self.review_button.clicked.connect(self.review_selected)
        self.retry_button = QPushButton("ตรวจใหม่")
        self.retry_button.clicked.connect(self.retry_selected)
        self.save_all_button = QPushButton("บันทึกที่แก้แล้วทั้งหมด")
        self.save_all_button.clicked.connect(self.save_all_issues)
        review_actions.addWidget(self.review_button)
        review_actions.addWidget(self.retry_button)
        review_actions.addWidget(self.save_all_button)
        review_actions.addStretch()
        review_page.addWidget(QLabel("แก้เฉพาะข้อมูลที่มีปัญหา แล้วกดบันทึกที่แถวนั้น หรือเลือกหลายแถวแล้วบันทึกพร้อมกัน · เรียงเลขที่น้อย → มาก"))
        
        # Bulk Actions Toolbar
        self.bulk_bar_widget = QWidget()
        bulk_bar = QHBoxLayout(self.bulk_bar_widget)
        bulk_bar.setContentsMargins(0, 4, 0, 4)
        self.select_all_btn = QPushButton("เลือกทั้งหมด")
        self.select_all_btn.clicked.connect(self.select_all_issues)
        self.clear_selection_btn = QPushButton("ล้างการเลือก")
        self.clear_selection_btn.clicked.connect(self.clear_issue_selection)
        self.selection_label = QLabel("เลือก 0 รายการ")
        self.selection_label.setProperty("role", "muted")

        self.bulk_confirm_btn = QPushButton("ยืนยันข้อมูลที่ระบบอ่านไว้")
        self.bulk_confirm_btn.setToolTip(
            "ยืนยันค่า prefill ของแต่ละแถวที่เลือก โดยไม่บังคับใช้คำตอบเดียวกับทุกแถว"
        )
        self.bulk_confirm_btn.setEnabled(False)
        self.bulk_confirm_btn.clicked.connect(self.confirm_bulk_prefilled)

        self.bulk_combo = QComboBox()
        self.bulk_combo.setMinimumWidth(220)
        self.bulk_combo.addItem("— กำหนดคำตอบ / สถานะให้แถวที่เลือก —", None)
        for thai, latin in zip("กขคงจ", "ABCDE"):
            self.bulk_combo.addItem(f"{thai} / {latin}", latin)
        self.bulk_combo.addItem("เว้นว่าง (blank)", "blank")
        self.bulk_combo.addItem("หลายคำตอบ (multiple)", "multiple")
        self.bulk_combo.addItem("ข้ามเลขที่นี้ (skipped)", "skipped")
        self.bulk_combo.addItem("ขาดสอบ (absent)", "absent")
        self.bulk_combo.addItem("ลา / ได้รับยกเว้น (excused)", "excused")
        self.bulk_combo.currentIndexChanged.connect(lambda _: self._update_bulk_selection_state())

        self.bulk_apply_btn = QPushButton("นำไปใช้และบันทึกที่เลือก")
        self.bulk_apply_btn.setProperty("accent", True)
        self.bulk_apply_btn.setEnabled(False)
        self.bulk_apply_btn.clicked.connect(self.apply_bulk_edit)

        bulk_bar.addWidget(self.select_all_btn)
        bulk_bar.addWidget(self.clear_selection_btn)
        bulk_bar.addWidget(self.selection_label)
        bulk_bar.addSpacing(12)
        bulk_bar.addWidget(self.bulk_confirm_btn)
        bulk_bar.addWidget(self.bulk_combo)
        bulk_bar.addWidget(self.bulk_apply_btn)
        bulk_bar.addStretch()
        review_page.addWidget(self.bulk_bar_widget)

        self.issue_table = QTableWidget(0, 6)
        self.issue_table.setHorizontalHeaderLabels(
            ["เลือก", "เลขที่", "ข้อมูลที่ต้องแก้", "ภาพ", "คำตอบ / สถานะ", "บันทึก"]
        )
        self.issue_table.verticalHeader().hide()
        self.issue_table.setAlternatingRowColors(True)
        self.issue_table.setItemDelegateForColumn(0, CheckBoxDelegate(self.issue_table))
        header = self.issue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.issue_table.setColumnWidth(0, 52)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.issue_table.cellDoubleClicked.connect(self.open_issue_source)
        self.issue_table.itemChanged.connect(self._on_issue_item_changed)
        review_page.addWidget(self.issue_table)
        self.empty_review = QLabel("ไม่มีข้อมูลที่ต้องแก้ไข · พร้อมออกผลตรวจ")
        review_page.addWidget(self.empty_review)
        self.skip_missing_button = QPushButton("ข้ามเลขที่ที่ยังไม่ส่งทั้งหมด")
        self.skip_missing_button.clicked.connect(self.skip_missing)
        review_page.addWidget(self.skip_missing_button)

        results_page = QVBoxLayout()
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        results_page.addWidget(self.output_label)
        output_actions = QHBoxLayout()
        self.output_button = QPushButton("เปลี่ยนตำแหน่งบันทึก…")
        self.output_button.clicked.connect(self.choose_output_root)
        self.color_button = QPushButton("สีรอยตรวจ…")
        self.color_button.setToolTip("ตั้งค่าสีรอยตรวจ (ถูก/ผิด/คาบเส้น/คะแนน) สำหรับไฟล์ภาพผลตรวจ")
        self.color_button.clicked.connect(self.open_color_settings)
        self.export_button = QPushButton("บันทึกผลตรวจ + Excel")
        self.export_button.setMinimumWidth(190)
        self.export_button.setToolTip("สร้าง snapshot ใหม่ของผลตรวจ ภาพตรวจแล้ว และไฟล์ Excel")
        self.export_button.clicked.connect(self.export)
        output_actions.addWidget(self.output_button)
        output_actions.addWidget(self.color_button)
        output_actions.addWidget(self.export_button)
        output_actions.addStretch()
        results_page.addLayout(output_actions)
        history_actions = QHBoxLayout()
        self.export_history = QComboBox()
        self.export_history.setMinimumContentsLength(24)
        self.export_history.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.export_history.setPlaceholderText("ยังไม่มีผลตรวจที่บันทึก")
        self.reveal_button = QPushButton("เปิดโฟลเดอร์ผลลัพธ์")
        self.reveal_button.clicked.connect(self.reveal_result)
        history_actions.addWidget(self.export_history, 1)
        history_actions.addWidget(self.reveal_button)
        results_page.addLayout(history_actions)
        self.results_summary = QLabel()
        self.results_summary.setWordWrap(True)
        results_page.addWidget(self.results_summary)
        results_page.addStretch()

        for label, page in (
            ("เฉลย", key_page),
            ("นักเรียน", student_page),
            ("ตรวจทาน", review_page),
            ("ผลลัพธ์", results_page),
        ):
            widget = QWidget()
            widget.setLayout(page)
            self.tabs.addTab(widget, label)
        layout.addWidget(self.tabs)

        self.progress_label = QLabel()
        layout.addWidget(self.progress_label)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.cancel = QPushButton("หยุดหลังภาพปัจจุบัน")
        self.cancel.clicked.connect(self.cancel_batch)
        self.cancel.setEnabled(False)
        layout.addWidget(self.cancel)
        self.action_buttons = [
            self.key_button,
            self.student_button,
            self.review_button,
            self.retry_button,
            self.save_all_button,
            self.output_button,
            self.export_button,
            self.adopt_button,
            self.delete_student_button,
            self.delete_all_students_button,
            self.indicator_button,
            self.add_room_button,
        ]
        self.issue_drafts = {}
        self.issue_dirty = set()
        self.selected_issue_keys: set[tuple] = set()
        self.refresh()
        # Run the freshness check once after the initial widgets are visible.
        # Scheduling it from every refresh can accumulate zero-delay events
        # while other dialogs/tests are being torn down.
        QTimer.singleShot(0, self._ensure_current_pipeline)

    def _show_photo_guidance(self):
        button = self.photo_guidance_button
        QToolTip.showText(
            button.mapToGlobal(QPoint(0, button.height())),
            PHOTO_GUIDANCE_TEXT,
            button,
        )

    def _update_template_badge(self) -> None:
        t_name = self.template_def.name if getattr(self, "template_def", None) else "Default #1"
        c_count = self.template_def.choice_count if getattr(self, "template_def", None) else 5
        q_count = self.exam.details.question_count if getattr(self, "exam", None) else 60
        self.template_badge.setText(
            f"แม่แบบข้อสอบ: <b>{t_name}</b> ({c_count} ตัวเลือก, {q_count} ข้อ)"
        )

    def _on_room_changed(self, index: int) -> None:
        room_id = self.room_combo.itemData(index)
        if not room_id or room_id == self.room_id:
            return
        room = next((item for item in self.rooms if item.id == room_id), None)
        if room is None:
            return
        self.room_id = room.id
        self.room_label = room.label
        self.review_service = ReviewService(self.application.exams.path, room_id=self.room_id)
        self.refresh()

    def _add_room(self) -> None:
        label, accepted = QInputDialog.getText(self, "เพิ่มห้อง", "ชื่อห้อง / ชั้นเรียน:")
        if not accepted:
            return
        try:
            room = self.application.exams.create_room(self.exam.id, label)
        except ValueError as error:
            QMessageBox.warning(self, "เพิ่มห้องไม่ได้", str(error))
            return
        self.rooms = self.application.exams.list_rooms(self.exam.id)
        self.room_combo.blockSignals(True)
        self.room_combo.clear()
        for item in self.rooms:
            self.room_combo.addItem(item.label, item.id)
        self.room_combo.setCurrentIndex(self.room_combo.findData(room.id))
        self.room_combo.blockSignals(False)
        self.room_id = room.id
        self.room_label = room.label
        self.review_service = ReviewService(self.application.exams.path, room_id=self.room_id)
        self.refresh()

    def _open_indicators(self) -> None:
        dialog = AssessmentIndicatorsDialog(
            self.application.exams.path,
            self.exam.id,
            self.exam.details.question_count,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _change_exam_template(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        from exam_grader.template_manager import BUILTIN_TEMPLATE_IDS, load_builtin_template

        available = []
        for b_id in BUILTIN_TEMPLATE_IDS:
            try:
                available.append(load_builtin_template(b_id))
            except Exception:
                pass
        try:
            for t in self.application.exams.list_templates():
                if t.template_id not in BUILTIN_TEMPLATE_IDS:
                    available.append(t)
        except Exception:
            pass

        items = [f"{t.name} ({t.choice_count} ตัวเลือก · {len(t.answer_blocks)} ชุด) [ID: {t.template_id}]" for t in available]
        current_idx = 0
        for i, t in enumerate(available):
            if t.template_id == self.template_def.template_id:
                current_idx = i
                break

        chosen_item, ok = QInputDialog.getItem(
            self,
            "เปลี่ยนรูปแบบกระดาษคำตอบของข้อสอบ",
            f"ข้อสอบปัจจุบันใช้: {self.template_def.name}\nเลือกแม่แบบใหม่ที่ต้องการให้ข้อสอบนี้ใช้:",
            items,
            current_idx,
            False,
        )
        if not ok or not chosen_item:
            return

        chosen_t = available[items.index(chosen_item)]
        if chosen_t.template_id == self.template_def.template_id:
            return

        self.application.exams.update_exam_template(
            self.exam.id, chosen_t.template_id, chosen_t.version, chosen_t.question_count
        )
        self.exam = self.application.exams.get(self.exam.id)
        self.template_def = chosen_t
        self._update_template_badge()

        reply = QMessageBox.question(
            self,
            "ตรวจหาคำตอบใหม่",
            f"เปลี่ยนแม่แบบเป็น '{chosen_t.name}' เรียบร้อยแล้ว\n\nต้องการตรวจหาคำตอบในใบเฉลยและกระดาษคำตอบใหม่ทั้งหมดตามแม่แบบนี้หรือไม่?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._reanalyze_all_sources()
        else:
            self.refresh()

    def _reanalyze_all_sources(self) -> None:
        from exam_grader.imaging import analyze, decode

        with self.flow.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sources WHERE exam_id=? AND archived_at IS NULL", (self.exam.id,)
            ).fetchall()
        for r in rows:
            source = dict(r)
            try:
                data = self.importer.verified_bytes(source)
                decoded = decode(data)
                obs = analyze(
                    data,
                    template_def=self.template_def,
                    app_data_dir=getattr(self.application, "data_dir", None),
                    decoded_image=decoded,
                )
            except Exception as e:
                obs = {
                    "requires_review": True,
                    "failure": str(e),
                    "pipeline_version": "draft-omr-v2",
                }
            self.flow.save_detection(source["id"], obs)
        self.refresh()

    @staticmethod
    def _item(text: str, data: dict) -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, data)
        return item

    def _add_student_item(self, text: str, source: dict) -> None:
        from PySide6.QtCore import QSize

        item = self._item(text, source)
        item.setToolTip(text)
        self.student_list.addItem(item)
        row = QWidget()
        row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.addStretch()
        remove = QPushButton("ลบ")
        remove.setProperty("kind", "compact")
        remove.setFixedHeight(32)
        remove.setAccessibleName("ลบกระดาษนักเรียน")
        remove.setToolTip("เก็บกระดาษนี้แบบกู้คืนได้")
        remove.clicked.connect(lambda _checked=False, value=source: self.archive_student(value))
        row_layout.addWidget(remove)
        self.student_list.setItemWidget(item, row)
        item.setSizeHint(QSize(0, 44))

    def _add_failure_item(self, text: str, failure: dict) -> None:
        from PySide6.QtCore import QSize

        data = {"failure": failure}
        item = self._item(text, data)
        item.setToolTip(text)
        self.student_list.addItem(item)
        row = QWidget()
        row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.addStretch()
        remove = QPushButton("ลบ")
        remove.setProperty("kind", "compact")
        remove.setFixedHeight(32)
        remove.setAccessibleName("ลบรายการนำเข้า")
        remove.setToolTip("ลบรายการที่ล้มเหลวนี้ออก")
        remove.clicked.connect(lambda _checked=False, val=failure: self.dismiss_failure(val))
        row_layout.addWidget(remove)
        self.student_list.setItemWidget(item, row)
        item.setSizeHint(QSize(0, 44))

    def dismiss_failure(self, failure: dict) -> None:
        try:
            self.importer.clear_failure(
                self.exam.id,
                Path(failure["path"]),
                failure["purpose"],
                room_id=failure.get("room_id"),
            )
            self.refresh()
        except Exception as error:
            QMessageBox.warning(self, "ลบรายการไม่ได้", str(error))

    def refresh(self):
        self.key_list.clear()
        self.student_list.clear()
        self.review_list.clear()
        try:
            key = self.flow.current_key(self.exam.id)
            key_state = "ระบบอ่านเฉลยแล้ว" if key.get("origin") == "machine" else "ยืนยันเฉลยแล้ว"
            key_message = f"{key_state} {len(key['answers'])} ข้อ · ข้อละ 1 คะแนน"
        except ValueError:
            key = None
            key_message = f"ยังไม่มีเฉลยยืนยัน · จำนวนข้อของข้อสอบ {self.exam.details.question_count} ข้อ"

        records = self.importer.list_sources(self.exam.id, self.room_id)
        failures = self.importer.list_failures(self.exam.id, self.room_id)
        student_sources = [source for source in records if source["purpose"] == "student"]
        ready = review_count = prefilled_count = 0
        reviewed_numbers: dict[int, int] = {}
        identity_states = {s["source"]["id"]: s for s in self.review_service.states(self.exam.id)}
        current_issues = self.review_service.issues(self.exam.id)
        issue_source_ids = {
            issue["source"]["id"] for issue in current_issues if issue.get("source")
        }
        for candidate in records:
            candidate_review = self.flow.latest_review(candidate["id"])
            if candidate_review:
                reviewed_numbers.setdefault(int(candidate_review["student_number"]), 0)
                reviewed_numbers[int(candidate_review["student_number"])] += 1
                candidate["student_number"] = candidate_review["student_number"]
            identity_state = identity_states.get(candidate["id"], {})
            if identity_state.get("number"):
                candidate["student_number"] = identity_state["number"]
            elif identity_state:
                candidate["student_number"] = (
                    identity_state["detection"].get("student_number_observation") or {}
                ).get("candidate", "")
        records.sort(key=self._student_sort_key, reverse=self.student_sort_desc)
        for source in records:
            review = self.flow.latest_review(source["id"])
            detection = self.flow.latest_detection(source["id"])
            if source["purpose"] == "key":
                state = "ภาพเฉลย"
                if key and key["source_id"] == source["id"]:
                    state = f"{'อ่านอัตโนมัติ' if key.get('origin') == 'machine' else 'ยืนยันแล้ว'} {len(key['answers'])} ข้อ"
                elif key:
                    state = "เฉลยเก่า · ต้องยืนยันใหม่"
                self.key_list.addItem(self._item(f"{source['original_name']}\n{state}", source))
                continue
            active_answers = (
                detection.get("answers", [])[: self.exam.details.question_count]
                if detection
                else []
            )
            needs_decision = bool(
                not detection
                or "failure" in detection
                or len(active_answers) < self.exam.details.question_count
                or any(not item.get("auto_resolved") for item in active_answers)
                or source["id"] in issue_source_ids
            )
            if (
                review
                and key
                and review["key_id"] == key["id"]
                and source["id"] not in issue_source_ids
            ):
                state = f"พร้อม · เลขที่ {review['student_number']}"
                ready += 1
            elif review:
                state = "ต้องตรวจใหม่ (เฉลยเปลี่ยน)"
                review_count += 1
            elif detection and not needs_decision:
                state = (
                    "อ่านได้ครบ · พร้อมยืนยันเลขที่"
                    if not source.get("student_number")
                    else f"อ่านได้ครบ · ยืนยันเลขที่ {source['student_number']}"
                )
                prefilled_count += 1
            else:
                state = "ต้องตรวจทาน"
                review_count += 1
            if detection and "failure" in detection:
                state = f"อ่านไม่ได้ · {detection['failure']}"
            number_observation = (detection or {}).get("student_number_observation", {})
            if not review and not source.get("student_number") and number_observation.get("candidate"):
                candidates = number_observation.get("candidates") or []
                if candidates == [number_observation["candidate"]]:
                    state += f" · ผู้ช่วยอ่านเลขที่ {number_observation['candidate']} (ต้องตรวจทาน)"
                else:
                    state += f" · เลขที่อาจเป็น {' / '.join(candidates)} (ต้องตรวจทาน)"
            if review and reviewed_numbers.get(int(review["student_number"]), 0) > 1:
                state = f"เลขที่ซ้ำ · {review['student_number']} · {state}"
            self._add_student_item(f"{source['original_name']}\n{state}", source)
            if (not review or not key or review["key_id"] != key["id"]) and needs_decision:
                self.review_list.addItem(self._item(f"{source['original_name']}\n{state}", source))

        for failure in failures:
            data = {"failure": failure}
            text = f"{Path(failure['path']).name}\nล้มเหลว · {failure['error']}"
            self._add_failure_item(text, failure)
            self.review_list.addItem(self._item(text, data))

        failed_count = len(failures)
        self.status.setText(
            f"{key_message}\nนักเรียน: พร้อม {ready} · พร้อมยืนยัน {prefilled_count} · "
            f"ต้องตรวจ {review_count} · ล้มเหลว {failed_count}"
        )
        if key and ready:
            try:
                missing = self.flow.missing_numbers(self.exam.id, room_id=self.room_id)
                if missing["missing_expected"]:
                    self.status.setText(
                        self.status.text() + f"\nเลขที่คาดหวังที่ยังไม่พบ: {missing['missing_expected']}"
                    )
                elif missing["missing_internal"]:
                    self.status.setText(
                        self.status.text() + f"\nเลขที่ขาดภายในช่วงที่พบ: {missing['missing_internal']}"
                    )
            except ValueError:
                pass
        t_name = self.template_def.name if getattr(self, "template_def", None) else "Default #1"
        self.output_label.setText(f"แม่แบบกระดาษ: {t_name}\nตำแหน่งบันทึกผลลัพธ์: {self.output_root}")
        partial_count = 0
        try:
            partial_count = sum(
                result.get("status") == "review_skipped"
                for result in self.flow.snapshot(self.exam.id, room_id=self.room_id)["results"]
            )
        except ValueError:
            pass
        summary = (
            f"สถานะปัจจุบัน: พร้อม {ready} · พร้อมยืนยัน {prefilled_count} · "
            f"ต้องตรวจ {review_count} · ล้มเหลว {failed_count}\n"
        )
        if partial_count:
            summary += (
                f"มีผลลัพธ์บางส่วน {partial_count} กระดาษ · รายการที่ยังไม่ชัดคิดเป็น 0 คะแนน "
                "และบันทึกสถานะ review_skipped"
            )
        else:
            summary += (
                "พร้อมบันทึกผลตรวจ"
                if key and not current_issues
                else "ตรวจทานรายการที่ค้างอยู่ก่อนบันทึกผล"
            )
        self.results_summary.setText(summary)
        processed_count = sum(self.flow.latest_detection(source["id"]) is not None for source in student_sources)
        pending_sheets = len(
            {issue["source"]["id"] for issue in current_issues if issue.get("source")}
        )
        if student_sources and processed_count == len(student_sources):
            self.progress_label.setText(
                f"ประมวลผล 100% · รอตรวจทาน {pending_sheets} กระดาษ"
                if pending_sheets
                else "ประมวลผล 100% · พร้อมออกผล"
            )
        elif student_sources:
            percentage = round(processed_count * 100 / len(student_sources))
            self.progress_label.setText(
                f"ประมวลผล {percentage}% · รอตรวจทาน {pending_sheets} กระดาษ"
            )
        else:
            self.progress_label.setText("พร้อมทำงาน")
        self.export_history.clear()
        for run in self.application.exams.export_runs(self.exam.id, self.room_id):
            path = Path(run["path"])
            timestamp = (
                datetime.fromisoformat(run["created_at"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            )
            label = f"ผลตรวจ · {timestamp}"
            if not path.is_dir():
                label += " · ไม่พบโฟลเดอร์"
            self.export_history.addItem(label, str(path))
        if self.export_history.count() == 0:
            self.export_history.setCurrentIndex(-1)
        self.reveal_button.setEnabled(self.export_history.count() > 0)
        self.populate_issues()
        self.update_key_gate()
        self.adopt_button.setEnabled(
            any(
                not s["number"]
                and (s["detection"].get("student_number_observation") or {}).get("candidate")
                for s in self.review_service.states(self.exam.id)
            )
        )
        self.attendance_restore.clear()
        self.attendance_restore.addItem("แก้สถานะขาดสอบที่บันทึกแล้ว…", None)
        with self.flow.connection() as con:
            for row in con.execute(
                "SELECT student_number,status FROM attendance WHERE room_id=? AND status!='pending' ORDER BY student_number",
                (self.room_id,),
            ):
                status = "ขาดสอบ" if row["status"] == "absent" else "ลา / ยกเว้น"
                self.attendance_restore.addItem(
                    f"เลขที่ {row['student_number']} · {status} → ส่งกลับตรวจทาน",
                    str(row["student_number"]),
                )
            for row in con.execute(
                "SELECT student_number FROM skipped_numbers WHERE room_id=? ORDER BY student_number",
                (self.room_id,),
            ):
                self.attendance_restore.addItem(
                    f"เลขที่ {row['student_number']} · ข้ามไว้ → ส่งกลับตรวจทาน",
                    str(row["student_number"]),
                )
        self.attendance_restore.setVisible(self.attendance_restore.count() > 1)
    def restore_attendance(self, index):
        number = self.attendance_restore.itemData(index)
        if number:
            self.review_service.set_attendance(self.exam.id, number, "pending")
            self.refresh()
            self.tabs.setCurrentIndex(2)

    def update_key_gate(self):
        try:
            self.flow.confirmed_key(self.exam.id)
            confirmed = True
        except ValueError:
            confirmed = False
        self.student_button.setEnabled(confirmed)
        for index in (1, 2, 3):
            self.tabs.setTabEnabled(index, confirmed)
        self.confirm_key_button.setEnabled(self.key_list.count() > 0)
        if not confirmed:
            self.tabs.setCurrentIndex(0)
        if self.key_list.count() and self.key_list.currentRow() < 0:
            self.key_list.setCurrentRow(self.key_list.count() - 1)

    def skip_missing(self):
        count = self.review_service.skip_missing(self.exam.id)
        self.refresh()
        self.progress_label.setText(f"ข้ามเลขที่ที่ยังไม่ส่งแล้ว {count} เลขที่ · เพิ่มกระดาษภายหลังได้")

    def adopt_numbers(self):
        try:
            outcome = self.review_service.adopt_numbers(self.exam.id)
            self.refresh()
            self.progress_label.setText(
                f"ใช้เลขที่แล้ว {len(outcome['applied'])} ใบ · ยังต้องแก้ {len(outcome['skipped'])} ใบ"
            )
            if outcome["skipped"]:
                self.tabs.setCurrentIndex(2)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "ใช้เลขที่ไม่ได้", str(error))

    def archive_selected_student(self):
        item = self.student_list.currentItem()
        source = item.data(Qt.ItemDataRole.UserRole) if item else None
        if isinstance(source, dict) and "failure" in source:
            self.dismiss_failure(source["failure"])
            return
        self.archive_student(source)

    def archive_student(self, source):
        if not source or source.get("purpose") != "student" or not source.get("id"):
            QMessageBox.information(self, "ยังไม่ได้เลือก", "เลือกกระดาษนักเรียนก่อน")
            return
        answer = QMessageBox.question(
            self,
            "ลบกระดาษแบบกู้คืนได้",
            f"เก็บกระดาษ {source['original_name']} ออกจากการตรวจและผลลัพธ์หรือไม่?\n"
            "ต้นฉบับจะเก็บไว้และกู้คืนได้จากการนำเข้าภาพเดิม",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.importer.archive_source(source["id"])
            self.refresh()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "ลบกระดาษไม่ได้", str(error))

    def archive_all_students(self):
        sources = [
            s
            for s in self.importer.list_sources(self.exam.id, self.room_id)
            if s["purpose"] == "student"
        ]
        if not sources:
            QMessageBox.information(self, "ไม่มีภาพนักเรียน", "ยังไม่มีภาพนักเรียนที่ใช้งานอยู่")
            return
        answer = QMessageBox.question(
            self,
            "ลบกระดาษนักเรียนทั้งหมดแบบกู้คืนได้",
            f"เก็บกระดาษนักเรียน {len(sources)} ใบออกจากการตรวจและผลลัพธ์หรือไม่?\n"
            "ต้นฉบับและข้อมูลตรวจทานจะเก็บไว้ กู้คืนได้ด้วยการนำเข้าภาพเดิม",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            for source in sources:
                self.importer.archive_source(source["id"])
            self.refresh()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "ลบกระดาษไม่ได้", str(error))

    def reprocess_students(self):
        paths = [
            self.application.exams.path.parent / s["relative_path"]
            for s in self.importer.list_sources(self.exam.id, self.room_id)
            if s["purpose"] == "student"
        ]
        self.start_import(paths, "student")

    def _ensure_current_pipeline(self) -> None:
        """Re-read persisted images when their detection predates this app.

        Source images are immutable, so reprocessing is safe and keeps an opened
        exam from presenting stale algorithm output. Current detections that are
        merely review-required are left alone; uncertainty must remain visible to
        the teacher instead of being retried until the UI opens.
        """
        if self.worker and self.worker.isRunning():
            return
        stale_by_purpose: dict[str, list[Path]] = {"key": [], "student": []}
        for source in self.importer.list_sources(self.exam.id, self.room_id):
            if source["purpose"] not in stale_by_purpose:
                continue
            detection = self.flow.latest_detection(source["id"])
            if not detection or detection.get("pipeline_version") == OMR_PIPELINE_VERSION:
                continue
            stale_by_purpose[source["purpose"]].append(
                self.application.exams.path.parent / source["relative_path"]
            )

        if stale_by_purpose["key"]:
            try:
                self.flow.confirmed_key(self.exam.id)
            except ValueError:
                # A key that has not been teacher-confirmed still needs the
                # current pipeline before it can be reviewed.
                self.start_import(stale_by_purpose["key"], "key")
                return
            # A teacher-confirmed key is durable evidence. Keep it while student
            # sheets are refreshed; re-reading it would reopen a solved key.
        if not stale_by_purpose["student"]:
            return
        try:
            self.flow.confirmed_key(self.exam.id)
        except ValueError:
            # Student detection will be refreshed automatically after the key is
            # confirmed; never bypass the existing key gate.
            return
        self.start_import(stale_by_purpose["student"], "student")

    def populate_issues(self):
        self._capture_issue_drafts()
        self.issue_rows = self.review_service.issues(self.exam.id)
        self.issue_table.blockSignals(True)
        self.issue_table.clearContents()
        self.skip_missing_button.setVisible(
            any(i["kind"] == "attendance" and i["source"] is None for i in self.issue_rows)
        )
        self.empty_review.setVisible(not self.issue_rows)
        self.empty_review.setText(
            "ไม่มีข้อมูลที่ต้องแก้ไข" if self.student_list.count() else "เพิ่มเฉลยและภาพนักเรียนเพื่อเริ่มตรวจ"
        )
        self.bulk_bar_widget.setVisible(bool(self.issue_rows))
        self.issue_table.setRowCount(len(self.issue_rows))
        previews = {}
        geometries = {}
        # Retain selection state across populate / refresh using stable issue keys
        valid_keys = {self._issue_key(i) for i in self.issue_rows}
        self.selected_issue_keys.intersection_update(valid_keys)

        for row, issue in enumerate(self.issue_rows):
            # Column 0: Checkbox
            key = self._issue_key(issue)
            chk_item = QTableWidgetItem()
            chk_item.setData(Qt.ItemDataRole.UserRole, key)
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(
                Qt.CheckState.Checked if key in self.selected_issue_keys else Qt.CheckState.Unchecked
            )
            self.issue_table.setItem(row, 0, chk_item)

            for column, text in enumerate(
                (
                    issue["number"] or "—",
                    issue["label"],
                    issue["source"]["original_name"] if issue["source"] else "ยังไม่มีภาพ",
                ),
                start=1,
            ):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(text)
                if column == 2:
                    if issue.get("status") == "duplicate":
                        item.setBackground(QColor("#fee2e2"))
                        item.setForeground(QColor("#991b1b"))
                    elif issue.get("status") == "missing":
                        item.setBackground(QColor("#e0e7ff"))
                        item.setForeground(QColor("#3730a3"))
                    else:
                        item.setBackground(QColor("#fff0cd"))
                        item.setForeground(QColor("#503800"))
                self.issue_table.setItem(row, column, item)
            if issue["source"] and issue["kind"] in {"answer", "number"}:
                try:
                    cell_item = self.issue_table.item(row, 3)
                    if cell_item is not None:
                        cell_item.setText("")
                    sid = issue["source"]["id"]
                    t_def = getattr(self, "template_def", None)
                    if t_def is None:
                        t_def = load_exam_template_def(self.application.exams.path, self.exam.id)
                        self.template_def = t_def
                    detection = self.flow.latest_detection(sid)
                    if not detection:
                        raise ValueError("ยังไม่มีผลอ่าน")
                    if sid not in geometries:
                        geometries[sid] = geometry_from_detection(
                            detection,
                            t_def,
                            source_sha256=issue["source"].get("sha256"),
                        )
                    geometry = geometries[sid]
                    if sid not in previews:
                        matrix = geometry["transform"]["matrix"]
                        if matrix is None:
                            raise ValueError("ยังไม่มี transform ที่เชื่อถือได้")
                        previews[sid] = cv2.warpPerspective(
                            decode(self.importer.verified_bytes(issue["source"])),
                            np.asarray(matrix, dtype=np.float64),
                            (t_def.canonical_width, t_def.canonical_height),
                        )
                    if issue["kind"] == "number":
                        identity_roi = geometry.get("identity_roi")
                        if identity_roi:
                            rx1, ry1, rx2, ry2 = identity_roi
                            pad_y = max(8, int((ry2 - ry1) * 0.15))
                            pad_x = max(8, int((rx2 - rx1) * 0.15))
                            y1 = max(0, ry1 - pad_y)
                            y2 = min(t_def.canonical_height, ry2 + pad_y)
                            x1 = max(0, rx1 - pad_x)
                            x2 = min(t_def.canonical_width, rx2 + pad_x)
                        else:
                            x1, y1, x2, y2 = 0, 0, 100, 50
                    else:
                        q_num = issue["question"]
                        roi_rects = geometry["answer_rois"].get(str(q_num))
                        if not roi_rects:
                            raise ValueError("ไม่พบ ROI ของข้อนี้ใน geometry resolver")
                        x1 = max(0, min(int(rect[0]) for rect in roi_rects.values()) - 8)
                        y1 = max(0, min(int(rect[1]) for rect in roi_rects.values()) - 4)
                        x2 = min(
                            t_def.canonical_width,
                            max(int(rect[0]) + int(rect[2]) for rect in roi_rects.values()) + 8,
                        )
                        y2 = min(
                            t_def.canonical_height,
                            max(int(rect[1]) + int(rect[3]) for rect in roi_rects.values()) + 4,
                        )
                    crop = np.ascontiguousarray(previews[sid][y1:y2, x1:x2])
                    picture = QImage(
                        crop.data,
                        crop.shape[1],
                        crop.shape[0],
                        crop.strides[0],
                        QImage.Format.Format_BGR888,
                    ).copy()
                    preview_label = QLabel()
                    preview_label.setPixmap(
                        QPixmap.fromImage(picture).scaled(
                            230,
                            62,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    preview_label.setToolTip(
                        issue["source"]["original_name"] + " · ดับเบิลคลิกแถวเพื่อดูทั้งใบ"
                    )
                    self.issue_table.setCellWidget(row, 3, preview_label)
                except (ValueError, OSError, KeyError, TypeError):
                    pass
            editor: QLineEdit | QComboBox
            if issue["kind"] == "number":
                editor = QLineEdit(
                    issue.get("prefill") or issue.get("candidate") or issue["number"] or ""
                )
                editor.setPlaceholderText("เลขที่")
            else:
                editor = QComboBox()
                options: list[tuple[str, str | None]] = [("— เลือก —", None)]
                if issue["kind"] == "answer":
                    options += [
                        (f"{thai} / {latin}", latin) for thai, latin in zip("กขคงจ", "ABCDE")
                    ]
                    options += [("เว้นว่าง", "blank"), ("หลายคำตอบ", "multiple")]
                elif issue["kind"] == "attendance":
                    options += [
                        ("รอกระดาษ / ยกเลิกขาดสอบ", "pending"),
                        ("ข้ามเลขที่นี้", "skipped"),
                        ("ขาดสอบ", "absent"),
                        ("ลา / ได้รับยกเว้น", "excused"),
                    ]
                elif issue["kind"] in {"image", "import"}:
                    options += [("ลบรายการนี้ออก", "dismiss")]
                else:
                    options += [("ใช้คำตอบเดิมกับเฉลยใหม่", "reuse")]
                for label, value in options:
                    editor.addItem(label, value)
                editor.setCurrentIndex(
                    max(0, editor.findData(issue.get("prefill") or issue.get("candidate")))
                )
            issue_key = self._issue_key(issue)
            if issue_key in self.issue_drafts:
                draft = self.issue_drafts[issue_key]
                editor.blockSignals(True)
                if isinstance(editor, QLineEdit):
                    editor.setText(str(draft))
                else:
                    editor.setCurrentIndex(max(0, editor.findData(draft)))
                editor.blockSignals(False)
            if isinstance(editor, QLineEdit):
                editor.textEdited.connect(lambda _value, key=issue_key: self.issue_dirty.add(key))
            else:
                editor.currentIndexChanged.connect(
                    lambda _index, key=issue_key: self.issue_dirty.add(key)
                )
            self.issue_table.setCellWidget(row, 4, editor)
            button = QPushButton("บันทึก")
            button.clicked.connect(lambda checked=False, i=issue, e=editor: self.save_issue(i, e))
            self.issue_table.setCellWidget(row, 5, button)
        self.issue_table.resizeRowsToContents()
        self.issue_table.blockSignals(False)
        self._update_bulk_selection_state()

    @staticmethod
    def _issue_key(issue):
        source = issue.get("source") or {}
        failure = issue.get("failure") or {}
        return (
            source.get("id"),
            issue.get("kind"),
            issue.get("question"),
            issue.get("number"),
            issue.get("key_id"),
            issue.get("detection_id"),
            failure.get("id") or failure.get("path"),
        )

    def _capture_issue_drafts(self):
        for row, issue in enumerate(getattr(self, "issue_rows", [])):
            editor = self.issue_table.cellWidget(row, 4)
            if editor is None:
                continue
            value = (
                editor.text()
                if isinstance(editor, QLineEdit)
                else cast(QComboBox, editor).currentData()
            )
            key = self._issue_key(issue)
            if key in self.issue_dirty:
                self.issue_drafts[key] = value

    def _save_issue_value(self, issue, value):
        if not value:
            raise ValueError("เลือกข้อมูลก่อนบันทึก")
        if issue["kind"] == "number":
            self.review_service.set_number(
                issue["source"], value, expected_detection=issue["detection_id"]
            )
        elif issue["kind"] == "answer":
            self.review_service.resolve_answer(
                issue["source"],
                issue["question"],
                value,
                key_id=issue["key_id"],
                detection_id=issue["detection_id"],
            )
        elif issue["kind"] == "attendance":
            self.review_service.set_attendance(self.exam.id, issue["number"], value)
        elif issue["kind"] in {"image", "import"}:
            raise ValueError("กู้คืนภาพต้องกดจากรายการนั้นโดยตรง")
        else:
            state = self.review_service.state(issue["source"])
            self.flow.review(
                issue["source"]["id"],
                state["number"],
                state["review"]["answers"],
                issue["key_id"],
                origin="teacher",
                detection_id=issue["detection_id"],
            )

    def save_issue(self, issue, editor):
        try:
            value = (
                editor.text()
                if isinstance(editor, QLineEdit)
                else cast(QComboBox, editor).currentData()
            )
            if issue["kind"] in {"image", "import"}:
                if value == "dismiss":
                    if issue.get("failure"):
                        self.importer.clear_failure(
                            self.exam.id,
                            Path(issue["failure"]["path"]),
                            issue["failure"]["purpose"],
                            room_id=issue["failure"].get("room_id"),
                        )
                    elif issue.get("source"):
                        self.importer.archive_source(issue["source"]["id"])
                    self.refresh()
                    return
                raise ValueError("เลือกคำสั่งที่ต้องการก่อนบันทึก")
            self._save_issue_value(issue, value)
            key = self._issue_key(issue)
            self.issue_dirty.discard(key)
            self.issue_drafts.pop(key, None)
            self.refresh()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "บันทึกไม่ได้", str(error))

    def save_all_issues(self):
        self._capture_issue_drafts()
        pending = []
        for row, issue in enumerate(getattr(self, "issue_rows", [])):
            key = self._issue_key(issue)
            if key not in self.issue_dirty:
                continue
            editor = self.issue_table.cellWidget(row, 4)
            value = (
                editor.text()
                if isinstance(editor, QLineEdit)
                else cast(QComboBox, editor).currentData()
            )
            pending.append((issue, value, key))
        errors = []
        for issue, value, key in pending:
            try:
                self._save_issue_value(issue, value)
                self.issue_dirty.discard(key)
                self.issue_drafts.pop(key, None)
            except (ValueError, OSError) as error:
                errors.append(f"{issue.get('label', 'รายการ')}: {error}")
        self.refresh()
        if errors:
            QMessageBox.warning(self, "บันทึกได้บางรายการ", "\n".join(errors))

    def _on_issue_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            key = item.data(Qt.ItemDataRole.UserRole)
            if key is None and 0 <= item.row() < len(self.issue_rows):
                key = self._issue_key(self.issue_rows[item.row()])
            if key is not None:
                if item.checkState() == Qt.CheckState.Checked:
                    self.selected_issue_keys.add(key)
                else:
                    self.selected_issue_keys.discard(key)
            self._update_bulk_selection_state()

    def _update_bulk_selection_state(self) -> None:
        count = len(self.selected_issue_keys)
        self.selection_label.setText(f"เลือก {count} รายการ")
        has_val = self.bulk_combo.currentData() is not None
        self.bulk_apply_btn.setEnabled(count > 0 and has_val)
        has_prefill = any(
            self._issue_key(issue) in self.selected_issue_keys
            and self.review_service.prefilled_value(issue) is not None
            for issue in getattr(self, "issue_rows", [])
        )
        self.bulk_confirm_btn.setEnabled(has_prefill)

    def select_all_issues(self) -> None:
        for issue in self.issue_rows:
            self.selected_issue_keys.add(self._issue_key(issue))
        self.issue_table.blockSignals(True)
        for r in range(self.issue_table.rowCount()):
            it = self.issue_table.item(r, 0)
            if it:
                it.setCheckState(Qt.CheckState.Checked)
        self.issue_table.blockSignals(False)
        self._update_bulk_selection_state()

    def clear_issue_selection(self) -> None:
        self.selected_issue_keys.clear()
        self.issue_table.blockSignals(True)
        for r in range(self.issue_table.rowCount()):
            it = self.issue_table.item(r, 0)
            if it:
                it.setCheckState(Qt.CheckState.Unchecked)
        self.issue_table.blockSignals(False)
        self._update_bulk_selection_state()

    def apply_bulk_edit(self) -> None:
        if not self.selected_issue_keys:
            QMessageBox.information(
                self, "ยังไม่ได้เลือกรายการ", "กรุณาคลิกเลือกช่องหน้ารายการที่ต้องการแก้ไข"
            )
            return
        val = self.bulk_combo.currentData()
        if not val:
            QMessageBox.information(
                self, "ยังไม่ได้เลือกคำตอบ / สถานะ", "กรุณาเลือกคำตอบหรือสถานะที่ต้องการกำหนดจากเมนู"
            )
            return

        operations = []
        for issue in self.issue_rows:
            if self._issue_key(issue) in self.selected_issue_keys:
                operations.append({"issue": issue, "value": val})

        if not operations:
            return

        try:
            res = self.review_service.bulk_resolve(self.exam.id, operations)
            applied = res.get("applied", 0)
            for op in operations:
                key = self._issue_key(op["issue"])
                self.issue_dirty.discard(key)
                self.issue_drafts.pop(key, None)
                self.selected_issue_keys.discard(key)
            self.refresh()
            QMessageBox.information(
                self,
                "บันทึกข้อมูลเรียบร้อย",
                f"บันทึกและปรับปรุงข้อมูล {applied} รายการเรียบร้อยแล้ว",
            )
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "บันทึกไม่สำเร็จ", str(error))

    def confirm_bulk_prefilled(self) -> None:
        if not self.selected_issue_keys:
            QMessageBox.information(
                self, "ยังไม่ได้เลือกรายการ", "กรุณาคลิกเลือกแถวที่ต้องการยืนยันก่อน"
            )
            return
        selected = [
            issue
            for issue in self.issue_rows
            if self._issue_key(issue) in self.selected_issue_keys
        ]
        measurable = [
            issue
            for issue in selected
            if self.review_service.prefilled_value(issue) is not None
        ]
        if not measurable:
            QMessageBox.information(
                self,
                "ไม่มีค่าที่พร้อมยืนยัน",
                "แถวที่เลือกยังไม่มีค่า prefill ที่วัดได้ชัดเจน · ใช้การแก้ไขรายแถวแทน",
            )
            return
        try:
            result = self.review_service.confirm_prefilled(self.exam.id, measurable)
            applied = result.get("applied", [])
            applied_keys = {self._issue_key(issue) for issue in applied}
            self.selected_issue_keys.difference_update(applied_keys)
            for key in applied_keys:
                self.issue_dirty.discard(key)
                self.issue_drafts.pop(key, None)
            self.refresh()
            skipped = len(result.get("skipped", []))
            suffix = f" · คงค้าง {skipped} รายการให้ตรวจเอง" if skipped else ""
            QMessageBox.information(
                self,
                "ยืนยันข้อมูลเรียบร้อย",
                f"ยืนยันค่าที่ระบบอ่านไว้รายแถว {len(applied)} รายการ{suffix}",
            )
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "ยืนยันไม่สำเร็จ", str(error))

    def open_issue_source(self, row, column):
        if column == 0:
            return
        source = self.issue_rows[row]["source"]
        if source:
            self.open_source(source)

    def reveal_result(self):
        path = self.export_history.currentData()
        if not path or not Path(path).is_dir():
            QMessageBox.warning(
                self, "เปิดผลลัพธ์ไม่ได้", "ไม่พบโฟลเดอร์ กรุณาเชื่อมต่อไดรฟ์เดิมหรือสร้างผลตรวจใหม่"
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def busy(self, value):
        for action in self.action_buttons:
            action.setEnabled(not value)
        self.key_list.setEnabled(not value)
        self.student_list.setEnabled(not value)
        self.review_list.setEnabled(not value)
        self.issue_table.setEnabled(not value)
        self.attendance_restore.setEnabled(not value)
        self.room_combo.setEnabled(not value)
        self.skip_missing_button.setEnabled(not value)
        self.confirm_key_button.setEnabled(not value and self.key_list.count() > 0)
        if not value:
            self.update_key_gate()
        self.cancel.setEnabled(value and isinstance(self.worker, BatchWorker))

    def pick_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "เลือกภาพเฉลย", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self.start_import([Path(path)], "key")

    def pick_student_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "เลือกภาพนักเรียน", "", "Images (*.png *.jpg *.jpeg)"
        )
        self.start_import([Path(path) for path in paths], "student")

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์ภาพนักเรียน")
        if folder:
            self.start_import(
                sorted(
                    path
                    for path in Path(folder).iterdir()
                    if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
                ),
                "student",
            )

    def start_import(self, paths, purpose):
        if not paths or (self.worker and self.worker.isRunning()):
            return
        if purpose == "student":
            try:
                self.flow.confirmed_key(self.exam.id)
            except ValueError as error:
                QMessageBox.information(self, "ยืนยันเฉลยก่อน", str(error))
                self.tabs.setCurrentIndex(0)
                return
        room_id = self.room_id if purpose == "student" else None
        self.worker = BatchWorker(
            self.application.exams.path, self.exam.id, paths, purpose, room_id, self
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.completed.connect(self.import_done)
        self.worker.finished.connect(lambda: self.busy(False))
        self.busy(True)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.progress_label.setText(f"กำลังอ่าน 0 จาก {len(paths)}")
        self.worker.start()

    def on_progress(self, done, total, filename):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.progress_label.setText(f"กำลังอ่าน {done} จาก {total} · {filename}")

    def import_done(self, failures):
        self.refresh()
        # The worker emits completed before QThread.finished. Defer the stale
        # check one event-loop turn so a key refresh can be followed by students.
        QTimer.singleShot(0, self._ensure_current_pipeline)
        if failures:
            QMessageBox.warning(self, "บางภาพนำเข้าไม่ได้", "\n".join(failures))
        if isinstance(self.worker, BatchWorker) and self.worker.purpose == "key" and not failures:
            self.review_key()

    def cancel_batch(self):
        if self.worker:
            self.worker.requestInterruption()

    def review_key(self):
        item = self.key_list.currentItem()
        if item:
            self.open_source(item.data(Qt.ItemDataRole.UserRole))

    def review_student(self):
        item = self.student_list.currentItem()
        if item:
            self.open_source(item.data(Qt.ItemDataRole.UserRole))

    def review_selected(self):
        item = self.review_list.currentItem()
        if item:
            self.open_source(item.data(Qt.ItemDataRole.UserRole))

    def open_source(self, source):
        if "failure" in source:
            self.retry_selected()
            return
        try:
            while True:
                dialog = ReviewDialog(self.application.exams.path, source, self)
                accepted = dialog.exec()
                if dialog.normalization_updated:
                    continue
                break
            if dialog.skip_remaining_completed:
                self.refresh()
                self.tabs.setCurrentIndex(3)
                self.export()
                return
            self.review_service.finalize(self.exam.id)
            self.refresh()
            if source["purpose"] == "key" and accepted:
                self.tabs.setCurrentIndex(1)
        except Exception as error:
            QMessageBox.warning(self, "เปิดภาพไม่ได้", str(error))

    def retry_selected(self):
        item = self.review_list.currentItem()
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        failure = data.get("failure") if isinstance(data, dict) else None
        if failure is None:
            QMessageBox.information(self, "ตรวจใหม่", "เลือกรายการที่ล้มเหลวก่อน")
            return
        path = Path(failure["path"])
        if not path.exists():
            QMessageBox.warning(self, "ตรวจใหม่ไม่ได้", f"ไม่พบไฟล์ต้นฉบับ\n{path}")
            return
        self.start_import([path], failure["purpose"])

    def choose_output_root(self):
        path = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์ผลลัพธ์")
        if path:
            self.output_root = Path(path).expanduser().resolve()
            self.application.exams.set_output_root(self.exam.id, self.output_root)
            self.refresh()

    def open_color_settings(self):
        from exam_grader.settings_ui import AnnotationColorSettingsDialog

        AnnotationColorSettingsDialog(self).exec()

    def change_student_sort(self, index):
        self.student_sort_desc = index == 1
        self.refresh()

    @staticmethod
    def _student_sort_key(source):
        value = source.get("student_number", "")
        return int(value) if str(value).isdigit() else 10**9

    def export(self):
        self.worker = ExportWorker(
            self.application.exams.path, self.exam.id, self.output_root, self.room_id, self
        )
        self.worker.completed.connect(self.export_done)
        self.worker.finished.connect(lambda: self.busy(False))
        self.busy(True)
        self.progress.setRange(0, 0)
        self.progress_label.setText("กำลังสร้างผลตรวจและ Excel…")
        self.worker.start()

    def export_done(self, path, error):
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        if error:
            QMessageBox.warning(self, "สร้างผลไม่ได้", error)
        else:
            self.refresh()
            QMessageBox.information(
                self, "สร้างผลแล้ว", f"ผลเป็น snapshot ของเฉลยและการตรวจทานขณะนี้\n{path}"
            )
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not (self.worker and self.worker.isRunning()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.start_import(
            [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()],
            "student",
        )
        event.acceptProposedAction()

    def reject(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "กำลังทำงาน", "กรุณารอให้เสร็จ หรือหยุดการนำเข้าก่อนปิด")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            event.accept()
