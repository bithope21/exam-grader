"""Evaluate current student-number candidates against independent labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from exam_grader.identity import IDENTITY_PIPELINE_VERSION, observe
from exam_grader.imaging import decode
from exam_grader.template_manager import TemplateDefinition


def _bootstrap_ci(
    values: list[bool], *, seed: int = 1729, iterations: int = 2000
) -> list[float] | None:
    """Return a deterministic percentile bootstrap interval for Bernoulli data."""
    if not values:
        return None
    state = seed & 0xFFFFFFFF
    estimates: list[float] = []
    for _ in range(iterations):
        sample_sum = 0
        for _value in values:
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            sample_sum += int(values[state % len(values)])
        estimates.append(sample_sum / len(values))
    estimates.sort()
    low = estimates[round((len(estimates) - 1) * 0.025)]
    high = estimates[round((len(estimates) - 1) * 0.975)]
    return [round(low, 6), round(high, 6)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("kind") != "student_number_teacher_confirmed_benchmark_corpus":
        raise ValueError("unsupported identity corpus manifest kind")
    records = manifest.get("records")
    corpora = manifest.get("corpora")
    if not isinstance(records, list) or not isinstance(corpora, dict) or not records:
        raise ValueError("identity corpus manifest has no records/corpora")
    seen_ids: set[str] = set()
    seen_hashes: dict[str, str] = {}
    for record in records:
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or record_id in seen_ids:
            raise ValueError(f"duplicate or invalid record id: {record_id!r}")
        seen_ids.add(record_id)
        if record.get("split") != "held_out":
            raise ValueError("benchmark manifest may only evaluate held_out records")
        source_hash = record.get("source_sha256")
        if not isinstance(source_hash, str) or source_hash in seen_hashes:
            raise ValueError(f"duplicate or invalid source hash in {record_id}")
        seen_hashes[source_hash] = record_id
        truth = record.get("label")
        if not isinstance(truth, str) or not truth.isascii() or not truth.isdigit():
            raise ValueError(f"invalid whole-number label in {record_id}")
        if record.get("corpus_id") not in corpora:
            raise ValueError(f"unknown corpus in {record_id}")


def evaluate(
    manifest: dict[str, Any],
    digit_model_path: Path | None = None,
    *,
    use_bundled_digit_model: bool = True,
    review_only: bool = False,
) -> dict[str, Any]:
    _validate_manifest(manifest)
    records = []
    for record in manifest["records"]:
        corpus = manifest["corpora"][record["corpus_id"]]
        source = Path(corpus["source_root_at_extraction"]) / record["source_path"]
        if _sha256(source) != record["source_sha256"]:
            raise ValueError(f"source hash mismatch: {source}")
        template = TemplateDefinition.from_dict(corpus["template"])
        data = source.read_bytes()
        image = decode(data)
        started = time.perf_counter()
        observation = observe(
            data,
            record["registration_matrix"],
            template_def=template,
            image=image,
            digit_model_path=digit_model_path,
            use_bundled_digit_model=use_bundled_digit_model,
        )
        seconds = time.perf_counter() - started
        candidate = observation.get("candidate")
        candidates = observation.get("candidates") or []
        suggestions = [
            item.get("candidate")
            for item in observation.get("review_suggestions") or []
            if isinstance(item, dict)
        ]
        requires_review = True if review_only else bool(observation.get("requires_review", True))
        records.append(
            {
                "record_id": record["record_id"],
                "corpus_id": record["corpus_id"],
                "truth": record["label"],
                "candidate": candidate,
                "candidates": candidates,
                "review_suggestions": suggestions,
                "primary_exact": candidate == record["label"],
                "candidate_visible": record["label"] in candidates
                or record["label"] in suggestions,
                "requires_review": requires_review,
                "auto_accept": not requires_review,
                "wrong_auto_accept": not requires_review and candidate != record["label"],
                "confidence": observation.get("confidence"),
                "confidence_margin": observation.get("confidence_margin"),
                "seconds": round(seconds, 6),
                "pipeline_version": observation.get("pipeline_version"),
            }
        )
    primary_values = [bool(item["primary_exact"]) for item in records]
    visible_values = [bool(item["candidate_visible"]) for item in records]
    by_corpus = {
        corpus_id: _summary([item for item in records if item["corpus_id"] == corpus_id])
        for corpus_id in sorted({item["corpus_id"] for item in records})
    }
    return {
        "schema_version": 1,
        "kind": "student_number_labeled_benchmark",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": IDENTITY_PIPELINE_VERSION,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "metric_definitions": {
            "primary_exact": "top candidate exactly equals the independent teacher-confirmed whole number",
            "candidate_visible": "truth appears in primary candidate, OCR candidates, or review-only suggestions",
            "auto_accept": "observation.requires_review is false; current identity contract expects zero",
            "wrong_auto_accept": "auto-accepted candidate differs from independent teacher label",
            "confidence": "uncalibrated backend score; not a probability",
        },
        "summary": {
            **_summary(records),
            "primary_exact_bootstrap_95_ci": _bootstrap_ci(primary_values),
            "candidate_visible_bootstrap_95_ci": _bootstrap_ci(visible_values),
        },
        "by_corpus": by_corpus,
        "records": records,
        "manifest": manifest,
        "limitations": [
            "All records are held-out evaluation evidence; none is training data.",
            "Writer identity is unknown, so writer-disjoint generalization is not established.",
            "Auto-accept remains disabled; no threshold promotion is performed by this tool.",
            "review_only forces every evaluated record through review so recognizer quality is measured independently of calibration.",
        ],
    }


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    exact = sum(bool(item["primary_exact"]) for item in records)
    visible = sum(bool(item["candidate_visible"]) for item in records)
    accepted = sum(bool(item["auto_accept"]) for item in records)
    return {
        "records": total,
        "primary_exact": exact,
        "primary_exact_rate": round(exact / total, 6) if total else None,
        "candidate_visible": visible,
        "candidate_visible_rate": round(visible / total, 6) if total else None,
        "review_required": sum(bool(item["requires_review"]) for item in records),
        "auto_accept": accepted,
        "auto_accept_coverage": round(accepted / total, 6) if total else None,
        "wrong_auto_accept": sum(bool(item["wrong_auto_accept"]) for item in records),
        "mean_seconds": round(
            sum(float(item["seconds"]) for item in records) / total, 6
        )
        if total
        else None,
        "pipeline_versions": dict(Counter(item["pipeline_version"] for item in records)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--digit-model", type=Path)
    parser.add_argument(
        "--no-digit-model",
        action="store_true",
        help="benchmark the legacy OCR path without the bundled digit model",
    )
    parser.add_argument(
        "--review-only",
        action="store_true",
        help="force every record to remain review-required during recognizer bake-off",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = evaluate(
        manifest,
        args.digit_model,
        use_bundled_digit_model=not args.no_digit_model,
        review_only=args.review_only,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
