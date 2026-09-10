"""Engineering-only student-number recognizer benchmark.

The real fixture set has no independent number labels, so this reports candidates
and review coverage without fabricating accuracy.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from exam_grader.identity import observe
from exam_grader.imaging import analyze


def evaluate(root: Path) -> dict:
    records = []
    for path in sorted(root.iterdir()):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        started = time.perf_counter()
        try:
            detection = analyze(path.read_bytes())
            result = observe(path.read_bytes(), detection["registration"].get("matrix"))
            status = "candidate" if result.get("candidate") else "unavailable"
        except (OSError, ValueError) as error:
            result = {"candidate": None, "confidence": None, "review_reason": str(error)}
            status = "failed"
        records.append({"filename": path.name, "status": status, "observation": result,
                        "seconds": round(time.perf_counter() - started, 4)})
    return {
        "schema_version": 1,
        "kind": "student_number_engineering_benchmark",
        "evaluated": len(records),
        "accuracy": None,
        "accuracy_note": "No independent handwritten-number labels are available.",
        "auto_accept_count": 0,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.fixtures.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evaluated": report["evaluated"], "auto_accept_count": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
