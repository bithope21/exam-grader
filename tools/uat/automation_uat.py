"""Fresh six-sheet automatic workflow, plus explicitly injected review defects."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.exam_ui import BatchWorker, ExamDialog
from exam_grader.exporting import export_results
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.review_ui import ReviewDialog
from exam_grader.ui import MainWindow, NewExamDialog
from exam_grader.workflow import Workflow
from tools.uat.polish_uat import capture, settle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    truth = json.loads(Path("docs/evidence/automation/teacher-run.json").read_text())
    fixtures = Path("tests/fixtures/real")
    original_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures.iterdir()}
    qt = QApplication.instance() or QApplication([])
    qt.setApplicationName("Exam Grader · Automation UAT")
    app = initialize(Path(tempfile.mkdtemp(prefix="exam-grader-automation-")))
    exam = app.exams.create(ExamDetails("อัตโนมัติ 6 ใบ", "2569", "ม.4", "1", "eng", 30, 5))
    flow = Workflow(app.exams.path)
    service = ReviewService(app.exams.path)
    importer = ImportService(app.exams.path)
    app.exams.set_output_root(exam.id, out / "exports")
    for purpose, paths in (("key", [fixtures / "key.JPG"]), ("student", sorted(fixtures.glob("IMG*")))):
        worker = BatchWorker(app.exams.path, exam.id, paths, purpose)
        worker.start()
        assert worker.wait(90000)
        assert not importer.list_failures(exam.id)
    key = flow.current_key(exam.id)
    assert key["origin"] == "machine"
    assert key["answers"] == truth["key"]["answers"]
    dialog = ExamDialog(app, exam)
    dialog.tabs.setCurrentIndex(1)
    dialog.show()
    settle()
    dialog.grab().save(str(out / "students-before-bulk.png"))
    dialog.adopt_button.click()
    settle()
    assert not service.issues(exam.id)
    snapshot = flow.snapshot(exam.id)
    references = {r["source"]["sha256"]: r for r in truth["results"]}
    comparison = []
    for result in snapshot["results"]:
        expected = references[result["source"]["sha256"]]
        assert result["answers"] == expected["answers"]
        assert result["score"] == expected["score"]
        assert result["student_number"] == expected["student_number"]
        assert result["decision_origin"] == "machine_with_teacher_identity"
        comparison.append({"filename": result["source"]["original_name"], "number": result["student_number"],
                           "exact_answers": 30, "score": result["score"], "unresolved": 0})
    final = export_results(flow, exam.id, out / "exports")
    dialog.refresh()
    dialog.grab().save(str(out / "students-ready.png"))
    dialog.tabs.setCurrentIndex(2)
    dialog.grab().save(str(out / "review-empty.png"))
    key_source = next(s for s in importer.list_sources(exam.id) if s["purpose"] == "key")
    key_dialog = ReviewDialog(app.exams.path, key_source)
    ui = capture(key_dialog, out, "key-automatic")
    key_dialog.close()
    new_dialog = NewExamDialog(MainWindow(app))
    new_dialog.show()
    settle()
    new_dialog.grab().save(str(out / "new-exam.png"))
    new_dialog.close()
    # Separate exam: one deliberately uncertain question and two missing numbers.
    injected = app.exams.create(ExamDetails("ทดสอบแก้เฉพาะจุด", "2569", "ม.4", "1", "eng", 30, 3))
    for purpose, paths in (("key", [fixtures / "key.JPG"]), ("student", [fixtures / "IMG_0791.JPG"])):
        worker = BatchWorker(app.exams.path, injected.id, paths, purpose)
        worker.start()
        assert worker.wait(90000)
    source = next(s for s in importer.list_sources(injected.id) if s["purpose"] == "student")
    detection = flow.latest_detection(source["id"])
    detection["answers"][6].update(auto_resolved=False, classification="uncertain", decision_reason="injected-ui-test-only")
    flow.save_detection(source["id"], detection)
    state = service.state(source)
    service.set_number(source, "1", expected_detection=state["detection_id"])
    review = ExamDialog(app, injected)
    review.tabs.setCurrentIndex(2)
    review.resize(1024, 768)
    review.show()
    settle()
    assert len(review.issue_rows) == 3
    review.grab().save(str(out / "review-inline-1024.png"))
    review.resize(1440, 900)
    settle()
    review.grab().save(str(out / "review-inline-1440.png"))
    assert review.issue_table.horizontalScrollBar().maximum() == 0
    # Exercise the actual row controls; no ReviewDialog is opened.
    for kind, number, value in (("attendance", "2", "absent"), ("attendance", "3", "excused"), ("answer", "1", "C")):
        row = next(i for i, issue in enumerate(review.issue_rows) if issue["kind"] == kind and issue["number"] == number)
        editor = review.issue_table.cellWidget(row, 3)
        editor.setCurrentIndex(editor.findData(value))
        review.issue_table.cellWidget(row, 4).click()
        settle()
    assert not service.issues(injected.id)
    attendance_run = export_results(flow, injected.id, out / "status-exports")
    report = {"data_dir": str(app.data_dir), "platform": QApplication.platformName(), "key_exact": 30,
              "student_comparisons": comparison, "total_exact": 180, "unresolved_answers": 0,
              "identity_bulk_clicks": 1, "answer_review_clicks": 0, "output": str(final), "ui": ui,
              "injected_inline_review_pass": True, "attendance_output": str(attendance_run),
              "original_hashes_unchanged": original_hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures.iterdir()}}
    assert report["original_hashes_unchanged"]
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
    review.close()
    dialog.close()


if __name__ == "__main__":
    main()
