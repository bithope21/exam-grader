"""Generic geometry helpers for immutable-source document normalization.

This module deliberately knows nothing about answer counts, blocks, or choices.
Template-aware quality scoring remains in the registration pipeline.
"""

from __future__ import annotations

import hashlib

import cv2
import numpy as np

DOCUMENT_NORMALIZATION_VERSION = "document-normalization-v2"


def validate_manual_corners(
    corners: np.ndarray | list[list[float]],
    image_shape: tuple[int, ...],
    *,
    target_size: tuple[int, int] | None = None,
) -> np.ndarray:
    """Validate four ordered, in-frame page corners without silently reordering them."""
    points = np.asarray(corners, dtype=np.float32)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise ValueError("ต้องระบุมุมกระดาษ 4 มุมที่มีพิกัดถูกต้อง")

    height, width = int(image_shape[0]), int(image_shape[1])
    if (
        (points[:, 0] < 0).any()
        or (points[:, 1] < 0).any()
        or (points[:, 0] > width - 1).any()
        or (points[:, 1] > height - 1).any()
    ):
        raise ValueError("มุมกระดาษต้องอยู่ภายในภาพต้นฉบับ")

    edges = np.roll(points, -1, axis=0) - points
    lengths = np.linalg.norm(edges, axis=1)
    if float(lengths.min()) < max(image_shape[:2]) * 0.04:
        raise ValueError("มุมกระดาษอยู่ใกล้กันเกินไป กรุณาปรับกรอบใหม่")

    cross = edges[:, 0] * np.roll(edges, -1, axis=0)[:, 1] - edges[:, 1] * np.roll(
        edges, -1, axis=0
    )[:, 0]
    if not (np.all(cross > 1e-3) or np.all(cross < -1e-3)):
        raise ValueError("กรอบกระดาษตัดกันหรือไม่เป็นสี่เหลี่ยมนูน กรุณาปรับมุมใหม่")

    area = abs(float(cv2.contourArea(points)))
    area_ratio = area / max(1.0, float(width * height))
    if not 0.08 <= area_ratio <= 0.999:
        raise ValueError("กรอบกระดาษมีขนาดไม่สมเหตุผล กรุณาตรวจมุมทั้ง 4 อีกครั้ง")

    if target_size is not None:
        target_width, target_height = target_size
        source_aspect = float((lengths[0] + lengths[2]) / max(1.0, lengths[1] + lengths[3]))
        target_aspect = float(target_width / max(1, target_height))
        if abs(float(np.log(max(source_aspect, 1e-4) / max(target_aspect, 1e-4)))) > 0.75:
            raise ValueError("สัดส่วนกรอบไม่ตรงกับแม่แบบที่เลือก กรุณาตรวจมุมหรือแม่แบบ")

    return points.copy()


def perspective_normalize(
    image: np.ndarray,
    source_to_canonical: np.ndarray | list[list[float]],
    target_size: tuple[int, int],
) -> np.ndarray:
    """Create a canonical perspective-normalized raster from the source image."""
    matrix = np.asarray(source_to_canonical, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("เมทริกซ์จัดแนวภาพไม่ถูกต้อง")
    if abs(float(np.linalg.det(matrix))) < 1e-12:
        raise ValueError("เมทริกซ์จัดแนวภาพกลับด้านไม่ได้")
    width, height = int(target_size[0]), int(target_size[1])
    if width < 1 or height < 1:
        raise ValueError("ขนาดภาพมาตรฐานไม่ถูกต้อง")
    return cv2.warpPerspective(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def source_sha256(data: bytes) -> str:
    """Return provenance for the immutable encoded source bytes."""
    return hashlib.sha256(data).hexdigest()
