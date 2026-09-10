"""Review-required student-number observation adapter.

This module deliberately has no silent fallback to a guessed number.  Tesseract,
when installed, is only a benchmark candidate and its result remains uncalibrated.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from exam_grader.imaging import decode, template

IDENTITY_PIPELINE_VERSION = "student-number-adaptive-roi-v4"


def find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    # Finder-launched macOS apps do not inherit the interactive shell PATH.
    if sys.platform == "darwin":
        for location in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"):
            if Path(location).is_file():
                return location
    return None


@lru_cache(maxsize=4)
def backend_provenance(executable: str) -> dict:
    result = {"executable": executable, "language": "eng"}
    try:
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=8)
        result["version"] = version.stdout.splitlines()[0]
        languages = subprocess.run([executable, "--list-langs"], capture_output=True, text=True, timeout=8)
        match = re.search(r'"([^"]+)"', languages.stdout)
        if match:
            model = Path(match.group(1)) / "eng.traineddata"
            if model.is_file():
                result["traineddata_sha256"] = hashlib.sha256(model.read_bytes()).hexdigest()
    except (OSError, subprocess.TimeoutExpired, IndexError):
        result["provenance_status"] = "backend metadata unavailable"
    return result


def _roi_crop(aligned: np.ndarray) -> np.ndarray:
    x1, y1, x2, y2 = template()["student_number_roi"]
    if x2 <= x1 or y2 <= y1 or x1 < 0 or y1 < 0:
        raise ValueError("student-number ROI ไม่ถูกต้อง")
    crop = aligned[y1:y2, x1:x2]
    if crop.size == 0:
        raise ValueError("student-number ROI ว่าง")
    return crop


def number_roi(data: bytes, matrix: list[list[float]] | None = None, *, top_padding: int = 0) -> np.ndarray:
    """Return a high-resolution ROI crop in canonical coordinates when possible."""
    image = decode(data)
    geometry = template()
    transform = np.eye(3, dtype=np.float64) if matrix is None else np.asarray(matrix, dtype=np.float64)
    if transform.shape != (3, 3) or not np.isfinite(transform).all() or abs(np.linalg.det(transform)) < 1e-12:
        raise ValueError("registration transform ไม่ถูกต้อง")
    scale = max(1.0, min(4.0, max(image.shape[:2]) / max(geometry["width"], geometry["height"])))
    x1, y1, x2, y2 = (int(value * scale) for value in geometry["student_number_roi"])
    y1 = max(0, y1 - int(top_padding * scale))
    scaled = np.array([[1, 0, -x1], [0, 1, -y1], [0, 0, 1]]) @ np.diag([scale, scale, 1.0]) @ transform
    corners = np.array([[[0., 0.], [x2 - x1 - 1., 0.], [x2 - x1 - 1., y2 - y1 - 1.], [0., y2 - y1 - 1.]]])
    source_corners = cv2.perspectiveTransform(corners, np.linalg.inv(scaled))[0]
    if (not np.isfinite(source_corners).all() or (source_corners < 0).any()
            or (source_corners[:, 0] >= image.shape[1]).any()
            or (source_corners[:, 1] >= image.shape[0]).any()):
        raise ValueError("student-number ROI อยู่นอกภาพ")
    crop = cv2.warpPerspective(
        image,
        scaled,
        (x2 - x1, y2 - y1),
        borderValue=(255, 255, 255),
    )
    if crop.size == 0:
        raise ValueError("student-number ROI ว่าง")
    return crop


def _normalize_candidate(value: str) -> str | None:
    value = value.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
    digits = re.sub(r"[^0-9]", "", value)
    return digits or None


def preprocess(crop: np.ndarray) -> tuple[np.ndarray, list[list[int]], np.ndarray]:
    """Suppress form texture, locate ink, retain gray strokes for OCR.

    Component boxes are diagnostics, not independently recognized characters:
    disconnected strokes are joined by their overlapping x projection.
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    scale = crop.shape[0] / 136.0
    darkness = cv2.GaussianBlur(gray, (0, 0), max(2, 9 * scale)) - gray
    mask = (darkness > 30).astype(np.uint8) * 255
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    ink = np.zeros_like(mask)
    for index, (x, y, w, h, area) in enumerate(stats[1:], 1):
        if h >= 25 * scale and area >= 55 * scale * scale and w < crop.shape[1] * 0.8:
            ink[labels == index] = 255
    occupied = np.flatnonzero(ink.any(axis=0))
    boxes = []
    if occupied.size:
        groups = np.split(occupied, np.where(np.diff(occupied) > max(2, round(3 * scale)))[0] + 1)
        for group in groups:
            x1, x2 = int(group[0]), int(group[-1]) + 1
            ys = np.flatnonzero(ink[:, x1:x2].any(axis=1))
            boxes.append([x1, int(ys[0]), x2 - x1, int(ys[-1] - ys[0] + 1)])
    return 255 - ink, boxes, gray.astype(np.uint8)


def _ocr(executable: str, path: Path, psm: int, *, allow_zero: bool = False) -> dict:
    try:
        result = subprocess.run(
            [executable, str(path), "stdout", "-l", "eng", "--psm", str(psm),
             "-c", "tessedit_char_whitelist=0123456789", "tsv"],
            capture_output=True, text=True, check=False, timeout=8,
        )
    except subprocess.TimeoutExpired:
        return {"candidate": None, "raw_score": None, "error": "timeout"}
    words = [row for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t")
             if row.get("level") == "5" and row.get("text", "").strip()]
    value = "".join(row["text"].strip() for row in words)
    valid = value.isascii() and value.isdigit() and 1 <= len(value) <= 6 and (int(value) > 0 or allow_zero)
    return {"candidate": value if valid else None,
            "raw_score": min((float(row["conf"]) for row in words), default=None),
            "exit_code": result.returncode}


def observe(data: bytes, matrix: list[list[float]] | None = None, *, diagnostics_dir: Path | None = None) -> dict:
    base: dict = {"pipeline_version": IDENTITY_PIPELINE_VERSION, "candidate": None,
            "candidates": [], "confidence": None, "requires_review": True,
            "review_reason": "uncalibrated local OCR; teacher confirmation required"}
    if matrix is None and decode(data).shape[:2] != (template()["height"], template()["width"]):
        return {**base, "review_reason": "registration unavailable; teacher confirmation required"}
    crop = number_roi(data, matrix)
    processed, boxes, gray = preprocess(crop)
    top_padding = 0
    if any(y <= 1 and h > crop.shape[0] * .2 for x, y, w, h in boxes):
        top_padding = 20
        crop = number_roi(data, matrix, top_padding=top_padding)
        processed, boxes, gray = preprocess(crop)
    encoded = cv2.imencode(".png", crop)[1].tobytes()
    diagnostics = {
        "roi": list(template()["student_number_roi"]), "template_id": template()["id"],
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "registration_matrix": matrix,
        "crop_width": int(crop.shape[1]), "crop_height": int(crop.shape[0]),
        "crop_sha256": hashlib.sha256(encoded).hexdigest(), "model": IDENTITY_PIPELINE_VERSION,
        "confidence_semantics": "uncalibrated OCR scores, not probability of correctness",
        "segmented_boxes": boxes, "recognizer_runs": [],
        "top_padding": top_padding,
    }
    if diagnostics_dir is not None:
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        (diagnostics_dir / "number_roi_original.png").write_bytes(encoded)
        cv2.imwrite(str(diagnostics_dir / "number_roi_processed.png"), processed)
        boxed = crop.copy()
        for x, y, w, h in boxes:
            cv2.rectangle(boxed, (x, y), (x + w, y + h), (0, 0, 220), 1)
        cv2.imwrite(str(diagnostics_dir / "segmented_digits.png"), boxed)
    executable = find_tesseract()
    if executable is None or not boxes or len(boxes) > 6:
        reason = "numeric recognizer unavailable" if executable is None else "blank or unresolved handwriting"
        return {**base, "review_reason": reason + "; teacher confirmation required", "diagnostics": diagnostics}
    diagnostics["backend"] = backend_provenance(executable)
    x1 = max(0, min(b[0] for b in boxes) - 3)
    y1 = max(0, min(b[1] for b in boxes) - 3)
    x2 = min(gray.shape[1], max(b[0] + b[2] for b in boxes) + 3)
    y2 = min(gray.shape[0], max(b[1] + b[3] for b in boxes) + 3)
    glyph = gray[y1:y2, x1:x2].copy()
    cv2.normalize(glyph, glyph, 0, 255, cv2.NORM_MINMAX)
    binary = cv2.threshold(glyph, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    variants = [("gray-line", glyph, 64, 7), ("binary-line", binary, 64, 7),
                ("gray-word", glyph, 64, 13), ("binary-word", binary, 64, 13)]
    # A separate ink-only view tests 1/4 ambiguity without changing the original.
    ys, xs = np.where(processed == 0)
    ink_glyph = processed[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    variants.append(("ink-word", ink_glyph, 100, 13))
    runs = []
    with tempfile.TemporaryDirectory(prefix="exam-grader-number-") as directory:
        for name, pixels, height, psm in variants:
            resized = cv2.resize(pixels, (max(1, round(pixels.shape[1] * height / pixels.shape[0])), height),
                                 interpolation=cv2.INTER_AREA)
            padding = 12 if name == "ink-word" else 16
            resized = cv2.copyMakeBorder(resized, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=255)
            path = Path(directory) / f"{name}.png"
            cv2.imwrite(str(path), resized)
            if diagnostics_dir is not None:
                (diagnostics_dir / path.name).write_bytes(path.read_bytes())
            runs.append({"variant": name, **_ocr(executable, path, psm)})
    values = [r["candidate"] for r in runs if r["candidate"]]
    candidates = sorted(set(values), key=lambda value: (-values.count(value), -max(r["raw_score"] or 0 for r in runs if r["candidate"] == value), value))
    # Narrow upper hook + lower shaft is evidence for 1 only when OCR itself
    # supplies 1 as an alternative. Never synthesize a digit from geometry alone.
    lower = ink_glyph[2 * ink_glyph.shape[0] // 3:] == 0
    columns = np.flatnonzero(lower.any(axis=0))
    slender = (len(boxes) == 1 and ink_glyph.shape[1] / ink_glyph.shape[0] < 0.5
               and columns.size > 0 and np.ptp(columns) / ink_glyph.shape[1] < 0.55)
    if slender and "1" in candidates and "4" in candidates:
        candidates.remove("1")
        candidates.insert(0, "1")
    diagnostics["recognizer_runs"] = runs
    diagnostics["slender_shaft_1_4"] = bool(slender)
    if 2 <= len(boxes) <= 6:
        segmented: list[dict] = []
        with tempfile.TemporaryDirectory(prefix="exam-grader-digits-") as directory:
            for index, (x, y, w, h) in enumerate(boxes):
                pixels = gray[max(0, y - 3):min(gray.shape[0], y + h + 3), max(0, x - 3):min(gray.shape[1], x + w + 3)].copy()
                cv2.normalize(pixels, pixels, 0, 255, cv2.NORM_MINMAX)
                ink = processed[y:y + h, x:x + w]
                options = []
                for label, part, height, psm in (("gray", pixels, 64, 10), ("ink", ink, 100, 13)):
                    scaled = cv2.resize(part, (max(1, round(part.shape[1] * height / part.shape[0])), height), interpolation=cv2.INTER_AREA)
                    scaled = cv2.copyMakeBorder(scaled, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
                    path = Path(directory) / f"digit-{index}-{label}.png"
                    cv2.imwrite(str(path), scaled)
                    if diagnostics_dir is not None:
                        (diagnostics_dir / path.name).write_bytes(path.read_bytes())
                    options.append({"variant": label, **_ocr(executable, path, psm, allow_zero=True)})
                digits = [o["candidate"] for o in options if o["candidate"] and len(o["candidate"]) == 1]
                shaft = np.flatnonzero((ink[2 * h // 3:] == 0).any(axis=0))
                is_one = w / h < 0.5 and shaft.size > 0 and np.ptp(shaft) / w < 0.55
                left_y, left_x = np.where(ink[:, :w // 2] == 0)
                bottom_y, bottom_x = np.where(ink[3 * h // 4:] == 0)
                correlation = float(np.corrcoef(left_x, left_y)[0, 1]) if len(left_x) > 10 and np.std(left_x) > 0 else 0
                right_shaft = bottom_x.size > 0 and float(bottom_x.mean()) > w * .65
                ranked = sorted((o for o in options if o["candidate"] in digits),
                                key=lambda o: o["raw_score"] or 0, reverse=True)
                value = "1" if is_one and "1" in digits else ranked[0]["candidate"] if ranked else None
                if right_shaft and w / h < .75 and correlation < -.65:
                    value = "1"
                elif value is None and right_shaft and w / h < .65 and correlation > .65:
                    value = "4"
                # Whole-word OCR can resolve an isolated glyph that yields no
                # character result. Require agreement at this exact position.
                whole = [v[index] for v in values if len(v) == len(boxes)]
                if value is None and whole and len(set(whole)) == 1:
                    value = whole[0]
                segmented.append({"box": [x, y, w, h], "candidate": value, "runs": options})
        diagnostics["digit_observations"] = segmented
        if all(d["candidate"] is not None for d in segmented):
            value = "".join(d["candidate"] for d in segmented)
            if int(value) > 0:
                if value in candidates:
                    candidates.remove(value)
                candidates.insert(0, value)
    ambiguous_leading_digit = False
    if top_padding and len(boxes) == 2 and candidates and candidates[0].startswith("4") and len(candidates[0]) == 2:
        x, y, w, h = boxes[0]
        if w / h < .5:
            alternative = "1" + candidates[0][1:]
            if alternative not in candidates:
                candidates.append(alternative)
            ambiguous_leading_digit = True
    return {**base, "candidate": candidates[0] if candidates and not ambiguous_leading_digit else None,
            "candidates": candidates, "diagnostics": diagnostics,
            "review_reason": ("conflicting OCR candidates; teacher confirmation required"
                              if len(candidates) > 1 else base["review_reason"])}
