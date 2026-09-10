import json
from pathlib import Path

import pytest

from tools.benchmark.golden_labels import build_manifest

RUN = Path("/Users/zubinpijit/Desktop/exam-grader1/1ddd200c-43eb-47c4-bebd-e61bb435d255/run-8ce2f112-9395-4584-ad5f-955eadd097c1")


@pytest.mark.skipif(not RUN.is_dir(), reason="confirmed external run is not mounted")
def test_golden_manifest_separates_visual_and_scoring_truth():
    manifest = build_manifest(RUN, Path("tests/fixtures/real/vol.1"), disputed={("key.JPG", 6)})
    assert manifest["schema_version"] == 1
    assert len(manifest["records"]) == 5
    assert manifest["excluded_for_recognition"] == [{
        "filename": "key.JPG",
        "question": 6,
        "reason": "conflicting visual/scoring evidence",
    }]
    record = next(item for item in manifest["records"] if item["filename"] == "IMG_0791.JPG")
    assert record["source_sha256"] == record["fixture_sha256"]
    question = record["questions"][0]
    assert "machine" in question and "teacher_scoring_decision" in question
    assert question["visual_label"] is None


@pytest.mark.skipif(not RUN.is_dir(), reason="confirmed external run is not mounted")
def test_manifest_is_json_serializable():
    manifest = build_manifest(RUN, Path("tests/fixtures/real/vol.1"))
    json.dumps(manifest, ensure_ascii=False)
