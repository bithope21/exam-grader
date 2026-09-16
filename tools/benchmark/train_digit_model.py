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


def train(manifest_path: Path, output_dir: Path) -> dict[str, Any]:
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
    label_array = np.asarray(labels, dtype=np.int64)
    features = feature_matrix(images)
    train_indices, validation_indices = stratified_split(labels)
    if not train_indices or not validation_indices:
        raise ValueError("internal split produced an empty partition")

    candidates: dict[str, dict[str, Any]] = {}
    for kind in ("knn", "centroid"):
        model = DigitModel.from_training(kind, features[train_indices], label_array[train_indices])
        candidates[kind] = _evaluate(model, features, label_array, validation_indices)
    majority_label = Counter(label_array[train_indices].tolist()).most_common(1)[0][0]
    naive = [int(label_array[index]) == majority_label for index in validation_indices]
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
        "status": "calibrated_for_review_only",
        "method": "internal_seed_validation_conservative_cap",
        "max_confidence": 95.0,
        "validation_records": len(validation_indices),
        "generalization_claim_allowed": False,
        "auto_accept_enabled": False,
    }
    final_model = DigitModel.from_training(
        selected_kind, features, label_array, calibration=calibration
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
    args = parser.parse_args()
    report = train(args.manifest, args.output_dir)
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
