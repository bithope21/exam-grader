"""Compare Vol.8 visual reference labels with the current OMR/identity pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from exam_grader.identity import observe as observe_student_number
from exam_grader.imaging import OMR_PIPELINE_VERSION, analyze, decode
from exam_grader.template_manager import default_1_template_definition


def _state(answer: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    classification = str(answer.get("classification", "uncertain"))
    selected = tuple(sorted(answer.get("selected", [])))
    return classification, selected


def _reference_state(photo: dict[str, Any], question: int) -> tuple[str, tuple[str, ...]]:
    key = str(question)
    if question in photo.get("uncertain_questions", []):
        return "uncertain", ()
    selected = tuple(sorted(photo.get("answers", {}).get(key, [])))
    if not selected:
        return "blank", ()
    return ("multiple" if len(selected) > 1 else "single_mark"), selected


def compare_photo(photo: dict[str, Any], prediction: dict[str, Any], question_count: int) -> dict:
    by_question = {int(item["question"]): item for item in prediction.get("answers", [])}
    counts: Counter[str] = Counter()
    mismatches: list[dict] = []
    compared = 0
    human_ambiguous = 0
    for question in range(1, question_count + 1):
        expected_class, expected_selected = _reference_state(photo, question)
        predicted = by_question.get(question, {"classification": "uncertain", "selected": []})
        actual_class, actual_selected = _state(predicted)
        if expected_class == "uncertain":
            human_ambiguous += 1
            if actual_class == "uncertain":
                counts["machine_uncertain_on_ambiguous"] += 1
            else:
                counts["unsafe_decision_on_ambiguous"] += 1
                mismatches.append(
                    {
                        "question": question,
                        "expected": "uncertain",
                        "predicted": actual_class,
                        "selected": list(actual_selected),
                        "kind": "unsafe_decision_on_ambiguous",
                    }
                )
            continue

        compared += 1
        if (actual_class, actual_selected) == (expected_class, expected_selected):
            counts["exact_match"] += 1
            continue

        if actual_class == "uncertain":
            kind = "uncertain"
        elif actual_class == "multiple" and expected_class != "multiple":
            kind = "false_multi"
        elif actual_class == "blank" and expected_class != "blank":
            kind = "false_blank"
        else:
            kind = "wrong"
        counts[kind] += 1
        mismatches.append(
            {
                "question": question,
                "expected": expected_class,
                "expected_selected": list(expected_selected),
                "predicted": actual_class,
                "predicted_selected": list(actual_selected),
                "kind": kind,
                "decision_reason": predicted.get("decision_reason"),
                "ink_density": predicted.get("ink_density"),
                "core_density": predicted.get("core_density"),
            }
        )

    expected_number = photo.get("student_number", {})
    identity = prediction.get("student_number_observation", {})
    candidate = identity.get("candidate")
    identity_state = expected_number.get("state", "clear")
    if identity_state == "clear":
        identity_result = {
            "expected": expected_number.get("value"),
            "candidate": candidate,
            "candidates": identity.get("candidates", []),
            "exact_primary_candidate": candidate == expected_number.get("value"),
            "candidate_contains_reference": expected_number.get("value")
            in identity.get("candidates", []),
            "requires_review": bool(identity.get("requires_review", True)),
            "review_reason": identity.get("review_reason"),
        }
    else:
        identity_result = {
            "expected": None,
            "candidate": candidate,
            "candidates": identity.get("candidates", []),
            "exact_primary_candidate": candidate is None,
            "candidate_contains_reference": candidate is None,
            "requires_review": bool(identity.get("requires_review", True)),
            "review_reason": identity.get("review_reason"),
        }

    registration = prediction.get("registration", {})
    return {
        "source": photo["source"],
        "student_number": identity_result,
        "question_count": question_count,
        "human_resolved_questions": compared,
        "human_ambiguous_questions": human_ambiguous,
        "exact_match": counts["exact_match"],
        "wrong": counts["wrong"],
        "false_multi": counts["false_multi"],
        "false_blank": counts["false_blank"],
        "machine_uncertain": counts["uncertain"],
        "machine_uncertain_on_ambiguous": counts["machine_uncertain_on_ambiguous"],
        "unsafe_decision_on_ambiguous": counts["unsafe_decision_on_ambiguous"],
        "mismatches": mismatches,
        "registration": {
            key: registration.get(key)
            for key in (
                "method",
                "selected_candidate",
                "normalization_confidence",
                "normalization_requires_review",
                "grid_residual_px",
                "grid_median_residual_px",
                "grid_line_coverage",
                "alignment_confidence",
            )
        },
        "document_normalization": prediction.get("document_normalization", {}),
        "diagnostic_stages": prediction.get("diagnostic_stages", {}),
    }


def run(fixtures: Path, labels_path: Path, output: Path) -> dict:
    labels_data = labels_path.read_bytes()
    labels = json.loads(labels_data.decode("utf-8"))
    key_reference = labels["key"]
    key_source = fixtures / key_reference["source"]
    key_sha256 = hashlib.sha256(key_source.read_bytes()).hexdigest()
    if key_sha256 != key_reference["sha256"]:
        raise ValueError(f"Fixture hash changed: {key_source.name}")
    template = default_1_template_definition()
    output.mkdir(parents=True, exist_ok=True)
    photos = []
    for reference in labels["photos"]:
        source = fixtures / reference["source"]
        data = source.read_bytes()
        source_sha256 = hashlib.sha256(data).hexdigest()
        if source_sha256 != reference["sha256"]:
            raise ValueError(f"Fixture hash changed: {source.name}")
        decoded = decode(data)
        observation = analyze(data, template_def=template, decoded_image=decoded)
        observation["student_number_observation"] = observe_student_number(
            data,
            observation.get("registration", {}).get("matrix"),
            template_def=template,
            image=decoded,
        )
        active_count = int(labels["scoring_key_question_count"])
        grid_count = int(labels["question_grid_count"])
        active_comparison = compare_photo(reference, observation, active_count)
        grid_comparison = compare_photo(reference, observation, grid_count)
        active_questions = set(range(1, active_count + 1))
        active_comparison["out_of_key_grid"] = {
            "question_count": grid_count - active_count,
            "human_resolved_questions": grid_comparison["human_resolved_questions"]
            - active_comparison["human_resolved_questions"],
            "human_ambiguous_questions": grid_comparison["human_ambiguous_questions"]
            - active_comparison["human_ambiguous_questions"],
            "exact_match": grid_comparison["exact_match"] - active_comparison["exact_match"],
            "wrong": grid_comparison["wrong"] - active_comparison["wrong"],
            "false_multi": grid_comparison["false_multi"] - active_comparison["false_multi"],
            "false_blank": grid_comparison["false_blank"] - active_comparison["false_blank"],
            "machine_uncertain": grid_comparison["machine_uncertain"]
            - active_comparison["machine_uncertain"],
            "mismatches": [
                mismatch
                for mismatch in grid_comparison["mismatches"]
                if mismatch["question"] not in active_questions
            ],
            "human_visible_marks": sum(
                bool(reference.get("answers", {}).get(str(question)))
                for question in range(active_count + 1, grid_count + 1)
            ),
        }
        photos.append(
            {
                "source_sha256": source_sha256,
                "pipeline_version": observation.get("pipeline_version"),
                **active_comparison,
                "machine_classification_counts": dict(
                    Counter(item["classification"] for item in observation.get("answers", []))
                ),
                "stage_timings": observation.get("stage_timings", {}),
            }
        )

    summary_counts: Counter[str] = Counter()
    for photo in photos:
        for field in (
            "human_resolved_questions",
            "human_ambiguous_questions",
            "exact_match",
            "wrong",
            "false_multi",
            "false_blank",
            "machine_uncertain",
            "machine_uncertain_on_ambiguous",
            "unsafe_decision_on_ambiguous",
        ):
            summary_counts[field] += int(photo[field])
    summary = {
        key: summary_counts[key]
        for key in summary_counts
    }
    summary["exact_accuracy"] = (
        round(summary_counts["exact_match"] / summary_counts["human_resolved_questions"], 6)
        if summary_counts["human_resolved_questions"]
        else None
    )
    summary["registered_photos"] = len(photos)
    summary["photo_count"] = len(labels["photos"])
    summary["student_number_primary_exact"] = sum(
        int(photo["student_number"]["exact_primary_candidate"]) for photo in photos
    )
    summary["student_number_legible_count"] = sum(
        photo["student_number"]["expected"] is not None for photo in photos
    )
    summary["identity_candidates_requiring_review"] = sum(
        int(photo["student_number"]["requires_review"]) for photo in photos
    )
    result = {
        "schema": "exam-grader.vol8-accuracy-report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": OMR_PIPELINE_VERSION,
        "reference_path": str(labels_path),
        "reference_sha256": hashlib.sha256(labels_data).hexdigest(),
        "reference_adjudication_status": labels.get("adjudication_status"),
        "key_source": key_reference["source"],
        "key_source_sha256": key_sha256,
        "reference_question_grid_count": labels["question_grid_count"],
        "scoring_key_question_count": labels["scoring_key_question_count"],
        "metric_definition": {
            "exact_match": "Exact choice and state match on visually resolved questions; blank, single and exact multi-choice are distinct.",
            "wrong": "Resolved nonblank prediction has a different choice/state, excluding false multi and false blank categories.",
            "false_multi": "Machine labels multiple where visual reference is not multiple.",
            "false_blank": "Machine labels blank where visual reference has a clear mark.",
            "machine_uncertain": "Machine leaves a visually resolved question uncertain.",
            "ambiguous": "Visual-reference uncertain questions are excluded from exact accuracy and checked separately for an unsafe machine decision.",
        },
        "limitations": labels.get("limitations", []),
        "photos": photos,
        "summary": summary,
    }
    target = output / "report.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=root / "tests/fixtures/real/vol.8")
    parser.add_argument(
        "--labels",
        type=Path,
        default=root / "docs/evidence/vol8-accuracy/ground_truth.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "docs/evidence/vol8-accuracy/after",
    )
    args = parser.parse_args()
    result = run(args.fixtures.resolve(), args.labels.resolve(), args.output.resolve())
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    for photo in result["photos"]:
        ident = photo["student_number"]
        print(
            f"{photo['source']}: {photo['exact_match']}/{photo['human_resolved_questions']} exact; "
            f"wrong={photo['wrong']} false_multi={photo['false_multi']} "
            f"false_blank={photo['false_blank']} uncertain={photo['machine_uncertain']} "
            f"human_uncertain={photo['human_ambiguous_questions']} "
            f"number={ident['candidate']!r}/{ident['expected']!r} "
            f"review={ident['requires_review']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
