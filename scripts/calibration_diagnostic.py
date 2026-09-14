"""Write inspectable calibration overlays and metrics for a fixture directory."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import cv2

from exam_grader.imaging import analyze
from exam_grader.template_discovery import discover_template


def overlay(image, template):
    canvas = image.copy()
    for block in template.answer_blocks:
        for x in block.col_boundaries:
            cv2.line(canvas, (x, block.row_boundaries[0]), (x, block.row_boundaries[-1]), (0, 220, 170), 2)
        for y in block.row_boundaries:
            cv2.line(canvas, (block.col_boundaries[0], y), (block.col_boundaries[-1], y), (0, 220, 170), 2)
        cv2.rectangle(canvas, (block.col_boundaries[0], block.row_boundaries[0]),
                      (block.col_boundaries[-1], block.row_boundaries[-1]), (255, 190, 0), 3)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("fixture_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = discover_template(args.reference.read_bytes())
    template = result.template_def
    cv2.imwrite(str(args.output / "vol7_reference_grid_overlay.png"), overlay(result.warped_image, template))
    metrics = {
        "reference": str(args.reference),
        "blocks": len(template.answer_blocks),
        "rows": [block.rows for block in template.answer_blocks],
        "choices": template.choice_count,
        "question_count": template.question_count,
        "confidence": result.confidence,
        "overall_confidence": result.overall_confidence,
        "warnings": result.warnings,
        "images": [],
    }
    for path in sorted(args.fixture_root.rglob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png"} or path.resolve() == args.reference.resolve():
            continue
        entry = {"file": str(path), "classifications": {}, "status": "error"}
        try:
            analysis = analyze(path.read_bytes(), template_def=template, reference_override=result.warped_image)
            entry["status"] = "ok"
            entry["registration"] = analysis["registration"]
            entry["classifications"] = dict(Counter(item["classification"] for item in analysis["answers"]))
            entry["answer_count"] = len(analysis["answers"])
        except Exception as error:
            entry["error"] = type(error).__name__ + ": " + str(error)
        metrics["images"].append(entry)
    (args.output / "vol7_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
