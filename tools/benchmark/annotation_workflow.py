"""Small, explicit state machine shared by the offline annotation tools."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_STATES = {"needs_review", "accepted", "excluded"}


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_annotation_manifest(manifest, path.parent, check_training_ready=False)
    manifest.setdefault("audit_log", [])
    return manifest


def atomic_save(path: Path, manifest: dict[str, Any]) -> None:
    """Write a manifest durably, then replace the old file in one rename."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def counts(manifest: dict[str, Any]) -> dict[str, int]:
    records = manifest.get("records", [])
    labeled = sum(record.get("label_status") == "accepted" for record in records)
    excluded = sum(record.get("label_status") == "excluded" for record in records)
    remaining = sum(record.get("label_status") == "needs_review" for record in records)
    bad_bbox = sum(bool(record.get("bad_bbox")) for record in records)
    return {
        "total": len(records),
        "labeled": labeled,
        "excluded": excluded,
        "remaining": remaining,
        "bad_bbox": bad_bbox,
    }


def next_review_index(manifest: dict[str, Any], start: int = 0) -> int | None:
    records = manifest.get("records", [])
    if not records:
        return None
    for offset in range(len(records)):
        index = (start + offset) % len(records)
        if records[index].get("label_status") == "needs_review":
            return index
    return None


def _record(manifest: dict[str, Any], annotation_id: str) -> dict[str, Any]:
    for record in manifest["records"]:
        if record.get("annotation_id") == annotation_id:
            return record
    raise KeyError(f"unknown annotation id: {annotation_id}")


def _event(
    manifest: dict[str, Any],
    record: dict[str, Any],
    annotator_id: str,
    action: str,
    **details: Any,
) -> None:
    manifest.setdefault("audit_log", []).append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "annotator_id": annotator_id,
            "annotation_id": record["annotation_id"],
            "action": action,
            "details": details,
        }
    )


def _annotation_fields(record: dict[str, Any]) -> dict[str, Any]:
    return record.setdefault(
        "annotation",
        {
            "annotator_id": None,
            "annotated_at": None,
            "decision_reason": None,
            "notes": None,
        },
    )


def accept_label(manifest: dict[str, Any], annotation_id: str, digit: int, annotator_id: str) -> None:
    if digit not in range(10):
        raise ValueError("label must be a digit from 0 to 9")
    record = _record(manifest, annotation_id)
    if record.get("bad_bbox") or record.get("bbox_status") == "bad_bbox":
        raise ValueError("correct the bad bbox before accepting a label")
    bbox = record.get("bbox_annotated_px") or record.get("bbox_proposed_px")
    if not _valid_bbox(bbox):
        raise ValueError("a valid bbox is required before accepting a label")
    previous = record.get("label_status")
    record["label"] = str(digit)
    record["label_status"] = "accepted"
    annotation = _annotation_fields(record)
    annotation.update(
        {
            "annotator_id": annotator_id,
            "annotated_at": datetime.now(timezone.utc).isoformat(),
            "decision_reason": "explicit_digit_key",
        }
    )
    _event(manifest, record, annotator_id, "accept_label", digit=digit, previous=previous)


def exclude_record(manifest: dict[str, Any], annotation_id: str, annotator_id: str) -> None:
    record = _record(manifest, annotation_id)
    previous = record.get("label_status")
    record["label"] = None
    record["label_status"] = "excluded"
    annotation = _annotation_fields(record)
    annotation.update(
        {
            "annotator_id": annotator_id,
            "annotated_at": datetime.now(timezone.utc).isoformat(),
            "decision_reason": "excluded_or_ambiguous",
        }
    )
    _event(manifest, record, annotator_id, "exclude", previous=previous)


def mark_bad_bbox(manifest: dict[str, Any], annotation_id: str, annotator_id: str) -> None:
    record = _record(manifest, annotation_id)
    record["label"] = None
    record["label_status"] = "needs_review"
    record["bad_bbox"] = True
    record["bbox_status"] = "bad_bbox"
    _event(manifest, record, annotator_id, "mark_bad_bbox")


def set_bbox(
    manifest: dict[str, Any], annotation_id: str, bbox: list[int], annotator_id: str
) -> None:
    if not _valid_bbox(bbox):
        raise ValueError("bbox must be [x1, y1, x2, y2] with positive area")
    record = _record(manifest, annotation_id)
    record["label"] = None
    record["label_status"] = "needs_review"
    record["bbox_annotated_px"] = [int(value) for value in bbox]
    record["bbox_status"] = "corrected"
    record["bad_bbox"] = False
    _event(manifest, record, annotator_id, "correct_bbox", bbox=record["bbox_annotated_px"])


def reset_record(manifest: dict[str, Any], annotation_id: str, annotator_id: str) -> None:
    record = _record(manifest, annotation_id)
    record["label"] = None
    record["label_status"] = "needs_review"
    record["bad_bbox"] = False
    if record.get("bbox_annotated_px"):
        record["bbox_status"] = "corrected"
    else:
        record["bbox_status"] = "proposal"
    annotation = _annotation_fields(record)
    annotation.update({"annotator_id": None, "annotated_at": None, "decision_reason": None})
    _event(manifest, record, annotator_id, "reset_to_needs_review")


def _valid_bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
        and value[0] >= 0
        and value[1] >= 0
        and value[2] > value[0]
        and value[3] > value[1]
    )


def validate_annotation_manifest(
    manifest: dict[str, Any], root: Path, *, check_training_ready: bool = True
) -> None:
    if manifest.get("kind") not in {
        "student_number_digit_annotation_worklist",
        "student_number_digit_training_ready_manifest",
    }:
        raise ValueError("unexpected annotation manifest kind")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    identifiers: set[str] = set()
    for record in records:
        annotation_id = record.get("annotation_id")
        if not annotation_id or annotation_id in identifiers:
            raise ValueError(f"duplicate sample id: {annotation_id}")
        identifiers.add(annotation_id)
        source_path = root / record.get("source_crop_path", "")
        proposed_path = root / record.get("proposed_digit_path", "")
        if not source_path.is_file() or not proposed_path.is_file():
            raise ValueError(f"missing crop for sample: {annotation_id}")
        status = record.get("label_status")
        if status not in REVIEW_STATES:
            raise ValueError(f"invalid label status for {annotation_id}: {status}")
        label = record.get("label")
        if status == "accepted":
            if label not in {str(digit) for digit in range(10)}:
                raise ValueError(f"label outside 0-9: {annotation_id}")
            if record.get("bad_bbox") or record.get("bbox_status") == "bad_bbox":
                raise ValueError(f"bad bbox is unresolved: {annotation_id}")
            bbox = record.get("bbox_annotated_px") or record.get("bbox_proposed_px")
            if not _valid_bbox(bbox):
                raise ValueError(f"invalid bbox: {annotation_id}")
            annotation = record.get("annotation", {})
            for field in ("annotator_id", "annotated_at", "decision_reason"):
                if not annotation.get(field):
                    raise ValueError(f"missing annotation field {field}: {annotation_id}")
        elif label is not None:
            raise ValueError(f"non-accepted sample has a label: {annotation_id}")
        if status == "needs_review" and record.get("bad_bbox") and check_training_ready:
            raise ValueError(f"bad bbox is unresolved: {annotation_id}")
    if check_training_ready and manifest.get("training_ready"):
        if any(record.get("label_status") != "accepted" for record in records):
            raise ValueError("training-ready manifest contains non-accepted samples")
