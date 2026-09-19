"""Small working desktop shell; only supported actions are exposed."""

import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
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
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyle,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from exam_grader.app import Application
from exam_grader.domain import ExamDetails
from exam_grader.preferences import (
    appearance_mode,
    apply_appearance_theme,
    default_template_id,
    save_appearance_mode,
    save_output_root,
)
from exam_grader.template_manager import (
    BUILTIN_TEMPLATE_IDS,
    TemplateDefinition,
    load_builtin_template,
)

HOME_CAMERA_GUIDANCE_TEXT = (
    "ถ่ายภาพกระดาษคำตอบ\n"
    "• ให้เห็นมุมกระดาษครบทั้ง 4 มุม บนพื้นหลังที่ตัดกับกระดาษ\n"
    "• ถือกล้องขนานกับกระดาษ และหลีกเลี่ยงเงาหรือแสงสะท้อน\n"
    "• ไม่ต้องครอปภาพ ระบบจะจัดแนวจากมุมกระดาษ"
)


class NewExamDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, application: Application | None = None):
        super().__init__(parent)
        self.setWindowTitle("สร้างข้อสอบ")
        if application is None and hasattr(parent, "application"):
            application = getattr(parent, "application")
        self.application = application

        self.setMinimumWidth(500)
        layout = QFormLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setVerticalSpacing(12)
        layout.setHorizontalSpacing(16)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.fields = {}
        for key, label in (
            ("name", "ชื่อข้อสอบ"),
            ("academic_year", "ปีการศึกษา"),
            ("grade", "ชั้น"),
            ("room", "ห้องเริ่มต้น (ไม่บังคับ)"),
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
                    field.addItems(
                        [f"ป.{i}" for i in range(1, 7)] + [f"ม.{i}" for i in range(1, 7)]
                    )
                    field.setToolTip("เลือกชั้น หรือพิมพ์เอง เช่น ปวช.1")
                    field.setMinimumContentsLength(8)
                    field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
                else:
                    field.addItems([""] + [str(i) for i in range(1, 13)])
                    field.setCurrentText("")
                    field.setToolTip("เว้นว่างได้ หรือระบุห้องแรกของข้อสอบ")
                line = field.lineEdit()
                if line:
                    line.setMaxLength(200)
            else:
                field = QLineEdit()
                field.setMaxLength(200)
            self.fields[key] = field
            layout.addRow(label, field)

        self.available_templates: list[TemplateDefinition] = []
        self.template_combo = QComboBox()
        self.manage_template_button = QPushButton("จัดการแม่แบบ…")
        self.manage_template_button.setToolTip("เพิ่ม, ปรับเทียบ (Calibrate), หรือจัดการแม่แบบกระดาษคำตอบ")
        self.manage_template_button.clicked.connect(self._open_template_manager)

        template_row = QHBoxLayout()
        template_row.addWidget(self.template_combo, stretch=1)
        template_row.addWidget(self.manage_template_button)
        layout.addRow("รูปแบบกระดาษคำตอบ", template_row)

        self.question_count = QSpinBox()
        self.question_count.setRange(1, 60)
        self.question_count.setValue(60)
        layout.addRow("จำนวนข้อของข้อสอบ", self.question_count)

        self._load_templates_list()
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)

        self.expected_number_max = QSpinBox()
        self.expected_number_max.setRange(0, 9999)
        self.expected_number_max.setSpecialValueText("ไม่กำหนด")
        self.expected_number_max.setMinimumWidth(110)
        layout.addRow("เลขที่คาดหวังถึง", self.expected_number_max)

        buttons = QDialogButtonBox()
        buttons.addButton("บันทึก", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("ยกเลิก", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _open_template_manager(self) -> None:
        from exam_grader.settings_ui import TemplateSettingsDialog

        if self.application is not None:
            prev_id = (
                self.available_templates[self.template_combo.currentIndex()].template_id
                if 0 <= self.template_combo.currentIndex() < len(self.available_templates)
                else None
            )
            dlg = TemplateSettingsDialog(self.application, self)
            dlg.exec()
            chosen_id = (
                getattr(dlg, "last_created_template_id", None)
                or (dlg.selected_template.template_id if getattr(dlg, "selected_template", None) else None)
                or prev_id
            )
            self._load_templates_list(select_template_id=chosen_id)

    def _load_templates_list(self, select_template_id: str | None = None) -> None:
        self.available_templates = []
        for b_id in BUILTIN_TEMPLATE_IDS:
            try:
                self.available_templates.append(load_builtin_template(b_id))
            except Exception:
                pass
        if self.application is not None:
            try:
                for t in self.application.exams.list_templates():
                    if t.template_id not in BUILTIN_TEMPLATE_IDS:
                        self.available_templates.append(t)
            except Exception:
                pass

        target_id = select_template_id or default_template_id()
        selected_idx = 0
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        for idx, t in enumerate(self.available_templates):
            kind_str = "ในตัว" if t.kind == "builtin" else "กำหนดเอง"
            self.template_combo.addItem(f"{t.name} ({kind_str})")
            if t.template_id == target_id:
                selected_idx = idx

        if self.available_templates:
            self.template_combo.setCurrentIndex(selected_idx)
        self.template_combo.blockSignals(False)
        self._on_template_changed(self.template_combo.currentIndex())

    def _on_template_changed(self, idx: int) -> None:
        if hasattr(self, "question_count") and 0 <= idx < len(self.available_templates):
            t = self.available_templates[idx]
            self.question_count.setMaximum(t.question_count)
            self.question_count.setValue(t.question_count)

    def accept(self) -> None:
        try:
            values = {
                k: v.currentText() if isinstance(v, QComboBox) else v.text()
                for k, v in self.fields.items()
            }
            idx = self.template_combo.currentIndex()
            selected_t = (
                self.available_templates[idx] if 0 <= idx < len(self.available_templates) else None
            )
            tid = selected_t.template_id if selected_t else "default-1"
            tver = selected_t.version if selected_t else 1

            self.details = ExamDetails(
                name=values.get("name", ""),
                academic_year=values.get("academic_year", ""),
                grade=values.get("grade", ""),
                room=values.get("room", ""),
                subject=values.get("subject", ""),
                question_count=self.question_count.value(),
                expected_number_max=self.expected_number_max.value() or None,
                template_id=tid,
                template_version=tver,
            )
        except ValueError as error:
            QMessageBox.warning(self, "ข้อมูลไม่ครบ", str(error))
            return
        super().accept()


class TrashDialog(QDialog):
    def __init__(self, main_window: "MainWindow", parent: QWidget | None = None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.setWindowTitle("ถังขยะ (ข้อสอบที่ลบ)")
        self.resize(640, 440)
        self.setMinimumSize(520, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        notice = QLabel("ข้อสอบในถังขยะสามารถเลือกกู้คืนกลับไปหน้าหลัก หรือลบออกจากระบบอย่างถาวรได้")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.listing = QListWidget()

        self.populate_listing()
        layout.addWidget(self.listing)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.restore_btn = QPushButton("กู้คืนข้อสอบที่เลือก")
        self.restore_btn.clicked.connect(
            lambda: self.main_window.restore_archived(self, self.listing)
        )
        btn_row.addWidget(self.restore_btn)

        self.purge_btn = QPushButton("ลบถาวร…")
        self.purge_btn.setProperty("destructive", True)
        self.purge_btn.clicked.connect(
            lambda: self.main_window._purge_selected(self.listing, self.populate_listing)
        )
        btn_row.addWidget(self.purge_btn)

        btn_row.addStretch()
        self.close_btn = QPushButton("ปิด")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def populate_listing(self) -> None:
        self.listing.clear()
        archived = self.main_window.application.exams.list_archived()
        for ex in archived:
            d = ex.details
            text_desc = (
                f"{d.name} — {d.subject}"
                + chr(10)
                + f"ปี {d.academic_year} · ชั้น {d.grade} · ห้อง {d.room} · {d.question_count} ข้อ"
            )
            it = QListWidgetItem(text_desc)
            it.setData(Qt.ItemDataRole.UserRole, ex)
            self.listing.addItem(it)


class MainWindow(QMainWindow):
    def __init__(self, application: Application):
        super().__init__()
        self.application = application
        self.setWindowTitle("Exam Grader")
        self.resize(780, 540)
        container = QWidget()
        layout = QVBoxLayout(container)

        header_layout = QHBoxLayout()
        title = QLabel("ข้อสอบของคุณ")
        title.setProperty("role", "page-title")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # A QToolButton with InstantPopup makes the whole visible control a
        # reliable menu target on macOS. QPushButton.setMenu() can leave only
        # the small native menu-indicator area responsive in packaged builds.
        self.settings_button = QToolButton()
        self.settings_button.setText("ตั้งค่า")
        self.settings_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.settings_button.setToolTip("ตั้งค่าแม่แบบกระดาษคำตอบ, สีรอยตรวจ และโฟลเดอร์ผลลัพธ์")

        settings_popup = QMenu(self)
        settings_popup.addAction(
            "รูปแบบกระดาษคำตอบ (เพิ่ม/ปรับเทียบ/จัดการแม่แบบ)…", self.open_template_settings
        )
        settings_popup.addAction("สีรอยตรวจและสัญลักษณ์…", self.open_color_settings)
        settings_popup.addSeparator()

        appearance_submenu = settings_popup.addMenu("ธีมการแสดงผล (Appearance)")
        self._populate_appearance_menu(appearance_submenu)

        settings_popup.addSeparator()
        settings_popup.addAction("ตำแหน่งบันทึกผลลัพธ์…", self.choose_output_root)
        settings_popup.addAction("ถังขยะ…", self.show_trash)
        self.settings_button.setMenu(settings_popup)
        header_layout.addWidget(self.settings_button)

        self.camera_help_button = QToolButton()
        self.camera_help_button.setText("ⓘ")
        self.camera_help_button.setFixedSize(36, 36)
        self.camera_help_button.setAutoRaise(True)
        self.camera_help_button.setToolTip(HOME_CAMERA_GUIDANCE_TEXT)
        self.camera_help_button.setAccessibleName("คำแนะนำการถ่ายภาพกระดาษคำตอบ")
        self.camera_help_button.setAccessibleDescription(HOME_CAMERA_GUIDANCE_TEXT)
        self.camera_help_button.setProperty("kind", "icon")
        self.camera_help_button.clicked.connect(self._show_camera_help)
        header_layout.addWidget(self.camera_help_button)

        layout.addLayout(header_layout)
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
        settings_menu.addAction("รูปแบบกระดาษคำตอบ…", self.open_template_settings)
        settings_menu.addAction("สีรอยตรวจและสัญลักษณ์…", self.open_color_settings)
        bar_appearance = settings_menu.addMenu("ธีมการแสดงผล…")
        self._populate_appearance_menu(bar_appearance)
        self.menuBar().addAction("ถังขยะ…", self.show_trash)
        self.refresh()

    def _show_camera_help(self) -> None:
        button = self.camera_help_button
        QToolTip.showText(
            button.mapToGlobal(QPoint(0, button.height())),
            HOME_CAMERA_GUIDANCE_TEXT,
            button,
        )

    def _populate_appearance_menu(self, menu: QMenu) -> None:
        current_mode = appearance_mode()
        from PySide6.QtGui import QAction, QActionGroup

        group = QActionGroup(menu)
        modes = [
            ("system", "ตามระบบ (System)"),
            ("light", "สว่าง (Light)"),
            ("dark", "มืด (Dark)"),
        ]
        for mode_key, mode_label in modes:
            action = QAction(mode_label, menu)
            action.setCheckable(True)
            if mode_key == current_mode:
                action.setChecked(True)
            action.triggered.connect(lambda _chk=False, m=mode_key: self._on_appearance_selected(m))
            group.addAction(action)
            menu.addAction(action)

    def _on_appearance_selected(self, mode: str) -> None:
        from PySide6.QtWidgets import QApplication

        save_appearance_mode(mode)
        apply_appearance_theme(QApplication.instance(), mode)

    def open_template_settings(self) -> None:
        from exam_grader.settings_ui import TemplateSettingsDialog

        TemplateSettingsDialog(self.application, self).exec()

    def open_color_settings(self) -> None:
        from exam_grader.settings_ui import AnnotationColorSettingsDialog

        AnnotationColorSettingsDialog(self).exec()

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
            row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 4, 8, 4)
            row_layout.addStretch()
            remove = QPushButton()
            remove.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
            remove.setIconSize(QSize(16, 16))
            remove.setProperty("kind", "icon")
            remove.setProperty("destructive", True)
            remove.setAccessibleName("ย้ายไปถังขยะ")
            remove.setAccessibleDescription("ย้ายชุดข้อสอบนี้ไปที่ถังขยะ สามารถกู้คืนได้")
            remove.setToolTip("ย้ายชุดนี้ไปที่ถังขยะ · สามารถกู้คืนหรือลบถาวรได้จากเมนูถังขยะ")
            remove.clicked.connect(lambda _checked=False, value=exam: self.archive_exam(value))
            row_layout.addWidget(remove)
            self.exam_list.setItemWidget(item, row)
            item.setSizeHint(QSize(0, 44))

    def archive_exam(self, exam) -> None:
        details = exam.details
        summary = self.application.exams.summary(exam.id)
        answer = QMessageBox.question(
            self,
            "ย้ายไปถังขยะ",
            f"ย้ายชุด {details.name} · {details.subject} · ชั้น {details.grade} ห้อง {details.room} ไปไว้ในถังขยะหรือไม่?\n\n"
            f"ภาพ {summary['sources']} ใบ · การตรวจทาน {summary['reviews']} รายการ · ผลลัพธ์ {summary['exports']} ชุด\n"
            "แอปจะนำชุดนี้ออกจากหน้าหลัก โดยสามารถกู้คืนหรือลบถาวรได้จากเมนู ‘ถังขยะ’",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.application.exams.archive(exam.id)
            self.refresh()
        except (OSError, sqlite3.Error, ValueError) as error:
            QMessageBox.warning(self, "ย้ายไปถังขยะไม่ได้", str(error))

    def show_trash(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("ถังขยะ (ข้อสอบที่ลบ)")
        dialog.resize(640, 440)
        layout = QVBoxLayout(dialog)
        notice = QLabel("ข้อสอบในถังขยะสามารถเลือกกู้คืนกลับไปหน้าหลัก หรือลบออกจากระบบอย่างถาวรได้")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        listing = QListWidget()

        def _populate_listing():
            listing.clear()
            archived = self.application.exams.list_archived()
            for ex in archived:
                d = ex.details
                it = QListWidgetItem(
                    f"{d.name} — {d.subject}\nปี {d.academic_year} · "
                    f"ชั้น {d.grade} · ห้อง {d.room} · {d.question_count} ข้อ"
                )
                it.setData(Qt.ItemDataRole.UserRole, ex)
                listing.addItem(it)

        _populate_listing()
        layout.addWidget(listing)

        btn_row = QHBoxLayout()
        restore_btn = QPushButton("กู้คืนข้อสอบที่เลือก")
        restore_btn.clicked.connect(lambda: self.restore_archived(dialog, listing))
        btn_row.addWidget(restore_btn)

        purge_btn = QPushButton("ลบถาวร…")
        purge_btn.setProperty("destructive", True)
        purge_btn.clicked.connect(lambda: self._purge_selected(listing, _populate_listing))
        btn_row.addWidget(purge_btn)

        btn_row.addStretch()
        close_btn = QPushButton("ปิด")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dialog.exec()

    def show_archived(self) -> None:
        """Alias for backward compatibility."""
        self.show_trash()

    def _purge_selected(self, listing: QListWidget, refresh_callback) -> None:
        item = listing.currentItem()
        if item is None:
            QMessageBox.information(self, "ยังไม่ได้เลือก", "เลือกข้อสอบในถังขยะที่ต้องการลบถาวรก่อน")
            return
        exam = item.data(Qt.ItemDataRole.UserRole)
        details = exam.details
        answer = QMessageBox.question(
            self,
            "ยืนยันการลบถาวร",
            f"ต้องการลบชุด {details.name} · {details.subject} ออกจากระบบอย่างถาวรหรือไม่?\n\n"
            "• ข้อมูลข้อสอบ ประวัติการตรวจทาน และภาพในระบบจะถูกลบถาวร\n"
            "• ไม่สามารถกู้คืนข้อสอบนี้ได้อีก\n"
            "(ไฟล์ผลตรวจ Excel ที่เคยส่งออกไปยังโฟลเดอร์ภายนอกแล้วจะไม่ได้รับผลกระทบ)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.application.exams.purge(exam.id)
            refresh_callback()
            self.refresh()
            QMessageBox.information(self, "ลบสำเร็จ", f"ลบชุด {details.name} อย่างถาวรเรียบร้อยแล้ว")
        except (OSError, sqlite3.Error, ValueError) as error:
            QMessageBox.warning(self, "ลบถาวรไม่ได้", str(error))

    def restore_archived(self, dialog: QDialog, listing: QListWidget) -> None:
        item = listing.currentItem()
        if item is None:
            QMessageBox.information(self, "ยังไม่ได้เลือก", "เลือกข้อสอบที่ต้องการกู้คืนก่อน")
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
