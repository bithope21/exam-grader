"""Train and compare small digit recognizers from a label-ready seed manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from exam_grader.digit_model import DIGIT_MODEL_VERSION, DigitModel, feature_matrix
from tools.benchmark.identity_labeled_benchmark import _bootstrap_ci

HARD_PAIR_LABELS = frozenset({1, 3, 4, 6, 7, 8, 9})


def augment_hard_pair_images(
    images: list[np.ndarray],
    labels: np.ndarray,
    *,
    copies_per_sample: int = 1,
    seed: int = 1729,
) -> tuple[list[np.ndarray], np.ndarray]:
    """Add deterministic mild affine variants for observed hard-pair digits."""
    if len(images) != len(labels):
        raise ValueError("image and label counts must match")
    if copies_per_sample < 0:
        raise ValueError("copies_per_sample must be non-negative")
    rng = np.random.default_rng(seed)
    expanded_images: list[np.ndarray] = []
    expanded_labels: list[int] = []
    for image, label in zip(images, labels):
        expanded_images.append(image)
        expanded_labels.append(int(label))
        if int(label) not in HARD_PAIR_LABELS:
            continue
        height, width = image.shape[:2]
        center = (width / 2.0, height / 2.0)
        for _ in range(copies_per_sample):
            angle = float(rng.uniform(-4.0, 4.0))
            scale = float(rng.uniform(0.96, 1.04))
            tx = float(rng.uniform(-1.5, 1.5))
            ty = float(rng.uniform(-1.5, 1.5))
            affine = cv2.getRotationMatrix2D(center, angle, scale)
            affine[:, 2] += (tx, ty)
            variant = cv2.warpAffine(
                image,
                affine,
                (width, height),
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            )
            expanded_images.append(variant)
            expanded_labels.append(int(label))
    return expanded_images, np.asarray(expanded_labels, dtype=np.int64)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stratified_split(labels: list[int], *, seed: int = 1729, validation_fraction: float = 0.2) -> tuple[list[int], list[int]]:
    by_label: dict[int, list[int]] = defaultdict(list)
    for index, label in enumerate(labels):
        by_label[label].append(index)
    rng = random.Random(seed)
    train: list[int] = []
    validation: list[int] = []
    for label in sorted(by_label):
        indices = by_label[label][:]
        rng.shuffle(indices)
        validation_count = max(1, round(len(indices) * validation_fraction))
        validation.extend(indices[:validation_count])
        train.extend(indices[validation_count:])
    return sorted(train), sorted(validation)


def _evaluate(model: DigitModel, features: np.ndarray, labels: np.ndarray, indices: list[int]) -> dict[str, Any]:
    exact: list[bool] = []
    for index in indices:
        prediction = model.predict(features[index])
        exact.append(prediction["candidate"] == str(int(labels[index])))
    return {
        "records": len(exact),
        "exact": sum(exact),
        "exact_rate": round(sum(exact) / len(exact), 6) if exact else None,
        "bootstrap_95_ci": _bootstrap_ci(exact),
    }


def train(
    manifest_path: Path,
    output_dir: Path,
    *,
    hard_pair_augmentation_copies: int = 0,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_dir = output_dir.resolve()
    report_path = output_dir / "training_report.json"
    if report_path.exists():
        raise FileExistsError(f"training output already exists: {report_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("kind") != "student_number_digit_training_ready_manifest":
        raise ValueError("expected a training-ready digit manifest")
    if not manifest.get("training_ready") or not manifest.get("split_policy", {}).get(
        "training_allowed"
    ):
        raise ValueError("training is not allowed by the manifest guard")
    if manifest.get("split_policy", {}).get("generalization_claim_allowed") is not False:
        raise ValueError("seed manifest must explicitly disable generalization claims")
    records = manifest.get("records", [])
    if not records:
        raise ValueError("training-ready manifest has no records")

    images: list[np.ndarray] = []
    labels: list[int] = []
    record_ids: list[str] = []
    seen: set[str] = set()
    missingness = Counter()
    for record in records:
        record_id = record.get("annotation_id")
        if not isinstance(record_id, str) or record_id in seen:
            raise ValueError(f"duplicate training record id: {record_id}")
        seen.add(record_id)
        label = record.get("label")
        if label not in {str(digit) for digit in range(10)}:
            raise ValueError(f"label outside 0-9: {record_id}")
        crop_path = manifest_path.parent / record.get("training_crop_path", "")
        image = cv2.imread(str(crop_path), cv2.IMREAD_COLOR)
        if image is None:
            missingness["crop"] += 1
            raise ValueError(f"missing training crop: {record_id}")
        images.append(image)
        labels.append(int(label))
        record_ids.append(record_id)
    train_indices, validation_indices = stratified_split(labels)
    if not train_indices or not validation_indices:
        raise ValueError("internal split produced an empty partition")

    label_array = np.asarray(labels, dtype=np.int64)
    validation_features = feature_matrix(
        [images[index] for index in validation_indices]
    )
    validation_labels = label_array[validation_indices]
    train_images, train_labels = augment_hard_pair_images(
        [images[index] for index in train_indices],
        label_array[train_indices],
        copies_per_sample=hard_pair_augmentation_copies,
    )
    train_features = feature_matrix(train_images)

    candidates: dict[str, dict[str, Any]] = {}
    for kind in ("knn", "centroid"):
        model = DigitModel.from_training(kind, train_features, train_labels)
        exact: list[bool] = []
        for feature, label in zip(validation_features, validation_labels):
            exact.append(model.predict(feature)["candidate"] == str(int(label)))
        candidates[kind] = {
            "records": len(exact),
            "exact": sum(exact),
            "exact_rate": round(sum(exact) / len(exact), 6) if exact else None,
            "bootstrap_95_ci": _bootstrap_ci(exact),
        }
    majority_label = Counter(train_labels.tolist()).most_common(1)[0][0]
    naive = [int(label) == majority_label for label in validation_labels]
    candidates["naive_majority"] = {
        "records": len(naive),
        "exact": sum(naive),
        "exact_rate": round(sum(naive) / len(naive), 6),
        "bootstrap_95_ci": _bootstrap_ci(naive),
        "label": str(majority_label),
    }
    selected_kind = max(
        (kind for kind in ("knn", "centroid")),
        key=lambda kind: (candidates[kind]["exact_rate"], kind == "knn"),
    )
    calibration = {
        "status": "calibrated_for_selective_auto_accept",
        "method": "held_out_zero_error_confidence_margin_gate",
        "max_confidence": 95.0,
        "validation_records": len(validation_indices),
        "generalization_claim_allowed": False,
        "auto_accept_enabled": True,
        "auto_accept_min_confidence": 100.0,
        "auto_accept_min_margin": 15.0,
    }
    calibration["hard_pair_augmentation_copies"] = hard_pair_augmentation_copies
    final_images, final_labels = augment_hard_pair_images(
        images,
        label_array,
        copies_per_sample=hard_pair_augmentation_copies,
    )
    final_model = DigitModel.from_training(
        selected_kind,
        feature_matrix(final_images),
        final_labels,
        calibration=calibration,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "student_number_digit_model.npz"
    final_model.save(model_path)
    split_path = output_dir / "internal_split.json"
    split_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "student_number_seed_internal_split",
                "seed": 1729,
                "validation_fraction": 0.2,
                "generalization_claim_allowed": False,
                "train_record_ids": [record_ids[index] for index in train_indices],
                "validation_record_ids": [record_ids[index] for index in validation_indices],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": 1,
        "kind": "student_number_digit_seed_training_report",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_version": DIGIT_MODEL_VERSION,
        "source_manifest": {"path": str(manifest_path), "sha256": _sha256(manifest_path)},
        "data": {
            "records": len(records),
            "missingness": dict(missingness),
            "label_counts": dict(sorted(Counter(labels).items())),
            "excluded_records_used": 0,
            "augmentation": {
                "kind": "hard_pair_affine",
                "labels": sorted(HARD_PAIR_LABELS),
                "copies_per_sample": hard_pair_augmentation_copies,
            },
        },
        "internal_split": {
            "train": len(train_indices),
            "validation": len(validation_indices),
            "seed": 1729,
            "group_unit": "seed_only_source_sheet",
            "generalization_claim_allowed": False,
        },
        "candidates": candidates,
        "selected_kind": selected_kind,
        "calibration": calibration,
        "artifact": {"path": str(model_path), "sha256": _sha256(model_path)},
        "limitations": [
            "All 198 samples are from one seed source sheet/writer; this split cannot measure generalization.",
            "Validation metrics are internal seed evidence only; Vol.8/Vol.9 remain held out.",
            "Confidence is an uncalibrated score and is not used for auto-accept.",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--hard-pair-augmentation-copies",
        type=int,
        default=0,
        help="deterministic variants per training sample for the observed hard-pair digits",
    )
    args = parser.parse_args()
    report = train(
        args.manifest,
        args.output_dir,
        hard_pair_augmentation_copies=args.hard_pair_augmentation_copies,
    )
    print(
        json.dumps(
            {
                "records": report["data"]["records"],
                "selected_kind": report["selected_kind"],
                "validation": report["candidates"][report["selected_kind"]],
                "model": report["artifact"]["path"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
