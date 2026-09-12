"""Real-fixture UAT for the supplied 40-question vol.3 photographs.

The reference export is read only after fresh recognition has completed. It is
used for explicit teacher-review actions and comparison evidence; it is never
loaded by the recognition pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.exam_ui import BatchWorker, ExamDialog
from exam_grader.exporting import export_results
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.review_ui import ReviewDialog, key_answer_text
from exam_grader.workflow import Workflow


def settle() -> None:
    loop = QEventLoop()
    QTimer.singleShot(150, loop.quit)
    loop.exec()


def run_worker(database: Path, exam_id: str, paths: list[Path], purpose: str) -> list[str]:
    errors: list[str] = []
    worker = BatchWorker(database, exam_id, paths, purpose)
    worker.completed.connect(errors.extend)
    worker.run()
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    fixture_root = args.fixtures.resolve()
    reference_path = args.reference.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    count = len(reference["key"]["answers"])
    reference_by_hash = {row["source"]["sha256"]: row for row in reference["results"]}
    student_paths = sorted(fixture_root.glob("IMG*"))
    key_paths = sorted(fixture_root.glob("key.*"))
    assert len(student_paths) == len(reference_by_hash) == 8
    assert len(key_paths) == 1
    original_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in fixture_root.iterdir()
        if path.is_file()
    }

    qt = QApplication.instance() or QApplication([])
    qt.setApplicationName("Exam Grader · vol.3 real-fixture UAT")
    app = initialize(Path(tempfile.mkdtemp(prefix="exam-grader-vol3-")))
    exam = app.exams.create(ExamDetails("vol.3 real fixture", "2569", "ป.1", "1", "eeee", count))
    app.exams.set_expected_number_max(exam.id, 40)
    flow = Workflow(app.exams.path)
    service = ReviewService(app.exams.path)
    importer = ImportService(app.exams.path)
    app.exams.set_output_root(exam.id, output / "exports")

    report: dict = {
        "kind": "real-fixture-engineering-uat",
        "platform": qt.platformName(),
        "fixture_root": str(fixture_root),
        "reference": str(reference_path),
        "question_count": count,
        "student_count": len(student_paths),
        "ui": [],
        "automatic": [],
        "teacher_actions": [],
    }

    # The latest key confirmation gate must prevent student import.
    pre_key_errors = run_worker(app.exams.path, exam.id, student_paths, "student")
    assert pre_key_errors and not importer.list_sources(exam.id)
    report["key_gate"] = {"blocked_student_import": True, "errors": pre_key_errors}

    assert not run_worker(app.exams.path, exam.id, key_paths, "key")
    key_source = importer.list_sources(exam.id)[0]
    key_dialog = ReviewDialog(app.exams.path, key_source)
    key_dialog.show()
    settle()
    key_dialog.grab().save(str(output / "key-before-confirm.png"))
    for editor, answer in zip(key_dialog.combos, reference["key"]["answers"]):
        assert isinstance(editor, QLineEdit)
        editor.setText(key_answer_text(answer))
    key_dialog.confirmed.setChecked(True)
    key_dialog.accept()
    assert key_dialog.result() == QDialog.DialogCode.Accepted

    assert not run_worker(app.exams.path, exam.id, student_paths, "student")
    window = ExamDialog(app, exam)
    window.show()
    settle()
    window.tabs.setCurrentIndex(1)
    window.adopt_button.click()
    settle()

    states = service.states(exam.id)
    assert len(states) == len(student_paths)
    for state in states:
        source = state["source"]
        reference_row = reference_by_hash[source["sha256"]]
        detection = state["detection"]
        machine = service.machine_answers(detection, count)
        observed = detection.get("student_number_observation") or {}
        reference_detection = reference_row["detection"]["answers"]
        differences = []
        for index, (actual, previous) in enumerate(
            zip(detection["answers"][:count], reference_detection[:count]), 1
        ):
            if (actual["classification"], actual.get("selected")) != (
                previous["classification"],
                previous.get("selected"),
            ):
                differences.append(
                    {
                        "question": index,
                        "current": [actual["classification"], actual.get("selected")],
                        "reference_run": [previous["classification"], previous.get("selected")],
                    }
                )
        expected_uncertain = [
            index
            for index, item in enumerate(reference_detection[:count], 1)
            if item["classification"] == "uncertain"
        ]
        current_uncertain = [
            index
            for index, item in enumerate(detection["answers"][:count], 1)
            if item["classification"] == "uncertain"
        ]
        if source["original_name"] == "IMG_0805.jpg":
            assert differences == [
                {
                    "question": 25,
                    "current": ["boundary_cross", ["B", "C"]],
                    "reference_run": ["uncertain", ["B", "C"]],
                }
            ], differences
            assert current_uncertain == [
                question for question in expected_uncertain if question != 25
            ]
        else:
            assert not differences, (source["original_name"], differences)
            assert current_uncertain == expected_uncertain
        report["automatic"].append(
            {
                "file": source["original_name"],
                "reference_number": reference_row["student_number"],
                "adopted_number": state["number"],
                "identity_auto_applied": state["number"] == reference_row["student_number"],
                "candidate": observed.get("candidate"),
                "candidates": observed.get("candidates", []),
                "classification_counts": dict(
                    Counter(a["classification"] for a in detection["answers"][:count])
                ),
                "machine_resolved": sum(answer is not None for answer in machine),
                "machine_uncertain": [
                    index + 1 for index, answer in enumerate(machine) if answer is None
                ],
                "reference_run_differences": differences,
            }
        )

    window.tabs.setCurrentIndex(2)
    window.resize(1024, 768)
    settle()
    window.grab().save(str(output / "review-before-teacher-actions.png"))
    pending = list(service.issues(exam.id))
    report["pending_before_teacher_actions"] = [
        {
            "kind": issue["kind"],
            "number": issue.get("number"),
            "question": issue.get("question"),
            "label": issue["label"],
        }
        for issue in pending
    ]

    # Resolve only rows the current detector left unresolved. Multiple/blank/
    # boundary-cross states that are already auto-resolved are not re-entered.
    while True:
        actionable = [issue for issue in service.issues(exam.id) if issue["source"] is not None]
        if not actionable:
            break
        issue = actionable[0]
        row_index = next(
            index
            for index, candidate in enumerate(window.issue_rows)
            if candidate["source"]
            and candidate["source"]["id"] == issue["source"]["id"]
            and candidate["kind"] == issue["kind"]
            and candidate.get("question") == issue.get("question")
        )
        reference_row = reference_by_hash[issue["source"]["sha256"]]
        editor = window.issue_table.cellWidget(row_index, 4)
        if issue["kind"] == "number":
            editor.setText(str(reference_row["student_number"]))
            action = {
                "kind": "number",
                "file": issue["source"]["original_name"],
                "value": reference_row["student_number"],
            }
        elif issue["kind"] == "answer":
            answer = reference_row["answers"][issue["question"] - 1]
            editor.setCurrentIndex(editor.findData(answer))
            action = {
                "kind": "answer",
                "file": issue["source"]["original_name"],
                "question": issue["question"],
                "value": answer,
            }
        else:
            raise AssertionError(issue)
        report["teacher_actions"].append(action)
        window.issue_table.cellWidget(row_index, 5).click()
        settle()

    missing = [issue for issue in service.issues(exam.id) if issue["kind"] == "attendance"]
    report["missing_before_skip"] = [int(issue["number"]) for issue in missing]
    window.skip_missing_button.click()
    settle()
    assert not service.issues(exam.id)

    snapshot = flow.snapshot(exam.id)
    expected_scores = {row["source"]["sha256"]: row["score"] for row in reference["results"]}
    actual_by_hash = {row["source"]["sha256"]: row["score"] for row in snapshot["results"]}
    assert actual_by_hash == expected_scores, (actual_by_hash, expected_scores)
    report["scores"] = [row["score"] for row in snapshot["results"]]

    final = export_results(flow, exam.id, app.exams.output_root(exam.id))
    checked = sorted((final / "checked").glob("*.jpg"))
    assert len(checked) == len(student_paths)
    workbook = load_workbook(final / "scores.xlsx")
    report["export"] = str(final)
    report["checked_jpeg_bytes"] = {path.name: path.stat().st_size for path in checked}
    report["workbook_scores"] = [
        workbook.active.cell(row + 2, 2).value for row in range(len(student_paths))
    ]
    manifest = json.loads((final / "_system/manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest.items():
        assert hashlib.sha256((final / name).read_bytes()).hexdigest() == digest
    report["manifest_hashes_verified"] = len(manifest)
    report["checked_provenance"] = json.loads(
        (final / "_system/results.json").read_text(encoding="utf-8")
    )["results"][0]["checked_provenance"]

    window.tabs.setCurrentIndex(3)
    window.show()
    settle()
    window.grab().save(str(output / "results.png"))
    report["ui"].append(
        {
            "screenshot": str(output / "review-before-teacher-actions.png"),
            "width": window.width(),
            "height": window.height(),
            "review_scroll_max": window.issue_table.horizontalScrollBar().maximum(),
        }
    )
    assert original_hashes == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in fixture_root.iterdir()
        if path.is_file()
    }
    report["original_hashes_unchanged"] = True
    report["status"] = "passed"
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "scores": report["scores"],
                "teacher_actions": len(report["teacher_actions"]),
                "missing": len(report["missing_before_skip"]),
                "output": str(final),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
