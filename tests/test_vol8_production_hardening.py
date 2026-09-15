import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import cv2
import numpy as np
import pytest

from exam_grader.imaging import analyze, decode, reference_image
from exam_grader.review_ui import _normalization_corners
from exam_grader.template_discovery import discover_template
from exam_grader.template_manager import TemplateDefinition, default_1_template_definition

VOL8 = Path(__file__).parent / "fixtures" / "real" / "vol.8"


def _warped_reference_with_manual_miss() -> tuple[bytes, np.ndarray]:
    reference = reference_image()
    height, width = reference.shape[:2]
    source = np.full((height + 180, width + 180, 3), (45, 55, 65), dtype=np.uint8)
    actual = np.asarray(
        [[70, 55], [width + 95, 68], [width + 78, height + 112], [58, height + 100]],
        dtype=np.float32,
    )
    canonical = np.asarray(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    source = cv2.warpPerspective(
        reference,
        cv2.getPerspectiveTransform(canonical, actual),
        (source.shape[1], source.shape[0]),
        dst=source,
        borderMode=cv2.BORDER_TRANSPARENT,
    )
    manual = actual.copy()
    # A valid, convex teacher selection can still disagree with the grid enough
    # to fail the old hard grid gate; it must remain usable as a review crop.
    manual[0] += [40, 40]
    return cv2.imencode(".png", source)[1].tobytes(), manual


def test_valid_manual_crop_survives_weak_grid_fit_and_routes_answers_to_review():
    source, corners = _warped_reference_with_manual_miss()

    result = analyze(
        source,
        template_def=default_1_template_definition(),
        manual_corners=corners,
    )

    registration = result["registration"]
    assert registration["method"].startswith("manual-paper-quad")
    assert registration["normalization_boundary_status"] == "human-adjusted"
    assert registration["normalization_requires_review"] is True
    assert registration["manual_grid_status"] == "review-required"
    assert all(not answer["auto_resolved"] for answer in result["answers"])


def test_manual_corner_editor_prefers_verified_physical_boundary_over_raw_shape_rank():
    verified = [[60, 90], [940, 120], [920, 1410], [45, 1385]]
    misleading = [[0, 0], [999, 45], [990, 1499], [8, 1470]]
    detection = {
        "registration": {
            "physical_paper_corners": verified,
            "physical_boundary_confidence": 0.91,
            "paper_boundary_candidates": [
                {
                    "corners": misleading,
                    "geometry_confidence": 0.99,
                    "proposal_score": 0.99,
                    "physical_edge_support": 0.12,
                }
            ],
        }
    }

    result = _normalization_corners(detection, (1500, 1000, 3))

    assert np.allclose(result, np.asarray(verified, dtype=np.float32))


def test_vol8_1028_does_not_choose_mixed_edge_candidate_over_complete_grid_fit():
    source = VOL8 / "IMG_1028.jpg"
    if not source.exists():
        pytest.skip("Vol.8 user-supplied fixtures are not present")

    result = analyze(source.read_bytes(), template_def=default_1_template_definition())
    registration = result["registration"]
    selected = next(
        candidate
        for candidate in registration["candidate_diagnostics"]
        if candidate["kind"] == registration["selected_candidate"]
    )

    assert selected["grid_line_coverage"] >= 0.98
    assert selected["grid_residual_px"] <= 2.0


def test_vol8_discovery_selects_green_theme_and_replays_teacher_answers_q17_to_23():
    key_path = VOL8 / "key.jpg"
    sheet_path = VOL8 / "IMG_1028.jpg"
    if not key_path.exists() or not sheet_path.exists():
        pytest.skip("Vol.8 user-supplied fixtures are not present")

    discovery = discover_template(key_path.read_bytes(), template_id="vol8-color-evidence")
    template_data = discovery.template_def.to_dict()
    evidence = template_data["registration_config"]["color_theme_evidence"]
    assert template_data["registration_config"]["color_theme"] == "green"
    assert evidence["classifier"] == "grid-color-evidence-v1"
    assert evidence["sample_scope"] == "detected_answer_grids"
    assert evidence["green_coverage"] >= 0.03
    assert evidence["green_share_of_chromatic"] >= 0.60

    # Theme and its supporting evidence survive the same metadata round-trip
    # used when a discovered template is stored and loaded.
    persisted_template = TemplateDefinition.from_dict(template_data)
    assert persisted_template.registration_config["color_theme"] == "green"
    assert persisted_template.registration_config["color_theme_evidence"] == evidence

    result = analyze(
        sheet_path.read_bytes(),
        template_def=persisted_template,
        reference_override=discovery.warped_image,
    )
    expected = {17: "B", 18: "B", 19: "C", 20: "D", 21: "C", 22: "B", 23: "A"}
    for question, choice in expected.items():
        answer = result["answers"][question - 1]
        assert answer["classification"] == "single_mark", question
        assert answer["selected"] == [choice], question


def test_runtime_form_color_corrects_stale_monochrome_export_for_vol8():
    sheet_path = VOL8 / "IMG_1028.jpg"
    key_path = VOL8 / "key.jpg"
    export_path = (
        VOL8
        / "2569_ป.1_1_math_vol8 lunar ultra_30q"
        / "ผลการตรวจ"
        / "2026-09-14_205501"
        / "_system"
        / "results.json"
    )
    if not all(path.exists() for path in (sheet_path, key_path, export_path)):
        pytest.skip("Vol.8 user-supplied fixtures are not present")

    export_data = json.loads(export_path.read_text(encoding="utf-8"))
    template_data = export_data["export"]["template"]
    template_data["registration_config"]["color_theme"] = "monochrome"
    template_def = TemplateDefinition.from_dict(template_data)
    key = decode(key_path.read_bytes())
    matrix = np.asarray(
        template_def.registration_config["paper_to_canonical_matrix"], dtype=np.float64
    )
    reference = cv2.warpPerspective(
        key,
        matrix,
        (template_def.canonical_width, template_def.canonical_height),
        borderValue=(255, 255, 255),
    )

    result = analyze(
        sheet_path.read_bytes(), template_def=template_def, reference_override=reference
    )

    assert template_def.registration_config["color_theme"] == "monochrome"
    assert result["registration"]["configured_color_theme"] == "monochrome"
    assert result["registration"]["color_theme"] == "green"
    assert result["registration"]["color_theme_detection"]["green_coverage"] >= 0.03
    expected = {17: "B", 18: "B", 19: "C", 20: "D", 21: "C", 22: "B", 23: "A"}
    for question, choice in expected.items():
        answer = result["answers"][question - 1]
        assert answer["classification"] == "single_mark", question
        assert answer["selected"] == [choice], question


def test_grayscale_form_discovery_keeps_monochrome_theme_and_round_trips_metadata():
    key_path = VOL8 / "key.jpg"
    if not key_path.exists():
        pytest.skip("Vol.8 user-supplied fixtures are not present")

    key_image = decode(key_path.read_bytes())
    grayscale = cv2.cvtColor(key_image, cv2.COLOR_BGR2GRAY)
    ok, encoded = cv2.imencode(".png", grayscale)
    assert ok

    discovery = discover_template(encoded.tobytes(), template_id="grayscale-color-evidence")
    persisted_template = TemplateDefinition.from_dict(discovery.template_def.to_dict())
    assert persisted_template.registration_config["color_theme"] == "monochrome"
    evidence = persisted_template.registration_config["color_theme_evidence"]
    assert evidence["classifier"] == "grid-color-evidence-v1"
    assert evidence["green_coverage"] == 0.0


def test_vol8_1025_keeps_strong_grid_fit_in_review_when_page_edge_is_uncertain():
    source = VOL8 / "IMG_1025.jpg"
    if not source.exists():
        pytest.skip("Vol.8 user-supplied fixtures are not present")

    export_path = (
        VOL8
        / "2569_ป.1_1_math_vol8 lunar ultra_30q"
        / "ผลการตรวจ"
        / "2026-09-14_205501"
        / "_system"
        / "results.json"
    )
    export_data = json.loads(export_path.read_text(encoding="utf-8"))
    template_def = TemplateDefinition.from_dict(export_data["export"]["template"])
    key = decode((VOL8 / "key.jpg").read_bytes())
    key_matrix = np.asarray(
        template_def.registration_config["paper_to_canonical_matrix"], dtype=np.float64
    )
    reference = cv2.warpPerspective(
        key,
        key_matrix,
        (template_def.canonical_width, template_def.canonical_height),
        borderValue=(255, 255, 255),
    )
    result = analyze(
        source.read_bytes(), template_def=template_def, reference_override=reference
    )
    registration = result["registration"]

    assert registration["alignment_confidence"] >= 0.85
    assert registration["physical_boundary_confidence"] < 0.82
    assert registration["normalization_requires_review"] is True
    assert all(not answer["auto_resolved"] for answer in result["answers"])
