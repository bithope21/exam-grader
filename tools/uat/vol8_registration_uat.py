"""Replay Vol.8 registration and emit per-photo alignment evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from exam_grader.app import initialize
from exam_grader.domain import ExamDetails
from exam_grader.exporting import export_results
from exam_grader.imaging import OMR_PIPELINE_VERSION, analyze, decode
from exam_grader.imports import ImportService
from exam_grader.review_service import ReviewService
from exam_grader.template_manager import default_1_template_definition
from exam_grader.workflow import Workflow


def _write_jpeg(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise OSError(f"Cannot encode {path.name}")
    path.write_bytes(encoded.tobytes())


def _grid_overlay(aligned: np.ndarray, template_def) -> np.ndarray:
    lines = aligned.copy()
    for block in template_def.answer_blocks:
        x0, x1 = block.col_boundaries[0], block.col_boundaries[-1]
        y0, y1 = block.row_boundaries[0], block.row_boundaries[-1]
        for x in block.col_boundaries:
            cv2.line(lines, (x, y0), (x, y1), (255, 0, 255), 1, cv2.LINE_AA)
        for y in block.row_boundaries:
            cv2.line(lines, (x0, y), (x1, y), (255, 0, 255), 1, cv2.LINE_AA)
    return cv2.addWeighted(aligned, 0.72, lines, 0.28, 0)


def _photo_evidence(path: Path, result: dict, output: Path) -> dict:
    registration = result["registration"]
    aligned = result["aligned"]
    _write_jpeg(output / "normalized" / f"{path.stem}.jpg", aligned)
    template_def = default_1_template_definition()
    _write_jpeg(
        output / "grid-overlays" / f"{path.stem}.jpg",
        _grid_overlay(aligned, template_def),
    )
    return {
        "source": path.name,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_dimensions": [int(result["source_width"]), int(result["source_height"])],
        "registration": {
            key: registration.get(key)
            for key in (
                "method",
                "selected_candidate",
                "candidate_count",
                "candidate_diagnostics",
                "paper_confidence",
                "paper_corners",
                "physical_paper_corners",
                "physical_boundary_confidence",
                "physical_boundary_method",
                "physical_boundary_proposal_score",
                "physical_boundary_supporting_method_count",
                "physical_boundary_grid_fit_score",
                "physical_boundary_selection_basis",
                "physical_boundary_template_frame_alignment_error",
                "selected_corners",
                "paper_boundary_candidates",
                "matrix",
                "inverse_matrix",
                "canonical_size",
                "roi_coordinate_space",
                "normalization_confidence",
                "normalization_requires_review",
                "normalization_boundary_status",
                "fine_registration",
                "grid_residual_px",
                "grid_median_residual_px",
                "grid_line_coverage",
                "grid_line_contrast",
                "alignment_confidence",
                "table_coverage",
                "review_required",
            )
            if key in registration
        },
        "stage_timings": result["stage_timings"],
        "omr_classification_counts": dict(Counter(a["classification"] for a in result["answers"])),
        "questions": [
            {
                "question": answer["question"],
                "selected": answer["selected"],
                "classification": answer["classification"],
                "decision_reason": answer["decision_reason"],
                "ink_density": answer["ink_density"],
                "core_density": answer["core_density"],
                "roi_rects": answer["roi_rects"],
            }
            for answer in result["answers"]
        ],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=root / "tests/fixtures/real/vol.8")
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "docs/evidence/vol8-registration/after",
    )
    args = parser.parse_args()
    fixtures = args.fixtures.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    template_def = default_1_template_definition()
    report = {
        "pipeline_version": OMR_PIPELINE_VERSION,
        "reference_template_id": template_def.template_id,
        "fixture_directory": str(fixtures),
        "photos": [],
        "registration_errors": [],
        "checked_preview_note": (
            "Preview exercises partial checked-image rendering with a synthetic all-A key; "
            "it is not answer-accuracy evidence."
        ),
    }

    source_hashes = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(fixtures.glob("IMG_*.jpg"))
    }
    analyses: dict[Path, dict] = {}
    for path in source_hashes:
        decoded = decode(path.read_bytes())
        try:
            result = analyze(path.read_bytes(), template_def=template_def, decoded_image=decoded)
        except Exception as error:
            report["registration_errors"].append(
                {"source": path.name, "error_type": type(error).__name__, "message": str(error)}
            )
            continue
        result["source_width"] = int(decoded.shape[1])
        result["source_height"] = int(decoded.shape[0])
        analyses[path] = result
        report["photos"].append(_photo_evidence(path, result, output))

    report["summary"] = {
        "photo_count": len(source_hashes),
        "registered_count": len(analyses),
        "failed_count": len(report["registration_errors"]),
        "selected_candidate_counts": dict(
            Counter(r["registration"].get("selected_candidate") for r in report["photos"])
        ),
        "worst_grid_residual_px": max(
            (r["registration"].get("grid_residual_px", 0) for r in report["photos"]),
            default=None,
        ),
        "worst_alignment_confidence": min(
            (r["registration"].get("alignment_confidence", 1) for r in report["photos"]),
            default=None,
        ),
    }

    # Render a real-source checked image through the same database/export path.
    # The synthetic key is explicitly limited to visual pipeline verification.
    preview_source = fixtures / "IMG_1022.jpg"
    if preview_source in analyses:
        with tempfile.TemporaryDirectory(prefix="exam-grader-vol8-uat-") as temp_dir:
            app = initialize(Path(temp_dir) / "data")
            exam = app.exams.create(
                ExamDetails("Vol.8 checked preview", "2569", "ม.4", "1", "UAT", 60)
            )
            importer = ImportService(app.exams.path)
            key_source = importer.import_file(exam.id, fixtures / "key.jpg", "key")
            source = importer.import_file(exam.id, preview_source, "student")
            flow = Workflow(app.exams.path)
            flow.approve_key(exam.id, ["A"] * 60, key_source["id"])
            analysis = analyses[preview_source]
            flow.save_detection(
                source["id"],
                {
                    key: value
                    for key, value in analysis.items()
                    if key not in {"aligned", "source_width", "source_height"}
                },
            )
            ReviewService(app.exams.path).skip_remaining(exam.id)
            exported = export_results(flow, exam.id, output / "checked-preview")
            report["checked_preview"] = str(exported.relative_to(output))

    unchanged = all(
        hashlib.sha256(path.read_bytes()).hexdigest() == digest
        for path, digest in source_hashes.items()
    )
    report["source_fixtures_unchanged"] = unchanged
    if not unchanged:
        raise RuntimeError("A Vol.8 source fixture changed during UAT")
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return int(bool(report["registration_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
