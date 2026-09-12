"""Comprehensive Visual QA inspection across Light and Dark themes for all primary screens and dialogs."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.calibration_ui import CalibrationDialog
from exam_grader.domain import ExamDetails
from exam_grader.exam_ui import ExamDialog
from exam_grader.identity import observe
from exam_grader.imaging import analyze
from exam_grader.imports import ImportService
from exam_grader.preferences import apply_appearance_theme, save_appearance_mode
from exam_grader.review_ui import ReviewDialog
from exam_grader.settings_ui import TemplateSettingsDialog
from exam_grader.template_manager import load_builtin_template
from exam_grader.ui import MainWindow, NewExamDialog, TrashDialog
from exam_grader.workflow import Workflow


def run_visual_qa(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_data = output_dir / "app_data"
    if temp_data.exists():
        shutil.rmtree(temp_data, ignore_errors=True)

    qapp = QApplication.instance() or QApplication([])

    # Setup sample database with exams
    app = initialize(temp_data)

    # 1. Active exam with Default #3
    exam3 = app.exams.create(
        ExamDetails(
            name="ศิลปะ-ดนตรี สุทธิอนุสรณ์ 30 ข้อ",
            academic_year="2569",
            grade="ป.4",
            room="6",
            subject="ศิลปะ",
            question_count=30,
            template_id="default-3",
            template_version=1,
        )
    )

    # 2. Archived exam for Trash
    archived_exam = app.exams.create(
        ExamDetails(
            name="ประวัติศาสตร์ ม.2 ภาคเรียนที่ 1",
            academic_year="2568",
            grade="ม.2",
            room="3",
            subject="ประวัติศาสตร์",
            question_count=30,
            template_id="default-1",
            template_version=1,
        )
    )
    app.exams.archive(archived_exam.id)

    # 3. Setup Vol.6 sheet & detection for ReviewDialog
    t3 = load_builtin_template("default-3")
    importer = ImportService(app.exams.path)
    flow = Workflow(app.exams.path)
    vol6_dir = Path("tests/fixtures/real/vol.6")

    key_src = importer.import_file(exam3.id, vol6_dir / "key.JPG", "key")
    key_res = analyze(importer.verified_bytes(key_src), template_def=t3)
    flow.save_detection(key_src["id"], key_res)
    key_answers = [a["selected"][0] if a["selected"] else "A" for a in key_res["answers"]]
    flow.approve_key(exam3.id, key_answers, key_src["id"])

    student_src = importer.import_file(exam3.id, vol6_dir / "IMG_0911.JPG", "student")
    student_res = analyze(importer.verified_bytes(student_src), template_def=t3)
    obs = observe(
        importer.verified_bytes(student_src),
        student_res["registration"]["matrix"],
        template_def=t3,
        app_data_dir=app.exams.path.parent,
    )
    student_res["student_number_observation"] = obs
    flow.save_detection(student_src["id"], student_res)

    for mode in ("light", "dark"):
        print(f"\n--- Generating Visual QA for theme: {mode.upper()} ---")
        save_appearance_mode(mode)
        apply_appearance_theme(qapp, mode)
        qapp.processEvents()

        main_win = MainWindow(app)
        main_win.resize(1080, 720)
        main_win.show()
        qapp.processEvents()

        # 1. Create Exam Dialog
        new_dlg = NewExamDialog(main_win)
        new_dlg.show()
        qapp.processEvents()
        new_dlg.grab().save(str(output_dir / f"01_create_exam_dialog_{mode}.png"))
        print(f"  [✓] Saved 01_create_exam_dialog_{mode}.png")
        new_dlg.close()

        # 2. Trash Dialog
        trash_dlg = TrashDialog(main_win)
        trash_dlg.resize(640, 440)
        trash_dlg.show()
        qapp.processEvents()
        trash_dlg.grab().save(str(output_dir / f"02_trash_dialog_{mode}.png"))
        print(f"  [✓] Saved 02_trash_dialog_{mode}.png")
        trash_dlg.close()

        # 3. Template Manager Dialog (showing Default #3 selected)
        tmpl_dlg = TemplateSettingsDialog(app, parent=main_win)
        tmpl_dlg.resize(1000, 680)
        tmpl_dlg.show()
        qapp.processEvents()
        if tmpl_dlg.table.rowCount() >= 3:
            tmpl_dlg.table.selectRow(2)
            tmpl_dlg._on_selection_changed()
            qapp.processEvents()
        tmpl_dlg.grab().save(str(output_dir / f"03_template_manager_dialog_{mode}.png"))
        print(f"  [✓] Saved 03_template_manager_dialog_{mode}.png")
        tmpl_dlg.close()

        # 4. Calibration Dialog (Default #3 preloaded)
        calib_dlg = CalibrationDialog(app, edit_template=t3, parent=main_win)
        calib_dlg.show()
        qapp.processEvents()
        calib_dlg.grab().save(str(output_dir / f"04_calibration_dialog_{mode}.png"))
        print(f"  [✓] Saved 04_calibration_dialog_{mode}.png")
        calib_dlg.close()

        # 5. Review Dialog (vol.6 student sheet with OMR answers & number observation)
        review_dlg = ReviewDialog(app.exams.path, student_src, parent=main_win)
        review_dlg.resize(1180, 850)
        review_dlg.show()
        qapp.processEvents()
        review_dlg.grab().save(str(output_dir / f"05_review_dialog_{mode}.png"))
        print(f"  [✓] Saved 05_review_dialog_{mode}.png")
        review_dlg.close()

        # 6. Exam Workspace Window
        ws_win = ExamDialog(app, exam3, parent=main_win)
        ws_win.resize(1180, 780)
        ws_win.show()
        qapp.processEvents()
        ws_win.grab().save(str(output_dir / f"06_exam_workspace_{mode}.png"))
        print(f"  [✓] Saved 06_exam_workspace_{mode}.png")
        ws_win.close()

        # 7. Main Home Window
        main_win.grab().save(str(output_dir / f"07_home_{mode}.png"))
        print(f"  [✓] Saved 07_home_{mode}.png")
        main_win.close()

    print(f"\nAll Visual QA screenshots successfully generated in: {output_dir}")


if __name__ == "__main__":
    out = Path("docs/evidence/visual_qa")
    run_visual_qa(out)
