"""Benchmark the bundled-style Student Number ONNX adapter on held-out crops."""

from __future__ import annotations

import argparse
import json
import platform
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from exam_grader.identity import number_roi
from exam_grader.student_number_ocr import OnnxStudentNumberRecognizer
from exam_grader.template_manager import TemplateDefinition
from tools.benchmark.student_number_ocr_benchmark import (
    _clean_sequence_crop,
    _validate_manifest,
)


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    exact = sum(item["candidate"] == item["truth"] for item in records)
    review = sum(item["review_required"] for item in records)
    auto = sum(item["auto_accept"] for item in records)
    return {
        "records": total,
        "exact": exact,
        "exact_rate": round(exact / total, 6) if total else None,
        "wrong": sum(
            item["candidate"] is not None and item["candidate"] != item["truth"]
            for item in records
        ),
        "candidate_visible": exact,
        "review_required": review,
        "auto_accept": auto,
        "auto_accept_coverage": round(auto / total, 6) if total else None,
        "wrong_auto_accept": sum(item["wrong_auto_accept"] for item in records),
        "mean_inference_seconds": round(
            sum(item["inference_seconds"] for item in records) / total, 6
        )
        if total
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-threshold", type=float, default=0.90)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    _validate_manifest(manifest)
    started = time.perf_counter()
    recognizer = OnnxStudentNumberRecognizer(args.model, args.metadata)
    init_seconds = time.perf_counter() - started
    records: list[dict[str, Any]] = []
    for record in manifest["records"]:
        corpus = manifest["corpora"][record["corpus_id"]]
        source = Path(corpus["source_root_at_extraction"]) / record["source_path"]
        template_def = TemplateDefinition.from_dict(corpus["template"])
        crop = number_roi(source.read_bytes(), record["registration_matrix"], template_def=template_def)
        clean, boxes = _clean_sequence_crop(crop)
        inference_started = time.perf_counter()
        try:
            prediction = recognizer.predict(clean)
            error = None
        except Exception as exc:  # pragma: no cover - runtime guard
            prediction = {"candidate": None, "candidates": [], "confidence": None}
            error = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - inference_started
        confidence = prediction.get("confidence")
        auto_accept = (
            prediction.get("candidate") is not None
            and isinstance(confidence, (int, float))
            and confidence >= args.review_threshold
        )
        records.append(
            {
                "record_id": record["record_id"],
                "corpus_id": record["corpus_id"],
                "truth": record["label"],
                **prediction,
                "candidate_visible": prediction.get("candidate") == record["label"],
                "review_required": not auto_accept,
                "auto_accept": auto_accept,
                "wrong_auto_accept": auto_accept and prediction.get("candidate") != record["label"],
                "inference_seconds": round(elapsed, 6),
                "segmented_boxes": boxes,
                "error": error,
            }
        )
    by_corpus = {
        corpus_id: _summary(
            [item for item in records if item["corpus_id"] == corpus_id]
        )
        for corpus_id in sorted({item["corpus_id"] for item in records})
    }
    report = {
        "schema_version": 1,
        "kind": "student_number_onnx_benchmark",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "model": str(args.model.resolve()),
        "model_size_bytes": args.model.stat().st_size,
        "init_seconds": round(init_seconds, 6),
        "review_threshold": args.review_threshold,
        "summary": _summary(records),
        "by_corpus": by_corpus,
        "records": records,
        "pipeline_versions": dict(Counter(item.get("pipeline_version") for item in records)),
        "limitations": [
            "The fixed review threshold is a screening gate, not production calibration.",
            "Vol.8--11 are held-out and never used for training.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
