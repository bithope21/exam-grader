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
        raise RuntimeError("ขนาดภาพอ้างอิงไม่ตรงกับแบบฟอร์ม")
    for extension in (".png", ".jpg"):
        ok, data = cv2.imencode(extension, np.full((16, 16, 3), 255, np.uint8))
        if not ok or decode(data.tobytes()).shape != (16, 16, 3):
            raise RuntimeError(f"ตัวอ่านภาพ {extension} ไม่พร้อม")
    return {"opencv": cv2.__version__, "numpy": np.__version__, "openpyxl": openpyxl.__version__,
            "codecs": ["png", "jpeg"], "reference": "hash_verified",
            "answers": "experimental_teacher_review_required",
            "student_number": IDENTITY_PIPELINE_VERSION,
            "numeric_backend_available": find_tesseract() is not None}
