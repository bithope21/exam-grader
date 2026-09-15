"""Replay the current Vol.8 OMR and identity pipeline against teacher-confirmed results.

The exported review records contain exact confirmed choices for single-mark
answers. For responses recorded as ``multiple`` they preserve only the state,
not which choices were marked; those five rows are therefore evaluated as a
state match and are never described as exact choice matches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from exam_grader.identity import IDENTITY_PIPELINE_VERSION
from exam_grader.identity import observe as observe_student_number
from exam_grader.imaging import OMR_PIPELINE_VERSION, analyze, decode
from exam_grader.template_manager import TemplateDefinition

DEFAULT_EXPORT = (
    "2569_ป.1_1_math_vol8 lunar ultra_30q/ผลการตรวจ/2026-09-14_205501/_system/results.json"
)
ACTIVE_QUESTION_COUNT = 30


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _truth_state(value: Any) -> tuple[str, str | None]:
    """Return (state, exact_choice) from a teacher-confirmed result cell."""
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {"A", "B", "C", "D", "E"}:
            return "single", normalized
        lowered = value.strip().lower()
        if lowered in {"multiple", "multi"}:
            return "multiple", None
        if lowered in {"blank", "", "none", "unanswered"}:
            return "blank", None
        if lowered in {"uncertain", "unknown", "review"}:
            return "uncertain", None
    if value is None:
        return "blank", None
    if isinstance(value, (list, tuple, set)):
        choices = sorted(str(item).strip().upper() for item in value)
        if len(choices) == 1 and choices[0] in {"A", "B", "C", "D", "E"}:
            return "single", choices[0]
        if len(choices) > 1 and all(
            choice in {"A", "B", "C", "D", "E"} for choice in choices
        ):
            return "multiple", None
    return "unknown", None


def _prediction_state(prediction: dict[str, Any] | None) -> tuple[str, list[str]]:
    if not prediction:
        return "uncertain", []
    classification = str(prediction.get("classification", "uncertain"))
    selected = sorted(
        {
            str(choice).strip().upper()
            for choice in prediction.get("selected", [])
            if str(choice).strip()
        }
    )
    if classification == "single_mark" and len(selected) != 1:
        return "invalid_prediction", selected
    state_by_class = {
        "single_mark": "single",
        "multiple": "multiple",
        "blank": "blank",
        "uncertain": "uncertain",
        "boundary_cross": "boundary_cross",
    }
    return state_by_class.get(classification, "other"), selected


def _compare_question(
    question: int,
    expected_value: Any,
    prediction: dict[str, Any] | None,
) -> dict[str, Any]:
    expected_state, expected_choice = _truth_state(expected_value)
    predicted_state, predicted_choices = _prediction_state(prediction)
    auto_resolved = bool((prediction or {}).get("auto_resolved", False))

    if expected_state in {"unknown", "uncertain"}:
        outcome = (
            "safe_uncertain_on_unresolved_truth"
            if predicted_state == "uncertain"
            else "unsafe_decision_on_unresolved_truth"
        )
        choice_exact: bool | None = None
        state_match: bool | None = None
    elif predicted_state == "uncertain":
        outcome = "machine_uncertain"
        choice_exact = False if expected_state == "single" else None
        state_match = False
    elif predicted_state == "blank":
        if expected_state == "blank":
            outcome = "blank_state_match"
            choice_exact = None
            state_match = True
        else:
            outcome = "false_blank"
            choice_exact = False if expected_state == "single" else None
            state_match = False
    elif predicted_state == "multiple":
        if expected_state == "multiple":
            outcome = "multiple_state_match_choice_subset_unavailable"
            choice_exact = None
            state_match = True
        else:
            outcome = "false_multiple"
            choice_exact = False if expected_state == "single" else None
            state_match = False
    elif expected_state == "multiple":
        outcome = "multiple_state_missed"
        choice_exact = None
        state_match = False
    elif expected_state == "single" and predicted_state == "single":
        choice_exact = predicted_choices == [expected_choice]
        state_match = choice_exact
        outcome = "exact_choice_match" if choice_exact else "wrong_choice"
    elif predicted_state == "boundary_cross":
        outcome = "boundary_cross"
        choice_exact = False if expected_state == "single" else None
        state_match = False
    else:
        outcome = "wrong_state"
        choice_exact = False if expected_state == "single" else None
        state_match = False

    unsafe = bool(
        expected_state not in {"unknown", "uncertain"}
        and state_match is False
        and auto_resolved
    )
    return {
        "question": question,
        "expected_value": expected_value,
        "expected_state": expected_state,
        "expected_choice": expected_choice,
        "expected_multiple_choice_subset_available": expected_state != "multiple",
        "predicted_state": predicted_state,
        "predicted_choices": predicted_choices,
        "classification": (prediction or {}).get("classification"),
        "decision_reason": (prediction or {}).get("decision_reason"),
        "auto_resolved": auto_resolved,
        "choice_exact": choice_exact,
        "state_match": state_match,
        "outcome": outcome,
        "unsafe_confident_mismatch": unsafe,
    }


def _not_run_question(question: int, expected_value: Any) -> dict[str, Any]:
    expected_state, expected_choice = _truth_state(expected_value)
    return {
        "question": question,
        "expected_value": expected_value,
        "expected_state": expected_state,
        "expected_choice": expected_choice,
        "expected_multiple_choice_subset_available": expected_state != "multiple",
        "predicted_state": None,
        "predicted_choices": [],
        "classification": None,
        "decision_reason": None,
        "auto_resolved": False,
        "choice_exact": None,
        "state_match": None,
        "outcome": "not_run_registration_failed",
        "unsafe_confident_mismatch": False,
    }


def _reference_png(
    fixtures: Path, export_data: dict[str, Any], app_data_dir: Path
) -> tuple[TemplateDefinition, dict[str, Any]]:
    template_data = export_data["export"]["template"]
    template_def = TemplateDefinition.from_dict(template_data)
    key_info = export_data.get("key_source") or {}
    key_path = fixtures / str(key_info.get("original_name", "key.jpg"))
    key_bytes = key_path.read_bytes()
    actual_key_hash = _sha256(key_bytes)
    expected_key_hash = key_info.get("sha256")
    if expected_key_hash is not None and actual_key_hash != str(expected_key_hash):
        raise ValueError(
            f"Answer-key fixture hash mismatch for {key_path.name}: "
            f"expected {expected_key_hash}, got {actual_key_hash}"
        )

    registration = template_def.registration_config
    matrix = np.asarray(registration.get("paper_to_canonical_matrix"), dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("Exported template has no valid paper_to_canonical_matrix")
    key_image = decode(key_bytes)
    reference = cv2.warpPerspective(
        key_image,
        matrix,
        (template_def.canonical_width, template_def.canonical_height),
        borderValue=(255, 255, 255),
    )
    ok, encoded = cv2.imencode(".png", reference)
    if not ok:
        raise ValueError("Could not encode reconstructed canonical answer-key image")
    reference_bytes = encoded.tobytes()
    reference_hash = _sha256(reference_bytes)
    if reference_hash != template_def.reference_sha256:
        raise ValueError(
            "Reconstructed answer-key reference does not match the exported content hash "
            f"({reference_hash} != {template_def.reference_sha256})"
        )
    target = (
        app_data_dir
        / "templates"
        / "references"
        / f"{template_def.reference_sha256}.png"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(reference_bytes)
    return template_def, {
        "answer_key_source": key_path.name,
        "answer_key_sha256": actual_key_hash,
        "reference_sha256": reference_hash,
        "reference_reconstruction": "exported-key image warped by exported canonical matrix",
        "reference_verified": True,
        "template_id": template_def.template_id,
        "template_version": template_def.version,
        "canonical_size": [template_def.canonical_width, template_def.canonical_height],
        "template_question_count": template_def.question_count,
    }


def _classify_counts(questions: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(question["outcome"]) for question in questions))


def _registration_evidence(
    prediction: dict[str, Any], teacher_detection: dict[str, Any] | None = None
) -> dict[str, Any]:
    registration = prediction.get("registration") or {}
    normalization = prediction.get("document_normalization") or {}
    boundary_stage = (prediction.get("diagnostic_stages") or {}).get("boundary") or {}
    manual_reasons: list[str] = []
    if registration.get("normalization_requires_review"):
        manual_reasons.append("normalization_requires_review")
    if registration.get("review_required"):
        manual_reasons.append("registration_review_required")
    coverage = registration.get("table_coverage")
    if isinstance(coverage, (int, float)) and coverage < 0.985:
        manual_reasons.append("table_coverage_below_0.985")

    boundary_confidence = normalization.get(
        "physical_boundary_confidence",
        normalization.get("boundary_confidence", registration.get("paper_confidence")),
    )
    physical_corners = registration.get("physical_paper_corners") or registration.get(
        "paper_corners"
    )
    manual_corner_adjustment_required = bool(
        physical_corners is None
        or not isinstance(boundary_confidence, (int, float))
        or boundary_confidence < 0.82
        or (isinstance(coverage, (int, float)) and coverage < 0.985)
    )

    method = registration.get("method")
    boundary_status = normalization.get(
        "boundary_status", registration.get("normalization_boundary_status")
    )
    teacher_registration = (teacher_detection or {}).get("registration") or {}
    teacher_normalization = (teacher_detection or {}).get("document_normalization") or {}
    teacher_method = teacher_registration.get("method")
    teacher_boundary_status = teacher_normalization.get(
        "boundary_status", teacher_registration.get("normalization_boundary_status")
    )
    return {
        "method": method,
        "selected_candidate": registration.get("selected_candidate"),
        "boundary_status": boundary_status,
        "boundary_method": normalization.get("boundary_method"),
        "boundary_confidence": boundary_confidence,
        "physical_paper_corners": physical_corners,
        "manual_corner_adjustment_required": manual_corner_adjustment_required,
        "normalization_confidence": registration.get("normalization_confidence"),
        "normalization_requires_review": registration.get(
            "normalization_requires_review"
        ),
        "manual_intervention_required": bool(manual_reasons),
        "manual_intervention_reasons": manual_reasons,
        "teacher_reviewed_run": {
            "method": teacher_method,
            "boundary_status": teacher_boundary_status,
            "human_adjusted": bool(
                (isinstance(teacher_method, str) and "manual" in teacher_method.lower())
                or teacher_boundary_status == "human-adjusted"
            ),
            "selected_candidate": teacher_registration.get("selected_candidate"),
            "selected_corners": teacher_registration.get("selected_corners"),
            "paper_corners": teacher_registration.get("paper_corners"),
            "grid_residual_px": teacher_registration.get("grid_residual_px"),
            "grid_line_coverage": teacher_registration.get("grid_line_coverage"),
            "alignment_confidence": teacher_registration.get("alignment_confidence"),
            "normalization_requires_review": teacher_registration.get(
                "normalization_requires_review"
            ),
        },
        "selected_corners": registration.get("selected_corners"),
        "paper_corners": registration.get("paper_corners"),
        "paper_boundary_candidates": registration.get("paper_boundary_candidates")
        or boundary_stage.get("candidates"),
        "boundary_diagnostics": boundary_stage,
        "candidate_count": registration.get(
            "candidate_count", boundary_stage.get("candidate_count")
        ),
        "grid_residual_px": registration.get("grid_residual_px"),
        "grid_median_residual_px": registration.get("grid_median_residual_px"),
        "grid_line_coverage": registration.get("grid_line_coverage"),
        "grid_line_contrast": registration.get("grid_line_contrast"),
        "alignment_confidence": registration.get("alignment_confidence"),
        "table_coverage": coverage,
        "fine_registration": registration.get("fine_registration"),
        "review_required": registration.get("review_required"),
    }


def _identity_evidence(expected_number: Any, observation: dict[str, Any]) -> dict[str, Any]:
    expected = str(expected_number) if expected_number is not None else None
    candidate = observation.get("candidate")
    candidates = [str(item) for item in observation.get("candidates", [])]
    review_suggestions = observation.get("review_suggestions", [])
    review_suggestion_values = [
        str(item["candidate"])
        for item in review_suggestions
        if isinstance(item, dict) and item.get("candidate")
    ]
    return {
        "expected_teacher_confirmed": expected,
        "primary_candidate": candidate,
        "candidates": observation.get("candidates", []),
        "primary_exact": str(candidate) == expected if expected is not None and candidate is not None else False,
        "candidate_set_contains_truth": expected in candidates if expected is not None else None,
        "review_suggestions": review_suggestions,
        "review_suggestion_contains_truth": (
            expected in review_suggestion_values if expected is not None else None
        ),
        "requires_review": bool(observation.get("requires_review", True)),
        "review_reason": observation.get("review_reason"),
        "confidence": observation.get("confidence"),
        "pipeline_version": observation.get("pipeline_version", IDENTITY_PIPELINE_VERSION),
        "roi": observation.get("roi"),
        "diagnostics": observation.get("diagnostics"),
    }


def _summarize(photos: list[dict[str, Any]], expected_count: int) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    for photo in photos:
        for question in photo.get("questions", []):
            totals[question["outcome"]] += 1

    scored = totals["exact_choice_match"]
    expected_multiple = sum(
        question.get("expected_state") == "multiple"
        for photo in photos
        for question in photo.get("questions", [])
    )
    multiple_state_matches = totals["multiple_state_match_choice_subset_unavailable"]
    single_count = sum(
        question.get("expected_state") == "single"
        for photo in photos
        for question in photo.get("questions", [])
    )
    registered_single_count = sum(
        question.get("expected_state") == "single"
        for photo in photos
        if "error" not in photo
        for question in photo.get("questions", [])
    )
    state_compared = sum(
        1
        for photo in photos
        for question in photo.get("questions", [])
        if question.get("state_match") is not None
    )
    state_matches = sum(
        1
        for photo in photos
        for question in photo.get("questions", [])
        if question.get("state_match") is True
    )
    unsafe_confident_mismatches = sum(
        bool(question.get("unsafe_confident_mismatch"))
        for photo in photos
        for question in photo.get("questions", [])
    )
    identities = [photo.get("student_number") or {} for photo in photos]
    registrations = [photo.get("registration") or {} for photo in photos]
    resolved = sum(
        1
        for photo in photos
        for question in photo.get("questions", [])
        if question.get("expected_state") not in {"unknown", "uncertain"}
    )
    primary_identity_exact = sum(bool(item.get("primary_exact")) for item in identities)
    identity_truth_in_candidates = sum(
        bool(item.get("candidate_set_contains_truth")) for item in identities
    )
    identity_truth_in_review_suggestions = sum(
        bool(item.get("review_suggestion_contains_truth")) for item in identities
    )
    identity_truth_available_for_review = sum(
        bool(item.get("candidate_set_contains_truth"))
        or bool(item.get("review_suggestion_contains_truth"))
        for item in identities
    )
    requires_review = sum(bool(item.get("requires_review", True)) for item in identities)
    residuals = [
        float(reg["grid_residual_px"])
        for reg in registrations
        if isinstance(reg.get("grid_residual_px"), (int, float))
    ]
    return {
        "photo_count_expected": expected_count,
        "photo_count_processed": len(photos),
        "photo_count_failed": sum("error" in photo for photo in photos),
        "active_question_count_per_sheet": ACTIVE_QUESTION_COUNT,
        "teacher_confirmed_question_cells": resolved,
        "state_matches": state_matches,
        "state_comparable_question_cells_registered": state_compared,
        "state_match_rate_registered": round(state_matches / state_compared, 6)
        if state_compared
        else None,
        "end_to_end_state_match_rate": round(state_matches / resolved, 6) if resolved else None,
        "exact_single_choice_matches": scored,
        "teacher_confirmed_single_choice_count_end_to_end": single_count,
        "single_choice_exact_rate_end_to_end": round(scored / single_count, 6)
        if single_count
        else None,
        "teacher_confirmed_single_choice_count_registered": registered_single_count,
        "single_choice_exact_rate_registered": round(scored / registered_single_count, 6)
        if registered_single_count
        else None,
        "teacher_confirmed_multiple_states": expected_multiple,
        "multiple_state_matches": multiple_state_matches,
        "multiple_choice_subsets_evaluable": 0,
        "outcomes": dict(totals),
        "registration_failed_question_cells": totals["not_run_registration_failed"],
        "unsafe_confident_mismatches": unsafe_confident_mismatches,
        "student_number_primary_exact": primary_identity_exact,
        "student_number_candidate_set_contains_truth": identity_truth_in_candidates,
        "student_number_review_suggestion_contains_truth": identity_truth_in_review_suggestions,
        "student_number_truth_available_in_candidates_or_review_suggestions": identity_truth_available_for_review,
        "student_number_review_required": requires_review,
        "manual_intervention_required": sum(
            bool(item.get("manual_intervention_required")) for item in registrations
        ),
        "manual_corner_adjustment_required": sum(
            bool(item.get("manual_corner_adjustment_required")) for item in registrations
        ),
        "historical_teacher_run_human_adjusted": sum(
            bool((item.get("teacher_reviewed_run") or {}).get("human_adjusted"))
            for item in registrations
        ),
        "worst_grid_residual_px": max(residuals) if residuals else None,
        "lowest_alignment_confidence": min(
            (
                float(reg["alignment_confidence"])
                for reg in registrations
                if isinstance(reg.get("alignment_confidence"), (int, float))
            ),
            default=None,
        ),
        "exactness_note": (
            "295 teacher-confirmed single-choice rows support exact choice comparison. "
            "The five teacher-confirmed 'multiple' rows preserve only the multiple state, "
            "so marked-choice subsets cannot be scored. Registered-only rates exclude sheets "
            "where registration failed; end-to-end rates retain those expected questions "
            "in the denominator. State matches on multiple rows are state-only, not exact marks."
        ),
    }


def run(fixtures: Path, truth_path: Path, output: Path) -> dict[str, Any]:
    truth_bytes = truth_path.read_bytes()
    export_data = json.loads(truth_bytes.decode("utf-8"))
    if export_data.get("schema_version") != 2:
        raise ValueError(f"Unsupported results schema version: {export_data.get('schema_version')!r}")
    expected_question_count = int(export_data.get("exam", {}).get("question_count", 0))
    if expected_question_count < ACTIVE_QUESTION_COUNT:
        raise ValueError(
            f"Teacher export has only {expected_question_count} active questions; "
            f"expected at least {ACTIVE_QUESTION_COUNT}"
        )
    source_results = export_data.get("results", [])
    if not source_results:
        raise ValueError("Teacher-confirmed export contains no results")

    truth_provenance = {
        item["source"]["original_name"]: {
            "sha256": item["source"]["sha256"],
            "status": item.get("status"),
            "review_record_type": item.get("review_record_type"),
            "answer_provenance": item.get("answer_provenance", []),
            "decision_origin": item.get("decision_origin"),
            "identity_origin": item.get("identity_origin"),
            "student_number": item.get("student_number"),
        }
        for item in source_results
    }
    duplicate_names = len(truth_provenance) != len(source_results)
    if duplicate_names:
        raise ValueError("Teacher export contains duplicate original source filenames")

    fixture_hashes: dict[str, str] = {}
    for name, reference in truth_provenance.items():
        if reference["status"] != "teacher_reviewed":
            raise ValueError(f"Ground-truth row {name} is not teacher_reviewed")
        origins = {
            str(item.get("origin")) for item in reference["answer_provenance"]
        }
        if origins != {"teacher_confirmed"}:
            raise ValueError(
                f"Ground-truth answers for {name} are not all teacher_confirmed: {origins}"
            )
        source_path = fixtures / name
        source_bytes = source_path.read_bytes()
        actual_hash = _sha256(source_bytes)
        if actual_hash != reference["sha256"]:
            raise ValueError(
                f"Fixture hash mismatch for {name}: expected {reference['sha256']}, got {actual_hash}"
            )
        fixture_hashes[name] = actual_hash

    output.mkdir(parents=True, exist_ok=True)
    photos: list[dict[str, Any]] = []
    reference_info: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="exam-grader-vol8-production-uat-") as temp_root:
        app_data_dir = Path(temp_root) / "app-data"
        template_def, reference_info = _reference_png(fixtures, export_data, app_data_dir)
        result_by_name = {item["source"]["original_name"]: item for item in source_results}

        for name in sorted(result_by_name):
            confirmed = result_by_name[name]
            source_path = fixtures / name
            data = source_path.read_bytes()
            image = decode(data)
            photo: dict[str, Any] = {
                "source": name,
                "source_sha256": fixture_hashes[name],
                "source_dimensions_px": [int(image.shape[1]), int(image.shape[0])],
                "truth_provenance": {
                    "status": confirmed.get("status"),
                    "review_record_type": confirmed.get("review_record_type"),
                    "decision_origin": confirmed.get("decision_origin"),
                    "identity_origin": confirmed.get("identity_origin"),
                    "all_active_answers_teacher_confirmed": True,
                },
            }
            try:
                prediction = analyze(
                    data,
                    template_def=template_def,
                    app_data_dir=app_data_dir,
                    decoded_image=image,
                )
            except Exception as error:  # Keep registration failures distinct from OMR uncertainty.
                photo.update(
                    {
                        "error": {
                            "type": type(error).__name__,
                            "message": str(error),
                            "diagnostics": getattr(error, "diagnostics", None),
                        },
                        "student_number": _identity_evidence(
                            confirmed.get("student_number"),
                            {
                                "candidate": None,
                                "candidates": [],
                                "requires_review": True,
                                "review_reason": "registration failed; teacher confirmation required",
                            },
                        ),
                        "registration": {
                            **_registration_evidence({}, confirmed.get("detection")),
                            "manual_intervention_required": True,
                            "manual_intervention_reasons": ["registration_failed"],
                            "error_diagnostics": getattr(error, "diagnostics", None),
                        },
                        "question_count": ACTIVE_QUESTION_COUNT,
                        "questions": [
                            _not_run_question(
                                question,
                                confirmed.get("answers", [])[question - 1]
                                if question <= len(confirmed.get("answers", []))
                                else None,
                            )
                            for question in range(1, ACTIVE_QUESTION_COUNT + 1)
                        ],
                    }
                )
                photo["question_outcomes"] = _classify_counts(photo["questions"])
            else:
                identity_error = None
                try:
                    identity = observe_student_number(
                        data,
                        prediction.get("registration", {}).get("matrix"),
                        template_def=template_def,
                        app_data_dir=app_data_dir,
                        image=image,
                    )
                except Exception as error:
                    identity_error = {"type": type(error).__name__, "message": str(error)}
                    identity = {
                        "candidate": None,
                        "candidates": [],
                        "requires_review": True,
                        "review_reason": "identity observation failed; teacher confirmation required",
                        "pipeline_version": IDENTITY_PIPELINE_VERSION,
                    }
                answers = {
                    int(answer["question"]): answer
                    for answer in prediction.get("answers", [])
                }
                questions = [
                    _compare_question(
                        question,
                        confirmed.get("answers", [])[question - 1]
                        if question <= len(confirmed.get("answers", []))
                        else None,
                        answers.get(question),
                    )
                    for question in range(1, ACTIVE_QUESTION_COUNT + 1)
                ]
                photo.update(
                    {
                        "pipeline_version": prediction.get("pipeline_version", OMR_PIPELINE_VERSION),
                        "student_number": _identity_evidence(
                            confirmed.get("student_number"), identity
                        ),
                        "identity_error": identity_error,
                        "registration": _registration_evidence(
                            prediction, confirmed.get("detection")
                        ),
                        "question_count": ACTIVE_QUESTION_COUNT,
                        "question_outcomes": _classify_counts(questions),
                        "questions": questions,
                        "machine_classification_counts": dict(
                            Counter(q["predicted_state"] for q in questions)
                        ),
                        "machine_auto_resolved_count": sum(
                            bool(q.get("auto_resolved")) for q in questions
                        ),
                        "machine_uncertain_count": sum(
                            q["predicted_state"] == "uncertain" for q in questions
                        ),
                        "unsafe_confident_mismatch_count": sum(
                            bool(q.get("unsafe_confident_mismatch")) for q in questions
                        ),
                        "stage_timings": prediction.get("stage_timings", {}),
                        "identity_observation": identity,
                    }
                )
            photos.append(photo)

    if any(
        _sha256((fixtures / name).read_bytes()) != digest
        for name, digest in fixture_hashes.items()
    ):
        raise RuntimeError("A source fixture changed during the read-only UAT run")

    summary = _summarize(photos, len(source_results))
    report = {
        "schema": "exam-grader.vol8-production-uat.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": OMR_PIPELINE_VERSION,
        "identity_pipeline_version": IDENTITY_PIPELINE_VERSION,
        "fixture_directory": str(fixtures),
        "teacher_truth_path": str(truth_path),
        "teacher_truth_sha256": _sha256(truth_bytes),
        "teacher_truth_schema_version": export_data["schema_version"],
        "teacher_truth_rows": len(source_results),
        "source_hashes_verified": len(fixture_hashes),
        "template_reference": reference_info,
        "active_question_count": ACTIVE_QUESTION_COUNT,
        "metrics": {
            "single_choice_exact": "For teacher-confirmed single-letter rows, predicted single_mark choice must equal the confirmed letter.",
            "multiple_state": "The confirmed export stores 'multiple' without the marked-choice subset; only multiple/non-multiple state is compared for those rows.",
            "unsafe_confident_mismatch": "A machine-declared auto_resolved answer whose observable state or known single choice disagrees with teacher-confirmed truth.",
            "manual_intervention_required": "Broad review routing from registration confidence or coverage; reported separately from manual corner adjustment.",
            "manual_corner_adjustment_required": "No physical paper corners, physical-boundary confidence below 0.82, or answer-table coverage below 0.985.",
            "identity": "Candidate exactness is evaluated against teacher-confirmed student_number; every identity output remains review-required per pipeline contract.",
        },
        "summary": summary,
        "photos": photos,
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures", type=Path, default=root / "tests/fixtures/real/vol.8"
    )
    parser.add_argument(
        "--truth",
        type=Path,
        default=root / "tests/fixtures/real/vol.8" / DEFAULT_EXPORT,
    )
    parser.add_argument(
        "--output", type=Path, default=Path("/private/tmp/vol8-production-uat")
    )
    args = parser.parse_args()
    report = run(args.fixtures.resolve(), args.truth.resolve(), args.output.resolve())
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report: {args.output.resolve() / 'report.json'}")
    return int(bool(report["summary"]["photo_count_failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
