"""Startup checks for shipped dependencies and reference resources."""

import cv2
import numpy as np
import openpyxl

from exam_grader.identity import IDENTITY_PIPELINE_VERSION, find_tesseract
from exam_grader.imaging import decode, reference_image, template


def runtime_health() -> dict:
    reference = reference_image()
    geometry = template()
    if reference.shape[:2] != (geometry["height"], geometry["width"]):
        raise RuntimeError("ขนาดภาพอ้างอิง Default #1 ไม่ตรงกับแบบฟอร์ม")
    try:
        from exam_grader.template_manager import get_reference_image, load_builtin_template

        t2 = load_builtin_template("default-2")
        ref2 = get_reference_image(t2)
        if ref2.shape[:2] != (t2.canonical_height, t2.canonical_width):
            raise RuntimeError("ขนาดภาพอ้างอิง Default #2 ไม่ตรงกับแบบฟอร์ม")

        t3 = load_builtin_template("default-3")
        ref3 = get_reference_image(t3)
        if ref3.shape[:2] != (t3.canonical_height, t3.canonical_width):
            raise RuntimeError("ขนาดภาพอ้างอิง Default #3 ไม่ตรงกับแบบฟอร์ม")
    except (ValueError, FileNotFoundError) as err:
        raise RuntimeError(f"แม่แบบในตัวไม่พร้อม: {err}") from err
    for extension in (".png", ".jpg"):
        ok, data = cv2.imencode(extension, np.full((16, 16, 3), 255, np.uint8))
        if not ok or decode(data.tobytes()).shape != (16, 16, 3):
            raise RuntimeError(f"ตัวอ่านภาพ {extension} ไม่พร้อม")
    return {
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "openpyxl": openpyxl.__version__,
        "codecs": ["png", "jpeg"],
        "reference": "hash_verified",
        "answers": "experimental_teacher_review_required",
        "student_number": IDENTITY_PIPELINE_VERSION,
        "numeric_backend_available": find_tesseract() is not None,
    }
