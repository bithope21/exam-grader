import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from exam_grader.geometry_resolution import (
    GeometryResolutionError,
    geometry_from_detection,
    resolve_geometry,
)
from exam_grader.imaging import RegistrationError, analyze, decode
from exam_grader.template_manager import (
    AnswerBlock,
    TemplateDefinition,
    cell_rect_for_template,
    default_1_template_definition,
)

VOL9 = Path(__file__).parent / "fixtures" / "real" / "vol.9"
VOL9_RUN = VOL9 / "2026-09-14_214703"


def _vol9_template() -> TemplateDefinition:
    return TemplateDefinition(
        template_id="template-84a0bdde",
        name="vol9",
        kind="custom",
        version=2,
        canonical_width=1200,
        canonical_height=1720,
        choice_count=5,
        choice_labels=["A", "B", "C", "D", "E"],
        display_choice_labels=["ก", "ข", "ค", "ง", "จ"],
        choice_map={
            **dict.fromkeys(["A", "a", "1", "ก"], "A"),
            **dict.fromkeys(["B", "b", "2", "ข"], "B"),
            **dict.fromkeys(["C", "c", "3", "ค"], "C"),
            **dict.fromkeys(["D", "d", "4", "ง"], "D"),
            **dict.fromkeys(["E", "e", "5", "จ"], "E"),
        },
        question_count=60,
        answer_blocks=[AnswerBlock(**item) for item in [
            {
                "block_index": 0,
                "question_start": 1,
                "question_end": 15,
                "rows": 15,
                "choice_count": 5,
                "col_boundaries": [102, 146, 190, 236, 280, 324],
                "row_boundaries": [510, 576, 642, 706, 772, 836, 902, 967, 1032, 1098, 1162, 1228, 1294, 1360, 1426, 1496],
            },
            {
                "block_index": 1,
                "question_start": 16,
                "question_end": 30,
                "rows": 15,
                "choice_count": 5,
                "col_boundaries": [381, 425, 468, 512, 556, 600],
                "row_boundaries": [510, 576, 642, 706, 771, 835, 901, 966, 1031, 1097, 1161, 1227, 1292, 1358, 1424, 1494],
            },
            {
                "block_index": 2,
                "question_start": 31,
                "question_end": 45,
                "rows": 15,
                "choice_count": 5,
                "col_boundaries": [656, 700, 742, 787, 830, 874],
                "row_boundaries": [510, 576, 641, 705, 770, 834, 900, 964, 1029, 1094, 1158, 1224, 1289, 1355, 1420, 1490],
            },
            {
                "block_index": 3,
                "question_start": 46,
                "question_end": 60,
                "rows": 15,
                "choice_count": 5,
                "col_boundaries": [930, 975, 1018, 1064, 1107, 1152],
                "row_boundaries": [510, 576, 642, 706, 772, 836, 902, 967, 1032, 1098, 1162, 1228, 1294, 1360, 1426, 1496],
            },
        ]],
        student_number_roi=(828, 192, 978, 242),
        score_roi=(999, 58, 1161, 308),
        reference_sha256="6d68d1af12bb305aadf66d93c26e24f4fc33bd783e93a7183a7190ed2c8e8739",
        cell_inset=8,
        registration_config={
            "allow_paper_quad_fallback": True,
            "color_theme": "monochrome",
            "paper_to_canonical_matrix": [
                [0.3048950302872529, 0.006321587472468374, -84.9933244901621],
                [-0.006501916049919604, 0.4569401737605378, -72.31592639329092],
                [-0.000003984202874704289, 0.0000052723831863466655, 1.0],
            ],
        },
    )


def _vol9_reference() -> np.ndarray:
    key = decode((VOL9 / "key.jpg").read_bytes())
    matrix = np.asarray(_vol9_template().registration_config["paper_to_canonical_matrix"])
    return cv2.warpPerspective(key, matrix, (1200, 1720), borderValue=(255, 255, 255))


def _vol9_detection(name: str) -> tuple[bytes, dict, dict]:
    exported = json.loads((VOL9_RUN / "_system" / "results.json").read_text())
    record = next(item for item in exported["results"] if item["source"]["original_name"] == name)
    detection = record["detection"]
    data = (VOL9 / name).read_bytes()
    return data, detection, record["source"]


def test_resolver_is_the_persisted_template_roi_contract():
    template = default_1_template_definition()
    identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    resolution = resolve_geometry(
        template,
        {"matrix": identity, "inverse_matrix": identity, "method": "test"},
        block_offsets={0: (0, 0), 1: (0, 0), 2: (0, 0), 3: (0, 0)},
        source_sha256="source",
    )

    assert resolution["answer_rois"]["1"]["A"] == [*cell_rect_for_template(template, 1, 0)]
    assert geometry_from_detection(
        {"geometry_resolution": resolution}, template, source_sha256="source"
    ) == resolution

    stale = {**resolution, "answer_rois": {**resolution["answer_rois"]}}
    stale["answer_rois"]["1"] = {**stale["answer_rois"]["1"]}
    stale["answer_rois"]["1"]["A"] = [62, 235, 20, 25]
    with pytest.raises(GeometryResolutionError, match="ROI"):
        geometry_from_detection({"geometry_resolution": stale}, template, source_sha256="source")


def test_invalid_answer_roi_overlapping_number_strip_fails_closed():
    template = default_1_template_definition()
    template = replace(
        template,
        registration_config={"question_number_strips": [[57, 227, 40, 40]]},
    )
    with pytest.raises(GeometryResolutionError, match="question-number strip"):
        resolve_geometry(template)


@pytest.mark.parametrize("name", ["IMG_1071.jpg", "IMG_1080.jpg"])
def test_clear_answers_survive_page_gate_without_auto_resolving_ambiguity(name):
    data, _, _ = _vol9_detection(name)
    result = analyze(data, template_def=_vol9_template(), reference_override=_vol9_reference())

    assert result["review_gates"]["page"] is True
    assert result["review_gates"]["block"] is False
    assert all(
        answer["auto_resolved"] == (answer["classification"] in {"single_mark", "blank"})
        for answer in result["answers"]
    )
    assert all(answer["review_gates"]["page"] is True for answer in result["answers"])


def test_img1078_answer_rois_are_isolated_from_neighbor_number_strips():
    data, old_detection, source = _vol9_detection("IMG_1078.jpg")
    template = _vol9_template()
    with pytest.raises(RegistrationError, match="question-number strip"):
        analyze(data, template_def=template, reference_override=_vol9_reference())

    resolution = geometry_from_detection(
        old_detection, template, source_sha256=source["sha256"]
    )
    stale_detection = deepcopy(old_detection)
    stale_detection["answers"][9]["roi_rects"]["A"] = [0, 0, 1, 1]
    legacy_resolution = geometry_from_detection(
        stale_detection, template, source_sha256=source["sha256"]
    )
    assert legacy_resolution["answer_rois"]["10"] == resolution["answer_rois"]["10"]
    assert legacy_resolution["answer_rois"]["10"]["A"] != [0, 0, 1, 1]

    for question in range(10, 16):
        block = next(
            item
            for item in resolution["blocks"]
            if item["question_start"] <= question <= item["question_end"]
        )
        bx, by, bw, bh = block["outer_rect"]
        for rect in resolution["answer_rois"][str(question)].values():
            x, y, w, h = rect
            assert bx <= x and by <= y
            assert x + w <= bx + bw and y + h <= by + bh
            for strip in resolution["protected_strips_by_block"][str(block["block_index"])] :
                sx, sy, sw, sh = strip
                assert max(x, sx) >= min(x + w, sx + sw) or max(y, sy) >= min(y + h, sy + sh)
