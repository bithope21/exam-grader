"""Extract a provenance-first seed corpus from the supplied handwriting PDF.

The first page is a known 00-99 copying grid. It is exported as labeled
sequence crops, not as silently trusted digit boxes. Remaining pages are
rendered into a review queue only; their arithmetic answers, corrections and
blank fields are not auto-labeled.

The output is intentionally an external artifact. The source PDF can contain
personal data and should not be copied into the repository by this tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

EXTRACTOR_VERSION = "number-handwriting-sequence-seed-v1"
RENDER_DPI = 120

# Normalized coordinates measured against the A4 page-1 layout. Recording
# normalized geometry keeps the manifest reproducible if render DPI changes.
PAGE_ONE_GRID = (0.0847, 0.1690, 0.9254, 0.9166)
CELL_INK_CROP = (0.08, 0.30, 0.93, 0.92)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_files(render_dir: Path) -> list[Path]:
    return sorted(render_dir.glob("page-*.png"))


def _pixel_box(
    normalized: tuple[float, float, float, float], width: int, height: int
) -> list[int]:
    x1, y1, x2, y2 = normalized
    return [round(x1 * width), round(y1 * height), round(x2 * width), round(y2 * height)]


def grid_cell_boxes(
    width: int, height: int, grid: tuple[float, float, float, float] = PAGE_ONE_GRID
) -> list[dict[str, Any]]:
    """Return row-major page and ink boxes for the 100-cell seed grid."""
    gx1, gy1, gx2, gy2 = _pixel_box(grid, width, height)
    cell_width = (gx2 - gx1) / 10.0
    cell_height = (gy2 - gy1) / 10.0
    boxes: list[dict[str, Any]] = []
    for row in range(10):
        for column in range(10):
            x1 = round(gx1 + column * cell_width)
            y1 = round(gy1 + row * cell_height)
            x2 = round(gx1 + (column + 1) * cell_width)
            y2 = round(gy1 + (row + 1) * cell_height)
            ix1 = x1 + round((x2 - x1) * CELL_INK_CROP[0])
            iy1 = y1 + round((y2 - y1) * CELL_INK_CROP[1])
            ix2 = x1 + round((x2 - x1) * CELL_INK_CROP[2])
            iy2 = y1 + round((y2 - y1) * CELL_INK_CROP[3])
            boxes.append(
                {
                    "row": row,
                    "column": column,
                    "cell_index": row * 10 + column,
                    "label": f"{row * 10 + column:02d}",
                    "bbox_page_px": [x1, y1, x2, y2],
                    "bbox_ink_px": [ix1, iy1, ix2, iy2],
                }
            )
    return boxes


def _crop(image: Any, box: list[int]) -> Any:
    x1, y1, x2, y2 = box
    crop = image[max(0, y1) : min(image.shape[0], y2), max(0, x1) : min(image.shape[1], x2)]
    if crop.size == 0:
        raise ValueError(f"empty crop for box {box}")
    return crop


def _render_pdf(pdf: Path, render_dir: Path) -> list[Path]:
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise RuntimeError("pdftoppm is required to render the PDF")
    render_dir.mkdir(parents=True, exist_ok=True)
    if page_files(render_dir):
        raise FileExistsError(f"render directory is not empty: {render_dir}")
    prefix = render_dir / "page"
    subprocess.run(
        [renderer, "-png", "-r", str(RENDER_DPI), str(pdf), str(prefix)],
        check=True,
        capture_output=True,
        text=True,
    )
    pages = page_files(render_dir)
    if len(pages) != 11:
        raise ValueError(f"expected 11 rendered pages, found {len(pages)}")
    return pages


def extract(pdf: Path, output: Path) -> dict[str, Any]:
    pdf = pdf.resolve()
    output = output.resolve()
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    if (output / "manifest.json").exists():
        raise FileExistsError(f"manifest already exists: {output / 'manifest.json'}")
    output.mkdir(parents=True, exist_ok=True)
    render_dir = output / "rendered_pages"
    sample_dir = output / "samples" / "page-01-grid"
    pages = _render_pdf(pdf, render_dir)

    first = cv2.imread(str(pages[0]), cv2.IMREAD_COLOR)
    if first is None:
        raise ValueError(f"cannot decode rendered page: {pages[0]}")
    height, width = first.shape[:2]
    samples: list[dict[str, Any]] = []
    sample_dir.mkdir(parents=True, exist_ok=True)
    for box in grid_cell_boxes(width, height):
        crop = _crop(first, box["bbox_ink_px"])
        target = sample_dir / f"cell-{box['cell_index']:02d}-{box['label']}.png"
        if not cv2.imwrite(str(target), crop):
            raise OSError(f"could not write {target}")
        samples.append(
            {
                "sample_id": f"pdf-page-01-cell-{box['cell_index']:02d}",
                "source_page": 1,
                "source_group": "pdf-page-01",
                "split": "seed_only",
                "sample_kind": "known_sequence_crop",
                "label": box["label"],
                "label_origin": "page_01_grid_index",
                "label_status": "layout_labeled_visual_qc_required",
                "bbox_page_px": box["bbox_page_px"],
                "bbox_ink_px": box["bbox_ink_px"],
                "crop_path": str(target.relative_to(output)),
                "digit_boxes": None,
                "notes": (
                    "Known sequence label from the 00-99 grid. Do not split into "
                    "digit labels without visual annotation; this page is one writer/sheet."
                ),
            }
        )

    review_pages = [
        {
            "page": index,
            "source_group": f"pdf-page-{index:02d}",
            "split": "unassigned_review_queue",
            "sample_kind": "exercise_page_review_only",
            "label_status": "unlabeled_review_required",
            "page_path": str(path.relative_to(output)),
            "notes": (
                "Do not auto-label arithmetic answers, corrections, crossed-out marks, "
                "blank fields or student identity from this page."
            ),
        }
        for index, path in enumerate(pages[1:], start=2)
    ]
    manifest = {
        "schema_version": 1,
        "kind": "student_number_handwriting_seed_corpus",
        "extractor_version": EXTRACTOR_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_pdf": {
            "path_at_extraction": str(pdf),
            "sha256": sha256_file(pdf),
            "pages": len(pages),
            "render_dpi": RENDER_DPI,
        },
        "privacy": {
            "contains_potential_personal_data": True,
            "raw_source_copied_to_repo": False,
            "safe_default": "keep output local/private; review before sharing or committing",
        },
        "split_policy": {
            "group_unit": "source sheet and writer when known",
            "seed_page_group": "pdf-page-01",
            "seed_page_split": "seed_only",
            "training_ready": False,
            "reason": "one PDF page is not enough for leakage-free train/validation/test splits",
        },
        "labeled_samples": samples,
        "review_queue": review_pages,
        "limitations": [
            "Page 1 labels are sequence-level seed labels, not digit bounding-box labels.",
            "Exercise pages require independent visual transcription before any training use.",
            "No writer identity or independent held-out writer set is inferred from the PDF.",
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = extract(args.pdf, args.output)
    print(
        json.dumps(
            {
                "manifest": str(args.output.resolve() / "manifest.json"),
                "source_sha256": manifest["source_pdf"]["sha256"],
                "labeled_sequence_samples": len(manifest["labeled_samples"]),
                "review_queue_pages": len(manifest["review_queue"]),
                "training_ready": manifest["split_policy"]["training_ready"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
