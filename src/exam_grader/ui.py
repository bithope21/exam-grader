"""Small working desktop shell; only supported actions are exposed."""

import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from exam_grader.app import Application
from exam_grader.domain import ExamDetails
from exam_grader.preferences import save_output_root


class NewExamDialog(QDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setWindowTitle("สร้างข้อสอบ")
        layout = QFormLayout(self)
        self.fields = {}
        for key, label in (
            ("name", "ชื่อข้อสอบ"),
            ("academic_year", "ปีการศึกษา"),
            ("grade", "ชั้น"),
            ("room", "ห้อง"),
            ("subject", "วิชา"),
        ):
            field: QLineEdit | QComboBox
            if key in {"academic_year", "grade", "room"}:
                field = QComboBox()
                field.setEditable(key != "academic_year")
                if key == "academic_year":
                    current = date.today().year + 543
                    field.addItems([str(year) for year in range(current, 2499, -1)])
                elif key == "grade":
                    field.addItems([f"ป.{i}" for i in range(1, 7)] + [f"ม.{i}" for i in range(1, 7)])
                    field.setToolTip("เลือกชั้น หรือพิมพ์เอง เช่น ปวช.1")
                else:
                    field.addItems([str(i) for i in range(1, 13)])
                    field.setToolTip("เลือกห้อง หรือพิมพ์เอง")
                line = field.lineEdit()
                if line:
                    line.setMaxLength(200)
            else:
                field = QLineEdit()
                field.setMaxLength(200)
            self.fields[key] = field
            layout.addRow(label, field)
        self.question_count = QSpinBox()
        self.question_count.setRange(1, 60)
        self.question_count.setValue(60)
        layout.addRow("จำนวนข้อ", self.question_count)
        self.expected_number_max = QSpinBox()
        self.expected_number_max.setRange(0, 9999)
        self.expected_number_max.setSpecialValueText("ไม่กำหนด")
        layout.addRow("เลขที่คาดหวังถึง", self.expected_number_max)
        buttons = QDialogButtonBox()
        buttons.addButton("บันทึก", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("ยกเลิก", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self) -> None:
        try:
            self.details = ExamDetails(
                **{k: v.currentText() if isinstance(v, QComboBox) else v.text() for k, v in self.fields.items()},
                question_count=self.question_count.value(),
                expected_number_max=self.expected_number_max.value() or None,
            )
        except ValueError as error:
            QMessageBox.warning(self, "ข้อมูลไม่ครบ", str(error))
            return
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self, application: Application):
        super().__init__()
        self.application = application
        self.setWindowTitle("Exam Grader")
        self.resize(780, 540)
        container = QWidget()
        layout = QVBoxLayout(container)
        title = QLabel("ข้อสอบของคุณ")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        description = QLabel(
            "ตรวจข้อสอบแบบ offline · ตรวจทานเฉพาะข้อมูลที่ยังมีปัญหา\n"
            "สร้างข้อสอบ แล้วเปิดเพื่อนำเข้าเฉลยและภาพนักเรียน"
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        create = QPushButton("สร้างข้อสอบ")
        create.clicked.connect(self.create_exam)
        layout.addWidget(create)
        self.exam_list = QListWidget()
        self.exam_list.itemDoubleClicked.connect(lambda _: self.open_exam())
        layout.addWidget(self.exam_list)
        open_button = QPushButton("เปิดข้อสอบที่เลือก")
        open_button.clicked.connect(self.open_exam)
        layout.addWidget(open_button)
        location = QLabel(f"โฟลเดอร์ข้อมูล: {application.data_dir}")
        location.setWordWrap(True)
        layout.addWidget(location)
        self.setCentralWidget(container)
        settings_menu = self.menuBar().addMenu("ตั้งค่า")
        settings_menu.addAction("ตำแหน่งบันทึกผลลัพธ์…", self.choose_output_root)
        self.menuBar().addAction("ข้อสอบที่เก็บถาวร…", self.show_archived)
        self.refresh()

    def choose_output_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์ผลลัพธ์")
        if path:
            save_output_root(Path(path))
            QMessageBox.information(self, "บันทึกแล้ว", f"ตำแหน่งเริ่มต้นคือ\n{Path(path).resolve()}")

    def refresh(self) -> None:
        self.exam_list.clear()
        for exam in self.application.exams.list_exams():
            details = exam.details
            text = (
                f"{details.name} — {details.subject}\n"
                f"ปี {details.academic_year} · ชั้น {details.grade} · ห้อง {details.room} · "
                f"{details.question_count} ข้อ"
            )
            # Keep the text on the item as well as in the custom row widget so
            # keyboard selection, accessibility clients, and existing callers
            # can still read the exam metadata.
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, exam)
            item.setToolTip(text)
            self.exam_list.addItem(item)
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 4, 8, 4)
            row_layout.addStretch()
            remove = QPushButton("ลบข้อสอบชุดนี้…")
            remove.setToolTip("ลบชุดนี้ออกจากรายการตอนนี้ · กู้คืนได้จากเมนูข้อสอบที่เก็บถาวร")
            remove.clicked.connect(lambda _checked=False, value=exam: self.archive_exam(value))
            row_layout.addWidget(remove)
            self.exam_list.setItemWidget(item, row)
            item.setSizeHint(row.sizeHint())

    def archive_exam(self, exam) -> None:
        details = exam.details
        summary = self.application.exams.summary(exam.id)
        answer = QMessageBox.question(
            self,
            "ลบข้อสอบชุดนี้ (กู้คืนได้)",
            f"ลบชุด {details.name} · {details.subject} · ชั้น {details.grade} ห้อง {details.room} ออกจากรายการตอนนี้หรือไม่?\n"
            f"ภาพ {summary['sources']} ใบ · การตรวจทาน {summary['reviews']} รายการ · ผลลัพธ์ {summary['exports']} ชุด\n"
            "แอปจะซ่อนข้อมูลที่จัดการอยู่และเก็บไว้ให้กู้คืนได้จากเมนู ‘ข้อสอบที่เก็บถาวร’ "
            "ส่วนผลลัพธ์ที่ export แล้วและไฟล์ต้นฉบับที่ใช้ร่วมกับชุดอื่นจะไม่ถูกลบ",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.application.exams.archive(exam.id)
            self.refresh()
        except (OSError, sqlite3.Error, ValueError) as error:
            QMessageBox.warning(self, "ลบข้อสอบไม่ได้", str(error))

    def show_archived(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("ข้อสอบที่เก็บถาวร · กู้คืนได้")
        dialog.resize(620, 420)
        layout = QVBoxLayout(dialog)
        listing = QListWidget()
        archived = self.application.exams.list_archived()
        for exam in archived:
            details = exam.details
            item = QListWidgetItem(
                f"{details.name} — {details.subject}\nปี {details.academic_year} · "
                f"ชั้น {details.grade} · ห้อง {details.room} · {details.question_count} ข้อ"
            )
            item.setData(Qt.ItemDataRole.UserRole, exam)
            listing.addItem(item)
        layout.addWidget(listing)
        restore = QPushButton("กู้คืนข้อสอบที่เลือก")
        restore.clicked.connect(lambda: self.restore_archived(dialog, listing))
        layout.addWidget(restore)
        close = QPushButton("ปิด")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def restore_archived(self, dialog: QDialog, listing: QListWidget) -> None:
        item = listing.currentItem()
        if item is None:
            return
        try:
            self.application.exams.restore(item.data(Qt.ItemDataRole.UserRole).id)
            self.refresh()
            dialog.accept()
        except (OSError, sqlite3.Error, ValueError) as error:
            QMessageBox.warning(self, "กู้คืนไม่ได้", str(error))

    def open_exam(self) -> None:
        item = self.exam_list.currentItem()
        if item is None:
            return
        from exam_grader.exam_ui import ExamDialog

        ExamDialog(self.application, item.data(Qt.ItemDataRole.UserRole), self).exec()

    def create_exam(self) -> None:
        dialog = NewExamDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.application.exams.create(dialog.details)
            self.refresh()
        except (OSError, sqlite3.Error):
            QMessageBox.critical(self, "บันทึกไม่ได้", "กรุณาตรวจสอบพื้นที่ว่างและสิทธิ์โฟลเดอร์ข้อมูล")
