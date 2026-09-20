"""Benchmark a compact whole-ROI sequence recognizer beside the frozen path.

The prototype deliberately avoids connected-component digit segmentation. It
normalizes the complete handwritten ink blob into a fixed canvas, then predicts
one or two output positions from compact per-digit centroids. Seed sequence
crops are support data only; Vol.8/9/10 remain evaluation-only.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import platform
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from exam_grader.identity import number_roi, preprocess
from exam_grader.imaging import decode
from exam_grader.template_manager import TemplateDefinition

FEATURE_HEIGHT = 32
FEATURE_WIDTH = 64
POSITION_WIDTH = FEATURE_WIDTH // 2
FEATURE_SIZE = FEATURE_HEIGHT * FEATURE_WIDTH + FEATURE_HEIGHT + FEATURE_WIDTH
POSITION_FEATURE_SIZE = FEATURE_HEIGHT * POSITION_WIDTH + FEATURE_HEIGHT + POSITION_WIDTH
MODEL_VERSION = "whole-roi-sequence-centroid-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canvas_feature(canvas: np.ndarray, position: int | None = None) -> np.ndarray:
    if position is None:
        view = canvas
    else:
        start = position * POSITION_WIDTH
        view = canvas[:, start : start + POSITION_WIDTH]
    return np.concatenate((view.reshape(-1), view.mean(axis=1), view.mean(axis=0))).astype(np.float32)


def _ink_feature(image: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    """Return a centered full-ink feature without finding individual digits."""
    processed, _boxes, _gray = preprocess(image)
    ink = (255 - processed).astype(np.uint8)
    points = cv2.findNonZero(ink)
    canvas = np.zeros((FEATURE_HEIGHT, FEATURE_WIDTH), dtype=np.float32)
    if points is None:
        return _canvas_feature(canvas), 0.0, canvas

    x, y, width, height = cv2.boundingRect(points)
    glyph = ink[y : y + height, x : x + width]
    scale = min(
        (FEATURE_WIDTH - 4) / max(width, 1),
        (FEATURE_HEIGHT - 4) / max(height, 1),
    )
    resized = cv2.resize(
        glyph,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    ).astype(np.float32) / 255.0
    offset_x = (FEATURE_WIDTH - resized.shape[1]) // 2
    offset_y = (FEATURE_HEIGHT - resized.shape[0]) // 2
    canvas[offset_y : offset_y + resized.shape[0], offset_x : offset_x + resized.shape[1]] = resized
    return _canvas_feature(canvas), width / max(1.0, float(image.shape[1])), canvas


def _sequence_seed_samples(seed_manifest_path: Path) -> tuple[list[np.ndarray], list[str], list[str]]:
    manifest = json.loads(seed_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("kind") != "student_number_handwriting_seed_corpus":
        raise ValueError("unexpected seed manifest kind")
    if manifest.get("split_policy", {}).get("seed_page_split") != "seed_only":
        raise ValueError("sequence seed is not explicitly seed-only")
    source_root = Path(manifest["source_manifest"]["path"]).resolve().parent if manifest.get("source_manifest") else seed_manifest_path.parent
    images: list[np.ndarray] = []
    labels: list[str] = []
    sample_ids: list[str] = []
    for record in manifest.get("labeled_samples", []):
        label = record.get("label")
        path = source_root / record["crop_path"]
        if not isinstance(label, str) or not label.isdigit() or not path.is_file():
            raise ValueError(f"invalid seed sample: {record.get('sample_id')}")
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"could not decode seed sample: {path}")
        images.append(image)
        labels.append(label)
        sample_ids.append(str(record["sample_id"]))
    if len(set(sample_ids)) != len(sample_ids) or not images:
        raise ValueError("seed manifest has no unique samples")
    return images, labels, sample_ids


class WholeRoiSequenceModel:
    """Small centroid sequence model with fixed output positions."""

    def __init__(self, *, centroids: dict[str, np.ndarray], width_by_length: dict[int, float], seed_count: int) -> None:
        self.centroids = centroids
        self.width_by_length = width_by_length
        self.seed_count = seed_count

    @classmethod
    def fit(cls, images: list[np.ndarray], labels: list[str]) -> "WholeRoiSequenceModel":
        if len(images) != len(labels) or not images:
            raise ValueError("seed images and labels must be non-empty and aligned")
        grouped: dict[str, list[np.ndarray]] = defaultdict(list)
        widths: dict[int, list[float]] = defaultdict(list)
        for image, label in zip(images, labels, strict=True):
            if len(label) not in {1, 2} or not label.isdigit():
                raise ValueError(f"unsupported sequence label: {label}")
            feature, width_ratio, canvas = _ink_feature(image)
            widths[len(label)].append(width_ratio)
            if len(label) == 1:
                grouped[f"1:{label}"].append(feature)
            else:
                grouped[f"2:0:{label[0]}"].append(feature)
                grouped[f"2:1:{label[1]}"].append(feature)
        centroids = {
            key: np.mean(np.vstack(values), axis=0).astype(np.float32)
            for key, values in grouped.items()
        }
        width_by_length = {
            length: float(np.mean(values)) for length, values in widths.items() if values
        }
        return cls(centroids=centroids, width_by_length=width_by_length, seed_count=len(images))

    def _digit_rank(self, feature: np.ndarray, prefix: str) -> list[tuple[str, float]]:
        rows = []
        for key, centroid in self.centroids.items():
            if not key.startswith(prefix):
                continue
            digit = key.rsplit(":", 1)[-1]
            distance = float(np.linalg.norm(feature - centroid) / np.sqrt(feature.size))
            rows.append((digit, distance))
        return sorted(rows, key=lambda item: (item[1], item[0]))

    def predict(self, image: np.ndarray, *, top_k: int = 5) -> dict[str, Any]:
        feature, width_ratio, canvas = _ink_feature(image)
        available_lengths = sorted(self.width_by_length)
        if not available_lengths:
            return {"candidate": None, "candidates": [], "confidence": None, "sequence_length": None}
        length = min(available_lengths, key=lambda item: abs(width_ratio - self.width_by_length[item]))
        if length == 1:
            ranked = self._digit_rank(feature, "1:")
            candidates = ranked[:top_k]
            distances = {digit: distance for digit, distance in candidates}
        else:
            left = self._digit_rank(feature, "2:0:")[:5]
            right = self._digit_rank(feature, "2:1:")[:5]
            combinations = []
            for (left_digit, left_distance), (right_digit, right_distance) in itertools.product(left, right):
                combinations.append((left_digit + right_digit, left_distance + right_distance))
            candidates = sorted(combinations, key=lambda item: (item[1], item[0]))[:top_k]
            distances = {candidate: distance for candidate, distance in candidates}
        if not candidates:
            return {"candidate": None, "candidates": [], "confidence": None, "sequence_length": length}
        candidate = candidates[0][0]
        best_distance = float(candidates[0][1])
        runner_distance = float(candidates[1][1]) if len(candidates) > 1 else best_distance + 1.0
        return {
            "candidate": candidate,
            "candidates": [item[0] for item in candidates],
            "scores": {key: round(100.0 / (1.0 + value), 4) for key, value in distances.items()},
            "confidence": round(100.0 / (1.0 + best_distance), 4),
            "confidence_margin": round((runner_distance - best_distance) * 100.0, 4),
            "sequence_length": length,
            "width_ratio": round(width_ratio, 6),
            "model_version": MODEL_VERSION,
        }

    @property
    def model_size_bytes(self) -> int:
        return int(sum(value.nbytes for value in self.centroids.values()))


def _record_summary(records: list[dict[str, Any]], *, breakdown: bool = True) -> dict[str, Any]:
    total = len(records)
    exact = sum(bool(item.get("exact", item.get("sequence_exact", False))) for item in records)
    visible = sum(bool(item.get("visible", item.get("sequence_visible", False))) for item in records)
    return {
        "records": total,
        "exact": exact,
        "exact_rate": round(exact / total, 6) if total else None,
        "visible": visible,
        "visible_rate": round(visible / total, 6) if total else None,
        "one_digit": _record_summary(
            [item for item in records if len(item["truth"]) == 1], breakdown=False
        )
        if breakdown
        else None,
        "two_digit": _record_summary(
            [item for item in records if len(item["truth"]) == 2], breakdown=False
        )
        if breakdown
        else None,
        "mean_seconds": round(sum(item["seconds"] for item in records) / total, 6) if total else None,
        "review_required": total,
        "auto_accept": 0,
        "wrong_auto_accept": 0,
    }


def evaluate(seed_manifest: Path, heldout_manifest: Path, baseline_report: Path, output: Path) -> dict[str, Any]:
    images, labels, sample_ids = _sequence_seed_samples(seed_manifest)
    model = WholeRoiSequenceModel.fit(images, labels)
    heldout = json.loads(heldout_manifest.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_report.read_text(encoding="utf-8"))
    baseline_by_id = {item["record_id"]: item for item in baseline["records"]}
    records: list[dict[str, Any]] = []
    for record in heldout["records"]:
        corpus = heldout["corpora"][record["corpus_id"]]
        source = Path(corpus["source_root_at_extraction"]) / record["source_path"]
        if sha256_file(source) != record["source_sha256"]:
            raise ValueError(f"source hash mismatch: {source}")
        template = TemplateDefinition.from_dict(corpus["template"])
        data = source.read_bytes()
        image = decode(data)
        crop = number_roi(data, record["registration_matrix"], template_def=template, image=image)
        started = time.perf_counter()
        sequence = model.predict(crop, top_k=5)
        seconds = time.perf_counter() - started
        prior = baseline_by_id[record["record_id"]]
        sequence_candidates = sequence.get("candidates", [])
        sequence_candidate = sequence.get("candidate")
        baseline_candidates = prior.get("candidates", [])
        hybrid_candidate = prior.get("candidate")
        if (
            sequence_candidate
            and len(sequence_candidate) == 2
            and isinstance(hybrid_candidate, str)
            and len(hybrid_candidate) > 2
        ):
            hybrid_candidate = sequence_candidate
        records.append(
            {
                "record_id": record["record_id"],
                "corpus_id": record["corpus_id"],
                "truth": record["label"],
                "baseline_candidate": prior.get("candidate"),
                "baseline_candidates": baseline_candidates,
                "sequence_candidate": sequence_candidate,
                "sequence_candidates": sequence_candidates,
                "hybrid_candidate": hybrid_candidate,
                "baseline_exact": prior.get("candidate") == record["label"],
                "sequence_exact": sequence_candidate == record["label"],
                "hybrid_exact": hybrid_candidate == record["label"],
                "baseline_visible": record["label"] in baseline_candidates,
                "sequence_visible": record["label"] in sequence_candidates,
                "union_visible": record["label"] in set(baseline_candidates) | set(sequence_candidates),
                "seconds": round(seconds, 6),
                "review_required": True,
                "auto_accept": False,
                "wrong_auto_accept": False,
                "failure_attribution": (
                    "sequence_regression"
                    if prior.get("candidate") == record["label"] and sequence_candidate != record["label"]
                    else "sequence_rescue"
                    if prior.get("candidate") != record["label"] and sequence_candidate == record["label"]
                    else "sequence_ranking_or_classifier"
                    if sequence_candidate != record["label"] and record["label"] in sequence_candidates
                    else "sequence_candidate_generation"
                    if sequence_candidate != record["label"]
                    else "none"
                ),
                "sequence": sequence,
            }
        )
    by_corpus = {
        corpus_id: _record_summary([item for item in records if item["corpus_id"] == corpus_id])
        for corpus_id in sorted({item["corpus_id"] for item in records})
    }
    hybrid_summary = _record_summary(
        [
            {
                **item,
                "exact": item["hybrid_exact"],
                "visible": item["union_visible"],
            }
            for item in records
        ]
    )
    report = {
        "schema_version": 1,
        "kind": "student_number_whole_roi_sequence_benchmark",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "seed_support": {
            "manifest": str(seed_manifest.resolve()),
            "manifest_sha256": sha256_file(seed_manifest),
            "sample_count": len(images),
            "unique_sample_ids": len(set(sample_ids)),
            "label_counts": dict(sorted(Counter(labels).items())),
            "writer_identity_known": False,
            "heldout_training_allowed": False,
            "claim": "seed-support training only; no writer-generalization claim",
        },
        "heldout_protocol": {
            "manifest": str(heldout_manifest.resolve()),
            "manifest_sha256": sha256_file(heldout_manifest),
            "records": len(records),
            "corpora": sorted({item["corpus_id"] for item in records}),
            "claim": "sheet/volume-disjoint evaluation; writer generalization unknown",
            "used_for_training_or_tuning": False,
        },
        "model": {
            "kind": "per-output-position centroid over normalized whole-ROI ink canvas",
            "requires_digit_segmentation": False,
            "feature_size": FEATURE_SIZE,
            "position_feature_size": POSITION_FEATURE_SIZE,
            "centroid_count": len(model.centroids),
            "model_size_bytes": model.model_size_bytes,
            "model_size_kib": round(model.model_size_bytes / 1024.0, 2),
        },
        "summary": _record_summary(
            [{"truth": item["truth"], "exact": item["sequence_exact"], "visible": item["sequence_visible"], "seconds": item["seconds"]} for item in records]
        ),
        "by_corpus": by_corpus,
        "hybrid_fixed_rule": "promote the two-digit sequence top-1 only when the frozen baseline emits more than two digits; otherwise retain baseline top-1",
        "hybrid_summary": hybrid_summary,
        "records": records,
        "limitations": [
            "Seed support has one source page/group and unknown writer identity.",
            "Held-out records are evaluation-only and were not used for training, feature selection, or ranking tuning.",
            "Writer-disjoint generalization is unknown.",
            "The sequence confidence is a distance-derived review score, not a probability.",
            "Auto-accept is disabled for both paths.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--heldout-manifest", type=Path, required=True)
    parser.add_argument("--baseline-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.seed_manifest, args.heldout_manifest, args.baseline_report, args.output)
    print(json.dumps({"summary": report["summary"], "hybrid_summary": report["hybrid_summary"], "model": report["model"]}, ensure_ascii=False))
    print(f"report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
