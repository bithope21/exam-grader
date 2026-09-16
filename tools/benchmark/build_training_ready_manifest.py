"""Validate annotations and export only explicit, QC-passed digit samples."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from tools.benchmark.annotation_workflow import atomic_save, validate_annotation_manifest
from tools.benchmark.extract_number_handwriting_dataset import sha256_file


def _inside_bbox(bbox: list[int], width: int, height: int) -> bool:
    return bbox[2] <= width and bbox[3] <= height


def build(annotation_path: Path, output_path: Path) -> dict[str, Any]:
    annotation_path = annotation_path.resolve()
    output_path = output_path.resolve()
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    manifest = json.loads(annotation_path.read_text(encoding="utf-8"))
    validate_annotation_manifest(manifest, annotation_path.parent)
    accepted = [record for record in manifest["records"] if record["label_status"] == "accepted"]
    if not accepted:
        raise ValueError("no accepted annotations; training-ready manifest was not created")

    crop_dir = output_path.parent / f"{output_path.stem}-crops"
    crop_dir.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    for record in accepted:
        source_path = annotation_path.parent / record["source_crop_path"]
        image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"missing crop: {record['annotation_id']}")
        if sha256_file(source_path) != record.get("source_crop_sha256"):
            raise ValueError(f"source crop hash changed: {record['annotation_id']}")
        bbox = record.get("bbox_annotated_px") or record.get("bbox_proposed_px")
        if not _inside_bbox(bbox, image.shape[1], image.shape[0]):
            raise ValueError(f"bbox exceeds source crop: {record['annotation_id']}")
        x1, y1, x2, y2 = bbox
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            raise ValueError(f"empty bbox crop: {record['annotation_id']}")
        target = crop_dir / f"{record['annotation_id']}.png"
        if not cv2.imwrite(str(target), crop):
            raise OSError(f"could not write training crop: {target}")
        records.append(
            {
                "annotation_id": record["annotation_id"],
                "label": record["label"],
                "source_group": record["source_group"],
                "sheet_group": record["sheet_group"],
                "writer_group": record["writer_group"],
                "split": "seed_only",
                "source_page": record["source_page"],
                "source_cell": record["source_cell"],
                "parent_sample_id": record["parent_sample_id"],
                "source_crop_path": record["source_crop_path"],
                "source_crop_sha256": record["source_crop_sha256"],
                "bbox_annotated_px": bbox,
                "training_crop_path": str(target.relative_to(output_path.parent)),
                "annotation": record["annotation"],
            }
        )

    result = {
        "schema_version": 1,
        "kind": "student_number_digit_training_ready_manifest",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_ready": True,
        "label_ready": True,
        "source_annotation_manifest": {
            "path": str(annotation_path),
            "sha256": sha256_file(annotation_path),
        },
        "split_policy": {
            "group_unit": "writer and source sheet",
            "split": "seed_only",
            "writer_identity_known": False,
            "training_allowed": False,
            "requires_group_split_before_training": True,
        },
        "selection_policy": "accepted annotations only; excluded and needs_review omitted",
        "records": records,
    }
    atomic_save(output_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.annotation_manifest, args.output)
    print(
        json.dumps(
            {
                "manifest": str(args.output.resolve()),
                "records": len(result["records"]),
                "training_ready": result["training_ready"],
                "training_allowed": result["split_policy"]["training_allowed"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
