import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools.benchmark.annotation_workflow import (
    accept_label,
    atomic_save,
    counts,
    load_manifest,
    mark_bad_bbox,
    next_review_index,
    set_bbox,
    validate_annotation_manifest,
)
from tools.benchmark.build_training_ready_manifest import build
from tools.benchmark.extract_number_handwriting_dataset import sha256_file


def _manifest(tmp_path: Path) -> tuple[Path, dict]:
    source = tmp_path / "source.png"
    proposed = tmp_path / "proposed.png"
    image = np.full((20, 20, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (4, 4), (14, 14), (0, 0, 0), 2)
    assert cv2.imwrite(str(source), image)
    assert cv2.imwrite(str(proposed), image[0:16, 0:10])
    record = {
        "annotation_id": "sample-1",
        "parent_sample_id": "parent-1",
        "source_page": 1,
        "source_cell": "01",
        "source_group": "sheet-1",
        "sheet_group": "sheet-1",
        "writer_group": "writer-1",
        "split": "seed_only",
        "sequence_label": "01",
        "layout_variant": "two_digit_sequence",
        "label_proposed": "0",
        "label": None,
        "label_status": "needs_review",
        "bbox_proposed_px": [0, 0, 10, 16],
        "bbox_annotated_px": None,
        "bbox_accepted_px": None,
        "bbox_status": "proposal",
        "bad_bbox": False,
        "source_crop_path": source.name,
        "proposed_digit_path": proposed.name,
        "source_crop_sha256": sha256_file(source),
        "annotation": {
            "annotator_id": None,
            "annotated_at": None,
            "decision_reason": None,
        },
    }
    manifest = {
        "kind": "student_number_digit_annotation_worklist",
        "training_ready": False,
        "source_manifest": {"path": str(tmp_path / "seed-manifest.json")},
        "records": [record],
    }
    path = tmp_path / "annotation_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, manifest


def test_explicit_actions_save_resume_and_audit(tmp_path: Path):
    path, _ = _manifest(tmp_path)
    manifest = load_manifest(path)

    assert counts(manifest)["remaining"] == 1
    assert next_review_index(manifest) == 0
    accept_label(manifest, "sample-1", 7, "po")
    atomic_save(path, manifest)
    resumed = load_manifest(path)

    assert counts(resumed) == {
        "total": 1,
        "labeled": 1,
        "excluded": 0,
        "remaining": 0,
        "bad_bbox": 0,
    }
    assert len(resumed["audit_log"]) == 1
    assert resumed["records"][0]["label"] == "7"
    assert resumed["records"][0]["bbox_accepted_px"] == [0, 0, 10, 16]


def test_bbox_correction_required_before_label(tmp_path: Path):
    path, _ = _manifest(tmp_path)
    manifest = load_manifest(path)
    mark_bad_bbox(manifest, "sample-1", "po")

    with pytest.raises(ValueError, match="bad bbox"):
        accept_label(manifest, "sample-1", 7, "po")

    set_bbox(manifest, "sample-1", [1, 1, 10, 15], "po")
    accept_label(manifest, "sample-1", 7, "po")
    assert manifest["records"][0]["bbox_status"] == "corrected"
    assert manifest["records"][0]["bbox_accepted_px"] == [1, 1, 10, 15]


def test_validation_blocks_unresolved_bad_bbox_and_nonaccepted_ready_state(tmp_path: Path):
    path, manifest = _manifest(tmp_path)
    mark_bad_bbox(manifest, "sample-1", "po")
    with pytest.raises(ValueError, match="bad bbox"):
        validate_annotation_manifest(manifest, path.parent)

    manifest["records"][0]["bad_bbox"] = False
    manifest["records"][0]["bbox_status"] = "proposal"
    manifest["training_ready"] = True
    with pytest.raises(ValueError, match="non-accepted"):
        validate_annotation_manifest(manifest, path.parent)


def test_validation_rejects_duplicate_id_missing_crop_and_bad_label(tmp_path: Path):
    path, manifest = _manifest(tmp_path)
    first = manifest["records"][0]
    duplicate = dict(first)
    manifest["records"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate sample id"):
        validate_annotation_manifest(manifest, path.parent, check_training_ready=False)

    manifest["records"] = [first]
    first["label_status"] = "accepted"
    first["label"] = "10"
    first["annotation"] = {
        "annotator_id": "po",
        "annotated_at": "now",
        "decision_reason": "test",
    }
    with pytest.raises(ValueError, match="outside 0-9"):
        validate_annotation_manifest(manifest, path.parent, check_training_ready=False)

    first["label"] = "1"
    first["source_crop_path"] = "missing.png"
    with pytest.raises(ValueError, match="missing crop"):
        validate_annotation_manifest(manifest, path.parent, check_training_ready=False)


def test_training_ready_export_contains_only_accepted_records(tmp_path: Path):
    path, manifest = _manifest(tmp_path)
    manifest["records"][0]["label"] = "3"
    manifest["records"][0]["label_status"] = "accepted"
    manifest["records"][0]["bbox_accepted_px"] = [0, 0, 10, 16]
    manifest["records"][0]["annotation"] = {
        "annotator_id": "po",
        "annotated_at": "now",
        "decision_reason": "explicit_digit_key",
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "training_ready.json"

    result = build(path, output)

    assert result["training_ready"] is True
    assert result["split_policy"]["training_allowed"] is False
    assert len(result["records"]) == 1
    assert result["records"][0]["label"] == "3"
    assert (tmp_path / "training_ready-crops" / "sample-1.png").is_file()
