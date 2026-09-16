import json
from pathlib import Path

import cv2
import numpy as np

from tools.benchmark.prepare_digit_annotation import prepare, proposed_digit_boxes


def test_proposed_digit_boxes_cover_sequence_crop_without_overlap():
    boxes = proposed_digit_boxes(70, 65)

    assert boxes == [[0, 0, 35, 65], [35, 0, 70, 65]]
    assert boxes[0][2] == boxes[1][0]


def test_prepare_creates_review_only_worklist(tmp_path: Path):
    seed_root = tmp_path / "seed"
    sample_dir = seed_root / "samples"
    sample_dir.mkdir(parents=True)
    image = np.full((20, 20, 3), 255, dtype=np.uint8)
    cv2.line(image, (4, 4), (15, 15), (0, 0, 0), 2)
    samples = []
    for index in range(100):
        path = sample_dir / f"cell-{index:02d}.png"
        assert cv2.imwrite(str(path), image)
        samples.append(
            {
                "sample_id": f"seed-{index:02d}",
                "source_group": "pdf-page-01",
                "crop_path": str(path.relative_to(seed_root)),
                "label": f"{index:02d}",
            }
        )
    seed_manifest = {
        "kind": "student_number_handwriting_seed_corpus",
        "source_pdf": {"sha256": "pdf-hash"},
        "labeled_samples": samples,
    }
    manifest_path = seed_root / "manifest.json"
    manifest_path.write_text(json.dumps(seed_manifest), encoding="utf-8")

    result = prepare(manifest_path, tmp_path / "annotation")

    assert len(result["records"]) == 200
    assert result["annotation_policy"]["training_ready"] is False
    assert all(record["label_status"] == "needs_review" for record in result["records"])
    assert all(
        record["label_proposed"] is None
        for record in result["records"]
        if record["sequence_label"] in {"06", "07", "08", "09"}
    )
    assert (tmp_path / "annotation" / "sequence-contact-sheet.png").is_file()
