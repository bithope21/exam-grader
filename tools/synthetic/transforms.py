"""Image transformation and augmentation routines for synthetic sheet generation."""

import cv2
import numpy as np


def apply_rotation(image: np.ndarray, angle_degrees: float) -> np.ndarray:
    """Rotates image by specified degrees with white border padding."""
    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle_degrees, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (w, h),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def apply_perspective_skew(image: np.ndarray, intensity: float = 0.05, rng: np.random.Generator | None = None) -> np.ndarray:
    """Applies a subtle perspective warp simulating camera angles."""
    if rng is None:
        rng = np.random.default_rng(42)

    h, w = image.shape[:2]
    dx = int(w * intensity)
    dy = int(h * intensity)

    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    dst = np.array(
        [
            [int(rng.integers(0, dx)), int(rng.integers(0, dy))],
            [w - int(rng.integers(0, dx)), int(rng.integers(0, dy))],
            [w - int(rng.integers(0, dx)), h - int(rng.integers(0, dy))],
            [int(rng.integers(0, dx)), h - int(rng.integers(0, dy))],
        ],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(
        image,
        matrix,
        (w, h),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def apply_brightness(image: np.ndarray, factor: float) -> np.ndarray:
    """Scales brightness by a factor (e.g. 0.7 for dark, 1.2 for bright)."""
    return np.clip(image.astype(np.float32) * factor, 0, 255).astype(np.uint8)


def apply_shadow(image: np.ndarray) -> np.ndarray:
    """Applies a diagonal lighting gradient / shadow across the sheet."""
    h, w = image.shape[:2]
    mask = np.linspace(0.65, 1.0, w, dtype=np.float32).reshape(1, w, 1)
    return np.clip(image.astype(np.float32) * mask, 0, 255).astype(np.uint8)


def apply_contrast(image: np.ndarray, factor: float = 0.6) -> np.ndarray:
    """Adjusts contrast around midpoint 128."""
    mean = 128.0
    return np.clip((image.astype(np.float32) - mean) * factor + mean, 0, 255).astype(np.uint8)


def apply_gaussian_blur(image: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Applies Gaussian blur."""
    return cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)


def apply_motion_blur(image: np.ndarray, size: int = 5) -> np.ndarray:
    """Applies horizontal motion blur."""
    kernel = np.zeros((size, size))
    kernel[int((size - 1) / 2), :] = np.ones(size)
    kernel /= size
    return cv2.filter2D(image, -1, kernel)


def apply_jpeg_compression(image: np.ndarray, quality: int = 50) -> np.ndarray:
    """Encodes to JPEG format at specified quality (1-100) and decodes back."""
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, encoded = cv2.imencode(".jpg", image, encode_param)
    if not success:
        return image
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    return decoded if decoded is not None else image


def apply_mild_crop(image: np.ndarray, crop_pct: float = 0.04) -> np.ndarray:
    """Crops edges by crop_pct and resizes back to original size."""
    h, w = image.shape[:2]
    dh = int(h * crop_pct)
    dw = int(w * crop_pct)
    cropped = image[dh : h - dh, dw : w - dw]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
