"""Build a teacher-confirmed, provenance-first identity benchmark manifest.

Usage accepts repeated ``--export corpus=/path/to/results.json`` and
``--source-root corpus=/path/to/source/files`` pairs. The source images are
never copied. Saved registration matrices are included so this benchmark can
measure the identity pipeline without reopening the unrelated geometry task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_mapping(value: str) -> tuple[str, Path]:
    corpus_id, separator, path = value.partition("=")
    if not separator or not corpus_id or not path:
        raise ValueError(f"expected corpus=path, got {value!r}")
    return corpus_id, Path(path).expanduser().resolve()


def build(exports: list[str], source_roots: list[str]) -> dict[str, Any]:
    export_map = dict(parse_mapping(item) for item in exports)
    root_map = dict(parse_mapping(item) for item in source_roots)
    if set(export_map) != set(root_map):
        raise ValueError("--export and --source-root corpus ids must match exactly")
    corpora: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    seen_hashes: dict[str, str] = {}
    for corpus_id in sorted(export_map):
        export_path = export_map[corpus_id]
        source_root = root_map[corpus_id]
        data = json.loads(export_path.read_text(encoding="utf-8"))
        template = data.get("export", {}).get("template")
        if not isinstance(template, dict):
            raise ValueError(f"{export_path}: missing persisted export.template")
        rows = data.get("results")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{export_path}: no result rows")
        corpora[corpus_id] = {
            "export_path": str(export_path),
            "export_sha256": sha256_file(export_path),
            "source_root_at_extraction": str(source_root),
            "split": "held_out",
            "template": template,
            "label_policy": "teacher_confirmed_identity_only",
        }
        for row in rows:
            source = row.get("source", {})
            name = source.get("original_name")
            truth = row.get("student_number")
            if not isinstance(name, str) or not name:
                raise ValueError(f"{export_path}: result has no source.original_name")
            if row.get("identity_origin") != "teacher_confirmed" or not row.get(
                "identity_confirmed"
            ):
                raise ValueError(f"{export_path}: {name} is not teacher-confirmed identity")
            if not isinstance(truth, str) or not truth.isascii() or not truth.isdigit():
                raise ValueError(f"{export_path}: {name} has invalid identity label")
            source_path = source_root / name
            actual_hash = sha256_file(source_path)
            expected_hash = source.get("sha256")
            if actual_hash != expected_hash:
                raise ValueError(
                    f"{source_path}: source hash mismatch; expected {expected_hash}, got {actual_hash}"
                )
            prior = seen_hashes.get(actual_hash)
            current = f"{corpus_id}/{name}"
            if prior is not None and prior != current:
                raise ValueError(f"duplicate source bytes across records: {prior} and {current}")
            seen_hashes[actual_hash] = current
            registration = row.get("detection", {}).get("registration", {})
            matrix = registration.get("matrix")
            if not isinstance(matrix, list):
                raise ValueError(f"{export_path}: {name} has no saved registration matrix")
            records.append(
                {
                    "record_id": current,
                    "corpus_id": corpus_id,
                    "source_path": name,
                    "source_sha256": actual_hash,
                    "source_group": current,
                    "writer_group": None,
                    "split": "held_out",
                    "label": truth,
                    "label_origin": "teacher_confirmed",
                    "label_status": "independent_teacher_reviewed_export",
                    "registration_matrix": matrix,
                    "template_id": template.get("template_id"),
                    "stored_identity_observation_version": row.get("detection", {})
                    .get("student_number_observation", {})
                    .get("pipeline_version"),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "student_number_teacher_confirmed_benchmark_corpus",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "split_policy": {
            "group_unit": "one immutable source sheet per record",
            "all_records_split": "held_out",
            "writer_identity_known": False,
            "training_allowed": False,
            "reason": "22 sheets are evaluation evidence, not training data",
        },
        "corpora": corpora,
        "records": sorted(records, key=lambda item: item["record_id"]),
        "limitations": [
            "Teacher-confirmed number labels are independent of the machine candidate, but writer identity is unknown.",
            "Saved transforms are used to isolate identity evaluation from the current geometry blocker.",
            "This corpus is too small to establish new-writer generalization or production accuracy.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="append", required=True, help="corpus=results.json")
    parser.add_argument("--source-root", action="append", required=True, help="corpus=directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args.export, args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "manifest": str(args.output.resolve()),
                "records": len(manifest["records"]),
                "splits": {"held_out": len(manifest["records"])},
                "training_allowed": manifest["split_policy"]["training_allowed"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
