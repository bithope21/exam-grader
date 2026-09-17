"""Settings UI dialogs for template management and annotation color preferences."""

from __future__ import annotations

from typing import TYPE_CHECKING

import cv2
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from exam_grader.preferences import (
    annotation_colors,
    default_template_id,
    reset_annotation_colors,
    save_annotation_colors,
    save_default_template_id,
)
from exam_grader.template_manager import (
    BUILTIN_TEMPLATE_IDS,
    TemplateDefinition,
    get_reference_image,
    load_builtin_template,
)

if TYPE_CHECKING:
    from exam_grader.app import Application


def bgra_to_hex(bgra: tuple[int, int, int, int]) -> str:
    b, g, r, _a = bgra
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_bgra(hex_str: str) -> tuple[int, int, int, int]:
    h = hex_str.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (b, g, r, 255)


class AnnotationColorSettingsDialog(QDialog):
    """Dialog for customizing checked export annotation mark colors."""

    COLOR_KEYS = [
        ("correct", "คำตอบถูกต้อง (เครื่องหมายถูก)", "#16A34A"),
        ("incorrect", "คำตอบไม่ถูกต้อง (เครื่องหมายกากบาท)", "#DC2626"),
        ("uncertain", "สถานะอื่น / ข้อสงสัย (กล่องเตือน)", "#EAB308"),
        ("score", "ข้อความคะแนนรวม", "#2563EB"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ตั้งค่าสีรอยตรวจและสัญลักษณ์")
        app_icon = QApplication.windowIcon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.resize(560, 440)
        self.current_colors: dict[str, tuple[int, int, int, int]] = annotation_colors()

        layout = QVBoxLayout(self)

        intro = QLabel(
            "กำหนดชุดสีสำหรับเครื่องหมายตรวจ (ถูก, กากบาท, ข้อสงสัย) และข้อความคะแนน "
            "ที่จะบันทึกบนภาพกระดาษคำตอบที่ส่งออก (Export)"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        group = QGroupBox("ชุดสีเครื่องหมาย")
        group_layout = QVBoxLayout(group)

        self.swatch_buttons: dict[str, QPushButton] = {}
        for key, label_text, default_hex in self.COLOR_KEYS:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            row.addWidget(lbl, 1)

            btn = QPushButton()
            btn.setFixedSize(64, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            color_val = self.current_colors.get(key)
            hex_code = bgra_to_hex(color_val) if color_val else default_hex
            self._style_swatch(btn, hex_code)
            btn.clicked.connect(lambda _chk=False, k=key, b=btn: self._choose_color(k, b))
            row.addWidget(btn)
            self.swatch_buttons[key] = btn

            group_layout.addLayout(row)

        layout.addWidget(group)

        # Live sample preview
        preview_group = QGroupBox("ตัวอย่างรอยตรวจบนกระดาษ")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_canvas = QLabel()
        self.preview_canvas.setFixedHeight(90)
        self.preview_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.preview_canvas)
        layout.addWidget(preview_group)

        # Action buttons
        bottom_layout = QHBoxLayout()
        reset_btn = QPushButton("คืนค่าเริ่มต้น")
        reset_btn.clicked.connect(self._reset_defaults)
        bottom_layout.addWidget(reset_btn)
        bottom_layout.addStretch()

        save_btn = QPushButton("บันทึก")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_and_close)
        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)
        bottom_layout.addWidget(save_btn)

        layout.addLayout(bottom_layout)
        self._update_preview()

    def _style_swatch(self, btn: QPushButton, hex_code: str) -> None:
        btn.setStyleSheet(
            f"background-color: {hex_code}; border: 1px solid #999; border-radius: 4px;"
        )
        btn.setToolTip(f"คลิกเพื่อเปลี่ยนสี ({hex_code})")

    def _choose_color(self, key: str, btn: QPushButton) -> None:
        color_val = self.current_colors.get(key)
        hex_code = bgra_to_hex(color_val) if color_val else "#000000"
        initial = QColor(hex_code)
        chosen = QColorDialog.getColor(initial, self, "เลือกสีเครื่องหมาย")
        if chosen.isValid():
            hex_val = chosen.name().upper()
            self.current_colors[key] = hex_to_bgra(hex_val)
            self._style_swatch(btn, hex_val)
            self._update_preview()

    def _reset_defaults(self) -> None:
        reset_annotation_colors()
        self.current_colors = annotation_colors()
        for key, _, default_hex in self.COLOR_KEYS:
            btn = self.swatch_buttons.get(key)
            if btn:
                color_val = self.current_colors.get(key)
                self._style_swatch(btn, bgra_to_hex(color_val) if color_val else default_hex)
        self._update_preview()

    def _update_preview(self) -> None:
        pixmap = QPixmap(500, 80)
        pixmap.fill(QColor(248, 249, 250))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw sample checkmark
        c_correct = self.current_colors.get("correct", (40, 180, 40, 255))
        correct_color = QColor(bgra_to_hex(c_correct))
        pen = QPen(correct_color, 3)
        painter.setPen(pen)
        painter.drawLine(30, 42, 45, 58)
        painter.drawLine(45, 58, 70, 25)

        painter.setPen(QPen(QColor("#333333"), 1))
        painter.setFont(QFont("Arial", 10))
        painter.drawText(22, 74, "ถูกต้อง")

        # Draw sample crossmark
        c_incorrect = self.current_colors.get("incorrect", (40, 40, 220, 255))
        incorrect_color = QColor(bgra_to_hex(c_incorrect))
        pen = QPen(incorrect_color, 3)
        painter.setPen(pen)
        painter.drawLine(120, 28, 150, 58)
        painter.drawLine(150, 28, 120, 58)

        painter.setPen(QPen(QColor("#333333"), 1))
        painter.drawText(117, 74, "ผิด")

        # Draw sample uncertain box
        c_unc = self.current_colors.get("uncertain", (0, 165, 255, 255))
        uncertain_color = QColor(bgra_to_hex(c_unc))
        pen = QPen(uncertain_color, 3)
        painter.setPen(pen)
        painter.drawRect(205, 28, 30, 30)

        painter.setPen(QPen(QColor("#333333"), 1))
        painter.drawText(192, 74, "ข้อสงสัย")

        # Draw sample score text
        c_score = self.current_colors.get("score", (180, 90, 20, 255))
        score_color = QColor(bgra_to_hex(c_score))
        painter.setPen(QPen(score_color, 1))
        painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        painter.drawText(310, 50, "48 / 60")

        painter.setPen(QPen(QColor("#333333"), 1))
        painter.setFont(QFont("Arial", 10, QFont.Weight.Normal))
        painter.drawText(315, 74, "คะแนนรวม")

        painter.end()
        self.preview_canvas.setPixmap(pixmap)

    def _save_and_close(self) -> None:
        save_annotation_colors(self.current_colors)
        self.accept()


class TemplateSettingsDialog(QDialog):
    """Dialog for listing, setting default, duplicating, testing, and deleting templates."""

    def __init__(self, application: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.application = application
        self.setWindowTitle("จัดการรูปแบบกระดาษคำตอบ")
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
            w = min(960, max(600, avail.width() - 32))
            h = min(620, max(440, avail.height() - 48))
            self.setMinimumSize(min(600, avail.width() - 16), min(420, avail.height() - 32))
            self.resize(w, h)
            x = avail.x() + max(0, (avail.width() - w) // 2)
            y = avail.y() + max(0, (avail.height() - h) // 2)
            self.setGeometry(x, y, w, h)
        else:
            self.resize(960, 620)
            self.setMinimumSize(600, 420)

        self.selected_template: TemplateDefinition | None = None
        self.templates_list: list[TemplateDefinition] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        header = QLabel("รูปแบบกระดาษคำตอบทั้งหมด")
        header.setProperty("role", "section-title")
        main_layout.addWidget(header)

        desc = QLabel(
            "ระบบรองรับกระดาษคำตอบมาตรฐานในตัว (Default #1, Default #2, Default #3) "
            "และสามารถสร้างหรือนำเข้าแม่แบบกำหนดเองเพิ่มเติมได้\n"
            "แม่แบบเริ่มต้นจะถูกเลือกเป็นค่าตั้งต้นเวลาสร้างข้อสอบชุดใหม่"
        )
        desc.setWordWrap(True)
        desc.setProperty("role", "muted")
        main_layout.addWidget(desc)

        # Responsive Splitter: Left (List navigation) vs Right (Main details & actions)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left pane: Template list navigation
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["ชื่อแม่แบบ", "ชนิด"])
        self.table.setColumnWidth(1, 95)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.table, 1)

        # Left action buttons
        btn_row = QVBoxLayout()
        btn_row.setSpacing(6)
        self.set_default_btn = QPushButton("ตั้งเป็นค่าเริ่มต้น")
        self.set_default_btn.clicked.connect(self._set_as_default)
        btn_row.addWidget(self.set_default_btn)

        self.add_custom_btn = QPushButton("สร้างแม่แบบใหม่จากภาพ…")
        self.add_custom_btn.setToolTip(
            "นำเข้าภาพกระดาษคำตอบเปล่าเพื่อวิเคราะห์หรือปรับเทียบ (Calibration) เป็นแม่แบบใหม่"
        )
        self.add_custom_btn.clicked.connect(self._create_new_template)
        btn_row.addWidget(self.add_custom_btn)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left_widget)

        # Right pane: Detail card, Preview, and Action controls (Main area)
        right_widget = QWidget()
        self.right_layout = QVBoxLayout(right_widget)
        self.right_layout.setContentsMargins(12, 0, 0, 0)
        self.right_layout.setSpacing(10)

        self.detail_title = QLabel("รายละเอียดแม่แบบ")
        self.detail_title.setProperty("role", "section-title")
        self.right_layout.addWidget(self.detail_title)

        self.detail_info = QLabel("เลือกรูปแบบกระดาษคำตอบทางด้านซ้ายเพื่อดูรายละเอียด")
        self.detail_info.setWordWrap(True)
        self.detail_info.setProperty("role", "body")
        self.right_layout.addWidget(self.detail_info)

        # Preview Container
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_image_lbl = QLabel()
        self.preview_image_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image_lbl.setFixedHeight(230)
        self.preview_image_lbl.setProperty("role", "preview")
        preview_layout.addWidget(self.preview_image_lbl)
        self.right_layout.addWidget(preview_container)

        # Action buttons for selected template
        actions_group = QGroupBox("การดำเนินการกับแม่แบบที่เลือก")
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setSpacing(8)

        self.duplicate_btn = QPushButton("สร้างแม่แบบใหม่จากแม่แบบนี้…")
        self.duplicate_btn.setToolTip("สร้างแม่แบบกำหนดเองใหม่โดยใช้แม่แบบนี้เป็นฐาน")
        self.duplicate_btn.clicked.connect(self._duplicate_template)
        actions_layout.addWidget(self.duplicate_btn)

        self.test_omr_btn = QPushButton("ทดสอบตรวจภาพ…")
        self.test_omr_btn.setToolTip("ทดสอบตรวจจับและอ่านรอยกากับภาพกระดาษคำตอบจริง")
        self.test_omr_btn.clicked.connect(self._test_sheet_omr)
        actions_layout.addWidget(self.test_omr_btn)

        self.edit_btn = QPushButton("แก้ไข/ปรับเทียบ…")
        self.edit_btn.setToolTip("เปิดหน้าต่างปรับเทียบเพื่อแก้ไขพิกัดแม่แบบนี้")
        self.edit_btn.clicked.connect(self._edit_template)
        actions_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("ลบแม่แบบ…")
        self.delete_btn.setProperty("destructive", True)
        self.delete_btn.clicked.connect(self._delete_template)
        actions_layout.addWidget(self.delete_btn)

        self.right_layout.addWidget(actions_group)
        self.right_layout.addStretch()

        splitter.addWidget(right_widget)
        # Left pane takes ~35%, Right pane takes ~65%
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        main_layout.addWidget(splitter, 1)

        # Bottom bar
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        close_btn = QPushButton("ปิด")
        close_btn.clicked.connect(self.accept)
        bottom_bar.addWidget(close_btn)
        main_layout.addLayout(bottom_bar)

        self.refresh_templates()

    def refresh_templates(self, select_id: str | None = None) -> None:
        """Load all built-in and stored templates and populate table."""
        self.templates_list = []
        for b_id in BUILTIN_TEMPLATE_IDS:
            try:
                self.templates_list.append(load_builtin_template(b_id))
            except Exception:
                pass

        # Custom from DB
        try:
            custom_templates = self.application.exams.list_templates()
            for t in custom_templates:
                if t.template_id not in BUILTIN_TEMPLATE_IDS:
                    self.templates_list.append(t)
        except Exception:
            pass

        current_def = default_template_id()
        target_id = select_id or getattr(self, "last_created_template_id", None) or (
            self.selected_template.template_id if getattr(self, "selected_template", None) else current_def
        )

        self.table.setRowCount(len(self.templates_list))
        selected_row = 0
        for row_idx, t in enumerate(self.templates_list):
            is_default = t.template_id == current_def
            display_name = f"⭐ {t.name}" if is_default else t.name
            name_item = QTableWidgetItem(display_name)
            if is_default:
                name_item.setForeground(QColor("#2563EB"))
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)

            kind_str = "ในตัว" if t.kind == "builtin" else "กำหนดเอง"
            kind_item = QTableWidgetItem(kind_str)
            kind_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            for item in (name_item, kind_item):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(row_idx, 0, name_item)
            self.table.setItem(row_idx, 1, kind_item)
            if t.template_id == target_id:
                selected_row = row_idx

        if self.templates_list:
            self.table.selectRow(selected_row)
            self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_template = None
            self.detail_title.setText("รายละเอียดแม่แบบ")
            self.detail_info.setText("เลือกรูปแบบกระดาษคำตอบทางด้านซ้าย")
            self.preview_image_lbl.clear()
            self.set_default_btn.setEnabled(False)
            self.duplicate_btn.setEnabled(False)
            self.edit_btn.setEnabled(False)
            self.test_omr_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return

        row = selected_rows[0].row()
        t = self.templates_list[row]
        self.selected_template = t

        is_def = t.template_id == default_template_id()
        self.set_default_btn.setEnabled(not is_def)
        self.duplicate_btn.setEnabled(True)
        self.test_omr_btn.setEnabled(True)
        self.edit_btn.setEnabled(t.kind != "builtin")
        self.delete_btn.setEnabled(t.kind != "builtin")
        if t.kind == "builtin":
            self.edit_btn.setToolTip(
                "แม่แบบมาตรฐานในตัวเป็นแบบอ่านอย่างเดียว หากต้องการแก้ไขให้กด 'สร้างแม่แบบใหม่จากแม่แบบนี้…'"
            )
            self.delete_btn.setToolTip("ไม่สามารถลบแม่แบบมาตรฐานในตัว (Built-in) ได้")
        else:
            self.edit_btn.setToolTip("เปิดหน้าต่างปรับเทียบเพื่อแก้ไขพิกัดแม่แบบนี้")
            self.delete_btn.setToolTip("ลบแม่แบบกำหนดเองนี้")

        # Display clean hierarchical details
        blocks_desc = f"{len(t.answer_blocks)} ชุด"
        if t.answer_blocks:
            b0 = t.answer_blocks[0]
            blocks_desc += f" (ชุดละ {b0.rows} ข้อ, {b0.choice_count} ตัวเลือก)"

        display_labels = ", ".join(t.display_choice_labels)
        canonical_labels = ", ".join(t.choice_labels)

        self.detail_title.setText(t.name)
        kind_badge = "ในตัว (Built-in) · มาตรฐานระบบ" if t.kind == "builtin" else "กำหนดเอง (Custom)"
        default_badge = " · ⭐ ค่าเริ่มต้นปัจจุบัน" if is_def else ""

        info_text = (
            f"<b>ชนิดแม่แบบ:</b> {kind_badge}{default_badge}<br>"
            f"<b>รหัสแม่แบบ (ID):</b> <code>{t.template_id}</code> (v{t.version})<br>"
            f"<b>โครงสร้าง:</b> {t.question_count} ข้อ · {t.choice_count} ตัวเลือก · {blocks_desc}<br>"
            f"<b>การแมปตัวเลือก:</b> {display_labels} → {canonical_labels}<br>"
            f"<b>ขนาดภาพอ้างอิง:</b> {t.canonical_width} × {t.canonical_height} px<br>"
            f"<b>ช่องเลขประจำตัว:</b> {'ตรวจจับอัตโนมัติ' if t.student_number_roi else 'ไม่มี'}&nbsp;&nbsp;&nbsp;&nbsp;"
            f"<b>พิมพ์คะแนน:</b> {'ในช่องคะแนนรวม' if t.score_roi else 'ไม่มี'}"
        )
        self.detail_info.setText(info_text)

        # Load thumbnail
        try:
            ref_bgr = get_reference_image(t, self.application.data_dir)
            rgb = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qimg)
            scaled = pix.scaled(
                QSize(320, 220),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_image_lbl.setPixmap(scaled)
        except Exception as e:
            self.preview_image_lbl.setText(f"ไม่สามารถโหลดภาพอ้างอิง: {e}")

    def _set_as_default(self) -> None:
        if not self.selected_template:
            return
        save_default_template_id(self.selected_template.template_id)
        self.refresh_templates()

    def _create_new_template(self) -> None:
        from exam_grader.calibration_ui import CalibrationDialog

        dialog = CalibrationDialog(self.application, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            created_id = getattr(dialog, "saved_template_id", None)
            if created_id:
                self.last_created_template_id = created_id
            self.refresh_templates(select_id=created_id)

    def _duplicate_template(self) -> None:
        if not self.selected_template:
            return
        from exam_grader.calibration_ui import CalibrationDialog

        dialog = CalibrationDialog(
            self.application,
            duplicate_from=self.selected_template,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_templates()

    def _edit_template(self) -> None:
        if not self.selected_template or self.selected_template.kind == "builtin":
            return
        from exam_grader.calibration_ui import CalibrationDialog

        dialog = CalibrationDialog(
            self.application,
            edit_template=self.selected_template,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_templates()

    def _test_sheet_omr(self) -> None:
        if not self.selected_template:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "เลือกภาพกระดาษคำตอบเพื่อทดสอบการอ่าน",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp)",
        )
        if not file_path:
            return

        from exam_grader.imaging import analyze

        try:
            image_bytes = open(file_path, "rb").read()
            res = analyze(
                image_bytes,
                template_def=self.selected_template,
                app_data_dir=self.application.data_dir,
            )
            reg = res["registration"]
            answers = res["answers"]
            single_count = sum(1 for a in answers if a["classification"] == "single_mark")
            blank_count = sum(1 for a in answers if a["classification"] == "blank")
            multi_count = sum(1 for a in answers if a["classification"] == "multiple")
            uncertain_count = sum(1 for a in answers if a["classification"] == "uncertain")

            msg = (
                f"ผลการทดสอบกับภาพ: {file_path.split('/')[-1]}\n\n"
                f"• การวางตำแหน่งกระดาษ (Table coverage): {reg.get('table_coverage', 0.0):.1%}\n"
                f"• คำตอบที่ตรวจพบ (มีกา 1 ตัวเลือก): {single_count} ข้อ\n"
                f"• ข้อว่าง: {blank_count} ข้อ\n"
                f"• ข้อกาซ้ำ (Multiple): {multi_count} ข้อ\n"
                f"• ข้อสงสัย (Uncertain): {uncertain_count} ข้อ\n"
                f"• ต้องการให้ครูตรวจทาน (Requires review): {'ใช่' if res.get('requires_review') else 'ไม่ใช่'}"
            )
            QMessageBox.information(self, "ผลการทดสอบ OMR", msg)
        except Exception as e:
            QMessageBox.critical(self, "เกิดข้อผิดพลาดในการทดสอบ", f"ไม่สามารถประมวลผลภาพได้: {e}")

    def _delete_template(self) -> None:
        if not self.selected_template or self.selected_template.kind == "builtin":
            return
        tid = self.selected_template.template_id

        if self.application.exams.is_template_referenced(tid):
            QMessageBox.warning(
                self,
                "ไม่สามารถลบแม่แบบได้",
                "แม่แบบนี้ถูกใช้งานอยู่ในข้อสอบที่มีอยู่แล้ว เพื่อความถูกต้องของผลการตรวจย้อนหลัง จึงไม่สามารถลบได้",
            )
            return

        confirm = QMessageBox.question(
            self,
            "ยืนยันการลบแม่แบบ",
            f"คุณแน่ใจหรือไม่ว่าต้องการลบแม่แบบ '{self.selected_template.name}'?\n"
            "การกระทำนี้ไม่สามารถย้อนกลับได้",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.application.exams.delete_template(tid)
            if default_template_id() == tid:
                save_default_template_id("default-1")
            self.refresh_templates()
        except Exception as e:
            QMessageBox.warning(self, "ลบแม่แบบไม่สำเร็จ", str(e))
