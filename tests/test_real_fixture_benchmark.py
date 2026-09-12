from pathlib import Path

from exam_grader.imaging import analyze
from tools.benchmark.real_fixture_benchmark import evaluate


def test_real_fixture_benchmark_is_engineering_only_and_not_all_choices():
    report = evaluate(Path("tests/fixtures/real/vol.1"))
    assert report["evaluated"] == 6
    assert report["registration_accepted"] == 6
    assert report["registration_rejected"] == 0
    assert report["selected_all_choices_total"] == 0
    assert report["auto_accept_count"] == 0
    assert "accuracy" not in report


def test_vol3_blank_heavy_sheets_remain_reviewable_and_do_not_invent_all_choices():
    """The supplied sparse/blank-heavy photos are an engineering probe only."""
    root = Path("tests/fixtures/real/vol.3")
    blank_counts = []
    for path in sorted(root.glob("IMG*")):
        result = analyze(path.read_bytes())
        classifications = [item["classification"] for item in result["answers"]]
        blank_counts.append(classifications.count("blank"))
        assert result["requires_review"] is True
        assert any(item in {"blank", "uncertain"} for item in classifications)
        assert all(item["selected"] != list("ABCDE") for item in result["answers"])
    assert max(blank_counts) >= 19


def test_vol3_benchmark_counts_the_declared_40_active_questions():
    report = evaluate(Path("tests/fixtures/real/vol.3"), question_count=40)
    assert report["evaluated"] == 9
    assert report["registration_rejected"] == 0
    assert report["selected_all_choices_total"] == 0
    assert (
        sum(
            record["uncertain_questions"]
            for record in report["records"]
            if record["filename"].startswith("IMG")
        )
        == 7
    )
