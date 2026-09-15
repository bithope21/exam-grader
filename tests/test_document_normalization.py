import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog

from exam_grader.document_normalization import (
    DOCUMENT_NORMALIZATION_VERSION,
    perspective_normalize,
    source_sha256,
    validate_manual_corners,
)
from exam_grader.document_normalization_ui import ManualCropDialog
from exam_grader.imaging import RegistrationError, analyze, decode, register
from exam_grader.template_discovery import detect_paper
from exam_grader.template_manager import (
    BUILTIN_TEMPLATE_IDS,
    get_reference_image,
    load_builtin_template,
)


def _exif_orientation_jpeg(image: np.ndarray, orientation: int) -> bytes:
    encoded = cv2.imencode(".jpg", image)[1].tobytes()
    tiff = (
        b"II*\x00\x08\x00\x00\x00\x01\x00"
        + b"\x12\x01\x03\x00\x01\x00\x00\x00"
        + int(orientation).to_bytes(2, "little")
        + b"\x00\x00\x00\x00\x00\x00"
    )
    payload = b"Exif\x00\x00" + tiff
    segment = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    return encoded[:2] + segment + encoded[2:]


def test_decode_honors_exif_orientation_without_mutating_encoded_source():
    image = np.zeros((40, 64, 3), dtype=np.uint8)
    image[:, :] = (30, 80, 170)
    encoded = _exif_orientation_jpeg(image, 6)
    digest = source_sha256(encoded)

    decoded = decode(encoded)

    assert decoded.shape[:2] == (64, 40)
    assert source_sha256(encoded) == digest


def test_manual_corner_validation_is_layout_agnostic_and_fail_closed():
    shape = (800, 1200, 3)
    valid = [[80, 50], [1100, 90], [1050, 740], [55, 700]]

    points = validate_manual_corners(valid, shape, target_size=(836, 818))

    assert points.shape == (4, 2)
    with pytest.raises(ValueError):
        validate_manual_corners([[80, 50], [1100, 90], [55, 700], [1050, 740]], shape)
    with pytest.raises(ValueError):
        validate_manual_corners([[80, 50], [1100, 90], [1050, 740], [55, 700]], (300, 300, 3))


def test_perspective_normalize_preserves_source_and_maps_geometry():
    source = np.full((300, 420, 3), 245, dtype=np.uint8)
    cv2.rectangle(source, (80, 55), (340, 255), (15, 20, 25), 4)
    original = source.copy()
    corners = np.asarray([[80, 55], [340, 55], [340, 255], [80, 255]], dtype=np.float32)
    target = np.asarray([[0, 0], [259, 0], [259, 199], [0, 199]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(corners, target)

    result = perspective_normalize(source, matrix, (260, 200))

    assert result.shape == (200, 260, 3)
    assert np.array_equal(source, original)
    assert result[3:197, 3:257].mean() < 250


def test_page_detector_exposes_multiple_generic_signals_without_source_changes():
    photo = np.full((720, 560, 3), (44, 58, 72), dtype=np.uint8)
    paper = np.full((630, 420, 3), (232, 235, 230), dtype=np.uint8)
    cv2.rectangle(paper, (26, 28), (394, 600), (42, 48, 50), 2)
    photo_corners = np.asarray([[80, 35], [488, 78], [456, 690], [45, 638]], dtype=np.float32)
    paper_corners = np.asarray([[0, 0], [419, 0], [419, 629], [0, 629]], dtype=np.float32)
    forward = cv2.getPerspectiveTransform(paper_corners, photo_corners)
    cv2.warpPerspective(paper, forward, (photo.shape[1], photo.shape[0]), dst=photo, borderMode=cv2.BORDER_TRANSPARENT)
    original = photo.copy()
    diagnostics = {}

    _, matrix, confidence, corners = detect_paper(photo, 836, 818, diagnostics=diagnostics)

    assert np.array_equal(photo, original)
    assert matrix.shape == (3, 3)
    assert corners.shape == (4, 2)
    assert 0.0 <= confidence <= 1.0
    assert diagnostics["candidate_count"] >= 1
    assert diagnostics["candidates"]
    assert all("geometry_confidence" in item and "source" in item for item in diagnostics["candidates"])


def _synthetic_smartphone_photo(variant: str) -> tuple[np.ndarray, np.ndarray]:
    height, width = 760, 640
    paper_height, paper_width = 620, 420
    paper_colors = {
        "white-paper": (248, 248, 245),
        "cream-paper": (235, 226, 207),
        "gray-paper": (194, 198, 201),
        "near-identical-brightness": (232, 233, 230),
    }
    page = np.full((paper_height, paper_width, 3), paper_colors.get(variant, (235, 237, 232)), dtype=np.uint8)
    cv2.rectangle(page, (12, 12), (paper_width - 12, paper_height - 12), (34, 80, 45), 4)
    cv2.rectangle(page, (32, 30), (paper_width - 30, 70), (70, 180, 95), -1)
    for y in range(120, 560, 44):
        cv2.line(page, (30, y), (paper_width - 30, y), (70, 80, 72), 1)
    for x in range(80, paper_width - 20, 54):
        cv2.line(page, (x, 120), (x, 558), (70, 80, 72), 1)

    corners = np.asarray([[115, 55], [555, 82], [535, 704], [88, 676]], dtype=np.float32)
    if variant == "distance":
        center = corners.mean(axis=0)
        corners = center + (corners - center) * 0.72
    elif variant == "small-page":
        center = corners.mean(axis=0)
        corners = center + (corners - center) * 0.50
    elif variant == "large-page":
        center = corners.mean(axis=0)
        corners = center + (corners - center) * 1.08
    elif variant == "slight-clipping":
        corners = np.asarray([[-3, 54], [621, 62], [621, 763], [39, 716]], dtype=np.float32)
    elif variant == "perspective":
        corners = np.asarray([[152, 54], [562, 118], [512, 692], [70, 635]], dtype=np.float32)
    page_corners = np.asarray(
        [[0, 0], [paper_width - 1, 0], [paper_width - 1, paper_height - 1], [0, paper_height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(page_corners, corners)
    backgrounds = {
        "white-paper": (90, 96, 104),
        "cream-paper": (104, 94, 80),
        "gray-paper": (58, 65, 75),
        "near-identical-brightness": (230, 231, 228),
    }
    background = backgrounds.get(variant, (55, 65, 78))
    photo = np.full((height, width, 3), background, dtype=np.uint8)
    if variant == "textured-background":
        noise = np.random.default_rng(4815).normal(0, 5, photo.shape).astype(np.float32)
        photo = np.clip(photo.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    cv2.warpPerspective(page, matrix, (width, height), dst=photo, borderMode=cv2.BORDER_TRANSPARENT)

    if variant == "clutter":
        cv2.rectangle(photo, (5, 6), (100, 132), (214, 216, 212), -1)
        cv2.rectangle(photo, (552, 16), (635, 110), (22, 28, 36), -1)
        cv2.circle(photo, (40, 720), 24, (30, 80, 160), -1)
    elif variant == "partial-border":
        cv2.line(photo, (int(corners[0, 0]), 315), (int(corners[3, 0]), 340), (55, 65, 78), 14)
    elif variant == "inner-border-near-edge":
        cv2.rectangle(page, (24, 22), (paper_width - 3, paper_height - 26), (23, 62, 35), 2)
        cv2.warpPerspective(page, matrix, (width, height), dst=photo, borderMode=cv2.BORDER_TRANSPARENT)
    elif variant == "rotation":
        rotate = cv2.getRotationMatrix2D((width / 2, height / 2), 7, 1.0)
        photo = cv2.warpAffine(photo, rotate, (width, height), borderValue=(55, 65, 78))
        corners = cv2.transform(corners.reshape(1, -1, 2), rotate).reshape(-1, 2)

    if variant == "shadow":
        yy, xx = np.indices(photo.shape[:2], dtype=np.float32)
        gradient = 0.82 + 0.18 * (xx / max(1, width - 1))
        shadow = 1.0 - 0.38 * np.exp(-(((xx - 130) / 120) ** 2 + ((yy - 400) / 250) ** 2))
        photo = np.clip(photo.astype(np.float32) * (gradient * shadow)[:, :, None], 0, 255).astype(
            np.uint8
        )
    elif variant == "warm-light":
        photo = np.clip(photo.astype(np.float32) * np.asarray([1.05, 1.0, 0.90]), 0, 255).astype(
            np.uint8
        )
    elif variant == "cool-light":
        photo = np.clip(photo.astype(np.float32) * np.asarray([0.90, 1.0, 1.08]), 0, 255).astype(
            np.uint8
        )
    elif variant == "blur":
        photo = cv2.GaussianBlur(photo, (7, 7), 1.4)
    elif variant == "mild-glare":
        glare_mask = np.zeros(photo.shape[:2], dtype=np.uint8)
        cv2.ellipse(glare_mask, (490, 250), (76, 38), -22, 0, 360, 72, -1)
        alpha = glare_mask.astype(np.float32)[:, :, None] / 255.0
        photo = np.clip(photo.astype(np.float32) * (1.0 - alpha) + 255.0 * alpha, 0, 255).astype(
            np.uint8
        )
    return photo, corners


@pytest.mark.parametrize(
    "variant",
    [
        "rotation",
        "perspective",
        "distance",
        "shadow",
        "clutter",
        "partial-border",
        "warm-light",
        "cool-light",
        "blur",
        "white-paper",
        "cream-paper",
        "gray-paper",
        "near-identical-brightness",
        "mild-glare",
        "textured-background",
        "small-page",
        "large-page",
        "slight-clipping",
        "inner-border-near-edge",
    ],
)
def test_smartphone_photo_variants_detect_plausible_page_or_stay_reviewable(variant):
    photo, expected_corners = _synthetic_smartphone_photo(variant)
    original = photo.copy()
    diagnostics = {}

    _, _, confidence, corners = detect_paper(photo, 1200, 1720, diagnostics=diagnostics)

    assert np.array_equal(photo, original)
    assert diagnostics["candidates"]
    assert corners.shape == (4, 2)
    # A strong geometry claim must agree with the generated physical page; any
    # weaker proposal remains eligible for the human corner-adjustment path.
    if confidence >= 0.85:
        assert float(np.mean(np.linalg.norm(corners - expected_corners, axis=1))) < 32, variant
    else:
        assert confidence < 0.85, variant


@pytest.mark.parametrize("template_id", BUILTIN_TEMPLATE_IDS)
def test_manual_normalization_accepts_multiple_builtin_layouts(template_id):
    template_def = load_builtin_template(template_id)
    reference = get_reference_image(template_def)
    height, width = reference.shape[:2]
    photo_width, photo_height = round(width * 1.35), round(height * 1.35)
    corners = np.asarray(
        [
            [width * 0.10, height * 0.12],
            [photo_width - width * 0.08, height * 0.06],
            [photo_width - width * 0.12, photo_height - height * 0.08],
            [width * 0.06, photo_height - height * 0.12],
        ],
        dtype=np.float32,
    )
    canonical_corners = np.asarray(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    forward = cv2.getPerspectiveTransform(canonical_corners, corners)
    source = cv2.warpPerspective(
        reference,
        forward,
        (photo_width, photo_height),
        flags=cv2.INTER_LINEAR,
        borderValue=(36, 45, 56),
    )
    original = source.copy()

    aligned, registration = register(
        source,
        template_def=template_def,
        manual_corners=corners,
    )

    assert aligned.shape == reference.shape, template_id
    assert registration["method"] == "manual-paper-quad-authoritative-v2", template_id
    assert registration["normalization_boundary_status"] == "human-adjusted", template_id
    assert registration["table_coverage"] >= 0.985, template_id
    assert len(template_def.answer_blocks) >= 1
    assert np.array_equal(source, original)


def test_manual_crop_dialog_has_keyboard_editable_corners_and_reset():
    app = QApplication.instance() or QApplication([])
    image = np.full((700, 500, 3), 250, dtype=np.uint8)
    initial = np.asarray([[40, 40], [460, 50], [450, 660], [35, 650]], dtype=np.float32)
    dialog = ManualCropDialog(image, initial, target_size=(836, 818))
    app.processEvents()
    before = dialog.current_corners()

    dialog.handles[0].keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    )
    keyboard_nudged = dialog.current_corners()
    dialog.handles[0].setPos(dialog.handles[0].pos().x() + 3, dialog.handles[0].pos().y() + 4)
    changed = dialog.current_corners()
    dialog.reset_corners()
    dialog._accept_corners()

    assert not np.array_equal(before, changed)
    assert keyboard_nudged[0, 0] == pytest.approx(before[0, 0] + 1)
    assert np.allclose(dialog.current_corners(), initial)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.accepted_corners() is not None
    assert DOCUMENT_NORMALIZATION_VERSION == "document-normalization-v2"
    dialog.close()


def test_manual_low_confidence_preserves_source_and_forces_answer_review():
    template_def = load_builtin_template("default-1")
    reference = get_reference_image(template_def)
    height, width = reference.shape[:2]
    photo_width, photo_height = round(width * 1.35), round(height * 1.35)
    corners = np.asarray(
        [
            [width * 0.10, height * 0.12],
            [photo_width - width * 0.08, height * 0.06],
            [photo_width - width * 0.12, photo_height - height * 0.08],
            [width * 0.06, photo_height - height * 0.12],
        ],
        dtype=np.float32,
    )
    page_corners = np.asarray(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    forward = cv2.getPerspectiveTransform(page_corners, corners)
    source = cv2.warpPerspective(
        reference,
        forward,
        (photo_width, photo_height),
        borderValue=(36, 45, 56),
    )
    encoded = cv2.imencode(".png", source)[1].tobytes()
    original = source.copy()

    result = analyze(encoded, template_def=template_def, manual_corners=corners)

    assert result["document_normalization"]["version"] == DOCUMENT_NORMALIZATION_VERSION
    assert result["document_normalization"]["source_sha256"] == source_sha256(encoded)
    assert result["document_normalization"]["original_immutable"] is True
    assert result["document_normalization"]["preview_storage"].startswith("regenerated-on-demand")
    assert result["registration"]["normalization_requires_review"] is True
    assert all(not answer["auto_resolved"] for answer in result["answers"])
    assert np.array_equal(source, original)


def test_registration_failure_reports_boundary_candidates_and_stage():
    source = np.full((700, 500, 3), 255, dtype=np.uint8)
    encoded = cv2.imencode(".png", source)[1].tobytes()

    with pytest.raises(RegistrationError) as failure:
        analyze(encoded, template_def=load_builtin_template("default-1"))

    assert failure.value.diagnostics.get("stage")
    assert "paper_boundary_candidates" in failure.value.diagnostics
