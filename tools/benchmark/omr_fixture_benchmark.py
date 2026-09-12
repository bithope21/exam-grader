"""Run the supplied synthetic manifest through the current OMR pipeline.

This tool is deliberately conservative: registration rejection is reported separately
from answer errors, and no result is an auto-accept or production accuracy claim.
"""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from exam_grader.imaging import RegistrationError, analyze


def evaluate(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["fixtures"]
    records = []
    for entry in entries:
        path = root / entry["filename"]
        data = path.read_bytes()
        started = time.perf_counter()
        record = {
            "filename": entry["filename"],
            "category": entry["category"],
            "sha256": hashlib.sha256(data).hexdigest(),
            "expected_review_flags": entry.get("expected_review_flags", []),
        }
        try:
            prediction = analyze(data)
        except RegistrationError as error:
            record.update(
                {
                    "status": "registration_or_decode_rejected",
                    "reason": str(error),
                    "diagnostics": error.diagnostics,
                }
            )
        except ValueError as error:
            record.update(
                {
                    "status": "registration_or_decode_rejected",
                    "reason": str(error),
                    "diagnostics": {"stage": "decode"},
                }
            )
        else:
            expected = entry.get("answers", {})
            exact = 0
            for item in prediction["answers"]:
                truth = expected.get(str(item["question"]), [])
                if item["selected"] == truth:
                    exact += 1
            record.update(
                {
                    "status": "predicted_review_required"
                    if prediction["requires_review"]
                    else "predicted",
                    "exact_selected_questions": exact,
                    "questions": len(prediction["answers"]),
                    "registration": prediction["registration"],
                    "stage_timings": prediction.get("stage_timings", {}),
                }
            )
        record["seconds"] = round(time.perf_counter() - started, 4)
        records.append(record)
    statuses = Counter(record["status"] for record in records)
    accepted = [r for r in records if r["status"] != "registration_or_decode_rejected"]
    question_total = sum(r.get("questions", 0) for r in accepted)
    exact_total = sum(r.get("exact_selected_questions", 0) for r in accepted)
    review_count = sum(r["status"] == "predicted_review_required" for r in records)
    return {
        "schema_version": 1,
        "kind": "synthetic_omr_regression_probe",
        "dataset_name": manifest.get("dataset_name"),
        "dataset_seed": manifest.get("seed"),
        "manifest_total": manifest.get("total_fixtures"),
        "evaluated": len(records),
        "status_counts": dict(statuses),
        "registration_accepted": len(accepted),
        "registration_rejected": statuses.get("registration_or_decode_rejected", 0),
        "answer_questions_evaluated": question_total,
        "exact_selected_questions": exact_total,
        "review_count": review_count,
        "review_rate": round(review_count / len(records), 6) if records else 0.0,
        "stage_timings": {
            "sum_seconds": round(sum(r["seconds"] for r in records), 4),
            "mean_seconds": round(sum(r["seconds"] for r in records) / len(records), 4)
            if records
            else 0.0,
            "max_seconds": round(max((r["seconds"] for r in records), default=0.0), 4),
        },
        # Production auto-accept remains contractually disabled in this draft pipeline.
        "auto_accept_count": 0,
        "warning": "Synthetic/provisional only; no production accuracy claim and no digit-model training",
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.fixtures.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "dataset_name",
                    "manifest_total",
                    "evaluated",
                    "status_counts",
                    "auto_accept_count",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
