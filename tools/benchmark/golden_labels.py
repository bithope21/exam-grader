"""Build a provenance-first label manifest from a confirmed engineering run.

The confirmed scoring answer is intentionally kept separate from visual recognition
truth.  A field is usable for recognition metrics only when an independent visual
adjudication exists.  In particular, the historical key question 6 is marked
disputed rather than silently treating the scoring answer as a visual label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = 1


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(run: Path, fixtures: Path, *, disputed: set[tuple[str, int]] | None = None) -> dict:
    disputed = disputed or set()
    metadata = run / "_system" / "results.json"
    if not metadata.is_file():
        metadata = run / "results.json"  # immutable legacy layout
    results = json.loads(metadata.read_text(encoding="utf-8"))
    records: list[dict] = []
    for result in results["results"]:
        filename = result["source"]["original_name"]
        fixture = fixtures / filename
        detection = result.get("detection") or {}
        observations = detection.get("answers", [])[: results["exam"]["question_count"]]
        confirmed = result["answers"]
        questions = []
        for index, observation in enumerate(observations, start=1):
            final = confirmed[index - 1] if index <= len(confirmed) else None
            key = (filename, index)
            questions.append(
                {
                    "question": index,
                    "machine": {
                        "classification": observation.get("classification"),
                        "selected": observation.get("selected", []),
                        "ink_density": observation.get("ink_density", []),
                        "feature": observation.get("feature"),
                    },
                    "teacher_scoring_decision": final,
                    "visual_label": None,
                    "label_status": "disputed" if key in disputed else "unadjudicated",
                    "label_origin": "none",
                }
            )
        records.append(
            {
                "filename": filename,
                "source_sha256": result["source"]["sha256"],
                "fixture_sha256": sha256(fixture) if fixture.is_file() else None,
                "source_id": result["source"]["id"],
                "detection_id": result.get("detection", {}).get("id"),
                "review_id": result.get("review_id"),
                "key_id": results["key"]["id"],
                "question_count": results["exam"]["question_count"],
                "questions": questions,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "exam_grader_golden_label_manifest",
        "run_id": results.get("run_id"),
        "run_path": str(run),
        "fixture_root": str(fixtures),
        "exam_id": results["exam"]["id"],
        "key_id": results["key"]["id"],
        "recognition_truth_policy": "independent_visual_adjudication_only",
        "scoring_truth_policy": "historical_teacher_review_decision",
        "fold_policy": "sheet_grouped; transformed copies stay with source sheet",
        "records": records,
        "excluded_for_recognition": [
            {"filename": filename, "question": question, "reason": "conflicting visual/scoring evidence"}
            for filename, question in sorted(disputed)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--disputed", action="append", default=[], metavar="FILE:QUESTION")
    args = parser.parse_args()
    disputed = {(value.rsplit(":", 1)[0], int(value.rsplit(":", 1)[1])) for value in args.disputed}
    manifest = build_manifest(args.run.resolve(), args.fixtures.resolve(), disputed=disputed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(manifest["records"]), "excluded": len(manifest["excluded_for_recognition"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
