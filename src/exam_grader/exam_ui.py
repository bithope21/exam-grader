"""Teacher workflow, background processing, review queue, and result export."""

from datetime import datetime
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from exam_grader.exporting import export_results
from exam_grader.identity import observe as observe_student_number
from exam_grader.imaging import OMR_PIPELINE_VERSION, analyze, decode, template
from exam_grader.imports import ImportService
from exam_grader.preferences import default_output_root
from exam_grader.review_service import ReviewService
from exam_grader.review_ui import ReviewDialog
from exam_grader.workflow import Workflow


class BatchWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(list)

    def __init__(self, database, exam_id, paths, purpose, parent=None):
        super().__init__(parent)
        self.database, self.exam_id, self.paths, self.purpose = database, exam_id, paths, purpose

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
        for index, path in enumerate(self.paths):
            if self.isInterruptionRequested():
                break
            try:
                source = importer.import_file(self.exam_id, path, self.purpose)
                existing = flow.latest_detection(source["id"])
                if existing is None or existing.get("pipeline_version") != OMR_PIPELINE_VERSION:
                    try:
                        observation = analyze(importer.verified_bytes(source))
                    except ValueError as error:
                        observation = {
                            "requires_review": True,
                            "failure": str(error),
                            "pipeline_version": "draft-omr-v2",
                        }
                    if self.purpose == "student" and "failure" not in observation:
                        try:
                            observation["student_number_observation"] = observe_student_number(
                                importer.verified_bytes(source),
                                observation.get("registration", {}).get("matrix"),
                            )
                        except (ValueError, OSError):
                            observation["student_number_observation"] = {
                                "candidate": None,
                                "confidence": None,
                                "review_reason": "student-number observation unavailable",
                            }
                    flow.save_detection(source["id"], observation)
                importer.clear_failure(self.exam_id, path, self.purpose)
            except Exception as error:
                importer.record_failure(self.exam_id, path, self.purpose, str(error))
                failures.append(f"{path.name}: {error}")
            self.progress.emit(index + 1, len(self.paths), path.name)
        try:
            service = ReviewService(self.database)
            service.finalize(self.exam_id)
        except Exception as error:
            failures.append(f"ประมวลผลอัตโนมัติไม่สำเร็จ: {error}")
        self.completed.emit(failures)


class ExportWorker(QThread):
    completed = Signal(str, str)

    def __init__(self, database, exam_id, output_root, parent=None):
        super().__init__(parent)
        self.database, self.exam_id, self.output_root = database, exam_id, output_root

    def run(self):
        try:
            path = export_results(
                Workflow(self.database), self.exam_id, output_root=self.output_root
            )
            self.completed.emit(str(path), "")
        except Exception as error:
            self.completed.emit("", str(error))


class ExamDialog(QDialog):
    def __init__(self, application, exam, parent=None):
        super().__init__(parent)
        self.application, self.exam = application, exam
        self.flow = Workflow(application.exams.path)
        self.review_service = ReviewService(application.exams.path)
        self.importer = ImportService(application.exams.path)
        self.worker = None
        self.output_root = application.exams.output_root(exam.id) or default_output_root()
        self.student_sort_desc = False
        self.setWindowTitle(f"{exam.details.name} · Exam Grader")
        self.resize(1100, 760)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

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
        key_actions.addStretch()
        key_page.addLayout(key_actions)
        key_page.addWidget(self.key_list)

        student_page = QVBoxLayout()
        student_actions = QHBoxLayout()
        self.student_button = QPushButton("＋ เพิ่มกระดาษคำตอบ")
        student_menu = QMenu(self.student_button)
        student_menu.addAction("เลือกไฟล์…", self.pick_student_files)
        student_menu.addAction("เลือกโฟลเดอร์…", self.pick_folder)
        self.student_button.setMenu(student_menu)
        student_actions.addWidget(self.student_button)
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
        review_page.addWidget(QLabel("แก้เฉพาะข้อมูลที่มีปัญหา แล้วกดบันทึกที่แถวนั้น · เรียงเลขที่น้อย → มาก"))
        self.issue_table = QTableWidget(0, 5)
        self.issue_table.setHorizontalHeaderLabels(["เลขที่", "ข้อมูลที่ต้องแก้", "ภาพ", "คำตอบ / สถานะ", "บันทึก"])
        self.issue_table.verticalHeader().hide()
        self.issue_table.setAlternatingRowColors(True)
        header = self.issue_table.horizontalHeader()
        for column in (0, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.issue_table.cellDoubleClicked.connect(self.open_issue_source)
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
        self.export_button = QPushButton("บันทึกผลตรวจ + Excel")
        self.export_button.setMinimumWidth(190)
        self.export_button.setToolTip("สร้าง snapshot ใหม่ของผลตรวจ ภาพตรวจแล้ว และไฟล์ Excel")
        self.export_button.clicked.connect(self.export)
        output_actions.addWidget(self.output_button)
        output_actions.addWidget(self.export_button)
        output_actions.addStretch()
        results_page.addLayout(output_actions)
        history_actions = QHBoxLayout()
        self.export_history = QComboBox()
        self.export_history.setMinimumContentsLength(24)
        self.export_history.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
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
        ]
        self.issue_drafts = {}
        self.issue_dirty = set()
        self.refresh()

    @staticmethod
    def _item(text: str, data: dict) -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, data)
        return item

    def _add_student_item(self, text: str, source: dict) -> None:
        item = self._item(text, source)
        item.setToolTip(text)
        self.student_list.addItem(item)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.addStretch()
        remove = QPushButton("ลบ")
        remove.setToolTip("เก็บกระดาษนี้แบบกู้คืนได้")
        remove.clicked.connect(lambda _checked=False, value=source: self.archive_student(value))
        row_layout.addWidget(remove)
        self.student_list.setItemWidget(item, row)
        item.setSizeHint(row.sizeHint())

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

        records = self.importer.list_sources(self.exam.id)
        failures = self.importer.list_failures(self.exam.id)
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
                candidate["student_number"] = (identity_state["detection"].get("student_number_observation") or {}).get("candidate", "")
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
            active_answers = detection.get("answers", [])[: self.exam.details.question_count] if detection else []
            needs_decision = bool(
                not detection
                or "failure" in detection
                or len(active_answers) < self.exam.details.question_count
                or any(not item.get("auto_resolved") for item in active_answers)
            )
            if review and key and review["key_id"] == key["id"] and source["id"] not in issue_source_ids:
                state = f"พร้อม · เลขที่ {review['student_number']}"
                ready += 1
            elif review:
                state = "ต้องตรวจใหม่ (เฉลยเปลี่ยน)"
                review_count += 1
            elif detection and not needs_decision:
                state = "อ่านได้ครบ · พร้อมยืนยันเลขที่" if not source.get("student_number") else "อ่านได้ครบ · พร้อมยืนยัน"
                prefilled_count += 1
            else:
                state = "ต้องตรวจทาน"
                review_count += 1
            if detection and "failure" in detection:
                state = f"อ่านไม่ได้ · {detection['failure']}"
            number_observation = (detection or {}).get("student_number_observation", {})
            if not review and number_observation.get("candidate"):
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
            self.student_list.addItem(self._item(text, data))
            self.review_list.addItem(self._item(text, data))

        failed_count = len(failures)
        self.status.setText(
            f"{key_message}\nนักเรียน: พร้อม {ready} · พร้อมยืนยัน {prefilled_count} · "
            f"ต้องตรวจ {review_count} · ล้มเหลว {failed_count}"
        )
        if key and ready:
            try:
                missing = self.flow.missing_numbers(self.exam.id)
                if missing["missing_expected"]:
                    self.status.setText(self.status.text() + f"\nเลขที่คาดหวังที่ยังไม่พบ: {missing['missing_expected']}")
                elif missing["missing_internal"]:
                    self.status.setText(self.status.text() + f"\nเลขที่ขาดภายในช่วงที่พบ: {missing['missing_internal']}")
            except ValueError:
                pass
        self.output_label.setText(f"บันทึกผลลัพธ์ที่\n{self.output_root}")
        self.results_summary.setText(
            f"สถานะปัจจุบัน: พร้อม {ready} · พร้อมยืนยัน {prefilled_count} · "
            f"ต้องตรวจ {review_count} · ล้มเหลว {failed_count}\n"
            + ("พร้อมบันทึกผลตรวจ" if key and not current_issues else "ตรวจทานรายการที่ค้างอยู่ก่อนบันทึกผล")
        )
        self.progress_label.setText("พร้อมทำงาน")
        self.export_history.clear()
        for run in self.application.exams.export_runs(self.exam.id):
            path = Path(run["path"])
            timestamp = datetime.fromisoformat(run["created_at"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            label = f"ผลตรวจ · {timestamp}"
            if not path.is_dir():
                label += " · ไม่พบโฟลเดอร์"
            self.export_history.addItem(label, str(path))
        if self.export_history.count() == 0:
            self.export_history.setCurrentIndex(-1)
        self.reveal_button.setEnabled(self.export_history.count() > 0)
        self.populate_issues()
        self.update_key_gate()
        self.adopt_button.setEnabled(any(
            not s["number"]
            and (s["detection"].get("student_number_observation") or {}).get("candidate")
            and (s["detection"].get("student_number_observation") or {}).get("candidates")
            == [(s["detection"].get("student_number_observation") or {}).get("candidate")]
            for s in self.review_service.states(self.exam.id)
        ))
        self.attendance_restore.clear()
        self.attendance_restore.addItem("แก้สถานะขาดสอบที่บันทึกแล้ว…", None)
        with self.flow.connection() as con:
            for row in con.execute("SELECT student_number,status FROM attendance WHERE exam_id=? AND status!='pending' ORDER BY student_number", (self.exam.id,)):
                status = "ขาดสอบ" if row["status"] == "absent" else "ลา / ยกเว้น"
                self.attendance_restore.addItem(f"เลขที่ {row['student_number']} · {status} → ส่งกลับตรวจทาน", str(row["student_number"]))
            for row in con.execute("SELECT student_number FROM skipped_numbers WHERE exam_id=? ORDER BY student_number", (self.exam.id,)):
                self.attendance_restore.addItem(f"เลขที่ {row['student_number']} · ข้ามไว้ → ส่งกลับตรวจทาน", str(row["student_number"]))
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
            self.progress_label.setText(f"ใช้เลขที่แล้ว {len(outcome['applied'])} ใบ · ยังต้องแก้ {len(outcome['skipped'])} ใบ")
            if outcome["skipped"]:
                self.tabs.setCurrentIndex(2)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "ใช้เลขที่ไม่ได้", str(error))

    def archive_selected_student(self):
        item = self.student_list.currentItem()
        source = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.archive_student(source)

    def archive_student(self, source):
        if not source or source.get("purpose") != "student" or not source.get("id"):
            QMessageBox.information(self, "ยังไม่ได้เลือก", "เลือกกระดาษนักเรียนก่อน")
            return
        answer = QMessageBox.question(
            self, "ลบกระดาษแบบกู้คืนได้",
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
        sources = [s for s in self.importer.list_sources(self.exam.id) if s["purpose"] == "student"]
        if not sources:
            QMessageBox.information(self, "ไม่มีภาพนักเรียน", "ยังไม่มีภาพนักเรียนที่ใช้งานอยู่")
            return
        answer = QMessageBox.question(
            self, "ลบกระดาษนักเรียนทั้งหมดแบบกู้คืนได้",
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
        paths = [self.application.exams.path.parent / s["relative_path"]
                 for s in self.importer.list_sources(self.exam.id) if s["purpose"] == "student"]
        self.start_import(paths, "student")

    def populate_issues(self):
        self._capture_issue_drafts()
        self.issue_rows = self.review_service.issues(self.exam.id)
        self.issue_table.clearContents()
        self.skip_missing_button.setVisible(any(i["kind"] == "attendance" and i["source"] is None for i in self.issue_rows))
        self.empty_review.setVisible(not self.issue_rows)
        self.empty_review.setText("ไม่มีข้อมูลที่ต้องแก้ไข" if self.student_list.count() else "เพิ่มเฉลยและภาพนักเรียนเพื่อเริ่มตรวจ")
        self.issue_table.setRowCount(len(self.issue_rows))
        previews = {}
        for row, issue in enumerate(self.issue_rows):
            for column, text in enumerate((issue["number"] or "—", issue["label"], issue["source"]["original_name"] if issue["source"] else "ยังไม่มีภาพ")):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(text)
                if column == 1:
                    item.setBackground(QColor("#fff0cd"))
                    item.setForeground(QColor("#503800"))
                self.issue_table.setItem(row, column, item)
            if issue["source"] and issue["kind"] in {"answer", "number"}:
                try:
                    sid = issue["source"]["id"]
                    geometry = template()
                    if sid not in previews:
                        detection = self.flow.latest_detection(sid)
                        if not detection:
                            raise ValueError("ยังไม่มีผลอ่าน")
                        previews[sid] = cv2.warpPerspective(decode(self.importer.verified_bytes(issue["source"])), np.asarray(detection["registration"]["matrix"]), (geometry["width"], geometry["height"]))
                    if issue["kind"] == "number":
                        x1, y1, x2, y2 = geometry["student_number_roi"]
                        y1 = max(0, y1 - 20)
                    else:
                        q = issue["question"] - 1
                        xs, ys = geometry["groups"][q // 15], geometry["rows"]
                        x1, x2, y1, y2 = xs[0], xs[-1], ys[q % 15], ys[q % 15 + 1]
                    crop = np.ascontiguousarray(previews[sid][y1:y2, x1:x2])
                    picture = QImage(crop.data, crop.shape[1], crop.shape[0], crop.strides[0], QImage.Format.Format_BGR888).copy()
                    preview_label = QLabel()
                    preview_label.setPixmap(QPixmap.fromImage(picture).scaled(230, 62, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    preview_label.setToolTip(issue["source"]["original_name"] + " · ดับเบิลคลิกแถวเพื่อดูทั้งใบ")
                    self.issue_table.setCellWidget(row, 2, preview_label)
                except (ValueError, OSError, KeyError, TypeError):
                    pass
            editor: QLineEdit | QComboBox
            if issue["kind"] == "number":
                editor = QLineEdit(issue.get("candidate") or issue["number"] or "")
                editor.setPlaceholderText("เลขที่")
            else:
                editor = QComboBox()
                options: list[tuple[str, str | None]] = [("— เลือก —", None)]
                if issue["kind"] == "answer":
                    options += [(f"{thai} / {latin}", latin) for thai, latin in zip("กขคงจ", "ABCDE")]
                    options += [("เว้นว่าง", "blank"), ("หลายคำตอบ", "multiple")]
                elif issue["kind"] == "attendance":
                    options += [("รอกระดาษ / ยกเลิกขาดสอบ", "pending"), ("ข้ามเลขที่นี้", "skipped"), ("ขาดสอบ", "absent"), ("ลา / ได้รับยกเว้น", "excused")]
                elif issue["kind"] in {"image", "import"}:
                    options += [("ลองอ่านภาพใหม่", "retry")]
                else:
                    options += [("ใช้คำตอบเดิมกับเฉลยใหม่", "reuse")]
                for label, value in options:
                    editor.addItem(label, value)
                editor.setCurrentIndex(max(0, editor.findData(issue.get("candidate"))))
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
                editor.currentIndexChanged.connect(lambda _index, key=issue_key: self.issue_dirty.add(key))
            self.issue_table.setCellWidget(row, 3, editor)
            button = QPushButton("บันทึก")
            button.clicked.connect(lambda checked=False, i=issue, e=editor: self.save_issue(i, e))
            self.issue_table.setCellWidget(row, 4, button)
        self.issue_table.resizeRowsToContents()

    @staticmethod
    def _issue_key(issue):
        source = issue.get("source") or {}
        failure = issue.get("failure") or {}
        return (source.get("id"), issue.get("kind"), issue.get("question"),
                issue.get("number"), issue.get("key_id"), issue.get("detection_id"),
                failure.get("id") or failure.get("path"))

    def _capture_issue_drafts(self):
        for row, issue in enumerate(getattr(self, "issue_rows", [])):
            editor = self.issue_table.cellWidget(row, 3)
            if editor is None:
                continue
            value = editor.text() if isinstance(editor, QLineEdit) else cast(QComboBox, editor).currentData()
            key = self._issue_key(issue)
            if key in self.issue_dirty:
                self.issue_drafts[key] = value

    def _save_issue_value(self, issue, value):
        if not value:
            raise ValueError("เลือกข้อมูลก่อนบันทึก")
        if issue["kind"] == "number":
            self.review_service.set_number(issue["source"], value, expected_detection=issue["detection_id"])
            self.review_service.finalize(self.exam.id)
        elif issue["kind"] == "answer":
            self.review_service.resolve_answer(issue["source"], issue["question"], value, key_id=issue["key_id"], detection_id=issue["detection_id"])
        elif issue["kind"] == "attendance":
            self.review_service.set_attendance(self.exam.id, issue["number"], value)
        elif issue["kind"] in {"image", "import"}:
            raise ValueError("กู้คืนภาพต้องกดจากรายการนั้นโดยตรง")
        else:
            state = self.review_service.state(issue["source"])
            self.flow.review(issue["source"]["id"], state["number"], state["review"]["answers"], issue["key_id"], origin="teacher", detection_id=issue["detection_id"])

    def save_issue(self, issue, editor):
        try:
            value = editor.text() if isinstance(editor, QLineEdit) else cast(QComboBox, editor).currentData()
            if issue["kind"] in {"image", "import"}:
                if value != "retry":
                    raise ValueError("เลือก ‘ลองอ่านภาพใหม่’ ก่อนบันทึก")
                source = issue["source"]
                path = self.application.exams.path.parent / source["relative_path"] if source else Path(issue["failure"]["path"])
                self.start_import([path], source["purpose"] if source else issue["failure"]["purpose"])
                return
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
            editor = self.issue_table.cellWidget(row, 3)
            value = editor.text() if isinstance(editor, QLineEdit) else cast(QComboBox, editor).currentData()
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

    def open_issue_source(self, row, column):
        source = self.issue_rows[row]["source"]
        if source:
            self.open_source(source)

    def reveal_result(self):
        path = self.export_history.currentData()
        if not path or not Path(path).is_dir():
            QMessageBox.warning(self, "เปิดผลลัพธ์ไม่ได้", "ไม่พบโฟลเดอร์ กรุณาเชื่อมต่อไดรฟ์เดิมหรือสร้างผลตรวจใหม่")
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
        self.worker = BatchWorker(self.application.exams.path, self.exam.id, paths, purpose, self)
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
            accepted = ReviewDialog(self.application.exams.path, source, self).exec()
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

    def change_student_sort(self, index):
        self.student_sort_desc = index == 1
        self.refresh()

    @staticmethod
    def _student_sort_key(source):
        value = source.get("student_number", "")
        return int(value) if str(value).isdigit() else 10**9

    def export(self):
        self.worker = ExportWorker(
            self.application.exams.path, self.exam.id, self.output_root, self
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
