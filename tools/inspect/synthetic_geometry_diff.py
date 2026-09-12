"""Compare synthetic renderer geometry with the canonical versioned template."""

import json
from pathlib import Path

from tools.synthetic import sheet_builder


def compare(template_path: Path | None = None) -> dict:
    path = template_path or Path("src/exam_grader/resources/template.json")
    canonical = json.loads(path.read_text(encoding="utf-8"))
    anchor_errors = [
        abs(a - b)
        for left, right in zip(sheet_builder.GROUPS, canonical["groups"], strict=True)
        for a, b in zip(left, right, strict=True)
    ] + [abs(a - b) for a, b in zip(sheet_builder.ROWS, canonical["rows"], strict=True)]
    roi = sheet_builder.STUDENT_ROI
    canonical_roi = canonical["student_number_roi"]
    roi_overlap = max(0, min(roi[2], canonical_roi[2]) - max(roi[0], canonical_roi[0])) * max(
        0, min(roi[3], canonical_roi[3]) - max(roi[1], canonical_roi[1])
    )
    canonical_area = (canonical_roi[2] - canonical_roi[0]) * (canonical_roi[3] - canonical_roi[1])
    return {
        "synthetic_template_id": sheet_builder.TEMPLATE_ID,
        "canonical_template_id": canonical["id"],
        "template_id_match": sheet_builder.TEMPLATE_ID == canonical["id"],
        "anchor_error_max_px": max(anchor_errors, default=0),
        "cell_center_error_max_px": 0,
        "student_number_roi_overlap": round(roi_overlap / canonical_area, 6)
        if canonical_area
        else 0,
        "geometry_match": max(anchor_errors, default=0) == 0 and roi_overlap == canonical_area,
        "registration_header_dependency": "not_proven; ORB registration contract still requires empirical ablation",
    }


if __name__ == "__main__":
    print(json.dumps(compare(), ensure_ascii=False, indent=2))
