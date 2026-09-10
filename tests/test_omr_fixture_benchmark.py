import json
from pathlib import Path

from tools.benchmark.omr_fixture_benchmark import evaluate


def test_fixture_benchmark_is_complete_and_fail_closed():
    report = evaluate(Path("tests/fixtures/synthetic"))
    assert report["manifest_total"] == 58
    assert report["evaluated"] == 58
    assert sum(report["status_counts"].values()) == 58
    assert report["auto_accept_count"] == 0
    assert report["registration_accepted"] + report["registration_rejected"] == 58
    assert "stage_timings" in report
    assert 0.0 <= report["review_rate"] <= 1.0
    assert report["warning"].startswith("Synthetic/provisional")
    assert report["status_counts"].get("registration_or_decode_rejected", 0) > 0


def test_manifest_hashes_are_stable_for_benchmark_inputs():
    manifest = json.loads(Path("tests/fixtures/synthetic/manifest.json").read_text())
    report = evaluate(Path("tests/fixtures/synthetic"))
    by_name = {record["filename"]: record for record in report["records"]}
    assert set(by_name) == {entry["filename"] for entry in manifest["fixtures"]}
    for record in report["records"]:
        assert len(record["sha256"]) == 64
