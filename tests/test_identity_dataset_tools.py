from pathlib import Path

import pytest

from tools.benchmark.extract_number_handwriting_dataset import grid_cell_boxes
from tools.benchmark.identity_labeled_benchmark import _bootstrap_ci, _validate_manifest


def test_pdf_seed_grid_has_one_sequence_sample_per_known_label():
    boxes = grid_cell_boxes(992, 1403)

    assert len(boxes) == 100
    assert [box["label"] for box in boxes[:3]] == ["00", "01", "02"]
    assert boxes[-1]["label"] == "99"
    assert all(box["bbox_ink_px"][0] > box["bbox_page_px"][0] for box in boxes)
    assert all(box["bbox_ink_px"][2] < box["bbox_page_px"][2] for box in boxes)


def test_bootstrap_ci_is_deterministic_and_bounded():
    values = [True, True, False, False]

    first = _bootstrap_ci(values, iterations=300)
    second = _bootstrap_ci(values, iterations=300)

    assert first == second
    assert first is not None
    assert 0.0 <= first[0] <= first[1] <= 1.0


def test_labeled_benchmark_rejects_non_held_out_or_duplicate_hashes():
    manifest = {
        "kind": "student_number_teacher_confirmed_benchmark_corpus",
        "corpora": {"vol8": {}},
        "records": [
            {
                "record_id": "vol8/a.jpg",
                "corpus_id": "vol8",
                "source_sha256": "same",
                "split": "train",
                "label": "1",
            },
            {
                "record_id": "vol8/b.jpg",
                "corpus_id": "vol8",
                "source_sha256": "same",
                "split": "held_out",
                "label": "2",
            },
        ],
    }

    with pytest.raises(ValueError, match="held_out"):
        _validate_manifest(manifest)


def test_labeled_benchmark_manifest_is_json_serializable(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text('{"kind": "example"}', encoding="utf-8")
    assert path.read_text(encoding="utf-8") == '{"kind": "example"}'
