from pathlib import Path

import cv2
import numpy as np
import pytest

from exam_grader.imaging import (
    RegistrationError,
    _green_core_decision,
    _green_cross_features,
    _green_form_ink_mask,
    analyze,
    cell_rect,
    reference_image,
    register,
)
from exam_grader.template_manager import default_1_template_definition

VOL8 = Path(__file__).parent / "fixtures" / "real" / "vol.8"


def test_vol8_registration_selects_grid_candidate_and_keeps_rois_canonical():
    sheets = sorted(VOL8.glob("IMG_*.jpg"))
    if not sheets:
        pytest.skip("Vol.8 real-sheet fixtures are not present in this checkout")

    template_def = default_1_template_definition()
    assert len(sheets) == 10
    results = {
        sheet.name: analyze(sheet.read_bytes(), template_def=template_def) for sheet in sheets
    }

    for name, result in results.items():
        registration = result["registration"]
        assert registration["method"] == "grid-quad-two-stage-v1", name
        assert registration["alignment_confidence"] >= 0.62, name
        assert registration["grid_line_coverage"] >= 0.70, name
        assert registration["grid_residual_px"] <= 2.5, name
        assert registration["candidate_count"] >= 1, name
        assert len(registration["candidate_diagnostics"]) >= 1, name
        assert registration["roi_coordinate_space"] == "canonical_px"
        assert len(result["answers"]) == 60
        assert result["answers"][0]["roi_rects"]["A"] == [61, 231, 25, 25]
        assert result["answers"][0]["roi_rects"]["E"][0] > result["answers"][0]["roi_rects"]["A"][0]

    # IMG_1022 is the known clear baseline; keep its first five visible marks stable.
    baseline = results["IMG_1022.jpg"]
    first_five = [answer["selected"] for answer in baseline["answers"][:5]]
    assert first_five == [["A"], ["B"], ["A"], ["D"], ["C"]]
    assert results["IMG_1025.jpg"]["answers"][16]["selected"] == ["A"]
    assert results["IMG_1025.jpg"]["answers"][22]["classification"] == "uncertain"
    fine = baseline["registration"]["fine_registration"]
    assert fine["applied"] is True
    assert fine["after_residual_px"] < fine["before_residual_px"]
    for result in results.values():
        matrix = np.asarray(result["registration"]["matrix"], dtype=np.float64)
        inverse = np.asarray(result["registration"]["inverse_matrix"], dtype=np.float64)
        assert np.allclose(matrix @ inverse, np.eye(3), atol=1e-5)


def test_exact_canonical_reference_is_never_moved_by_registration():
    reference = reference_image()
    aligned, registration = register(reference)
    assert (aligned == reference).all()
    assert registration["method"] == "exact-reference"
    assert registration["alignment_confidence"] == 1.0


def test_already_canonical_marked_sheet_keeps_identity_transform():
    marked = reference_image()
    x, y, width, height = cell_rect(1, 0)
    cv2.line(marked, (x + 4, y + 4), (x + width - 4, y + height - 4), (0, 0, 0), 3)
    cv2.line(marked, (x + width - 4, y + 4), (x + 4, y + height - 4), (0, 0, 0), 3)
    aligned, registration = register(marked, template_def=default_1_template_definition())
    assert np.array_equal(aligned, marked)
    assert registration["method"] == "canonical-grid-identity-v1"
    assert np.array_equal(np.asarray(registration["matrix"]), np.eye(3))
    assert registration["identity_grid_overlap"] >= 0.95


def test_low_evidence_image_fails_closed_before_omr():
    blank = np.full((800, 1000, 3), 255, dtype=np.uint8)
    with pytest.raises(RegistrationError):
        register(blank, template_def=default_1_template_definition())


def test_green_form_mask_removes_printed_green_but_retains_neutral_ink():
    cell = np.full((8, 8, 3), 255, dtype=np.uint8)
    darkness = np.zeros((8, 8), dtype=bool)
    cell[3, :, :] = (0, 70, 0)  # Printed green grid line in BGR.
    darkness[3, :] = True
    cell[4, 4] = (5, 5, 5)  # Neutral dark student ink.
    darkness[4, 4] = True

    mask = _green_form_ink_mask(cell, darkness)

    assert not mask[3, :].any()
    assert mask[4, 4]


def test_green_core_decision_resolves_isolated_mark_and_keeps_multiple_uncertain():
    selected, classification, reason = _green_core_decision([], "uncertain", [0.1, 0.0, 0, 0, 0])
    assert (selected, classification, reason) == (["A"], "single_mark", "green-center-ink-dominance")

    selected, classification, reason = _green_core_decision(
        ["A", "C"], "multiple", [0.1, 0, 0.03, 0, 0]
    )
    assert selected == ["A", "C"]
    assert classification == "uncertain"
    assert reason == "multiple-without-two-centered-marks"


def test_green_cross_geometry_requires_both_diagonal_strokes():
    crossed = np.zeros((25, 25), dtype=np.uint8)
    cv2.line(crossed, (5, 5), (19, 19), 255, 2)
    cv2.line(crossed, (19, 5), (5, 19), 255, 2)
    single = np.zeros((25, 25), dtype=np.uint8)
    cv2.line(single, (5, 5), (19, 19), 255, 2)

    assert _green_cross_features(crossed) == (True, True)
    assert _green_cross_features(single) == (False, True)
