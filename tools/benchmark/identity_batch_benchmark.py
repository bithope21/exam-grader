"""Measure room-scoped student-number batch assistance on saved observations."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from PySide6.QtGui import QImage

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.workflow import Workflow


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError("diagnostic report has no records")
    return rows


def _truth(row: dict[str, Any]) -> str:
    value = row.get("truth", row.get("label"))
    if not isinstance(value, str) or not value.isascii() or not value.isdigit() or int(value) < 1:
        raise ValueError(f"invalid truth label: {value!r}")
    return str(int(value))


def _visible(observation: dict[str, Any], truth: str) -> bool:
    if truth in observation.get("candidates", []):
        return True
    return any(
        isinstance(item, dict) and item.get("candidate") == truth
        for item in observation.get("review_suggestions", [])
    )


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def rate(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
        exact = sum(item["effective_candidate"] == item["truth"] for item in items)
        visible = sum(item["effective_visible"] for item in items)
        return {
            "records": len(items),
            "exact": exact,
            "exact_rate": round(exact / len(items), 6) if items else None,
            "visible": visible,
            "visible_rate": round(visible / len(items), 6) if items else None,
            "prefill_review_required": len(items),
            "wrong_auto_accept": 0,
            "digit_length": key,
        }

    one = [item for item in rows if len(item["truth"]) == 1]
    two = [item for item in rows if len(item["truth"]) == 2]
    return {
        "all": rate(rows, "all"),
        "one_digit": rate(one, "1"),
        "two_digit": rate(two, "2"),
        "changed_prefill": sum(
            item["effective_candidate"] != item["raw_candidate"] for item in rows
        ),
        "assisted_rows": sum(item["batch_assistance"] is not None for item in rows),
    }


def evaluate(rows: list[dict[str, Any]], anchor_count: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="exam-grader-batch-") as directory:
        root = Path(directory)
        application = initialize(root / "data")
        maximum = max(int(_truth(row)) for row in rows)
        exam = application.exams.create(
            ExamDetails("batch benchmark", "2026", "test", "room", "identity", 1, maximum)
        )
        importer = ImportService(application.exams.path)
        flow = Workflow(application.exams.path)
        sources: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            image_path = root / f"source-{index:03d}.png"
            image = QImage(80, 80, QImage.Format.Format_RGB32)
            shade = 255 - (index % 24)
            image.fill((0xFF << 24) | (shade << 16) | (shade << 8) | shade)
            image.save(str(image_path))
            source = importer.import_file(exam.id, image_path, "student")
            flow.save_detection(
                source["id"],
                {
                    "student_number_observation": row["observation"],
                    "answers": [],
                    "registration": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
                },
            )
            sources.append(source)

        service = ReviewService(application.exams.path)
        for source, row in zip(sources[:anchor_count], rows[:anchor_count], strict=True):
            service.set_number(
                source,
                _truth(row),
                expected_detection=service.state(source)["detection_id"],
            )
        anchor_ids = {source["id"] for source in sources[:anchor_count]}

        started = time.perf_counter()
        effective = service.effective_identity_observations(exam.id)
        if len(effective) != len(sources):
            raise ValueError(f"batch source/effective mismatch: {len(sources)} != {len(effective)}")
        elapsed = time.perf_counter() - started
        measured: list[dict[str, Any]] = []
        for source, row in zip(sources, rows, strict=True):
            observation = effective[source["id"]]
            measured.append(
                {
                    "record_id": row.get("record_id", row.get("source_path", source["id"])),
                    "truth": _truth(row),
                    "raw_candidate": row["observation"].get("candidate"),
                    "effective_candidate": observation.get("candidate"),
                    "effective_visible": _visible(observation, _truth(row)),
                    "batch_assistance": observation.get("batch_assistance"),
                    "teacher_anchor": source["id"] in anchor_ids,
                }
            )
        non_anchor = [item for item in measured if not item["teacher_anchor"]]
        post_confirmation = [
            {
                **item,
                "effective_candidate": item["truth"]
                if item["teacher_anchor"]
                else item["effective_candidate"],
                "effective_visible": True
                if item["teacher_anchor"]
                else item["effective_visible"],
            }
            for item in measured
        ]
        return {
            "anchor_count": anchor_count,
            "records": len(measured),
            "resolver_seconds": round(elapsed, 6),
            "summary": _summary(measured),
            "non_anchor_summary": _summary(non_anchor),
            "post_confirmation_summary": _summary(post_confirmation),
            "records_detail": measured,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--anchor-count", type=int, action="append", default=[])
    args = parser.parse_args()
    rows = _load_rows(args.input)
    counts = args.anchor_count or [0, 1, 3, 5, 10]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        group = str(row.get("corpus_id", "single-room"))
        groups.setdefault(group, []).append(row)
    report = {
        "schema_version": 1,
        "kind": "student_number_batch_assistance_benchmark",
        "input": str(args.input.resolve()),
        "anchor_contract": (
            "first N rows are explicitly teacher-confirmed anchors for this benchmark scenario; "
            "this is not model ground truth and anchors are reported separately"
        ),
        "runs": [
            {
                "anchor_count": count,
                "groups": {
                    group: evaluate(group_rows, min(max(count, 0), len(group_rows)))
                    for group, group_rows in sorted(groups.items())
                },
            }
            for count in counts
        ],
        "limitations": [
            "Anchor scenarios are deterministic simulations of teacher-confirmed identities.",
            "Batch assistance is review-only and never changes persisted raw detections.",
            "A teacher's later correction remains authoritative over all derived rankings.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"runs": len(report["runs"]), "output": str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
