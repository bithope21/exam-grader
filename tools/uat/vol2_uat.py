"""Two-volume regression and explicit key-first / sparse roster UI acceptance."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication, QLineEdit

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.exam_ui import BatchWorker, ExamDialog
from exam_grader.exporting import export_results
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.review_ui import ReviewDialog, key_answer_text
from exam_grader.workflow import Workflow, score_answer
from tools.uat.polish_uat import settle


def run_worker(app, exam, paths, purpose):
    errors = []
    worker = BatchWorker(app.exams.path, exam.id, paths, purpose)
    worker.completed.connect(errors.extend)
    worker.run()
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    qt = QApplication.instance() or QApplication([])
    qt.setApplicationName("ExamGrader Vol.2 verification")
    app = initialize(Path(tempfile.mkdtemp(prefix="exam-grader-vol2-")))
    flow = Workflow(app.exams.path)
    service = ReviewService(app.exams.path)
    importer = ImportService(app.exams.path)
    # Keep the replay self-contained in the repository.  The historical
    # teacher result is input only for explicit UAT actions; recognition never
    # reads it while processing the photographs.
    paths = [
        Path("docs/evidence/automation/teacher-run.json"),
        Path("docs/evidence/vol2/teacher-results.json"),
    ]
    reports = []
    for volume, truth_path in enumerate(paths, 1):
        truth = json.loads(truth_path.read_text())
        root = Path(f"tests/fixtures/real/vol.{volume}")
        hashes = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.iterdir()
            if p.is_file()
        }
        count = len(truth["key"]["answers"])
        exam = app.exams.create(
            ExamDetails(f"vol.{volume} regression", "2569", "ม.1", "6", "math", count)
        )
        student_paths = sorted(root.glob("IMG*"))
        assert run_worker(app, exam, student_paths, "student")  # server gate
        assert not importer.list_sources(exam.id)
        assert not run_worker(app, exam, [next(root.glob("key.*"))], "key")
        window = ExamDialog(app, exam)
        window.show()
        settle()
        assert not window.tabs.isTabEnabled(1)
        key_source = importer.list_sources(exam.id)[0]
        key_dialog = ReviewDialog(app.exams.path, key_source)
        key_dialog.show()
        settle()
        key_dialog.grab().save(str(out / f"vol{volume}-key-before-confirm.png"))
        key_edits = []
        for index, expected in enumerate(truth["key"]["answers"]):
            combo = key_dialog.combos[index]
            current = combo.text() if isinstance(combo, QLineEdit) else combo.currentData()
            if current != key_answer_text(expected):
                key_edits.append(index + 1)
                if isinstance(combo, QLineEdit):
                    combo.setText(key_answer_text(expected))
                else:
                    combo.setCurrentIndex(combo.findData(expected))
        key_dialog.confirmed.setChecked(True)
        key_dialog.accept()
        assert key_dialog.result()
        window.refresh()
        assert window.tabs.isTabEnabled(1)
        assert not run_worker(app, exam, student_paths, "student")
        window.refresh()
        window.tabs.setCurrentIndex(1)
        window.adopt_button.click()
        settle()
        automatic = []
        truth_by_hash = {r["source"]["sha256"]: r for r in truth["results"]}
        for state in service.states(exam.id):
            expected = truth_by_hash[state["source"]["sha256"]]
            detected = service.machine_answers(state["detection"], count)
            errors = [
                (q + 1, a, b)
                for q, (a, b) in enumerate(zip(detected, expected["answers"]))
                if a is not None and a != b and a != "boundary_cross"
            ]
            assert not errors, (state["source"]["original_name"], errors)
            if state["number"]:
                assert state["number"] == expected["student_number"]
            automatic.append(
                {
                    "file": state["source"]["original_name"],
                    "number": state["number"],
                    "resolved": sum(a is not None for a in detected),
                    "uncertain": [q + 1 for q, a in enumerate(detected) if a is None],
                }
            )
        before = service.issues(exam.id)
        assert not any(i["kind"] == "attendance" for i in before), (
            "Sparse files must not invent a roster"
        )
        window.tabs.setCurrentIndex(2)
        window.resize(1024, 768)
        settle()
        window.grab().save(str(out / f"vol{volume}-review-1024.png"))
        # Apply only remaining genuine ambiguities using supplied teacher decisions.
        while window.issue_rows:
            issue = window.issue_rows[0]
            expected = truth_by_hash[issue["source"]["sha256"]]
            editor = window.issue_table.cellWidget(0, 4)
            if issue["kind"] == "number":
                editor.setText(expected["student_number"])
            else:
                assert issue["kind"] == "answer", issue
                editor.setCurrentIndex(editor.findData(expected["answers"][issue["question"] - 1]))
            window.issue_table.cellWidget(0, 5).click()
            settle()
        result = flow.snapshot(exam.id)
        expected_scores = []
        for expected in truth["results"]:
            source = next(
                s
                for s in service.states(exam.id)
                if s["source"]["sha256"] == expected["source"]["sha256"]
            )
            expected_answers = list(expected["answers"])
            for index, item in enumerate(source["detection"].get("answers") or []):
                if item.get("classification") == "boundary_cross" and index < len(expected_answers):
                    expected_answers[index] = "boundary_cross"
            expected_scores.append(
                sum(
                    score_answer(answer, key_answer)
                    for answer, key_answer in zip(
                        expected_answers, truth["key"]["answers"], strict=True
                    )
                )
            )
        actual_scores = [r["score"] for r in result["results"]]
        assert actual_scores == expected_scores, (volume, actual_scores, expected_scores)
        app.exams.set_expected_number_max(exam.id, 24 if volume == 2 else 5)
        window.refresh()
        missing = len([i for i in window.issue_rows if i["kind"] == "attendance"])
        window.skip_missing_button.click()
        assert not service.issues(exam.id)
        output = export_results(flow, exam.id, out / "exports")
        assert len(list((output / "checked").glob("*.jpg"))) == 5
        assert hashes == {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.iterdir()
            if p.is_file()
        }
        reports.append(
            {
                "volume": volume,
                "key_adjudications": key_edits,
                "automatic": automatic,
                "review_actions": len(before),
                "skipped_missing": missing,
                "scores": [r["score"] for r in result["results"]],
                "export": str(output),
                "source_hashes_unchanged": True,
            }
        )
        window.close()
    (out / "report.json").write_text(
        json.dumps(
            {"platform": qt.platformName(), "volumes": reports}, ensure_ascii=False, indent=2
        )
    )
    print(json.dumps(reports, ensure_ascii=False))


if __name__ == "__main__":
    main()
