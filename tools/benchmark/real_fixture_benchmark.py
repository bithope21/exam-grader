"""Engineering-only report for the immutable real-fixture UAT set.

This report measures pipeline behavior and review burden. It has no independent
answer labels and must not be read as an accuracy or production-readiness claim.
"""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from exam_grader.imaging import analyze


def evaluate(root: Path, *, question_count: int = 30) -> dict:
    records = []
    paths = sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    for path in paths:
        data = path.read_bytes()
        started = time.perf_counter()
        record: dict[str, Any] = {
            "filename": path.name,
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        try:
            prediction = analyze(data)
        except ValueError as error:
            record.update(
                {
                    "status": "registration_or_decode_rejected",
                    "reason": str(error),
                    "diagnostics": getattr(error, "diagnostics", {}),
                }
            )
        else:
            states = Counter(item["classification"] for item in prediction["answers"])
            active_answers = prediction["answers"][:question_count]
            margins = [item.get("top_two_margin", 0.0) for item in active_answers]
            record.update(
                {
                    "status": "accepted_for_teacher_review",
                    "registration": prediction["registration"],
                    "state_counts": dict(states),
                    "selected_all_choices_count": sum(
                        item["selected"] == list("ABCDE") for item in prediction["answers"]
                    ),
                    "requires_review": prediction["requires_review"],
                    "stage_timings": prediction.get("stage_timings", {}),
                    "uncertain_questions": sum(
                        item["classification"] == "uncertain" for item in active_answers
                    ),
                    "multiple_questions": sum(
                        item["classification"] == "multiple" for item in active_answers
                    ),
                    "top_two_margin": {
                        "min": min(margins) if margins else None,
                        "median": sorted(margins)[len(margins) // 2] if margins else None,
                        "max": max(margins) if margins else None,
                    },
                }
            )
        record["seconds"] = round(time.perf_counter() - started, 4)
        records.append(record)
    statuses = Counter(record["status"] for record in records)
    return {
        "schema_version": 1,
        "kind": "real_fixture_engineering_uat",
        "fixture_root": str(root),
        "evaluated": len(records),
        "status_counts": dict(statuses),
        "registration_accepted": statuses.get("accepted_for_teacher_review", 0),
        "registration_rejected": statuses.get("registration_or_decode_rejected", 0),
        "selected_all_choices_total": sum(
            record.get("selected_all_choices_count", 0) for record in records
        ),
        "auto_accept_count": 0,
        "warning": "Real fixtures are engineering/UAT evidence only; no accuracy or production claim.",
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--question-count", type=int, default=30)
    args = parser.parse_args()
    if args.question_count < 1 or args.question_count > 60:
        parser.error("--question-count must be between 1 and 60")
    report = evaluate(args.fixtures.resolve(), question_count=args.question_count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "evaluated",
                    "status_counts",
                    "registration_accepted",
                    "registration_rejected",
                    "selected_all_choices_total",
                    "auto_accept_count",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
