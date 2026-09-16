"""Prepare an auditable visual-QC worklist from sequence-level seed crops.

The PDF seed has trusted sequence labels (00-99), but it does not yet have
trusted digit bounding boxes. This tool creates fixed-midline *proposals* and
quality diagnostics only. Every digit remains ``needs_review`` until a human
annotator records an explicit decision; the output is never training-ready by
construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from tools.benchmark.extract_number_handwriting_dataset import sha256_file

ANNOTATOR_SCHEMA_VERSION = 1
WORKLIST_VERSION = "digit-annotation-worklist-v1"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def proposed_digit_boxes(width: int, height: int) -> list[list[int]]:
    """Return conservative left/right proposals; humans must verify both."""
    midpoint = width // 2
    return [[0, 0, midpoint, height], [midpoint, 0, width, height]]


def _quality_metrics(crop: Any) -> dict[str, float | bool]:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    height, width = ink.shape[:2]
    border = max(1, min(width, height) // 20)
    border_pixels = np.zeros_like(ink)
    border_pixels[:border, :] = ink[:border, :]
    border_pixels[-border:, :] = ink[-border:, :]
    border_pixels[:, :border] = ink[:, :border]
    border_pixels[:, -border:] = ink[:, -border:]
    ink_fraction = float((ink > 0).mean())
    border_fraction = float((border_pixels > 0).mean())
    return {
        "width": width,
        "height": height,
        "ink_fraction": round(ink_fraction, 6),
        "border_ink_fraction": round(border_fraction, 6),
        "looks_nonempty": 0.005 <= ink_fraction <= 0.45,
    }


def _crop(image: Any, box: list[int]) -> Any:
    x1, y1, x2, y2 = box
    result = image[y1:y2, x1:x2]
    if result.size == 0:
        raise ValueError(f"empty digit proposal: {box}")
    return result


def _contact_sheet(items: list[tuple[str, Any]], target: Path) -> None:
    tile_width, tile_height = 160, 150
    columns = 10
    rows = (len(items) + columns - 1) // columns
    sheet = 255 * np.ones((rows * tile_height, columns * tile_width, 3), dtype="uint8")
    for index, (label, image) in enumerate(items):
        resized = cv2.resize(image, (tile_width - 12, tile_height - 34))
        row, column = divmod(index, columns)
        y = row * tile_height + 4
        x = column * tile_width + 6
        sheet[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
        cv2.rectangle(
            sheet,
            (column * tile_width, row * tile_height),
            ((column + 1) * tile_width - 1, (row + 1) * tile_height - 1),
            (190, 190, 190),
            1,
        )
        cv2.putText(
            sheet,
            label,
            (column * tile_width + 8, row * tile_height + tile_height - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    if not cv2.imwrite(str(target), sheet):
        raise OSError(f"could not write contact sheet: {target}")


def prepare(seed_manifest_path: Path, output: Path) -> dict[str, Any]:
    seed_manifest_path = seed_manifest_path.resolve()
    output = output.resolve()
    manifest_path = output / "annotation_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"manifest already exists: {manifest_path}")
    seed_manifest = json.loads(seed_manifest_path.read_text(encoding="utf-8"))
    if seed_manifest.get("kind") != "student_number_handwriting_seed_corpus":
        raise ValueError("unexpected seed manifest kind")
    samples = seed_manifest.get("labeled_samples", [])
    if len(samples) != 100:
        raise ValueError(f"expected 100 seed samples, found {len(samples)}")

    output.mkdir(parents=True, exist_ok=True)
    digit_dir = output / "proposed_digits"
    digit_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    contact_items: list[tuple[str, Any]] = []
    for sample in samples:
        source = seed_manifest_path.parent / sample["crop_path"]
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"cannot decode seed crop: {source}")
        height, width = image.shape[:2]
        sequence = sample["label"]
        boxes = proposed_digit_boxes(width, height)
        contact_items.append((sequence, image))
        for position, box in enumerate(boxes):
            digit = _crop(image, box)
            target = digit_dir / f"{sample['sample_id']}-digit-{position}.png"
            if not cv2.imwrite(str(target), digit):
                raise OSError(f"could not write digit proposal: {target}")
            quality = _quality_metrics(digit)
            reasons = ["fixed_midline_requires_visual_qc"]
            layout_variant = "two_digit_sequence"
            label_proposed: str | None = sequence[position]
            if sequence in {"06", "07", "08", "09"}:
                layout_variant = "single_digit_without_leading_zero"
                label_proposed = None
                reasons.append("leading_zero_not_visible_in_seed_cell")
            if not quality["looks_nonempty"]:
                reasons.append("ink_occupancy_anomaly")
            records.append(
                {
                    "annotation_id": f"{sample['sample_id']}-digit-{position}",
                    "parent_sample_id": sample["sample_id"],
                    "source_page": sample.get("source_page", 1),
                    "source_cell": sample.get(
                        "source_cell", sample["sample_id"].rsplit("-", 1)[-1]
                    ),
                    "source_group": sample["source_group"],
                    "sheet_group": sample["source_group"],
                    "writer_group": "unknown",
                    "split": "seed_only",
                    "digit_position": position,
                    "position_semantics": "spatial_left_or_right_proposal",
                    "sequence_label": sequence,
                    "layout_variant": layout_variant,
                    "label_proposed": label_proposed,
                    "label": None,
                    "label_status": "needs_review",
                    "bbox_proposed_px": box,
                    "bbox_annotated_px": None,
                    "bbox_status": "proposal",
                    "bad_bbox": False,
                    "proposal_method": "fixed_midline_proposal_v1",
                    "source_crop_path": sample["crop_path"],
                    "proposed_digit_path": str(target.relative_to(output)),
                    "source_crop_sha256": _sha256_bytes(source.read_bytes()),
                    "quality": quality,
                    "qc_reasons": reasons,
                    "annotation": {
                        "annotator_id": None,
                        "annotated_at": None,
                        "decision_reason": None,
                        "notes": None,
                    },
                }
            )

    _contact_sheet(contact_items, output / "sequence-contact-sheet.png")
    manifest = {
        "schema_version": ANNOTATOR_SCHEMA_VERSION,
        "kind": "student_number_digit_annotation_worklist",
        "worklist_version": WORKLIST_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": {
            "path": str(seed_manifest_path),
            "sha256": sha256_file(seed_manifest_path),
            "source_pdf_sha256": seed_manifest["source_pdf"]["sha256"],
        },
        "annotation_policy": {
            "state_values": ["needs_review", "accepted", "rejected"],
            "accepted_requires": [
                "annotator_id",
                "annotated_at",
                "label",
                "bbox_annotated_px",
                "decision_reason",
            ],
            "training_ready": False,
            "reason": "fixed-midline proposals require human visual QC and annotation",
        },
        "split_policy": {
            "group_unit": "writer and source sheet",
            "seed_split": "seed_only",
            "writer_identity_known": False,
            "training_allowed": False,
        },
        "quality_screen": {
            "missingness": {
                "label": 200,
                "bbox_annotated_px": 200,
                "annotator_id": 200,
            },
            "anomaly_policy": "retain anomalies for review; never silently drop samples",
        },
        "contact_sheet": "sequence-contact-sheet.png",
        "records": records,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare(args.seed_manifest, args.output)
    print(
        json.dumps(
            {
                "manifest": str(args.output.resolve() / "annotation_manifest.json"),
                "records": len(manifest["records"]),
                "needs_review": sum(
                    record["label_status"] == "needs_review" for record in manifest["records"]
                ),
                "training_ready": manifest["annotation_policy"]["training_ready"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
