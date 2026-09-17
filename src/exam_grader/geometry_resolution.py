"""One persisted, fail-closed geometry contract for runtime and review surfaces."""

from __future__ import annotations

from typing import Any

from exam_grader.template_manager import TemplateDefinition, cell_rect_for_template

GEOMETRY_RESOLUTION_VERSION = "geometry-resolution-v1"


class GeometryResolutionError(ValueError):
    """Raised when persisted or derived answer geometry cannot be trusted."""


def _rect_intersects(first: list[int], second: list[int]) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return max(ax, bx) < min(ax + aw, bx + bw) and max(ay, by) < min(ay + ah, by + bh)


def _as_rect(value: Any) -> list[int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        rect = [int(value[0]), int(value[1]), int(value[2]), int(value[3])]
    except (TypeError, ValueError):
        return None
    return rect if rect[2] > 0 and rect[3] > 0 else None


def _question_number_strips(
    template_def: TemplateDefinition,
) -> list[tuple[int | None, list[int]]]:
    """Return explicit strips plus safe inter-block gaps in canonical pixels.

    A discovered template may explicitly retain a number strip. Older custom
    templates did not, so the gap between adjacent answer blocks is also a
    protected strip. This is conservative: a gap can only reject malformed
    geometry; it never moves a cell or changes OMR classification.
    """

    config = template_def.registration_config
    configured = config.get("question_number_strips") or config.get("number_strip_rects") or []
    strips: list[tuple[int | None, list[int]]] = []
    if isinstance(configured, dict):
        configured = list(configured.values())
    if isinstance(configured, (list, tuple)):
        for item in configured:
            rect = _as_rect(item.get("rect") if isinstance(item, dict) else item)
            if rect is not None:
                owner = item.get("block_index") if isinstance(item, dict) else None
                strips.append((int(owner) if owner is not None else None, rect))

    ordered = sorted(template_def.answer_blocks, key=lambda block: block.block_index)
    for left, right in zip(ordered, ordered[1:]):
        gap_left = left.col_boundaries[-1]
        gap_right = right.col_boundaries[0]
        top = max(left.row_boundaries[0], right.row_boundaries[0])
        bottom = min(left.row_boundaries[-1], right.row_boundaries[-1])
        if gap_right > gap_left and bottom > top:
            strips.append((right.block_index, [gap_left, top, gap_right - gap_left, bottom - top]))

    # Preserve detector provenance when it explicitly says the first interval
    # was a printed number column. A bad inferred lattice is then rejected
    # rather than silently reinterpreted as five answer columns.
    for block in template_def.answer_blocks:
        source = block.source_geometry or {}
        detected = source.get("detected_column_boundaries")
        if not source.get("with_number") or not isinstance(detected, (list, tuple)):
            continue
        if len(detected) < block.choice_count + 2:
            continue
        first, second = int(detected[0]), int(detected[1])
        if second > first:
            strips.append(
                (
                    block.block_index,
                    [
                        first,
                        block.row_boundaries[0],
                        second - first,
                        block.row_boundaries[-1] - block.row_boundaries[0],
                    ],
                )
            )
    return strips


def _registration_metadata(registration: dict[str, Any] | None) -> dict[str, Any]:
    registration = registration or {}
    physical = registration.get("physical_paper_corners", registration.get("paper_corners"))
    return {
        "transform": {
            "matrix": registration.get("matrix"),
            "inverse_matrix": registration.get("inverse_matrix"),
        },
        "physical_paper_corners": physical,
        "registration_method": registration.get("method"),
        "registration_selected_candidate": registration.get("selected_candidate"),
        "confidence": {
            "page": registration.get(
                "normalization_confidence", registration.get("alignment_confidence")
            ),
            "physical_boundary": registration.get("physical_boundary_confidence"),
            "grid": registration.get("alignment_confidence"),
        },
        "provenance": {
            "coordinate_space": registration.get("roi_coordinate_space", "canonical_px"),
            "normalization_boundary_status": registration.get("normalization_boundary_status"),
            "pipeline_registration": registration.get("method"),
        },
    }


def resolve_geometry(
    template_def: TemplateDefinition,
    registration: dict[str, Any] | None = None,
    *,
    block_offsets: dict[int, tuple[int, int]] | dict[str, list[int]] | None = None,
    source_sha256: str | None = None,
    persisted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or validate the single geometry result used by all consumers."""

    if persisted is not None:
        validate_geometry_resolution(persisted, template_def, source_sha256=source_sha256)
        return persisted

    offsets = block_offsets or {}
    strip_specs = _question_number_strips(template_def)
    answer_rois: dict[str, dict[str, list[int]]] = {}
    blocks: list[dict[str, Any]] = []
    errors: list[str] = []
    protected_strips: dict[str, list[list[int]]] = {}
    offsets_by_block: dict[int, tuple[int, int]] = {}
    for block in template_def.answer_blocks:
        raw_offset = offsets.get(block.block_index, offsets.get(str(block.block_index), [0, 0]))
        offsets_by_block[block.block_index] = (int(raw_offset[0]), int(raw_offset[1]))
    all_protected_strips: list[list[int]] = []
    for owner, strip in strip_specs:
        shift_x, shift_y = offsets_by_block.get(owner, (0, 0)) if owner is not None else (0, 0)
        all_protected_strips.append([strip[0] + shift_x, strip[1] + shift_y, strip[2], strip[3]])

    for block in template_def.answer_blocks:
        dx, dy = offsets_by_block[block.block_index]
        outer = [
            block.col_boundaries[0] + dx,
            block.row_boundaries[0] + dy,
            block.col_boundaries[-1] - block.col_boundaries[0],
            block.row_boundaries[-1] - block.row_boundaries[0],
        ]
        block_data = {
            "block_index": block.block_index,
            "question_start": block.question_start,
            "question_end": block.question_end,
            "rows": block.rows,
            "choice_count": block.choice_count,
            "outer_rect": outer,
            "col_boundaries": list(block.col_boundaries),
            "row_boundaries": list(block.row_boundaries),
            "offset": [dx, dy],
            "geometry_state": block.geometry_state,
            "confidence": block.confidence,
        }
        blocks.append(block_data)
        block_strips: list[list[int]] = []
        for owner, strip in strip_specs:
            if owner not in (None, block.block_index):
                continue
            shift_x, shift_y = (dx, dy) if owner == block.block_index else (0, 0)
            block_strips.append([strip[0] + shift_x, strip[1] + shift_y, strip[2], strip[3]])
        protected_strips[str(block.block_index)] = block_strips
        for question in range(block.question_start, block.question_end + 1):
            rois: dict[str, list[int]] = {}
            for choice in range(block.choice_count):
                x, y, width, height = cell_rect_for_template(template_def, question, choice)
                rois["ABCDE"[choice]] = [x + dx, y + dy, width, height]
            answer_rois[str(question)] = rois

            for choice, rect in rois.items():
                if (
                    rect[0] < outer[0]
                    or rect[1] < outer[1]
                    or rect[0] + rect[2] > outer[0] + outer[2]
                    or rect[1] + rect[3] > outer[1] + outer[3]
                ):
                    errors.append(f"q{question}{choice}: answer ROI leaves block")
                if any(_rect_intersects(rect, strip) for strip in all_protected_strips):
                    errors.append(f"q{question}{choice}: answer ROI overlaps question-number strip")

    block_review_required = any(item["geometry_state"] == "draft" for item in blocks)

    result = {
        "version": GEOMETRY_RESOLUTION_VERSION,
        "template_id": template_def.template_id,
        "template_version": template_def.version,
        "source_sha256": source_sha256,
        "canonical_size": [template_def.canonical_width, template_def.canonical_height],
        "coordinate_space": "canonical_px",
        "question_number_strips": all_protected_strips,
        "protected_strips_by_block": protected_strips,
        "identity_roi": list(template_def.student_number_roi) if template_def.student_number_roi else None,
        "score_roi": list(template_def.score_roi) if template_def.score_roi else None,
        "blocks": blocks,
        "answer_rois": answer_rois,
        **_registration_metadata(registration),
        "review_gates": {
            "page": bool((registration or {}).get("normalization_requires_review")),
            "block": block_review_required,
            "answer": False,
            "identity": True,
        },
        "validation": {"valid": not errors, "errors": errors},
    }
    if errors:
        raise GeometryResolutionError("เรขาคณิตคำตอบไม่ถูกต้อง: " + "; ".join(errors[:4]))
    return result


def validate_geometry_resolution(
    resolution: dict[str, Any],
    template_def: TemplateDefinition,
    *,
    source_sha256: str | None = None,
) -> None:
    """Validate persisted geometry against the currently selected template."""

    if resolution.get("version") != GEOMETRY_RESOLUTION_VERSION:
        raise GeometryResolutionError("ไม่รู้จักเวอร์ชันเรขาคณิตที่บันทึกไว้")
    if resolution.get("template_id") != template_def.template_id:
        raise GeometryResolutionError("เรขาคณิตไม่ตรงกับแม่แบบข้อสอบปัจจุบัน")
    if int(resolution.get("template_version", -1)) != template_def.version:
        raise GeometryResolutionError("เวอร์ชันเรขาคณิตไม่ตรงกับแม่แบบข้อสอบปัจจุบัน")
    if resolution.get("canonical_size") != [template_def.canonical_width, template_def.canonical_height]:
        raise GeometryResolutionError("ขนาดภาพ canonical ของเรขาคณิตไม่ตรงกับแม่แบบ")
    stored_hash = resolution.get("source_sha256")
    if source_sha256 and stored_hash and stored_hash != source_sha256:
        raise GeometryResolutionError("เรขาคณิตไม่ตรงกับภาพต้นฉบับ")
    if resolution.get("coordinate_space") != "canonical_px":
        raise GeometryResolutionError("พิกัดเรขาคณิตไม่ใช่ canonical pixels")
    if resolution.get("validation", {}).get("valid") is not True:
        raise GeometryResolutionError("เรขาคณิตที่บันทึกไว้ถูกระบุว่าไม่ปลอดภัย")

    expected = resolve_geometry(
        template_def,
        block_offsets={
            int(block["block_index"]): tuple(block.get("offset", [0, 0]))
            for block in resolution.get("blocks", [])
        },
    )
    if resolution.get("answer_rois") != expected["answer_rois"]:
        raise GeometryResolutionError("ROI ที่บันทึกไว้ไม่ตรงกับขอบเขต block ปัจจุบัน")


def geometry_from_detection(
    detection: dict[str, Any] | None,
    template_def: TemplateDefinition,
    *,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    """Read the persisted result, or safely derive the legacy equivalent."""

    if not detection:
        raise GeometryResolutionError("ยังไม่มีผลเรขาคณิตของภาพนี้")
    persisted = detection.get("geometry_resolution")
    if isinstance(persisted, dict):
        return resolve_geometry(
            template_def,
            persisted=persisted,
            source_sha256=source_sha256,
        )
    registration = detection.get("registration") or {}
    offsets = registration.get("omr_block_offsets") or {}
    return resolve_geometry(
        template_def,
        registration=registration,
        block_offsets=offsets,
        source_sha256=source_sha256
        or (detection.get("document_normalization") or {}).get("source_sha256"),
    )
