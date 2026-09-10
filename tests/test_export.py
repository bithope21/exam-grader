import json

import cv2
import numpy as np
import pytest
from openpyxl import load_workbook
from test_workflow import prepare

from exam_grader.exporting import (
    checked_filename,
    checked_image,
    export_results,
    human_readable_name,
)
from exam_grader.imaging import reference_image


def test_export_consistent_versioned_and_keeps_originals(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    key = flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    flow.review(source["id"], "01", ["A", "blank", "C"], key["id"])
    first = export_results(flow, exam.id)
    snapshot = json.loads((first / "_system" / "results.json").read_text())
    workbook = load_workbook(first / "scores.xlsx")
    assert workbook.active.cell(2, 1).value == "01"
    assert workbook.active.cell(2, 2).value == snapshot["results"][0]["score"] == 2
    assert (first / snapshot["results"][0]["checked_image"]).is_file()
    second = export_results(flow, exam.id)
    assert second != first
    assert first.is_dir()
    assert flow.database.exists()
    assert len(__import__("sqlite3").connect(flow.database).execute(
        "select * from export_runs where exam_id=?", (exam.id,)
    ).fetchall()) == 2
    assert snapshot["export"]["human_readable_name"]
    assert snapshot["export"]["color_legend"]["correct"] == "green"
    assert snapshot["results"][0]["checked_provenance"]["encoding"]["format"] == "JPEG"
    assert first.parent.parent.name == snapshot["export"]["human_readable_name"]
    assert {p.name for p in first.iterdir()} == {"checked", "scores.xlsx", "_system"}
    assert (first / "checked" / "เลขที่-01.jpg").exists()


def test_human_readable_name_sanitizes_cross_platform_fields():
    assert human_readable_name({"academic_year": "2569", "grade": "M/6", "room": "1?", "subject": "คณิต", "name": "สอบ:*", "question_count": 30}).endswith("_30q")
    assert "/" not in human_readable_name({"academic_year": "a/b", "grade": "g", "room": "r", "subject": "s", "name": "n", "question_count": 1})
    assert len(human_readable_name({"name": "คณิตศาสตร์" * 100}).encode("utf-8")) < 255


def test_filename_collision_and_invalid_number_never_expose_ids_or_paths():
    used = set()
    assert checked_filename("02", used) == "เลขที่-02.jpg"
    assert checked_filename("๒", used) == "เลขที่-02_02.jpg"
    assert checked_filename("../../bad", used) == "ไม่ทราบเลขที่_01.jpg"
    assert checked_filename(None, used) == "ไม่ทราบเลขที่_02.jpg"


@pytest.mark.parametrize("maximum", [1, 30, 60])
def test_score_occupies_printed_score_box_and_never_number_line(maximum):
    image = reference_image()
    source = cv2.imencode(".png", image)[1].tobytes()
    result = {"answers": ["A"] * maximum, "score": maximum, "max": maximum,
              "student_number": "1", "detection": {"registration": {"matrix": np.eye(3).tolist()}}}
    pixels = cv2.imdecode(np.frombuffer(checked_image(source, result, {"answers": result["answers"]}), np.uint8), cv2.IMREAD_COLOR)
    blue = (pixels[:, :, 0] > 120) & (pixels[:, :, 1] < 150) & (pixels[:, :, 2] < 100)
    # Independent coordinates from the inspected printed reference, deliberately
    # not loaded from the implementation's score_roi.
    assert blue[55:117, 713:808].sum() > 100
    assert not blue[70:130, 590:700].any()
    assert not blue[15:48, 700:820].any()  # printed score title remains untouched


def test_identity_correction_regenerates_filename_and_excel_keeps_prior_run(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    key = flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    flow.review(source["id"], "1", ["A", "B", "C"], key["id"])
    first = export_results(flow, exam.id)
    original = (first / "_system/results.json").read_bytes()
    flow.review(source["id"], "12", ["A", "B", "C"], key["id"])
    second = export_results(flow, exam.id)
    assert (second / "checked/เลขที่-12.jpg").exists()
    assert load_workbook(second / "scores.xlsx").active.cell(2, 1).value == "12"
    assert (first / "_system/results.json").read_bytes() == original


def test_checked_renderer_marks_canonical_cells_and_score_without_source_mutation():
    image = reference_image()
    source = cv2.imencode(".png", image)[1].tobytes()
    key = {"answers": ["A"]}
    result = {
        "answers": ["A"],
        "score": 1,
        "max": 1,
        "student_number": "1",
        "detection": {"registration": {"matrix": np.eye(3).tolist()}, "template_id": "test"},
    }
    rendered = checked_image(source, result, key)
    decoded = cv2.imdecode(np.frombuffer(rendered, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == image.shape
    green = (decoded[:, :, 1] > 120) & (decoded[:, :, 0] < 100) & (decoded[:, :, 2] < 100)
    assert int(green.sum()) > 20
    assert source == cv2.imencode(".png", image)[1].tobytes()


def test_checked_renderer_uses_red_for_wrong_and_distinct_non_answer_colors():
    image = reference_image()
    source = cv2.imencode(".png", image)[1].tobytes()
    result = {
        "answers": ["B", "blank", "multiple", "boundary_cross"],
        "score": 0,
        "max": 4,
        "student_number": "1",
        "detection": {
            "registration": {"matrix": np.eye(3).tolist()},
            "answers": [
                {"selected": ["B"]}, {"selected": []},
                {"selected": ["A", "C"]}, {"selected": ["B", "C"]},
            ],
        },
    }
    decoded = cv2.imdecode(np.frombuffer(checked_image(source, result, {"answers": ["A"] * 4}), np.uint8), cv2.IMREAD_COLOR)
    red = (decoded[:, :, 2] > 140) & (decoded[:, :, 1] < 120) & (decoded[:, :, 0] < 120)
    orange = (decoded[:, :, 2] > 150) & (decoded[:, :, 1] > 70) & (decoded[:, :, 0] < 100)
    purple = (decoded[:, :, 2] > 100) & (decoded[:, :, 0] > 100) & (decoded[:, :, 1] < 130)
    assert int(red.sum()) > 20
    assert int(orange.sum()) > 20
    assert int(purple.sum()) > 20


def test_tampered_source_prevents_export(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    key = flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    flow.review(source["id"], "1", ["A", "B", "C"], key["id"])
    (flow.database.parent / source["relative_path"]).write_bytes(b"changed")
    with pytest.raises(ValueError):
        export_results(flow, exam.id)
    assert not list((flow.database.parent / "results" / exam.id).glob("run-*"))


def test_export_accepts_per_exam_output_root_and_rejects_file(tmp_path):
    flow, exam, key_source, source = prepare(tmp_path)
    key = flow.approve_key(exam.id, ["A", "B", "C"], key_source["id"])
    flow.review(source["id"], "1", ["A", "B", "C"], key["id"])
    output_root = tmp_path / "chosen-results"
    result = export_results(flow, exam.id, output_root=output_root)
    assert result.parent.parent.parent == output_root
    assert exam.id not in str(result)
    blocked = tmp_path / "not-a-folder"
    blocked.write_text("keep")
    with pytest.raises(OSError):
        export_results(flow, exam.id, output_root=blocked)
