"""Benchmark sequence OCR models on the verified Student Number ROI only.

The benchmark intentionally keeps the existing registration and ROI path. It
uses the existing conservative preprocessing to remove the printed form and
passes one cleaned sequence crop to PaddleOCR TextRecognition. Vol.8--11 must
remain held out; this tool never writes data into the repository.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from exam_grader.identity import number_roi, preprocess
from exam_grader.template_manager import TemplateDefinition

DEFAULT_MODELS = [
    "PP-OCRv6_small_rec",
    "PP-OCRv6_medium_rec",
    "PP-OCRv5_server_rec",
]
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("kind") != "student_number_teacher_confirmed_benchmark_corpus":
        raise ValueError("unsupported identity corpus manifest kind")
    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("benchmark manifest has no records")
    if manifest.get("split_policy", {}).get("training_allowed") is not False:
        raise ValueError("benchmark manifest must prohibit training")
    for record in records:
        if record.get("split") != "held_out":
            raise ValueError("benchmark may only evaluate held_out records")
        truth = record.get("label")
        if not isinstance(truth, str) or not truth.isascii() or not truth.isdigit():
            raise ValueError(f"invalid truth label: {truth!r}")


def _normalize_digits(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.translate(THAI_DIGITS).strip()
    if not re.fullmatch(r"[0-9]+", normalized):
        return None
    return normalized


def _clean_sequence_crop(crop: np.ndarray) -> tuple[np.ndarray, list[list[int]]]:
    """Return a tight, form-cleaned sequence crop and diagnostic boxes."""
    processed, boxes, _gray = preprocess(crop)
    ink_y, ink_x = np.where(processed == 0)
    if len(ink_x) == 0:
        return cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR), boxes

    pad = max(8, round(crop.shape[0] * 0.05))
    x1 = max(0, int(ink_x.min()) - pad)
    y1 = max(0, int(ink_y.min()) - pad)
    x2 = min(processed.shape[1], int(ink_x.max()) + pad + 1)
    y2 = min(processed.shape[0], int(ink_y.max()) + pad + 1)
    tight = processed[y1:y2, x1:x2]
    return cv2.cvtColor(tight, cv2.COLOR_GRAY2BGR), boxes


def _directory_size(path: Path) -> int | None:
    if not path.is_dir():
        return None
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    exact = sum(item["candidate"] == item["truth"] for item in records)
    visible = sum(item["candidate_visible"] for item in records)
    review = sum(item["review_required"] for item in records)
    auto = sum(item["auto_accept"] for item in records)
    wrong_auto = sum(item["wrong_auto_accept"] for item in records)
    wrong = sum(item["candidate"] is not None and item["candidate"] != item["truth"] for item in records)
    return {
        "records": total,
        "exact": exact,
        "exact_rate": round(exact / total, 6) if total else None,
        "wrong": wrong,
        "candidate_visible": visible,
        "candidate_visible_rate": round(visible / total, 6) if total else None,
        "review_required": review,
        "auto_accept": auto,
        "auto_accept_coverage": round(auto / total, 6) if total else None,
        "wrong_auto_accept": wrong_auto,
        "mean_inference_seconds": round(
            sum(item["inference_seconds"] for item in records) / total, 6
        )
        if total
        else None,
    }


def _benchmark_model(
    manifest: dict[str, Any],
    model_name: str,
    *,
    review_threshold: float,
) -> dict[str, Any]:
    from paddleocr import TextRecognition

    started = time.perf_counter()
    model = TextRecognition(model_name=model_name, device="cpu")
    cold_start_seconds = time.perf_counter() - started
    records: list[dict[str, Any]] = []
    for record in manifest["records"]:
        corpus = manifest["corpora"][record["corpus_id"]]
        source = Path(corpus["source_root_at_extraction"]) / record["source_path"]
        template_def = TemplateDefinition.from_dict(corpus["template"])
        data = source.read_bytes()
        crop = number_roi(data, record["registration_matrix"], template_def=template_def)
        clean, boxes = _clean_sequence_crop(crop)
        inference_started = time.perf_counter()
        try:
            result = model.predict(clean)[0]
            raw_text = result.get("rec_text")
            score = result.get("rec_score")
            score = float(score) if isinstance(score, (int, float)) else None
            if score is not None and not math.isfinite(score):
                score = None
            error = None
        except Exception as exc:  # pragma: no cover - records runtime failures
            raw_text = None
            score = None
            error = f"{type(exc).__name__}: {exc}"
        inference_seconds = time.perf_counter() - inference_started
        candidate = _normalize_digits(raw_text)
        auto_accept = candidate is not None and score is not None and score >= review_threshold
        records.append(
            {
                "record_id": record["record_id"],
                "corpus_id": record["corpus_id"],
                "truth": record["label"],
                "raw_text": raw_text,
                "candidate": candidate,
                "score": round(score, 8) if score is not None else None,
                "candidate_visible": candidate == record["label"],
                "review_required": not auto_accept,
                "auto_accept": auto_accept,
                "wrong_auto_accept": auto_accept and candidate != record["label"],
                "inference_seconds": round(inference_seconds, 6),
                "crop_shape": list(clean.shape),
                "segmented_boxes": boxes,
                "error": error,
            }
        )
    close = getattr(model, "close", None)
    if callable(close):
        close()

    by_corpus = {
        corpus_id: _summary(
            [item for item in records if item["corpus_id"] == corpus_id]
        )
        for corpus_id in sorted({item["corpus_id"] for item in records})
    }
    model_dir = Path.home() / ".paddlex" / "official_models" / model_name
    return {
        "model_name": model_name,
        "model_dir": str(model_dir),
        "model_size_bytes": _directory_size(model_dir),
        "device": "cpu",
        "input": "registered Student Number ROI -> existing preprocess -> tight cleaned sequence crop",
        "review_threshold": review_threshold,
        "top_k_available": False,
        "cold_start_seconds": round(cold_start_seconds, 6),
        "summary": _summary(records),
        "by_corpus": by_corpus,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--review-threshold", type=float, default=0.90)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    _validate_manifest(manifest)
    models = args.models or DEFAULT_MODELS
    report = {
        "schema_version": 1,
        "kind": "student_number_sequence_ocr_benchmark",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "held_out_policy": manifest["split_policy"],
        "models": [
            _benchmark_model(manifest, model_name, review_threshold=args.review_threshold)
            for model_name in models
        ],
        "limitations": [
            "PaddleOCR TextRecognition exposes top-1 text and score here; top-k was not available through this API.",
            "The fixed review threshold is a screening gate, not production calibration.",
            "Writer identity is unknown; Vol.8--11 remain held out and are not training data.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for item in report["models"]:
        print(json.dumps({"model": item["model_name"], **item["summary"]}, ensure_ascii=False))
    print(f"report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
