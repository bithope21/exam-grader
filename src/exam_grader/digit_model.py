"""Small dependency-free digit model shared by training and runtime benchmark tools."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

DIGIT_MODEL_VERSION = "student-number-digit-knn-v1"
FEATURE_SIZE = 28


def bundled_digit_model_path() -> Path | None:
    path = Path(__file__).resolve().parent / "resources" / "student_number_digit_model.npz"
    return path if path.is_file() else None


def digit_feature(image: np.ndarray) -> np.ndarray:
    """Normalize a dark-on-light digit without fitting on dataset statistics."""
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()
    gray = np.asarray(gray, dtype=np.uint8)
    if gray.size == 0:
        raise ValueError("empty digit image")
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    points = cv2.findNonZero(ink)
    canvas = np.zeros((FEATURE_SIZE, FEATURE_SIZE), dtype=np.uint8)
    if points is None:
        return canvas.reshape(-1).astype(np.float32)
    x, y, width, height = cv2.boundingRect(points)
    glyph = ink[y : y + height, x : x + width]
    scale = min((FEATURE_SIZE - 4) / max(width, 1), (FEATURE_SIZE - 4) / max(height, 1))
    resized = cv2.resize(
        glyph,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    offset_x = (FEATURE_SIZE - resized.shape[1]) // 2
    offset_y = (FEATURE_SIZE - resized.shape[0]) // 2
    canvas[offset_y : offset_y + resized.shape[0], offset_x : offset_x + resized.shape[1]] = resized
    return (canvas.reshape(-1).astype(np.float32) / 255.0)


def feature_matrix(images: list[np.ndarray]) -> np.ndarray:
    if not images:
        return np.empty((0, FEATURE_SIZE * FEATURE_SIZE), dtype=np.float32)
    return np.vstack([digit_feature(image) for image in images]).astype(np.float32)


class DigitModel:
    """Persisted KNN or centroid classifier with explicit top candidates."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.kind = str(payload["kind"])
        self.version = str(payload["version"])
        self.calibration = dict(payload.get("calibration", {}))
        self.labels = np.asarray(payload["labels"], dtype=np.int64)
        self.features = np.asarray(payload.get("features", []), dtype=np.float32)
        self.centroids = np.asarray(payload.get("centroids", []), dtype=np.float32)
        if self.kind not in {"knn", "centroid"}:
            raise ValueError(f"unsupported digit model kind: {self.kind}")
        if self.kind == "knn" and len(self.features) != len(self.labels):
            raise ValueError("KNN model feature/label length mismatch")
        if self.kind == "centroid" and len(self.centroids) != len(self.labels):
            raise ValueError("centroid model centroid/label length mismatch")

    @classmethod
    def load(cls, path: Path) -> "DigitModel":
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"].item()))
            payload: dict[str, Any] = {
                **metadata,
                "labels": archive["labels"],
            }
            for name in ("features", "centroids"):
                if name in archive:
                    payload[name] = archive[name]
        return cls(payload)

    @classmethod
    def from_training(
        cls,
        kind: str,
        features: np.ndarray,
        labels: np.ndarray,
        version: str = DIGIT_MODEL_VERSION,
        calibration: dict[str, Any] | None = None,
    ) -> "DigitModel":
        unique = np.array(sorted(set(int(value) for value in labels)), dtype=np.int64)
        if kind == "knn":
            return cls(
                {
                    "kind": kind,
                    "version": version,
                    "labels": labels,
                    "features": features,
                    "calibration": calibration or {},
                }
            )
        if kind == "centroid":
            centroids = np.vstack([features[labels == label].mean(axis=0) for label in unique])
            return cls(
                {
                    "kind": kind,
                    "version": version,
                    "labels": unique,
                    "centroids": centroids,
                    "calibration": calibration or {},
                }
            )
        raise ValueError(f"unsupported training kind: {kind}")

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = json.dumps(
            {"kind": self.kind, "version": self.version, "calibration": self.calibration},
            sort_keys=True,
        )
        values: dict[str, Any] = {"metadata": np.array(metadata), "labels": self.labels}
        if self.kind == "knn":
            values["features"] = self.features
        else:
            values["centroids"] = self.centroids
        np.savez_compressed(path, **values)

    def predict(self, image: np.ndarray, *, top_k: int = 3) -> dict[str, Any]:
        vector = image.astype(np.float32) if image.ndim == 1 else digit_feature(image)
        if vector.shape != (FEATURE_SIZE * FEATURE_SIZE,):
            raise ValueError("digit feature vector has unexpected shape")
        if self.kind == "knn":
            distances = np.linalg.norm(self.features - vector, axis=1)
            nearest = np.argsort(distances)[: min(5, len(distances))]
            votes = Counter(int(self.labels[index]) for index in nearest)
            ranked = sorted(
                votes,
                key=lambda label: (-votes[label], float(np.min(distances[self.labels == label])), label),
            )
            denominator = max(1, len(nearest))
            scores = {
                str(label): round(100.0 * votes[label] / denominator, 4) for label in ranked
            }
        else:
            distances = np.linalg.norm(self.centroids - vector, axis=1)
            order = np.argsort(distances)
            ranked = [int(self.labels[index]) for index in order]
            best = float(distances[order[0]]) if len(order) else 1.0
            scores = {
                str(label): round(100.0 / (1.0 + float(distances[index])), 4)
                for index, label in zip(order, ranked)
            }
            if best == 0:
                scores[str(ranked[0])] = 100.0
        ranked = ranked[:top_k]
        confidence = scores[str(ranked[0])] if ranked else None
        cap = self.calibration.get("max_confidence")
        if isinstance(cap, (int, float)) and confidence is not None:
            confidence = min(float(confidence), float(cap))
        return {
            "candidate": str(ranked[0]) if ranked else None,
            "candidates": [str(label) for label in ranked],
            "scores": {str(label): scores[str(label)] for label in ranked},
            "confidence": round(confidence, 4) if confidence is not None else None,
            "margin": (
                round(scores[str(ranked[0])] - scores[str(ranked[1])], 4)
                if len(ranked) > 1
                else 100.0
            ),
            "model_kind": self.kind,
            "model_version": self.version,
            "calibration": self.calibration,
        }
