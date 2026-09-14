"""Reference registration/OMR with per-question automatic decision evidence."""

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QImageReader

from exam_grader.template_manager import (
    AnswerBlock,
    TemplateDefinition,
    cell_rect_for_template,
    default_1_template_definition,
    get_reference_image,
)

CHOICES = "ABCDE"
OMR_PIPELINE_VERSION = "omr-illumination-v5-boundary-cross-v1"
INK_DARKNESS_THRESHOLD = 30.0
SELECTED_DENSITY_THRESHOLD = 0.10
UNCERTAIN_DENSITY_THRESHOLD = 0.025


def classify_ink(densities: list[float], cores: list[float]) -> tuple[list[str], str, str]:
    """Distinguish a dominant mark from weak texture/border spill.

    A coherent faint second mark still requires review. Two strong marks are a
    resolved multiple answer, not an unreadable image. Scores are not calibrated
    probabilities and thresholds are independent of the student's answer/key.
    """
    selected = [
        CHOICES[i] for i, value in enumerate(densities) if value >= SELECTED_DENSITY_THRESHOLD
    ]
    peak = max(densities)
    weak = [
        i
        for i, value in enumerate(densities)
        if UNCERTAIN_DENSITY_THRESHOLD <= value < SELECTED_DENSITY_THRESHOLD
    ]
    unresolved = [
        i
        for i in weak
        if not (selected and densities[i] < 0.06 and densities[i] < peak * 0.35 and cores[i] < 0.08)
    ]
    if unresolved or (not selected and peak >= 0.012):
        return selected, "uncertain", "faint-or-competing-ink"
    if not selected:
        return [], "blank", "no-answer-ink"
    return (
        selected,
        "multiple" if len(selected) > 1 else "single_mark",
        "core-dominance" if weak else "clear-ink",
    )


class RegistrationError(ValueError):
    """Fail-closed registration error with safe, non-image diagnostics."""

    def __init__(self, message: str, *, diagnostics: dict | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def template() -> dict:
    return json.loads(files("exam_grader").joinpath("resources/template.json").read_text())


_DEFAULT1_REF_IMAGE: np.ndarray | None = None


def reference_image() -> np.ndarray:
    global _DEFAULT1_REF_IMAGE
    if _DEFAULT1_REF_IMAGE is not None:
        return _DEFAULT1_REF_IMAGE.copy()
    data = files("exam_grader").joinpath("resources/reference.png").read_bytes()
    if hashlib.sha256(data).hexdigest() != template()["reference_sha256"]:
        raise ValueError("ภาพอ้างอิงเสียหาย กรุณาติดตั้งแอปใหม่")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("อ่านภาพอ้างอิงไม่ได้")
    _DEFAULT1_REF_IMAGE = image
    return image.copy()



def decode(data: bytes) -> np.ndarray:
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError("อ่านภาพไม่ได้")
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    pixels = np.frombuffer(image.bits(), np.uint8).reshape(image.height(), image.bytesPerLine())
    rgb = pixels[:, : image.width() * 3].reshape(image.height(), image.width(), 3).copy()
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def cell_rect(
    question: int, choice: int, *, template_def: TemplateDefinition | None = None
) -> tuple[int, int, int, int]:
    if template_def is not None:
        return cell_rect_for_template(template_def, question, choice)
    if not 1 <= question <= 60 or not 0 <= choice < 5:
        raise ValueError("Invalid cell")
    geometry = template()
    xs = geometry["groups"][(question - 1) // 15]
    ys = geometry["rows"]
    row = (question - 1) % 15
    # Exclude printed borders from ink analysis.
    return xs[choice] + 4, ys[row] + 4, xs[choice + 1] - xs[choice] - 8, ys[row + 1] - ys[row] - 8


_REF_FEATURES_CACHE: dict[tuple[str, str, bool], tuple[tuple[cv2.KeyPoint, ...], np.ndarray]] = {}


def clear_imaging_cache() -> None:
    """Clear cached reference features and images."""
    global _DEFAULT1_REF_IMAGE
    _DEFAULT1_REF_IMAGE = None
    _REF_FEATURES_CACHE.clear()


def register(
    image: np.ndarray,
    *,
    template_def: TemplateDefinition | None = None,
    refined: bool = False,
    app_data_dir: Path | None = None,
    reference_override: np.ndarray | None = None,
) -> tuple[np.ndarray, dict]:
    started = perf_counter()
    if template_def is not None:
        reference = get_reference_image(
            template_def, app_data_dir=app_data_dir, reference_override=reference_override
        )
    elif reference_override is not None:
        reference = reference_override
    else:
        reference = reference_image()
    if image.shape == reference.shape and np.array_equal(image, reference):
        return image.copy(), {
            "matrix": np.eye(3).tolist(),
            "inliers": 0,
            "method": "exact-reference",
        }
    # Bound feature extraction size while retaining transform into decoded original pixels.
    scale = min(1.0, 1800 / max(image.shape[:2]))
    working = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
    extractor = cv2.SIFT.create(nfeatures=5000) if refined else cv2.ORB.create(nfeatures=5000)
    kp1, desc1 = extractor.detectAndCompute(cv2.cvtColor(working, cv2.COLOR_BGR2GRAY), None)

    # Reference feature caching avoids redundant 150-200ms SIFT / 20ms ORB extraction per sheet
    if template_def is not None:
        ref_key = (template_def.template_id, template_def.reference_sha256, refined)
    elif reference_override is not None:
        ref_key = ("override", str(id(reference_override)), refined)
    else:
        ref_key = ("default-1", template()["reference_sha256"], refined)

    cached_ref = _REF_FEATURES_CACHE.get(ref_key)
    if cached_ref is not None:
        kp2_tuple, desc2 = cached_ref
        kp2 = list(kp2_tuple)
    else:
        kp2_seq, desc2 = extractor.detectAndCompute(
            cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY), None
        )
        kp2 = list(kp2_seq)
        if desc2 is not None:
            _REF_FEATURES_CACHE[ref_key] = (tuple(kp2_seq), desc2)

    if desc1 is None or desc2 is None:
        raise RegistrationError(
            "หาตารางไม่พบ กรุณาตรวจภาพต้นฉบับ",
            diagnostics={"stage": "features", "seconds": round(perf_counter() - started, 6)},
        )
    matches = cv2.BFMatcher(cv2.NORM_L2 if refined else cv2.NORM_HAMMING).knnMatch(
        desc1, desc2, k=2
    )
    good = [
        pair[0] for pair in matches if len(pair) == 2 and pair[0].distance < 0.7 * pair[1].distance
    ]

    def _paper_quad_fallback() -> tuple[np.ndarray, dict] | None:
        """Register opt-in discovered templates from the page boundary."""
        if template_def is None or not template_def.registration_config.get(
            "allow_paper_quad_fallback", False
        ):
            return None
        from exam_grader.template_discovery import detect_paper

        fallback, fallback_matrix, paper_conf, corners = detect_paper(
            image, reference.shape[1], reference.shape[0]
        )
        if paper_conf < 0.55:
            return None
        coverage = cv2.warpPerspective(
            np.ones(image.shape[:2], np.uint8), fallback_matrix,
            (reference.shape[1], reference.shape[0]),
        )
        if template_def.answer_blocks:
            ymin = min(b.row_boundaries[0] for b in template_def.answer_blocks)
            ymax = max(b.row_boundaries[-1] for b in template_def.answer_blocks)
            xmin = min(b.col_boundaries[0] for b in template_def.answer_blocks)
            xmax = max(b.col_boundaries[-1] for b in template_def.answer_blocks)
            table_coverage = float(coverage[ymin:ymax, xmin:xmax].mean())
        else:
            table_coverage = 0.0
        if table_coverage < 0.985:
            return None
        return fallback, {
            "matrix": fallback_matrix.tolist(),
            "inverse_matrix": np.linalg.inv(fallback_matrix).tolist(),
            "inliers": 0,
            "good_matches": len(good),
            "method": "paper-quad-fallback-v1",
            "paper_confidence": round(float(paper_conf), 3),
            "paper_corners": corners.tolist(),
            "table_coverage": round(table_coverage, 6),
            "review_required": paper_conf < 0.85,
            "seconds": round(perf_counter() - started, 6),
        }

    if len(good) < 24:
        fallback_result = _paper_quad_fallback()
        if fallback_result is not None:
            return fallback_result
        raise RegistrationError(
            "จัดแนวภาพไม่ได้ กรุณาตรวจหรือถ่ายภาพใหม่",
            diagnostics={
                "stage": "matches",
                "good_matches": len(good),
                "seconds": round(perf_counter() - started, 6),
            },
        )
    src = np.asarray([kp1[m.queryIdx].pt for m in good], dtype=np.float32)
    dst = np.asarray([kp2[m.trainIdx].pt for m in good], dtype=np.float32)
    matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 2.5)

    def _is_valid_homography(m: np.ndarray | None, k: np.ndarray | None) -> bool:
        if m is None or k is None:
            return False
        inliers = int(k.sum())
        ratio = float(k.mean())
        if inliers < 20:
            return False
        if ratio >= 0.45:
            return True
        # For dense keypoint matching where paper background textures generate matches,
        # high inlier counts (>50 or >100) are mathematically impossible by chance with RANSAC
        if inliers >= 80 and ratio >= 0.35:
            return True
        if inliers >= 150 and ratio >= 0.30:
            return True
        return False

    if not _is_valid_homography(matrix, mask):
        if refined:
            matrix_alt, mask_alt = cv2.findHomography(src, dst, cv2.RANSAC, 3.5)
            if _is_valid_homography(matrix_alt, mask_alt):
                matrix, mask = matrix_alt, mask_alt
            else:
                fallback_result = _paper_quad_fallback()
                if fallback_result is not None:
                    return fallback_result
                raise RegistrationError(
                    "ภาพไม่ตรงแบบหลัก หรือจัดแนวไม่ชัดเจน",
                    diagnostics={
                        "stage": "homography",
                        "good_matches": len(good),
                        "seconds": round(perf_counter() - started, 6),
                    },
                )
        else:
            fallback_result = _paper_quad_fallback()
            if fallback_result is not None:
                return fallback_result
            raise RegistrationError(
                "ภาพไม่ตรงแบบหลัก หรือจัดแนวไม่ชัดเจน",
                diagnostics={
                    "stage": "homography",
                    "good_matches": len(good),
                    "seconds": round(perf_counter() - started, 6),
                },
            )
    inlier_points = dst[mask.ravel().astype(bool)]
    span = np.ptp(inlier_points, axis=0)
    min_span_x = 500 if template_def is None else int(reference.shape[1] * 0.45)
    min_span_y = (
        (300 if refined else 400)
        if template_def is None
        else int(reference.shape[0] * (0.25 if refined else 0.35))
    )
    if span[0] < min_span_x or span[1] < min_span_y:
        fallback_result = _paper_quad_fallback()
        if fallback_result is not None:
            return fallback_result
        raise RegistrationError(
            "พบตารางไม่ครบทั้งหน้า",
            diagnostics={
                "stage": "coverage",
                "anchor_span": [float(span[0]), float(span[1])],
                "seconds": round(perf_counter() - started, 6),
            },
        )
    matrix = matrix @ np.diag([scale, scale, 1.0])
    aligned = cv2.warpPerspective(
        image, matrix, (reference.shape[1], reference.shape[0]), borderValue=(255, 255, 255)
    )

    theme = (
        template_def.registration_config.get("color_theme", "green") if template_def else "green"
    )
    if theme == "green":

        def form_signal(pixels):
            values = pixels.astype(np.float32)
            green = values[:, :, 1] - (values[:, :, 0] + values[:, :, 2]) / 2
            return cv2.GaussianBlur(green, (5, 5), 0)
    else:

        def form_signal(pixels):
            gray_sig = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY).astype(np.float32)
            return cv2.GaussianBlur(gray_sig, (5, 5), 0)

    try:
        if not refined:
            raise cv2.error("refinement not requested")
        ref_sig = form_signal(reference)
        ali_sig = form_signal(aligned)
        max_dim = max(ref_sig.shape[:2])
        if max_dim > 860:
            ecc_scale = 860.0 / max_dim
            s_ref = cv2.resize(ref_sig, None, fx=ecc_scale, fy=ecc_scale)
            s_ali = cv2.resize(ali_sig, None, fx=ecc_scale, fy=ecc_scale)
        else:
            ecc_scale = 1.0
            s_ref, s_ali = ref_sig, ali_sig

        _, corr_small = cv2.findTransformECC(
            s_ref,
            s_ali,
            np.eye(3, dtype=np.float32),
            cv2.MOTION_HOMOGRAPHY,
            (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 25, 1e-5),
        )
        if ecc_scale < 1.0:
            S = np.diag([ecc_scale, ecc_scale, 1.0])
            correction = np.linalg.inv(S) @ corr_small @ S
        else:
            correction = corr_small

        corners = np.array(
            [
                [
                    [30.0, 180.0],
                    [float(reference.shape[1] - 30), 180.0],
                    [float(reference.shape[1] - 30), float(reference.shape[0] - 100)],
                    [30.0, float(reference.shape[0] - 100)],
                ]
            ],
            np.float32,
        )
        if (
            np.max(np.linalg.norm(cv2.perspectiveTransform(corners, correction) - corners, axis=2))
            < 25
        ):
            matrix = np.linalg.inv(correction) @ matrix
            aligned = cv2.warpPerspective(
                image, matrix, (reference.shape[1], reference.shape[0]), borderValue=(255, 255, 255)
            )
    except cv2.error:
        pass

    coverage = cv2.warpPerspective(
        np.ones(image.shape[:2], np.uint8), matrix, (reference.shape[1], reference.shape[0])
    )
    if template_def is None:
        table_cov = float(coverage[227:714, 56:814].mean())
    else:
        ymin = min(b.row_boundaries[0] for b in template_def.answer_blocks)
        ymax = max(b.row_boundaries[-1] for b in template_def.answer_blocks)
        xmin = min(b.col_boundaries[0] for b in template_def.answer_blocks)
        xmax = max(b.col_boundaries[-1] for b in template_def.answer_blocks)
        table_cov = float(coverage[ymin:ymax, xmin:xmax].mean())

    if table_cov < 0.995:
        raise RegistrationError(
            "ภาพตัดตารางคำตอบไม่ครบ",
            diagnostics={
                "stage": "coverage",
                "coverage": table_cov,
                "seconds": round(perf_counter() - started, 6),
            },
        )
    return aligned, {
        "matrix": matrix.tolist(),
        "inliers": int(mask.sum()),
        "method": "sift-ransac-ecc-v2" if refined else "orb-ransac-draft-v1",
        "good_matches": len(good),
        "inlier_ratio": round(float(mask.mean()), 6),
        "table_coverage": table_cov,
        "seconds": round(perf_counter() - started, 6),
    }


def align_block_lattice(
    gray: np.ndarray, block: AnswerBlock, search_range: int = 18
) -> tuple[int, int]:
    """Find exact (dx, dy) translation offset for an answer block by Sobel line resonance.

    Photocopied and photographed sheets often carry a 5-32px translation residual
    relative to the canonical blank reference. Correlating horizontal and vertical
    Sobel gradients along the block's expected row and column boundaries snaps the
    cell coordinates snugly to the physical table grid.
    """
    bx0, by0 = block.col_boundaries[0], block.row_boundaries[0]
    bx1, by1 = block.col_boundaries[-1], block.row_boundaries[-1]
    pad = search_range + 5
    h_img, w_img = gray.shape[:2]
    y_min, y_max = max(0, by0 - pad), min(h_img, by1 + pad)
    x_min, x_max = max(0, bx0 - pad), min(w_img, bx1 + pad)
    region = gray[y_min:y_max, x_min:x_max]
    if region.size == 0 or region.shape[0] < 10 or region.shape[1] < 10:
        return 0, 0

    sob_y = np.abs(cv2.Sobel(region, cv2.CV_64F, 0, 1, ksize=3))
    sob_x = np.abs(cv2.Sobel(region, cv2.CV_64F, 1, 0, ksize=3))
    expected_rows = [r - y_min for r in block.row_boundaries]
    expected_cols = [c - x_min for c in block.col_boundaries]

    best_dy, max_score_y = 0, -1.0
    for dy in range(-search_range, search_range + 1):
        valid_rows = [r + dy for r in expected_rows if 0 <= r + dy < region.shape[0]]
        if not valid_rows:
            continue
        score = sum(float(sob_y[r, :].mean()) for r in valid_rows)
        if score > max_score_y:
            max_score_y = score
            best_dy = dy

    best_dx, max_score_x = 0, -1.0
    for dx in range(-search_range, search_range + 1):
        valid_cols = [c + dx for c in expected_cols if 0 <= c + dx < region.shape[1]]
        if not valid_cols:
            continue
        score = sum(float(sob_x[:, c].mean()) for c in valid_cols)
        if score > max_score_x:
            max_score_x = score
            best_dx = dx

    return best_dx, best_dy


def analyze(
    data: bytes,
    *,
    refined: bool = False,
    template_def: TemplateDefinition | None = None,
    app_data_dir: Path | None = None,
    reference_override: np.ndarray | None = None,
    decoded_image: np.ndarray | None = None,
) -> dict:
    decode_started = perf_counter()
    decoded = decoded_image if decoded_image is not None else decode(data)
    decode_seconds = perf_counter() - decode_started
    registration_started = perf_counter()
    try:
        aligned, registration = register(
            decoded,
            template_def=template_def,
            refined=refined,
            app_data_dir=app_data_dir,
            reference_override=reference_override,
        )
    except RegistrationError:
        if refined:
            raise
        return analyze(
            data,
            template_def=template_def,
            refined=True,
            app_data_dir=app_data_dir,
            reference_override=reference_override,
            decoded_image=decoded,
        )
    registration_seconds = perf_counter() - registration_started

    effective_template = (
        template_def if template_def is not None else default_1_template_definition()
    )
    if template_def is not None:
        ref_img = get_reference_image(
            template_def, app_data_dir=app_data_dir, reference_override=reference_override
        )
    elif reference_override is not None:
        ref_img = reference_override
    else:
        ref_img = reference_image()
    reference = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY).astype(np.float32)
    # Raw pixel subtraction is invalid for photographs with exposure/illumination
    # differences. Local darkness is a conservative mark feature that suppresses
    # broad lighting changes while retaining dark strokes inside a cell.
    local_background = cv2.GaussianBlur(gray, (0, 0), 9)
    darkness = local_background - gray
    if refined:
        darkness = darkness * 180 / np.maximum(local_background, 30)
    omr_started = perf_counter()
    answers = []

    # Phase-2 Local Grid Snapping: for discovered/custom templates with fallback registration,
    # compute local (dx, dy) per block to absorb physical paper margin skew.
    block_offsets: dict[int, tuple[int, int]] = {}
    use_lattice_snapping = (
        registration.get("method") == "paper-quad-fallback-v1"
        or effective_template.registration_config.get("allow_paper_quad_fallback", False)
    )
    if use_lattice_snapping:
        gray_u8 = gray.astype(np.uint8)
        for block in effective_template.answer_blocks:
            block_offsets[block.block_index] = align_block_lattice(gray_u8, block)
    else:
        for block in effective_template.answer_blocks:
            block_offsets[block.block_index] = (0, 0)

    q_to_block: dict[int, AnswerBlock] = {}
    for block in effective_template.answer_blocks:
        for q in range(block.question_start, block.question_end + 1):
            q_to_block[q] = block

    theme = effective_template.registration_config.get("color_theme", "green")
    total_q = effective_template.question_count
    for question in range(1, total_q + 1):
        block = q_to_block[question]
        dx, dy = block_offsets.get(block.block_index, (0, 0))
        choice_count = block.choice_count
        densities = []
        cores = []
        for choice in range(choice_count):
            x, y, w, h = cell_rect(question, choice, template_def=effective_template)
            x += dx
            y += dy
            cell_raw = darkness[y : y + h, x : x + w] > (16 if refined else INK_DARKNESS_THRESHOLD)
            cell_ink = cell_raw.astype(np.uint8) * 255
            # Morphological grid line removal: eliminates table borders that encroach on the cell
            # while leaving diagonal pencil strokes ("X") intact.
            if refined and theme != "green":
                h_k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(7, min(13, w // 2)), 1))
                v_k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(7, min(13, h // 3))))
                h_lines = cv2.morphologyEx(cell_ink, cv2.MORPH_OPEN, h_k)
                v_lines = cv2.morphologyEx(cell_ink, cv2.MORPH_OPEN, v_k)
                clean_ink = cv2.bitwise_and(cell_ink, cv2.bitwise_not(cv2.bitwise_or(h_lines, v_lines)))
            else:
                clean_ink = cell_ink
            cores.append(float((clean_ink[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] > 0).mean()))
            densities.append(float((clean_ink > 0).mean()))
        selected, classification, reason = classify_ink(densities, cores)
        winner = int(np.argmax(densities))
        rivals = [i for i in range(choice_count) if i != winner]

        # Differential Row SNR: median baseline subtraction across choices in this row
        row_med = float(np.median(cores))
        delta_cores = [c - row_med for c in cores]
        c_winner = int(np.argmax(delta_cores))
        c_ranked = sorted(delta_cores, reverse=True)
        c_top1 = c_ranked[0]
        c_top2 = c_ranked[1] if len(c_ranked) > 1 else 0.0

        is_custom = template_def is not None and getattr(template_def, "kind", None) == "custom"
        if is_custom and classification in {"uncertain", "multiple"}:
            if not selected and max(densities) < 0.06 and (
                (c_top1 < 0.035 and max(cores) < 0.05) or (max(densities) < 0.035 and max(cores) < 0.03)
            ):
                selected = []
                classification = "blank"
                reason = "no-answer-ink"
            elif c_top1 >= 0.05 and c_top2 < c_top1 * 0.45 and cores[c_winner] >= 0.06:
                selected = [CHOICES[c_winner]]
                classification = "single_mark"
                reason = "differential-core-dominance"
            elif c_top1 >= 0.06 and c_top2 >= c_top1 * 0.70:
                selected = [CHOICES[i] for i, dc in enumerate(delta_cores) if dc >= c_top1 * 0.70]
                classification = "multiple"
                reason = "competing-marks"

        if (
            refined
            and classification == "uncertain"
            and densities[winner] >= 0.045
            and cores[winner] >= 0.08
        ):
            if all(densities[i] < densities[winner] * 0.38 and cores[i] < 0.08 for i in rivals):
                selected, classification, reason = (
                    [CHOICES[winner]],
                    "single_mark",
                    "relative-contrast-dominance",
                )
        if refined and not selected and max(densities) >= 0.025:
            x, y, w, h = cell_rect(question, winner, template_def=effective_template)
            x += dx
            y += dy
            faint = darkness[y : y + h, x : x + w] > 12
            if (
                faint.mean() >= 0.05
                and faint[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4].mean() >= 0.07
                and all(densities[i] < 0.01 for i in rivals)
            ):
                selected, classification, reason = (
                    [CHOICES[winner]],
                    "single_mark",
                    "coherent-faint-ink",
                )
        if refined and classification in {"uncertain", "multiple"} and max(cores) < 0.08:
            xs = [c + dx for c in block.col_boundaries]
            row_idx = question - block.question_start
            y1 = block.row_boundaries[row_idx] + dy
            y2 = block.row_boundaries[row_idx + 1] + dy
            strip = aligned[y1 + 3 : y2 - 3, xs[0] : xs[-1]].astype(np.float32)
            if theme == "green":
                green = strip[:, :, 1] - (strip[:, :, 0] + strip[:, :, 2]) / 2
                mask = ((darkness[y1 + 3 : y2 - 3, xs[0] : xs[-1]] > 16) & (green < 10)).astype(
                    np.uint8
                )
            else:
                raw_mask = (darkness[y1 + 3 : y2 - 3, xs[0] : xs[-1]] > 16).astype(np.uint8)
                h_k = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
                v_k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
                h_l = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, h_k)
                v_l = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, v_k)
                mask = cv2.bitwise_and(raw_mask, cv2.bitwise_not(cv2.bitwise_or(h_l, v_l)))
            _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
            if len(stats) > 1:
                component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                area = int(stats[component, cv2.CC_STAT_AREA])
                mass = [
                    int((labels[:, xs[c] - xs[0] : xs[c + 1] - xs[0]] == component).sum())
                    for c in range(choice_count)
                ]
                other_area = max(
                    (
                        int(s[cv2.CC_STAT_AREA])
                        for i, s in enumerate(stats[1:], 1)
                        if i != component
                    ),
                    default=0,
                )
                if area > 100 and other_area < area * 0.3 and np.count_nonzero(mass) > 1:
                    if max(mass) / area >= 0.6:
                        selected, classification, reason = (
                            [CHOICES[int(np.argmax(mass))]],
                            "single_mark",
                            "connected-mark-majority",
                        )
                    else:
                        # A single connected stroke that genuinely spans two
                        # cells is a resolved invalid answer. It earns zero,
                        # while faint spill and disconnected marks remain
                        # reviewable/multiple through the paths above.
                        classification, reason = "boundary_cross", "mark-straddles-two-cells"
        ranked = sorted(densities, reverse=True)
        margin = ranked[0] - ranked[1] if len(ranked) > 1 else ranked[0]
        confidence_band = (
            "explicit-zero-boundary"
            if classification == "boundary_cross"
            else "review-required"
            if classification in {"uncertain", "multiple", "blank"}
            else "uncalibrated-single"
        )
        answers.append(
            {
                "question": question,
                "selected": selected,
                "classification": classification,
                "ink_density": densities,
                "core_density": cores,
                "decision_reason": reason,
                "auto_resolved": classification != "uncertain",
                "top_two_margin": round(float(margin), 6),
                "confidence_band": confidence_band,
                "feature": "relative-contrast-v2" if refined else "local-darkness-v1",
            }
        )
    omr_seconds = perf_counter() - omr_started
    if not refined and any(a["classification"] == "uncertain" for a in answers):
        try:
            rescued = analyze(
                data,
                template_def=template_def,
                refined=True,
                app_data_dir=app_data_dir,
                reference_override=reference_override,
                decoded_image=decoded,
            )
            if sum(a["classification"] == "uncertain" for a in rescued["answers"]) < sum(
                a["classification"] == "uncertain" for a in answers
            ):
                return rescued
        except RegistrationError:
            pass  # Retain the valid conservative observation if rescue fails.
    out_template_id = template()["id"] if template_def is None else template_def.template_id
    return {
        "template_id": out_template_id,
        "pipeline_version": OMR_PIPELINE_VERSION,
        "registration": registration,
        "answers": answers,
        "aligned": aligned,
        "student_number": None,
        "requires_review": True,
        "review_reason": "Experimental geometry/OMR; no calibrated real-sheet benchmark or digit model",
        "stage_timings": {
            "decode_seconds": round(decode_seconds, 6),
            "registration_seconds": round(registration_seconds, 6),
            "omr_seconds": round(omr_seconds, 6),
        },
        "photometric_diagnostics": {
            "reference_gray_mean": round(float(reference.mean()), 3),
            "aligned_gray_mean": round(float(gray.mean()), 3),
            "local_darkness_median": round(float(np.median(darkness)), 3),
            "feature_config": "local-background-gaussian-sigma-9",
        },
    }
